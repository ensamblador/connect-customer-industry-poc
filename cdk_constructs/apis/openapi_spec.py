"""
cdk_constructs/apis/openapi_spec.py — load an authored OpenAPI spec and render it
for an AgentCore gateway's inline OpenAPI target.

Industry-agnostic loader. The authored ``openapi.yaml`` stays in each app under
``apis/openapi/openapi.yaml`` (industry data); this module just reads it, forces
the single server URL to the Fn::Sub TEMPLATE, and re-serializes to a compact
JSON string. Callers pass the path to their spec and the server description.

Flow (decided design — "render at synth with Fn.sub"):

  1. ``apis/openapi/openapi.yaml`` is the authored, rich spec (descriptions,
     request/response schemas, examples). Its ``servers[0].url`` is a TEMPLATE:
         https://${ApiId}.execute-api.${AWS::Region}.amazonaws.com/${Stage}
  2. At synth we read + parse the YAML and re-serialize it to a compact JSON
     string (AgentCore's inline_payload is a single string; JSON is a valid
     OpenAPI document and avoids YAML-in-string quoting pitfalls).
  3. The ${ApiId} / ${Stage} / ${AWS::Region} markers are left intact in that
     string and resolved at deploy time by CloudFormation Fn::Sub, which the
     gateway construct wraps the string in. So the inline spec the gateway
     receives carries the REAL deployed API URL.

This keeps the authored spec as the single source of truth and guarantees the
inline spec's server URL matches the actually-deployed API.
"""

from __future__ import annotations

import json

import yaml

# The Fn::Sub variables the server URL template uses. ${AWS::Region} is a
# CloudFormation pseudo-parameter resolved automatically; ApiId and Stage are
# supplied by the gateway construct from the deployed REST API.
SERVER_URL_TEMPLATE = (
    "https://${ApiId}.execute-api.${AWS::Region}.amazonaws.com/${Stage}"
)


def load_spec(spec_path: str) -> dict:
    """Parse the authored OpenAPI YAML at ``spec_path`` into a dict."""
    with open(spec_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def render_spec_json(spec_path: str, server_description: str) -> str:
    """
    Return the spec at ``spec_path`` as a compact JSON string with the server
    URL set to the Fn::Sub TEMPLATE (markers intact). The caller wraps this in
    Fn.sub so the markers resolve to the real deployed values at deploy time.

    ``server_description`` is the human label for the single server entry (an
    industry-specific string, e.g. "Deployed banking self-service API Gateway
    endpoint"). JSON is used (not YAML) because it's a valid OpenAPI document,
    stdlib-serializable, and embedding it as a single CloudFormation string is
    far less error-prone than multi-line YAML.
    """
    spec = load_spec(spec_path)

    # Force the single server URL to the template; the authored file already
    # has it, but we set it explicitly so the contract is not dependent on the
    # authored value.
    spec["servers"] = [
        {
            "url": SERVER_URL_TEMPLATE,
            "description": server_description,
        }
    ]

    # Compact separators keep the inline payload small.
    return json.dumps(spec, separators=(",", ":"))


def operation_summaries(spec_path: str) -> list[dict]:
    """
    Convenience: list (operationId, method, path) for every operation in the
    authored spec — handy for building tool filters/overrides if a target ever
    needs them alongside the inline schema.
    """
    spec = load_spec(spec_path)
    out: list[dict] = []
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            out.append(
                {
                    "path": path,
                    "method": method.upper(),
                    "operationId": op.get("operationId"),
                    "summary": op.get("summary"),
                }
            )
    return out
