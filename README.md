---
title: IQVIA Configuration Agent
emoji: 🏥
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: "6.12.0"
app_file: app.py
pinned: false
---

# 🏥 IQVIA Configuration Agent

> **End-to-End AI-Powered Configuration Lifecycle for Clinical & Enterprise Platforms**

An intelligent agent that converts plain-English business requirements into validated, versioned, and audit-logged system configurations — demonstrating the complete pipeline from requirement ingestion to simulated multi-environment deployment.

Built for the IQVIA AI & Automation CoE case study.

---

## Live Demo

**Hugging Face Spaces:** `https://huggingface.co/spaces/Sambmoha/iqvia-config-agent`

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Gradio UI (app.py)                       │
│  ┌─────────────┐   ┌─────────────────────────────────────────┐  │
│  │ LEFT SIDEBAR│   │          RIGHT MAIN CONTENT             │  │
│  │             │   │  Step 1: Business Requirement Input     │  │
│  │  Pipeline   │   │  Step 2: Generated Configuration        │  │
│  │  Status     │   │  Step 3: Validation Report              │  │
│  │             │   │  Step 4: Human-in-the-Loop Approval     │  │
│  │  LLM Model  │   │  Step 5: Deployment Pipeline            │  │
│  │  Selector   │   │  Step 6: Audit Logs & Environment       │  │
│  │             │   │  Step 7: Performance Metrics            │  │
│  └─────────────┘   └─────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   agent/flow.py    │
                    │  Pipeline Orchestr │
                    └─────────┬──────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
  ┌───────▼──────┐  ┌────────▼───────┐  ┌────────▼────────┐
  │  tools/llm   │  │tools/validator │  │tools/deployer   │
  │  Qwen3-8B    │  │ Schema+Rules   │  │ Dev→QA→Prod     │
  │  via HF API  │  │ Validation     │  │ Simulation      │
  └──────────────┘  └────────────────┘  └─────────────────┘
          │
  ┌───────▼──────────────────────────────────────────┐
  │                tools/logger.py                    │
  │   NDJSON Audit Log  ·  JSON Config Persistence   │
  └──────────────────────────────────────────────────┘
```

### Data Flow Per Request

```
User Input (requirement text + parameters)
        │
        ▼
app.py → on_generate()
        │
        ▼
agent/flow.py → generate_and_validate()
        │
        ├──► tools/llm.py → call_llm()
        │         │  HF Inference API (Qwen3-8B)
        │         │  If token missing or LLM fails:
        │         └──► _fallback_config() [regex parser]
        │
        ├──► tools/validator.py → validate_config()
        │         Schema check · Rule check · Workflow check · ACL check
        │         Returns score 0–100 + errors + warnings
        │
        └──► tools/logger.py → log_action() + save_config()
                  Appends to data/logs.json (NDJSON)
                  Saves to data/configs.json (JSON array)
                  │
                  ▼
        UI updates: JSON · YAML · Rules Table · API Info · Validation · Pipeline
```

---

## File Structure

```
iqvia-config-agent/
│
├── app.py                  # Gradio UI — all event handlers + layout
│
├── agent/
│   └── flow.py             # Pipeline orchestrator
│                           #   generate_and_validate() — Step 1+2
│                           #   approve() / reject()    — Step 3
│                           #   deploy()                — Step 4
│
├── tools/
│   ├── llm.py              # HF InferenceClient wrapper
│   │                       #   call_llm() → Qwen3-8B via HF Serverless API
│   │                       #   _extract_json() → strips thinking tags, parses JSON
│   ├── validator.py        # Config validation engine
│   │                       #   _check_schema()          — required top-level fields
│   │                       #   _check_validation_rules() — rule field checks
│   │                       #   _check_workflow()         — approval logic
│   │                       #   _check_access_controls()  — ACL structure
│   ├── deployer.py         # Dev→QA→Prod deployment simulator
│   │                       #   deploy_config() — runs pre-deploy checks per env
│   └── logger.py           # Audit logger + config persistence
│                           #   log_action()        — NDJSON append
│                           #   save_config()       — JSON array persist
│                           #   get_recent_logs()   — last N entries (reversed)
│                           #   get_config_history()— all saved configs
│
├── data/
│   ├── configs.json        # All generated configs (JSON array)
│   └── logs.json           # Audit trail (newline-delimited JSON)
│
├── .env                    # Local secrets (NOT committed — in .gitignore)
├── requirements.txt
└── README.md
```

---

## Component Details

### `app.py` — UI & Event Handlers

| Function | Inputs | Outputs | Purpose |
|---|---|---|---|
| `on_generate()` | requirement, domain, priority, approval, approver, notification, strict_mode, model | 10 values (JSON, YAML, table, API meta, validation, status, tokens, pipeline, config_state, val_state) | Full generation pipeline |
| `on_approve()` | config_state, notes | approval_json, status, pipeline_md | Log human approval |
| `on_reject()` | config_state, notes | approval_json, status, pipeline_md | Log human rejection |
| `on_deploy()` | config_state, val_state, environment, notes | deployment_json, status, pipeline_md | Strict mode gate + deployment |
| `compute_metrics()` | — | Markdown table | Reads logs, computes live metrics |

**Strict Mode gate (in `on_deploy`):**
```python
if strict_mode=True AND validation.errors is non-empty:
    → block deployment, return blocked JSON
else:
    → proceed with deploy_config()
```

### `agent/flow.py` — Pipeline Orchestrator

Calls tools in sequence. Contains `_fallback_config()` — a deterministic regex parser that extracts rules from plain English when the LLM is unavailable. The app **never crashes** — it always returns a usable config.

### `tools/llm.py` — LLM Integration

- Uses `huggingface_hub.InferenceClient` for serverless Qwen3-8B calls
- System prompt instructs model to output **only valid JSON**
- `_extract_json()` strips `<think>...</think>` blocks, tries direct parse, then regex extraction
- Falls back gracefully on any exception

### `tools/validator.py` — Validation Engine

4 check categories, each contributes 25 points to the score:
1. **Schema** — required top-level keys present
2. **Rules** — each rule has `rule_id`, `field`, `operator`, `severity`, `message`; operators in allowed set
3. **Workflow** — steps defined, `approver_role` present when `approval_required=true`
4. **Access Controls** — `read`, `write`, `approve` lists non-empty

### `tools/deployer.py` — Deployment Simulator

Pre-deploy checks increase with environment strictness:
- **dev** — 3 checks (schema, fields, syntax)
- **qa** — 6 checks (+ business rules, cross-field, regression)
- **prod** — 9 checks (+ CAB sign-off, rollback plan, audit trail)

### `tools/logger.py` — Audit & Persistence

- `log_action()` — appends one NDJSON line per action (CONFIG_GENERATED, CONFIG_APPROVED, CONFIG_REJECTED, CONFIG_DEPLOYED)
- `save_config()` — persists config dict to JSON array
- Auto-creates `data/` directory if missing (safe on HF Spaces)

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **UI** | Gradio 6.x | Interactive web interface (Blocks API) |
| **LLM** | Qwen/Qwen3-8B | Config generation from natural language |
| **LLM API** | HuggingFace InferenceClient | Serverless API (no local GPU) |
| **Fallback** | Rule-based regex parser | Graceful degradation when LLM unavailable |
| **Validation** | Custom Python engine | Schema + business rule + ACL checks |
| **Serialisation** | JSON + YAML (PyYAML) | Config display and export |
| **Persistence** | JSON flat files | Config history + NDJSON audit logs |
| **Deployment** | Hugging Face Spaces | Free CPU hosting, auto-deploy from Git |
| **Language** | Python 3.10+ | — |

---

## How to Run Locally

### Prerequisites
- Python 3.10+
- Hugging Face account and API token (free tier works)

### 1. Clone
```bash
git clone https://github.com/sambmoha/iqvia-config-agent.git
cd iqvia-config-agent
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Create `.env` file with your token
```bash
cat > .env << EOF
HF_TOKEN=hf_your_token_here
MODEL_NAME=Qwen/Qwen3-8B
APP_ENV=development
LOG_LEVEL=INFO
EOF
```

### 4. Run
```bash
python app.py
```
Open `http://localhost:7860`

> **Note:** The app runs fully without a token using the rule-based fallback (tokens will show `None`). Set `HF_TOKEN` to enable the Qwen3-8B LLM for richer, multi-rule configs and real token counts.

---

## How to Use the App

### Step-by-step workflow

```
1. Enter requirement (or choose a preset)  →  Click ⚙️ Generate Configuration
2. Review outputs: JSON · YAML · Rules Table · API Info · Validation Report
3. Add reviewer notes  →  Click ✅ Approve  (or ❌ Reject)
4. Select environment (dev / qa / prod)  →  Click 🚀 Deploy
5. Check pipeline: all 6 steps should be 🟢
6. Open Step 6 accordion  →  Refresh Logs to see audit trail
7. Open Step 7 accordion  →  Refresh Metrics for live KPIs
```

---

## Sample Complex Business Requirement

Paste this into the **Natural Language** input box:

```
A clinical trial subject record must pass all of the following before database lock:

1. Patient age must be between 18 and 75 years. Date of birth is mandatory.
2. BMI must be between 16.0 and 45.0 kg/m². Both weight (40–200 kg) and height
   (120–220 cm) are required fields.
3. Haemoglobin must be between 8.0 and 18.0 g/dL. Creatinine must be below
   2.0 mg/dL. Glucose must be between 70 and 300 mg/dL.
4. All Serious Adverse Events (SAE) must have: event date, description, severity
   classification (mild/moderate/severe), and outcome. Severity of 'severe'
   triggers immediate escalation to medical monitor.
5. Informed consent date must precede the first study procedure date. ICF version
   must match the currently approved protocol version — mismatch is a critical error.
6. Visit dates cannot be future dates. Each follow-up visit must occur after the
   baseline visit. Missing visit dates are errors that block record lock.
7. At least one valid lab result must exist per visit. Outlier values (> 3 standard
   deviations from site mean) require medical monitor sign-off before approval.
8. Principal Investigator e-signature is mandatory. Data manager e-signature is
   mandatory. Both must be captured before the record can be submitted for lock.

Domain: Clinical. Priority: High. Approval required from: Medical Monitor.
```

**Recommended settings:**
- Domain → `clinical`
- Priority → `high`
- Approver Role → `medical_monitor`
- Approval Required → `Yes`
- Model → `Qwen/Qwen3-8B`

**Expected output (with HF_TOKEN set):**
- 6–8 validation rules covering age, BMI, lab values, SAE fields, consent dates, visit dates, signatures
- Validation score: 100/100
- Workflow: 2-step with medical_monitor approval
- Prompt tokens: ~500–650 · Completion tokens: ~350–500

---

## Strict Mode — Example

**What it does:** When enabled, the Deploy button is blocked if the generated config has any validation errors. This enforces zero-tolerance before production deployment.

### Scenario to test it:

**Step 1 — Enable Strict Mode**
- Check ☑️ **Strict Mode (errors block deploy)** in Configuration Parameters

**Step 2 — Generate a config**
- Enter any requirement and click Generate
- The fallback parser always produces a valid config (score 100, 0 errors)
- **Result:** Deployment proceeds normally — Strict Mode passes because there are 0 errors ✅

**Step 3 — Simulate Strict Mode blocking (run in terminal)**
```bash
cd iqvia-config-agent
python -c "
from app import on_deploy
import json

# Config with strict_mode=True
cfg = {
    'config_id': 'CFG_TEST_001',
    'parameters': {'strict_mode': True}
}

# Validation result with 2 errors (simulates LLM returning incomplete config)
val = {
    'errors': ['Age field missing', 'Severity field missing'],
    'warnings': []
}

result_json, status_msg, pipeline = on_deploy(cfg, val, 'prod', '')
print(status_msg)
print(json.loads(result_json))
"
```

**Expected output:**
```
🚫 Deployment blocked — Strict Mode is enabled and 2 validation error(s) must be resolved first.
{'blocked': True, 'reason': 'Strict Mode is ON — deployment blocked due to validation errors',
 'errors': ['Age field missing', 'Severity field missing']}
```

**When does Strict Mode block in real usage?**
- Strict Mode is ON **+** LLM generates a config missing required fields (e.g. `approver_role` absent, empty `validation_rules`) → deployment blocked
- Strict Mode is OFF → deploy proceeds regardless of validation errors (with warnings logged)

---

## Performance Metrics (Step 7)

| Metric | Definition |
|---|---|
| **Validation Accuracy** | % of generated configs that pass validation (0 errors) |
| **Error Detection Rate** | % of configs that had at least one validation error |
| **Human Override Rate** | % of reviewed configs that were rejected by the human reviewer |
| **Total Deployments** | Count broken down by Dev / QA / Prod |
| **Configs Generated** | Total generated with approved vs rejected split |

Click **🔄 Refresh Metrics** to recompute from the live audit log.

---

## Governance & Compliance Notes

- **Audit trail:** Every action (generate, approve, reject, deploy) written to `data/logs.json` with UTC timestamp, actor, config ID, and details.
- **Versioning:** All configs saved to `data/configs.json` with `_saved_at` timestamp.
- **Human gate:** Approval is logged before deployment — enforces human-in-the-loop.
- **Explainability:** Validation errors are human-readable; fallback labels its source (`_source: fallback_parser`).
- **Strict Mode:** Prevents deployment of invalid configs in regulated environments.
- **Token masking:** HF_TOKEN is never exposed in UI (masked with ●●●●●●●●xxxx).

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `HF_TOKEN` | — | Hugging Face API token (enables LLM mode) |
| `MODEL_NAME` | `Qwen/Qwen3-8B` | Override LLM model |
| `APP_ENV` | `development` | Environment label shown in UI |
| `LOG_LEVEL` | `INFO` | Log verbosity |

---

## License

MIT — free to use and modify for educational and commercial purposes.
