"""
tools/llm.py
------------
LLM integration layer using HuggingFace InferenceClient.
Calls the HF Serverless Inference API — no local model download needed.

Model: Qwen/Qwen3-8B (default) — configurable via MODEL_NAME env var.
Note: Qwen3.6-35B-A3B is a vision-language model. For text-only config
      generation we use the text-instruct variant. Set MODEL_NAME env var
      to override (e.g. "Qwen/Qwen3-30B-A3B" for the MoE 3B-active variant).
"""

import os
import re
import json
from datetime import datetime, timezone

from huggingface_hub import InferenceClient

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen3-8B")

SYSTEM_MESSAGE = (
    "You are an expert clinical data configuration engineer at a pharmaceutical company. "
    "Your task is to convert business requirements into structured JSON configuration files. "
    "Output ONLY valid JSON — no markdown fences, no explanation, no thinking tags."
)

CONFIG_TEMPLATE = """\
{{
  "config_id": "CFG_{ts}",
  "version": "1.0",
  "description": "<one-line summary>",
  "domain": "{domain}",
  "validation_rules": [
    {{
      "rule_id": "R001",
      "field": "<field_name>",
      "operator": "<gt|lt|gte|lte|eq|neq|required|regex|in>",
      "value": "<threshold or pattern>",
      "severity": "<error|warning>",
      "message": "<human-readable error message>"
    }}
  ],
  "workflow": {{
    "steps": [
      {{"step": 1, "role": "<role>", "action": "<review|approve|notify|escalate>", "condition": ""}}
    ],
    "approval_required": {approval_required},
    "approver_role": "<role>"
  }},
  "access_controls": {{
    "read":    ["analyst", "reviewer"],
    "write":   ["config_admin"],
    "approve": ["senior_reviewer"]
  }},
  "parameters": {{
    "priority":           "{priority}",
    "notification_enabled": true,
    "auto_deploy_to_dev": false
  }}
}}"""

USER_PROMPT_TEMPLATE = """\
Convert the following business requirement into a JSON configuration.

Requirement:
{requirement}

Use this exact JSON structure (fill in real values, keep all keys):
{template}

/no_think
Output only the JSON object."""


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> dict:
    """
    Pull the first complete JSON object out of LLM free-text response.
    Handles cases where the model wraps output in markdown or adds commentary.
    """
    # Strip <think>...</think> blocks (Qwen3 thinking mode leak)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON found in LLM response.\nRaw output (first 400 chars):\n{text[:400]}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def call_llm(
    requirement: str,
    ts: str = "001",
    domain: str = "clinical",
    priority: str = "medium",
    approval_required: bool = True,
    model_name: str | None = None,
) -> tuple[dict, dict]:
    """
    Send requirement to HF Inference API and return (config_dict, api_metadata).
    model_name overrides the default MODEL_NAME env var when provided.
    Returns a fallback dict with _llm_error key if the API call fails.
    """
    selected_model = model_name or MODEL_NAME
    token = os.environ.get("HF_TOKEN", "")

    template = CONFIG_TEMPLATE.format(
        ts=ts,
        domain=domain,
        priority=priority,
        approval_required=str(approval_required).lower(),
    )
    user_prompt = USER_PROMPT_TEMPLATE.format(
        requirement=requirement,
        template=template,
    )

    api_meta = {
        "model": selected_model,
        "api": "HuggingFace Inference API",
        "called_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }

    if not token:
        api_meta["status"] = "no_token — fallback used"
        return {"_llm_error": "HF_TOKEN not set"}, api_meta

    try:
        client = InferenceClient(model=selected_model, token=token)

        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=800,
            temperature=0.05,
        )

        raw_text = response.choices[0].message.content
        usage = getattr(response, "usage", None)

        api_meta["status"] = "success"
        api_meta["prompt_tokens"]     = getattr(usage, "prompt_tokens",     None)
        api_meta["completion_tokens"] = getattr(usage, "completion_tokens", None)
        api_meta["total_tokens"]      = getattr(usage, "total_tokens",      None)

        config = _extract_json(raw_text)
        return config, api_meta

    except Exception as exc:
        api_meta["status"] = f"error: {exc}"
        return {"_llm_error": str(exc)}, api_meta
