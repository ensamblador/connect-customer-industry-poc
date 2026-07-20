"""cdk_constructs.apis — shared OpenAPI-spec loader for AgentCore inline targets.

The authored ``openapi.yaml`` stays per-industry (``apis/openapi/openapi.yaml``);
``openapi_spec.render_spec_json(spec_path, server_description)`` reads it and
renders the compact JSON inline payload the gateway target embeds.
"""

from cdk_constructs.apis import openapi_spec

__all__ = ["openapi_spec"]
