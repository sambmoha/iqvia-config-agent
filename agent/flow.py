"""
agent/flow.py
-------------
Orchestrates the full configuration lifecycle:
  Requirement → LLM generation → Validation → Approval → Deployment

Each public function logs its action and returns a structured result dict
so the UI layer stays decoupled from business logic.
"""

import re
from datetime import datetime, timezone

from tools.llm import call_llm
from tools.validator import validate_config
from tools.deployer import deploy_config
from tools.logger import log_action, save_config


def _make_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


# ---------------------------------------------------------------------------
# Rule-based fallback (used when LLM API is unavailable or returns bad output)
# ---------------------------------------------------------------------------
def _fallback_config(
    requirement: str,
    ts: str,
    domain: str = "clinical",
    priority: str = "medium",
    approval_required: bool = True,
) -> dict:
    """
    Deterministic parser that extracts basic rules from natural-language text.
    Covers the most common clinical patterns (age, severity, mandatory fields).
    """
    rules = []
    idx = 1

    age_match = re.search(r"age\s*[><=!]+\s*(\d+)", requirement, re.IGNORECASE)
    if age_match:
        rules.append({
            "rule_id": f"R{idx:03d}", "field": "age", "operator": "gt",
            "value": age_match.group(1), "severity": "error",
            "message": f"Age must be > {age_match.group(1)}",
        })
        idx += 1

    if re.search(r"severity\s+(mandatory|required)", requirement, re.IGNORECASE):
        rules.append({
            "rule_id": f"R{idx:03d}", "field": "severity", "operator": "required",
            "value": "true", "severity": "error", "message": "Severity field is mandatory",
        })
        idx += 1

    if re.search(r"high\s+severity", requirement, re.IGNORECASE):
        rules.append({
            "rule_id": f"R{idx:03d}", "field": "severity", "operator": "eq",
            "value": "high", "severity": "warning",
            "message": "High severity cases require senior reviewer",
        })
        idx += 1

    bmi_match = re.search(r"bmi\s+(\d+)\s*[-–]\s*(\d+)", requirement, re.IGNORECASE)
    if bmi_match:
        rules.append({
            "rule_id": f"R{idx:03d}", "field": "bmi", "operator": "in",
            "value": f"{bmi_match.group(1)}-{bmi_match.group(2)}", "severity": "error",
            "message": f"BMI must be between {bmi_match.group(1)} and {bmi_match.group(2)}",
        })
        idx += 1

    if not rules:
        rules.append({
            "rule_id": "R001", "field": "record_id", "operator": "required",
            "value": "true", "severity": "error", "message": "Record ID is mandatory",
        })

    approver = "senior_reviewer" if re.search(r"senior", requirement, re.IGNORECASE) else "reviewer"
    det_priority = (
        "high" if re.search(r"high|critical|urgent|serious", requirement, re.IGNORECASE) else priority
    )

    return {
        "config_id": f"CFG_{ts}",
        "version": "1.0",
        "description": f"Auto-generated: {requirement[:80]}",
        "domain": domain,
        "validation_rules": rules,
        "workflow": {
            "steps": [
                {"step": 1, "role": "reviewer", "action": "review", "condition": ""},
                {"step": 2, "role": approver, "action": "approve", "condition": "all_rules_pass"},
            ],
            "approval_required": approval_required,
            "approver_role": approver,
        },
        "access_controls": {
            "read": ["analyst", "reviewer"],
            "write": ["config_admin"],
            "approve": [approver],
        },
        "parameters": {
            "priority": det_priority,
            "notification_enabled": True,
            "auto_deploy_to_dev": False,
        },
        "_source": "fallback_parser",
    }


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------
def generate_and_validate(
    requirement: str,
    domain: str = "clinical",
    priority: str = "medium",
    approval_required: bool = True,
    model_name: str | None = None,
) -> tuple[dict, dict, dict]:
    """
    Step 1+2: Call LLM → validate → log → persist.
    Returns (config, validation_report, api_metadata).
    """
    ts = _make_ts()

    config, api_meta = call_llm(
        requirement, ts,
        domain=domain,
        priority=priority,
        approval_required=approval_required,
        model_name=model_name,
    )

    # Degrade gracefully if LLM fails
    if "_llm_error" in config or not config.get("config_id"):
        config = _fallback_config(requirement, ts, domain, priority, approval_required)
        config["_llm_note"] = "LLM unavailable or returned invalid JSON — rule-based fallback used"
        api_meta["status"] = "fallback"

    config.setdefault("config_id", f"CFG_{ts}")
    validation = validate_config(config)

    log_action(
        action_type="CONFIG_GENERATED",
        actor="config_agent",
        config_id=config["config_id"],
        details={
            "requirement": requirement[:120],
            "domain": domain,
            "validation_status": validation["status"],
            "source": config.get("_source", "llm"),
        },
    )
    save_config(config)
    return config, validation, api_meta


def approve(config: dict, reviewer: str, notes: str) -> dict:
    """Step 3: Human approves the generated config."""
    config_id = config.get("config_id", "UNKNOWN")
    log_action("CONFIG_APPROVED", reviewer, config_id, {"notes": notes})
    return {"approved": True, "reviewer": reviewer, "notes": notes, "config_id": config_id}


def reject(config: dict, reviewer: str, notes: str) -> dict:
    """Step 3 (alt): Human rejects — config must be regenerated."""
    config_id = config.get("config_id", "UNKNOWN")
    log_action("CONFIG_REJECTED", reviewer, config_id, {"notes": notes})
    return {"approved": False, "reviewer": reviewer, "notes": notes, "config_id": config_id}


def deploy(config: dict, environment: str, reviewer_notes: str = "") -> dict:
    """Step 4: Simulate deployment through Dev → QA → Prod pipeline."""
    result = deploy_config(config, environment, reviewer_notes)
    log_action(
        action_type="CONFIG_DEPLOYED",
        actor="deploy_agent",
        config_id=config.get("config_id", "UNKNOWN"),
        details={"environment": environment, "success": result["success"]},
    )
    return result
