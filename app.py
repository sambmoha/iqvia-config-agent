"""
app.py
------
IQVIA Configuration Agent — Gradio UI
Demonstrates the full configuration lifecycle:
  Requirement Input → LLM Config Generation → Validation →
  Human Approval → Deployment Simulation → Audit Logs

Designed for Hugging Face Spaces deployment (Gradio SDK).
Requires HF_TOKEN secret set in Space settings.
"""

import os
import json
import yaml
import gradio as gr

from agent.flow import generate_and_validate, approve, reject, deploy
from tools.logger import get_recent_logs, get_config_history

# ---------------------------------------------------------------------------
# Constants — preset scenarios (10 examples, mix of domains)
# ---------------------------------------------------------------------------
PRESET_SCENARIOS = {
    "1. Age validation (Clinical)":
        "Patient age must be greater than 18. Date of birth is mandatory. "
        "Underage records must be flagged as errors and routed to senior reviewer.",

    "2. BMI range check (Clinical)":
        "Patient weight must be between 40 and 200 kg. Height is required. "
        "BMI must fall between 18 and 40. Out-of-range values trigger a data query.",

    "3. Serious Adverse Event — SAE (Safety)":
        "All SAE fields are mandatory: event date, description, severity, and outcome. "
        "High severity adverse events trigger immediate escalation to medical monitor.",

    "4. Visit date validation (Clinical)":
        "Visit date cannot be a future date. Baseline visit must exist before follow-up visits. "
        "Missing visit dates are errors.",

    "5. Lab values threshold (Clinical)":
        "Haemoglobin must be between 8 and 18 g/dL. Creatinine must be below 2.0 mg/dL. "
        "Glucose must be between 70 and 200 mg/dL. Outliers require medical monitor sign-off.",

    "6. Site audit trail (Compliance)":
        "Site ID is mandatory. Principal Investigator signature is required. "
        "IRB approval document must be on file. Missing items block site activation.",

    "7. Protocol deviation workflow (Quality)":
        "Deviation type is required. Severity classification (minor/major/critical) is mandatory. "
        "Major and critical deviations trigger CAPA workflow with QA manager approval.",

    "8. Informed consent version (Regulatory)":
        "ICF version on file must match the currently approved version. "
        "Consent date must precede the first study procedure date. Mismatch is a critical error.",

    "9. Drug dispensing safety (Safety)":
        "Kit number is mandatory. Expiry date must be at least 30 days in the future. "
        "Temperature log is required for cold-chain drugs. Failures block dispensing.",

    "10. EDC lock criteria (Clinical)":
        "All open queries must be resolved before lock. 100% source data verification required. "
        "Investigator and data manager e-signatures must be captured. Incomplete records block lock.",
}

DOMAINS        = ["clinical", "safety", "commercial", "compliance", "regulatory", "quality"]
PRIORITIES     = ["high", "medium", "low"]
APPROVER_ROLES = ["senior_reviewer", "medical_monitor", "qa_manager", "site_pi", "data_manager"]
REVIEWER_ID    = "human_reviewer"

LLM_MODELS = [
    "Qwen/Qwen3-8B",
    "Qwen/Qwen3-4B",
    "Qwen/Qwen3-30B-A3B",
]

# ---------------------------------------------------------------------------
# Helpers — data conversion
# ---------------------------------------------------------------------------
def _to_yaml(config: dict) -> str:
    try:
        return yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)
    except Exception as exc:
        return f"# YAML conversion error: {exc}\n{json.dumps(config, indent=2)}"


def _to_json_str(obj) -> str:
    try:
        return json.dumps(obj, indent=2, default=str)
    except Exception as exc:
        return f"// JSON serialization error: {exc}"


def _rules_to_table(config: dict) -> list[list]:
    rules = config.get("validation_rules", [])
    if not rules:
        return [["—", "—", "—", "—", "—", "—"]]
    return [
        [
            r.get("rule_id", ""),
            r.get("field", ""),
            r.get("operator", ""),
            str(r.get("value", "")),
            r.get("severity", ""),
            r.get("message", ""),
        ]
        for r in rules
    ]


def _env_vars_table() -> list[list]:
    token = os.environ.get("HF_TOKEN", "")
    masked = ("●" * 8 + token[-4:]) if len(token) > 4 else "⚠ Not set"
    return [
        ["HF_TOKEN",    masked,                                          "Hugging Face API token"],
        ["MODEL_NAME",  os.environ.get("MODEL_NAME", "Qwen/Qwen3-8B"),  "LLM model for config generation"],
        ["APP_ENV",     os.environ.get("APP_ENV",    "development"),     "Deployment environment"],
        ["LOG_LEVEL",   os.environ.get("LOG_LEVEL",  "INFO"),            "Application log verbosity"],
    ]


# ---------------------------------------------------------------------------
# Pipeline status markdown
# ---------------------------------------------------------------------------
def _pipeline_md(gen=False, val=False, appr=None, dep=False) -> str:
    def _b(done): return "🟢" if done else "⬜"
    appr_icon = "🟢" if appr is True else ("🔴" if appr is False else "⬜")
    return (
        f"| Step | Status |\n|------|--------|\n"
        f"| 📋 Requirement Input    | {_b(gen)} |\n"
        f"| ⚙️ Config Generation    | {_b(gen)} |\n"
        f"| ✅ Validation           | {_b(val)} |\n"
        f"| 👤 Human Approval       | {appr_icon} |\n"
        f"| 🚀 Deployment           | {_b(dep)} |\n"
        f"| 📊 Audit Log            | {_b(gen)} |\n"
    )


PIPELINE_IDLE = _pipeline_md()


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------
def fill_preset(scenario_name: str) -> str:
    return PRESET_SCENARIOS.get(scenario_name, "")


def _token_usage_md(api_meta: dict) -> str:
    status = api_meta.get("status", "—")
    model  = api_meta.get("model", "—")
    pt     = api_meta.get("prompt_tokens",     "—")
    ct     = api_meta.get("completion_tokens", "—")
    tt     = api_meta.get("total_tokens",      "—")
    called = api_meta.get("called_at",         "—")
    return (
        f"| Field | Value |\n|---|---|\n"
        f"| **Model** | `{model}` |\n"
        f"| **Status** | {status} |\n"
        f"| **Prompt tokens** | {pt} |\n"
        f"| **Completion tokens** | {ct} |\n"
        f"| **Total tokens** | {tt} |\n"
        f"| **Called at** | {called} |\n"
    )


def on_generate(
    requirement: str,
    domain: str,
    priority: str,
    approval_required: str,
    approver_role: str,
    notification: bool,
    strict_mode: bool,
    model_choice: str,
):
    if not requirement.strip():
        return (
            "", "", [], "",
            "",
            "⚠️ Please enter a requirement.",
            "—",
            PIPELINE_IDLE,
            {},
            {},
        )

    approval_bool = approval_required == "Yes"

    config, validation, api_meta = generate_and_validate(
        requirement=requirement,
        domain=domain,
        priority=priority,
        approval_required=approval_bool,
        model_name=model_choice,
    )

    config.setdefault("parameters", {})
    config["parameters"]["notification_enabled"] = notification
    config["parameters"]["strict_mode"] = strict_mode
    config["parameters"]["approver_role_override"] = approver_role

    yaml_str    = _to_yaml(config)
    rules_rows  = _rules_to_table(config)
    token_usage = _token_usage_md(api_meta)

    valid = validation["status"] == "valid"
    icon  = "✅" if valid else "⚠️"
    msg   = (
        f"{icon} **{config.get('config_id')}** · Model: `{api_meta.get('model')}` · "
        f"Status: **{api_meta.get('status')}** · "
        f"Validation: **{validation['status'].upper()}** "
        f"(score {validation['score']}/100 · "
        f"{len(validation['errors'])} error(s) · "
        f"{len(validation['warnings'])} warning(s))"
    )

    return (
        _to_json_str(config),       # JSON tab (string)
        yaml_str,                   # YAML tab
        rules_rows,                 # Rules table tab
        _to_json_str(api_meta),     # API info tab (string)
        _to_json_str(validation),   # Validation panel (string)
        msg,                        # Status message
        token_usage,                # Token usage panel
        _pipeline_md(gen=True, val=True),  # Pipeline progress
        config,                     # config_state
        validation,                 # validation_state
    )


def on_approve(config_state: dict, notes: str):
    if not config_state:
        return "", "⚠️ No config loaded.", _pipeline_md()
    result = approve(config_state, REVIEWER_ID, notes)
    return _to_json_str(result), f"✅ Approved: **{result['config_id']}**", _pipeline_md(gen=True, val=True, appr=True)


def on_reject(config_state: dict, notes: str):
    if not config_state:
        return "", "⚠️ No config loaded.", _pipeline_md()
    result = reject(config_state, REVIEWER_ID, notes)
    return _to_json_str(result), f"🔴 Rejected. Reason: {notes or 'None provided'}", _pipeline_md(gen=True, val=True, appr=False)


def on_deploy(config_state: dict, validation_state: dict, environment: str, notes: str):
    if not config_state:
        return "", "⚠️ Generate and approve a config first."

    strict = config_state.get("parameters", {}).get("strict_mode", False)
    errors = validation_state.get("errors", [])
    if strict and errors:
        blocked = {
            "blocked": True,
            "reason": "Strict Mode is ON — deployment blocked due to validation errors",
            "errors": errors,
        }
        return _to_json_str(blocked), f"🚫 **Deployment blocked** — Strict Mode is enabled and {len(errors)} validation error(s) must be resolved first."

    result = deploy(config_state, environment, notes)
    icon = "✅" if result["success"] else "❌"
    return _to_json_str(result), f"{icon} Deployed **{result.get('config_id')}** → **{result.get('target_environment')}** | Ref: {result.get('audit_ref')}"


def on_refresh_logs():
    return _to_json_str(get_recent_logs(25))


def on_load_history():
    return _to_json_str(get_config_history())


# ---------------------------------------------------------------------------
# UI layout
# ---------------------------------------------------------------------------
CSS = """
.step-label { font-weight: 600; margin-bottom: 2px; }
footer { display: none !important; }
"""

RULE_HEADERS = ["Rule ID", "Field", "Operator", "Value", "Severity", "Message"]

with gr.Blocks(title="IQVIA Configuration Agent", theme=gr.themes.Soft(primary_hue="blue"), css=CSS) as demo:

    # ── Shared state ─────────────────────────────────────────────────────────
    config_state     = gr.State({})
    validation_state = gr.State({})

    # ── Header ───────────────────────────────────────────────────────────────
    gr.Markdown("# 🏥 IQVIA Configuration Agent")
    gr.Markdown(
        "**End-to-End AI-Powered Configuration Lifecycle** · "
        "Requirement → Generation → Validation → Approval → Deployment → Audit"
    )

    pipeline_md = gr.Markdown(PIPELINE_IDLE)

    gr.Markdown("---")

    # ── STEP 1: Requirement Input ─────────────────────────────────────────────
    gr.Markdown("### 📋 Step 1 — Business Requirement", elem_classes=["step-label"])

    with gr.Tabs():
        with gr.Tab("✏️ Natural Language"):
            requirement_input = gr.Textbox(
                label="Enter requirement in plain English",
                placeholder=(
                    "e.g. Age must be > 18, severity field is mandatory, "
                    "high severity cases must be routed to senior reviewer..."
                ),
                lines=4,
            )
        with gr.Tab("📂 Preset Examples"):
            gr.Markdown("Select a preset scenario — click **Load** to copy it into the input box.")
            preset_radio = gr.Radio(
                choices=list(PRESET_SCENARIOS.keys()),
                label="Preset Configuration Scenarios",
                value=None,
            )
            load_preset_btn = gr.Button("⬆️ Load into Requirement Box", size="sm")

    with gr.Accordion("⚙️ Configuration Parameters", open=True):
        with gr.Row():
            domain_dd = gr.Dropdown(
                choices=DOMAINS, value="clinical",
                label="Domain", info="Target platform domain"
            )
            priority_radio = gr.Radio(
                choices=PRIORITIES, value="medium",
                label="Priority"
            )
            approver_dd = gr.Dropdown(
                choices=APPROVER_ROLES, value="senior_reviewer",
                label="Approver Role"
            )
        with gr.Row():
            approval_yn     = gr.Radio(choices=["Yes", "No"], value="Yes", label="Approval Required?")
            notification_cb = gr.Checkbox(value=True,  label="Enable Notifications")
            strict_cb       = gr.Checkbox(value=False, label="Strict Mode (errors block deploy)")

    with gr.Row():
        model_dd = gr.Dropdown(
            choices=LLM_MODELS,
            value=LLM_MODELS[0],
            label="🤖 LLM Model",
            info="Select which Qwen model to use for config generation",
            scale=2,
        )

    generate_btn   = gr.Button("⚙️ Generate Configuration", variant="primary", size="lg")
    gen_status     = gr.Markdown("")
    token_usage_md = gr.Markdown("", label="Token Usage")

    gr.Markdown("---")

    # ── STEP 2+3: Config Output + Validation ────────────────────────────────
    with gr.Row():
        with gr.Column(scale=3):
            gr.Markdown("### ⚙️ Step 2 — Generated Configuration", elem_classes=["step-label"])
            with gr.Tabs():
                with gr.Tab("📄 JSON"):
                    config_json = gr.Code(label="Configuration (JSON)", language="json", lines=20)
                with gr.Tab("📝 YAML"):
                    config_yaml = gr.Code(label="Configuration (YAML)", language="yaml", lines=20)
                with gr.Tab("📊 Rules Table"):
                    rules_table = gr.Dataframe(
                        headers=RULE_HEADERS,
                        datatype=["str"] * 6,
                        label="Validation Rules",
                        interactive=False,
                        wrap=True,
                    )
                with gr.Tab("🔌 API Response Info"):
                    api_info_json = gr.Code(label="LLM API Metadata", language="json", lines=15)

        with gr.Column(scale=2):
            gr.Markdown("### ✅ Step 3 — Validation Report", elem_classes=["step-label"])
            validation_json = gr.Code(label="Validation Results", language="json", lines=15)

    gr.Markdown("---")

    # ── STEP 4: Human Approval ────────────────────────────────────────────────
    gr.Markdown("### 👤 Step 4 — Human-in-the-Loop Approval", elem_classes=["step-label"])
    reviewer_notes  = gr.Textbox(label="Reviewer Notes", placeholder="Add override reason or comments here...", lines=2)
    with gr.Row():
        approve_btn = gr.Button("✅ Approve", variant="primary")
        reject_btn  = gr.Button("❌ Reject",  variant="stop")
    approval_json   = gr.Code(label="Approval Record", language="json", lines=8)
    approval_status = gr.Markdown("")

    gr.Markdown("---")

    # ── STEP 5: Deployment ────────────────────────────────────────────────────
    gr.Markdown("### 🚀 Step 5 — Deployment Pipeline (Dev → QA → Prod)", elem_classes=["step-label"])
    env_radio       = gr.Radio(choices=["dev", "qa", "prod"], value="dev", label="Target Environment")
    deploy_btn      = gr.Button("🚀 Deploy", variant="primary")
    deployment_json = gr.Code(label="Deployment Status", language="json", lines=20)
    deploy_status   = gr.Markdown("")

    gr.Markdown("---")

    # ── STEP 6: Audit Logs + Environment ────────────────────────────────────
    with gr.Accordion("📊 Step 6 — Audit Logs & Environment", open=False):
        with gr.Tab("📋 Audit Logs"):
            logs_json   = gr.Code(label="Recent Actions (newest first)", language="json", lines=20)
            refresh_btn = gr.Button("🔄 Refresh Logs")
        with gr.Tab("📁 Config History"):
            history_json = gr.Code(label="All Saved Configs", language="json", lines=20)
            history_btn  = gr.Button("🔄 Load History")
        with gr.Tab("🔧 Environment Variables"):
            gr.Markdown("Active runtime environment variables (token is masked).")
            env_table = gr.Dataframe(
                value=_env_vars_table(),
                headers=["Variable", "Value", "Description"],
                datatype=["str", "str", "str"],
                interactive=False,
            )
            env_refresh_btn = gr.Button("🔄 Refresh")

    # ── Wire-up ───────────────────────────────────────────────────────────────
    load_preset_btn.click(
        fn=fill_preset,
        inputs=[preset_radio],
        outputs=[requirement_input],
    )

    generate_btn.click(
        fn=on_generate,
        inputs=[
            requirement_input,
            domain_dd, priority_radio,
            approval_yn, approver_dd,
            notification_cb, strict_cb,
            model_dd,
        ],
        outputs=[
            config_json, config_yaml, rules_table, api_info_json,
            validation_json,
            gen_status,
            token_usage_md,
            pipeline_md,
            config_state,
            validation_state,
        ],
    )

    approve_btn.click(
        fn=on_approve,
        inputs=[config_state, reviewer_notes],
        outputs=[approval_json, approval_status, pipeline_md],
    )

    reject_btn.click(
        fn=on_reject,
        inputs=[config_state, reviewer_notes],
        outputs=[approval_json, approval_status, pipeline_md],
    )

    deploy_btn.click(
        fn=on_deploy,
        inputs=[config_state, validation_state, env_radio, reviewer_notes],
        outputs=[deployment_json, deploy_status],
    )

    refresh_btn.click(fn=on_refresh_logs,  outputs=[logs_json])
    history_btn.click(fn=on_load_history,  outputs=[history_json])
    env_refresh_btn.click(fn=_env_vars_table, outputs=[env_table])

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    demo.launch()
