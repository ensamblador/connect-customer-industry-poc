INSTANCE_ID = "b626d1c5-a63e-4334-aac2-f3e8b4a2aefe"
ASSISTANT_ID = "f319a787-91f1-4afa-b34c-11059e5f38bd"

# --- Answer Recommendation suggested messages ----------------------------
# NOTE: not currently applied. The native AWS::Wisdom::AIAgent CloudFormation
# resource does not expose a suggestedMessages property (the Q in Connect API
# does), so these are not wired into the Answer Recommendation agent on the
# native L1 path. Kept here for reference / future re-introduction via a thin
# custom resource scoped to that single agent.
SUGGESTED_MESSAGES = ["Generar Notas", "Como me puedes ayudar?"]

# --- Target locales -------------------------------------
LOCALES = {"en_US": True, "es_US": True, "pt_BR": False}

# --- Optional per-agent locale override ----------------------------------
# The reference Answer Recommendation agent in the source account uses es_ES
# while Manual Search / Note Taking use es_US. Our build defaults every agent
# to the active Target_Locale (es_US); this optional map lets an operator pin
# a specific agent to a different locale if the reference content requires it.
# e.g. {"ANSWER_RECOMMENDATION": "es_ES"}
AGENT_LOCALE_OVERRIDES: dict[str, str] = {}

# --- Hold messages + TTS voices (per language) ---------------------------
# The English, Spanish, and Portuguese hold-message texts played by the
# Localized_Queue_Flow, each non-empty and at most 3000 characters
HOLD_MESSAGE_EN = (
    "Thank you for calling. Your call is very important to us and will be "
    "answered in the order it was received"
)
HOLD_MESSAGE_ES = (
    "Gracias por llamar. Su llamada es muy importante para nosotros y será "
    "atendida en el orden en que fue recibida"
)
HOLD_MESSAGE_PT = (
    "Obrigado por ligar. Sua chamada é muito importante para nós e será "
    "atendida na ordem em que foi recebida"
)

# Per-language Amazon Polly voice ids and engine used by the
# UpdateContactTextToSpeechVoice blocks in each language path

TTS_VOICE_EN = "Joanna"
TTS_VOICE_ES = "Lupe"
TTS_VOICE_PT = "Camila"
TTS_ENGINE = "neural"

# --- Queue hold music ----------------------------------------------------
# Instance system prompt played as the queue hold music inside the localized
# customer-queue flow's Loop prompts block (alongside the localized TTS hold
# message), exactly like the Default Customer Queue.
#
# Referenced by NAME (not id): prompt ids differ per instance, so the stack
# resolves the id at deploy time via a custom resource that paginates
# connect:ListPrompts and matches this name. Referencing the prompt (not a bare
# S3 filename) is what actually makes the music play.
QUEUE_MUSIC_PROMPT_NAME = "Music_Jazz_MyTimetoFly_Inst.wav"

# --- SSM Parameter Store names for created resource ARNs -----------------
# The stack publishes created resource ARNs to SSM Parameter Store so other
# flows/stacks can reference them by a stable name (e.g. a "Transfer to flow"
# block) without hard-coding the ARN.
#
# The localized customer-queue flow ARN is published under this name.
QUEUE_FLOW_PARAM_NAME = "/flows/localized_queue_transfer"

# The init-flow-es contact-flow MODULE ARN is published under this name. The
# module is ported from telco-cx; its "Set customer queue flow" block points at
# the localized customer-queue flow above.
INIT_FLOW_PARAM_NAME = "/flows/init/es"

# Contact-flow MODULE name for the ported init-flow-es. 
INIT_FLOW_MODULE_NAME = "init-flow-es"

# Each localized AI agent ARN is published under this prefix, one parameter per
# agent, named "<prefix>/<agent_type_lowercase>_<locale>" — for example
# "/agents/answer_recommendation_es_US", "/agents/manual_search_es_US",
# "/agents/note_taking_es_US".
AGENT_PARAM_PREFIX = "/agents"

