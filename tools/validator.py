from typing import Any

REQUIRED_TOP_LEVEL = ["config_id", "version", "description", "validation_rules", "workflow", "access_controls"]
REQUIRED_RULE_FIELDS = ["rule_id", "field", "operator", "severity", "message"]
VALID_OPERATORS = {"gt", "lt", "eq", "neq", "required", "regex", "gte", "lte", "in"}
VALID_SEVERITIES = {"error", "warning", "info"}
VALID_WORKFLOW_ACTIONS = {"review", "approve", "notify", "escalate"}


def _check_schema(config: dict, errors: list, warnings: list):
    for field in REQUIRED_TOP_LEVEL:
        if field not in config:
            errors.append(f"Missing required top-level field: '{field}'")

    if "_llm_error" in config:
        errors.append(f"LLM generation failed: {config['_llm_error']}")


def _check_validation_rules(config: dict, errors: list, warnings: list):
    rules = config.get("validation_rules", [])
    if not isinstance(rules, list):
        errors.append("'validation_rules' must be a list")
        return
    if len(rules) == 0:
        warnings.append("No validation rules defined — config may be incomplete")
        return

    rule_ids = set()
    for i, rule in enumerate(rules):
        prefix = f"Rule[{i}]"
        for rf in REQUIRED_RULE_FIELDS:
            if rf not in rule:
                errors.append(f"{prefix}: missing '{rf}'")
        op = rule.get("operator", "")
        if op and op not in VALID_OPERATORS:
            warnings.append(f"{prefix}: unknown operator '{op}' (expected one of {sorted(VALID_OPERATORS)})")
        sev = rule.get("severity", "")
        if sev and sev not in VALID_SEVERITIES:
            errors.append(f"{prefix}: invalid severity '{sev}' — must be error|warning|info")
        rid = rule.get("rule_id", "")
        if rid in rule_ids:
            errors.append(f"{prefix}: duplicate rule_id '{rid}'")
        rule_ids.add(rid)


def _check_workflow(config: dict, errors: list, warnings: list):
    wf = config.get("workflow", {})
    if not isinstance(wf, dict):
        errors.append("'workflow' must be an object")
        return
    steps = wf.get("steps", [])
    if not steps:
        warnings.append("Workflow has no steps defined")
    for i, step in enumerate(steps):
        action = step.get("action", "")
        if action and action not in VALID_WORKFLOW_ACTIONS:
            warnings.append(f"Workflow step[{i}]: unknown action '{action}'")
    if wf.get("approval_required") and not wf.get("approver_role"):
        errors.append("Workflow: approval_required is true but 'approver_role' is missing")


def _check_access_controls(config: dict, errors: list, warnings: list):
    ac = config.get("access_controls", {})
    if not isinstance(ac, dict):
        errors.append("'access_controls' must be an object")
        return
    for perm in ["read", "write", "approve"]:
        if perm not in ac:
            warnings.append(f"Access control: '{perm}' permission not defined")
        elif not isinstance(ac[perm], list) or len(ac[perm]) == 0:
            warnings.append(f"Access control: '{perm}' has no roles assigned")


def validate_config(config: Any) -> dict:
    errors: list = []
    warnings: list = []

    if not isinstance(config, dict):
        return {
            "status": "invalid",
            "errors": ["Config is not a valid JSON object"],
            "warnings": [],
            "score": 0,
            "checks_passed": 0,
            "checks_total": 4,
        }

    _check_schema(config, errors, warnings)
    _check_validation_rules(config, errors, warnings)
    _check_workflow(config, errors, warnings)
    _check_access_controls(config, errors, warnings)

    checks_total = 4
    checks_passed = checks_total - sum([
        1 if any("Missing required" in e or "LLM generation" in e for e in errors) else 0,
        1 if any("validation_rules" in e for e in errors) else 0,
        1 if any("Workflow" in e for e in errors) else 0,
        1 if any("Access control" in e for e in errors) else 0,
    ])
    score = round((checks_passed / checks_total) * 100)

    return {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "warnings": warnings,
        "score": score,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
    }
