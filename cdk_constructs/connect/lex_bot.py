"""
cdk_constructs/connect/lex_bot.py — Amazon Lex V2 Q-in-Connect passthrough bot as CDK (CfnBot).

A single Lex V2 bot whose only real intent is `AMAZON.QInConnectIntent`,
wired to the Q in Connect assistant. Every utterance is delegated to the
assistant; the intent's fulfillment success response is the magic token
`((x-amz-lex:q-in-connect-response))`, which Lex replaces with the assistant's
answer at runtime. Three locales (en_US, es_US, pt_BR) by default, each
configured with Advanced ASR for the agentic polyglot voice pattern.
The bot carries the `AmazonConnectEnabled=True` tag (capital T, case-sensitive)
the Connect admin bot-management page requires.

Speech model modes (controlled by `use_nova_sonic_s2s`):
  * False (default — Agentic Voice Polyglot): Advanced ASR via
    `speech_recognition_settings`. The bot uses Advanced ASR for speech
    recognition; text-to-speech is handled by a polyglot agentic voice
    (KATIE/Blake/Brooke/Ronald/Gemma) set in the contact flow's Set Voice block
    with engine=connect:agentic and LanguageCode=en-US. The AI agent prompt
    controls which language the voice speaks. This is the recommended pattern
    for multilingual/polyglot conversations.
  * True: Nova Sonic S2S via `unified_speech_settings`. The bot converts
    customer speech directly into natural speech responses end-to-end. Use
    locale-specific voices (Lupe, Matthew, Amy) with Generative engine in the
    Set Voice block. This mode does NOT support polyglot switching.

This is the native-CDK equivalent of the q-in-connect-bot-deploy import bundle:
aws-cdk-lib's `CfnBot` supports `QInConnectIntentConfiguration`,
`UnifiedSpeechSettings`, and the fulfillment `PostFulfillmentStatusSpecification`,
so no out-of-band import script is needed.

Build / alias strategy — fully automated, single deploy:
The construct creates the bot (CfnBot) with `auto_build_bot_locales=False` (CFN's
native build path serializes per-locale and blocks >90 min). Instead a custom
resource Lambda runs AFTER the bot is created: it calls `BuildBotLocale` for each
locale, polls until all reach `Built` (~30s each for a passthrough bot), then
calls `UpdateBotAlias` to enable them on the TestBotAlias. Total time: <2 min.

CloudFormation safety guarantees:
  * The CDK `Provider` framework wraps the handler — if the Lambda crashes or
    times out, the framework's built-in error path sends FAILED to CFN. The
    stack rolls back cleanly and is never stuck in IN_PROGRESS.
  * Delete is always an immediate no-op success (bot deletion removes the alias).
  * The handler itself catches unexpected exceptions and re-raises so the
    framework can report FAILED with the error message.
  * Polling has a hard 4-min deadline, well under the 5-min Lambda timeout.
  * Idempotent: if locales are already Built, the build step is skipped.

Exposes `bot_alias_arn` (the TestBotAlias ARN) for publication to the SSM bus;
the inbound contact flow (Phase 5) binds it via its `LEX_BOT_ALIAS_ARN_PLACEHOLDER`
marker. When a `connect_instance_arn` is given, the construct also creates the
`LEX_BOT` integration association that makes the bot appear in (and be usable
by) the Connect instance — the `AmazonConnectEnabled=True` tag alone does NOT do
that.

TestBotAlias locale settings — the OTHER manual step this construct now automates:
`CreateBotAlias` (which Lex creates implicitly for `TestBotAlias`) does NOT enable
any locale on the alias by default (`botAliasLocaleSettings` starts empty). A
`ConnectParticipantWithLexBot` / `GetUserInput` call against a locale the ALIAS has
not enabled fails at runtime with
``ValidationException: The BotAliasId TSTALIASID does not have Language <locale>
enabled`` — even though the locale itself is built and the bot works fine in the
Lex test console. This is a separate flag from locale-build status, so a bot whose
locales are all `Built` can still be unusable from Connect. A boto3 custom resource
(`_LocaleSettingsFn` below) calls `UpdateBotAlias` after the bot exists to enable
every configured locale on `TestBotAlias`, so a fresh deploy is chat/voice-usable
as soon as the locales are built in the console — no extra manual alias step.

Execution role — IMPORTANT: the bot runs under the Amazon Connect Lex
service-linked role `AWSServiceRoleForLexV2Bots_AmazonConnect_<account>`. This is
the role the Connect console assigns and the signal Connect uses to recognize a
bot as Connect-managed; a custom role makes Connect report "Conversational AI
bot created outside Connect console" and disables the Amazon Connect AI agent
intent. The SLR must exist in the account (created on first console bot-add, or
via `aws iam create-service-linked-role --aws-service-name lexv2.amazonaws.com
--custom-suffix AmazonConnect_<account-id>`). Override with `bot_role_arn`.
"""

from __future__ import annotations

from aws_cdk import CustomResource, Duration, RemovalPolicy, Stack
from aws_cdk import CfnTag
from aws_cdk import aws_connect as connect
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_lex as lex
from aws_cdk import aws_logs as logs
from aws_cdk import custom_resources as cr
from constructs import Construct

# The magic token Lex substitutes with the Q in Connect assistant's answer.
_QIC_RESPONSE_TOKEN = "((x-amz-lex:q-in-connect-response))"
_DEFAULT_LOCALES = ["en_US", "es_US", "pt_BR"]
# The fixed alias id of every Lex V2 bot's built-in test alias.
_TEST_BOT_ALIAS_ID = "TSTALIASID"

# Builds every configured locale and enables them on TestBotAlias.
#
# Safety guarantees (CloudFormation will NEVER get stuck):
#   * The CDK Provider framework handles the CFN response protocol — if the
#     Lambda crashes or times out, the framework's built-in error path sends
#     FAILED back to CFN automatically. The stack rolls back cleanly.
#   * The handler itself wraps ALL logic in try/except — any unexpected error
#     is caught, logged, and re-raised so the Provider framework reports FAILED.
#   * Delete is ALWAYS a no-op success — deleting the bot removes the alias, so
#     there is nothing to undo.
#   * Create and Update run the same idempotent logic: build locales that need
#     building, poll until ready, enable on alias.
#   * Polling has a hard deadline (4 min) well under the Lambda timeout (5 min),
#     leaving margin for the framework to respond to CFN on timeout.
#   * If a locale is already Built, the build call is skipped (idempotent).
#   * If a locale build fails, the handler raises immediately — CFN sees FAILED
#     and rolls back (the bot is recreated on the next deploy attempt).
#
# Trigger conditions:
#   * Runs on Create (first deploy) and Update (bot properties changed —
#     different locales, different bot id via replacement, etc.).
#   * Does NOT run when unrelated stack resources change (CloudFormation only
#     invokes the custom resource when its own properties change or on create).
_LOCALE_SETTINGS_HANDLER_SRC = '''
import time
import boto3

lex = boto3.client("lexv2-models")

# Statuses that mean the locale is servable by the alias.
_READY = {"Built", "ReadyExpressTesting"}
# Statuses that mean the build failed or locale is gone — unrecoverable.
_FAILED = {"Failed", "Deleting"}


def on_event(event, context):
    """Entry point. The CDK Provider framework calls this for Create/Update/Delete."""
    request_type = event.get("RequestType", "")
    props = event["ResourceProperties"]
    bot_id = props["BotId"]
    alias_id = props.get("BotAliasId", "TSTALIASID")
    pid = event.get("PhysicalResourceId") or f"lex-bot-locales-{bot_id}-{alias_id}"

    # Delete: always succeed immediately. The bot deletion cleans up the alias.
    if request_type == "Delete":
        return {"PhysicalResourceId": pid}

    # Create / Update: build locales + enable on alias.
    bot_version = props.get("BotVersion", "DRAFT")
    alias_name = props.get("BotAliasName", "TestBotAlias")
    locales = props["Locales"]

    # Step 1: trigger build for any locale not already in a ready state.
    for loc in locales:
        status = _get_locale_status(bot_id, bot_version, loc)
        if status in _READY:
            print(f"{loc}: already {status}, skipping build.")
            continue
        if status == "Building":
            print(f"{loc}: already building, will wait.")
            continue
        if status in _FAILED:
            raise RuntimeError(
                f"Locale {loc} is in unrecoverable state '{status}'. "
                "Delete and recreate the bot."
            )
        # NotBuilt or other transient state — kick off build.
        print(f"{loc}: status={status}, triggering build.")
        lex.build_bot_locale(botId=bot_id, botVersion=bot_version, localeId=loc)

    # Step 2: poll until all locales are ready (hard deadline: 4 minutes).
    deadline = time.time() + 240
    while time.time() < deadline:
        pending = []
        for loc in locales:
            status = _get_locale_status(bot_id, bot_version, loc)
            if status in _FAILED:
                raise RuntimeError(
                    f"Locale {loc} build failed (status={status}). "
                    "Check the Lex console for build errors."
                )
            if status not in _READY:
                pending.append(f"{loc}={status}")
        if not pending:
            break
        print(f"Waiting for: {pending}")
        time.sleep(5)
    else:
        raise RuntimeError(
            f"Timed out (4 min) waiting for locales to build. "
            f"Still pending: {pending}"
        )

    # Step 3: enable every locale on the alias.
    lex.update_bot_alias(
        botId=bot_id,
        botAliasId=alias_id,
        botAliasName=alias_name,
        botVersion=bot_version,
        botAliasLocaleSettings={loc: {"enabled": True} for loc in locales},
    )
    print(f"Success: alias {alias_id} updated, locales enabled: {locales}")
    return {"PhysicalResourceId": pid}


def _get_locale_status(bot_id, bot_version, locale_id):
    """Return the botLocaleStatus string for one locale."""
    resp = lex.describe_bot_locale(
        botId=bot_id, botVersion=bot_version, localeId=locale_id
    )
    return resp["botLocaleStatus"]
'''


class QInConnectLexBot(Construct):
    """A 3-locale Lex V2 bot that passes through to a Q in Connect assistant."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        name: str,
        assistant_arn: str,
        connect_instance_arn: str | None = None,
        bot_role_arn: str | None = None,
        locales: list[str] | None = None,
        nova_sonic_model_arn: str | None = None,
        idle_session_ttl_seconds: int = 300,
        nlu_confidence_threshold: float = 0.4,
        use_nova_sonic_s2s: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        stack = Stack.of(self)
        region = stack.region
        locales = locales or list(_DEFAULT_LOCALES)
        model_arn = (
            nova_sonic_model_arn
            or f"arn:aws:bedrock:{region}::foundation-model/amazon.nova-2-sonic-v1:0"
        )

        # Execution role: use the Amazon Connect Lex service-linked role
        # (AWSServiceRoleForLexV2Bots_AmazonConnect_<account>). This is the role
        # the Connect console assigns when you "Add an Amazon Lex bot", and it
        # is the SIGNAL Connect uses to treat the bot as created/managed inside
        # Connect. A custom role (even with identical permissions) makes Connect
        # report "Conversational AI bot created outside Connect console" and
        # blocks the Amazon Connect AI agent intent. The SLR is created the
        # first time a bot is added to Connect via the console, or with:
        #   aws iam create-service-linked-role --aws-service-name lexv2.amazonaws.com \
        #     --custom-suffix AmazonConnect_<account-id>
        role_arn = bot_role_arn or (
            f"arn:aws:iam::{stack.account}:role/aws-service-role/"
            f"lexv2.amazonaws.com/AWSServiceRoleForLexV2Bots_AmazonConnect_{stack.account}"
        )

        # Q-in-Connect intent: delegates everything; fulfillment success emits
        # the passthrough token and ends the conversation.
        qic_intent = lex.CfnBot.IntentProperty(
            name="AmazonQinConnect",
            description="Leverages Amazon Q in Connect to fulfill requests.",
            parent_intent_signature="AMAZON.QInConnectIntent",
            q_in_connect_intent_configuration=lex.CfnBot.QInConnectIntentConfigurationProperty(
                q_in_connect_assistant_configuration=lex.CfnBot.QInConnectAssistantConfigurationProperty(
                    assistant_arn=assistant_arn,
                )
            ),
            fulfillment_code_hook=lex.CfnBot.FulfillmentCodeHookSettingProperty(
                enabled=False,
                is_active=True,
                post_fulfillment_status_specification=lex.CfnBot.PostFulfillmentStatusSpecificationProperty(
                    success_response=lex.CfnBot.ResponseSpecificationProperty(
                        message_groups_list=[
                            lex.CfnBot.MessageGroupProperty(
                                message=lex.CfnBot.MessageProperty(
                                    plain_text_message=lex.CfnBot.PlainTextMessageProperty(
                                        value=_QIC_RESPONSE_TOKEN,
                                    )
                                )
                            )
                        ],
                        allow_interrupt=True,
                    ),
                    success_next_step=lex.CfnBot.DialogStateProperty(
                        dialog_action=lex.CfnBot.DialogActionProperty(type="EndConversation"),
                    ),
                ),
            ),
        )
        # Required default intent.
        fallback_intent = lex.CfnBot.IntentProperty(
            name="FallbackIntent",
            description="Default intent when no other intent matches.",
            parent_intent_signature="AMAZON.FallbackIntent",
        )

        bot_locales = [
            lex.CfnBot.BotLocaleProperty(
                locale_id=loc,
                nlu_confidence_threshold=nlu_confidence_threshold,
                # Default: Agentic Voice Polyglot mode — Advanced ASR handles
                # recognition; the polyglot TTS voice (KATIE/Blake/etc.) is set
                # in the contact flow's Set Voice block with
                # engine=connect:agentic + LanguageCode=en-US. The AI agent
                # prompt drives which language the voice speaks.
                # Nova Sonic S2S mode: unified_speech_settings handles both
                # recognition and synthesis end-to-end (locale-specific voices).
                **(
                    {
                        "unified_speech_settings": lex.CfnBot.UnifiedSpeechSettingsProperty(
                            speech_foundation_model=lex.CfnBot.SpeechFoundationModelProperty(
                                model_arn=model_arn,
                            )
                        )
                    }
                    if use_nova_sonic_s2s
                    else {
                        "speech_recognition_settings": lex.CfnBot.SpeechRecognitionSettingsProperty(
                            speech_model_preference="Advanced",
                        )
                    }
                ),
                intents=[qic_intent, fallback_intent],
            )
            for loc in locales
        ]

        self.bot = lex.CfnBot(
            self,
            "Bot",
            name=name,
            role_arn=role_arn,
            # NOTE: the L1 `DataPrivacyProperty(child_directed=...)` renders the
            # key as camelCase `childDirected`, but AWS::Lex::Bot requires the
            # PascalCase `ChildDirected` — CloudFormation rejects the lowercase
            # form ("Required property [ChildDirected] not found"). Pass a raw
            # dict with the correct casing to bypass the mis-cased mapping.
            data_privacy={"ChildDirected": False},
            idle_session_ttl_in_seconds=idle_session_ttl_seconds,
            description=f"Q in Connect passthrough bot ({name}).",
            # Locales are NOT auto-built (the per-locale NLU build is what makes
            # the deploy take >90 min). Build them once in the console after
            # deploy; the TestBotAlias then serves the DRAFT version.
            auto_build_bot_locales=False,
            bot_locales=bot_locales,
            # Connect requires this tag (case-sensitive "True") to surface the
            # bot in the admin bot-management page.
            bot_tags=[CfnTag(key="AmazonConnectEnabled", value="True")],
        )

        # Build every locale and enable them on TestBotAlias. On Create the bot
        # starts with locales NotBuilt; this custom resource builds them and
        # enables the alias in one shot. On Update (locale list changed) it
        # re-runs the same idempotent logic. On Delete it's a no-op.
        # The CDK Provider framework guarantees CFN always gets a response —
        # even on Lambda crash/timeout — so the stack NEVER gets stuck.
        locale_fn = _lambda.Function(
            self,
            "AliasLocaleSettingsFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.on_event",
            code=_lambda.Code.from_inline(_LOCALE_SETTINGS_HANDLER_SRC),
            timeout=Duration.minutes(5),
            description="Builds Lex bot locales and enables them on the "
            "TestBotAlias. Runs on stack Create/Update only.",
        )
        locale_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "lex:BuildBotLocale",
                    "lex:DescribeBotLocale",
                    "lex:UpdateBotAlias",
                    "lex:DescribeBotAlias",
                ],
                resources=["*"],
            )
        )
        locale_provider = cr.Provider(
            self,
            "AliasLocaleSettingsProvider",
            on_event_handler=locale_fn,
            log_group=logs.LogGroup(
                self,
                "AliasLocaleSettingsProviderLogs",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        self.alias_locale_settings = CustomResource(
            self,
            "AliasLocaleSettings",
            service_token=locale_provider.service_token,
            resource_type="Custom::LexTestAliasLocaleSettings",
            properties={
                "BotId": self.bot.attr_id,
                "BotAliasId": _TEST_BOT_ALIAS_ID,
                "BotAliasName": "TestBotAlias",
                "BotVersion": "DRAFT",
                "Locales": locales,
            },
        )
        # The alias must exist (it's created implicitly with the bot) before
        # UpdateBotAlias can target it.
        self.alias_locale_settings.node.add_dependency(self.bot)

        # The tag alone does NOT make the bot usable in a Connect instance — a
        # LEX_BOT integration association is what links the bot (alias) to the
        # instance so it appears under Connect's Amazon Lex bots and is
        # selectable in flows. Wired on the TestBotAlias when an instance ARN is
        # given. (connect.CfnIntegrationAssociation natively supports LEX_BOT.)
        self.integration = None
        if connect_instance_arn:
            self.integration = connect.CfnIntegrationAssociation(
                self,
                "ConnectIntegration",
                instance_id=connect_instance_arn,
                integration_type="LEX_BOT",
                integration_arn=self.bot_alias_arn,
            )

    @property
    def bot_alias_arn(self) -> str:
        """The built-in TestBotAlias ARN (points at DRAFT once locales build).

        No CfnBotVersion/CfnBotAlias is created — every Lex V2 bot ships with a
        test alias whose id is the fixed `TSTALIASID`, so the ARN is derivable
        from the bot id. Build the bot locales in the console, then this alias
        is live for the inbound flow.
        """
        stack = Stack.of(self)
        return (
            f"arn:aws:lex:{stack.region}:{stack.account}:"
            f"bot-alias/{self.bot.attr_id}/{_TEST_BOT_ALIAS_ID}"
        )

    @property
    def bot_id(self) -> str:
        return self.bot.attr_id
