# IQVIA Configuration Agent

> **End-to-End AI-Powered Configuration Lifecycle for Clinical & Enterprise Platforms**

A production-grade prototype that converts plain-English business requirements into
validated, versioned, and audit-logged system configurations — demonstrating the full
pipeline from requirement ingestion to simulated multi-environment deployment.

Built for the IQVIA AI & Automation CoE case study.

---

## Live Demo

Deployed on Hugging Face Spaces:
`https://huggingface.co/spaces/<your-hf-username>/iqvia-config-agent`

---

## Pipeline Overview

```
Business Requirement
        │
        ▼
┌──────────────────┐
│  LLM Generation  │  ← Qwen/Qwen3-8B via HF Inference API
│  (+ Fallback)    │  ← Rule-based parser if LLM unavailable
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│   Validation     │  ← Schema · Business rules · Access controls
│   Engine         │  ← Scores 0-100, lists errors + warnings
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Human-in-the-   │  ← Reviewer approves or rejects
│  Loop Approval   │  ← Notes captured in audit log
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Deployment      │  ← Simulated Dev → QA → Prod pipeline
│  Simulator       │  ← Pre-deploy checks per environment
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Audit Logging   │  ← Every action logged with timestamp + actor
│  + Versioning    │  ← All configs persisted to configs.json
└──────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **UI** | Gradio 6.x | Interactive web interface (Blocks API) |
| **LLM** | Qwen/Qwen3-8B | Config generation from natural language |
| **LLM API** | HuggingFace InferenceClient | Serverless API calls (no local GPU needed) |
| **Fallback** | Rule-based regex parser | Graceful degradation when LLM unavailable |
| **Validation** | Custom Python engine | Schema + business rule + access control checks |
| **Serialisation** | JSON + YAML (PyYAML) | Config display and export |
| **Persistence** | JSON flat files | Config history + NDJSON audit logs |
| **Deployment** | Hugging Face Spaces | Free CPU hosting, auto-deploy from Git |
| **Language** | Python 3.10+ | — |

---

## Architecture

```
iqvia-config-agent/
│
├── app.py                  # Gradio UI — all event handlers and layout
│
├── agent/
│   └── flow.py             # Pipeline orchestrator
│                           #   generate_and_validate()
│                           #   approve() / reject()
│                           #   deploy()
│
├── tools/
│   ├── llm.py              # HF InferenceClient wrapper (Qwen3-8B)
│   ├── validator.py        # Schema + business rule validation engine
│   ├── deployer.py         # Dev→QA→Prod deployment simulator
│   └── logger.py           # NDJSON audit logger + config persistence
│
├── data/
│   ├── configs.json        # Persisted config history (JSON array)
│   └── logs.json           # Audit trail (newline-delimited JSON)
│
├── requirements.txt
└── README.md
```

### Data flow per request

1. **app.py** receives user input (requirement text + parameters)
2. Calls `agent/flow.py → generate_and_validate()`
3. `flow.py` calls `tools/llm.py → call_llm()` → HF Inference API
4. If LLM fails → `flow.py` falls back to `_fallback_config()` (regex parser)
5. `tools/validator.py → validate_config()` scores the result (0–100)
6. `tools/logger.py` appends to `data/logs.json` and saves to `data/configs.json`
7. UI displays JSON view, YAML view, Rules Table, API metadata
8. Human clicks Approve → `flow.py → approve()` → logged
9. Human clicks Deploy → `tools/deployer.py → deploy_config()` → pipeline simulation

### GenAI vs Deterministic split

| Task | Approach | Reason |
|---|---|---|
| Config generation | GenAI (Qwen3) | Natural language → structured JSON requires LLM |
| JSON extraction | Deterministic regex | Reliable, auditable, no hallucination risk |
| Validation | Deterministic rules | Compliance requires reproducible, explainable checks |
| Deployment checks | Deterministic simulation | Predictable, environment-specific rule lists |
| Approval | Human-in-the-loop | Regulated environment requires human sign-off |
| Audit logging | Deterministic | Complete, tamper-evident trail |

---

## How to Run Locally

### Prerequisites
- Python 3.10+
- A Hugging Face account and API token (free)

### 1. Clone the repo
```bash
git clone https://github.com/<your-username>/iqvia-config-agent.git
cd iqvia-config-agent
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set your HF token
```bash
export HF_TOKEN=hf_your_token_here
```

### 4. Run
```bash
python app.py
```
Open `http://localhost:7860` in your browser.

> **Note:** The app runs fully without a token using the rule-based fallback.
> Set `HF_TOKEN` to enable the Qwen3-8B LLM for richer config generation.

### Optional environment variables

| Variable | Default | Description |
|---|---|---|
| `HF_TOKEN` | — | Hugging Face API token |
| `MODEL_NAME` | `Qwen/Qwen3-8B` | Override LLM model (any HF text model) |
| `APP_ENV` | `development` | Environment label shown in UI |
| `LOG_LEVEL` | `INFO` | Log verbosity |

---

## Deploy to Hugging Face Spaces

### Step 1 — Create a Space
1. Go to [huggingface.co/spaces](https://huggingface.co/spaces)
2. Click **Create new Space**
3. Set: **SDK → Gradio** | **Hardware → CPU Basic (free)**
4. Name it `iqvia-config-agent`

### Step 2 — Push your code
```bash
git remote add space https://huggingface.co/spaces/<your-username>/iqvia-config-agent
git push space main
```

Or upload files manually via the Space's **Files** tab.

**Files to upload:**
```
app.py
requirements.txt
agent/__init__.py
agent/flow.py
tools/__init__.py
tools/llm.py
tools/validator.py
tools/deployer.py
tools/logger.py
data/configs.json       ← upload as empty array: []
data/logs.json          ← upload as empty file
```

### Step 3 — Add secret token
```
Space → Settings → Repository secrets
  Name:  HF_TOKEN
  Value: hf_your_token_here
```

Hugging Face restarts the Space and reads the token via `os.environ.get("HF_TOKEN")`.
Your token is **never visible** in logs or the UI (it is masked in the env vars table).

### Step 4 — Verify
The Space auto-installs `requirements.txt` and runs `app.py`. Expect cold-start ~60s.

---

## UI Features

| Feature | Description |
|---|---|
| Natural language input | Free-text requirement entry |
| 10 preset scenarios | Radio buttons covering clinical, safety, compliance, regulatory domains |
| Config parameters | Domain dropdown · Priority radio · Approval Yes/No · Approver role dropdown · Notification checkbox · Strict mode checkbox |
| JSON view | Full config as interactive JSON tree |
| YAML view | Config as YAML (copy-paste ready) |
| Rules table | Validation rules as a sortable dataframe |
| API info tab | LLM model, status, tokens used, timestamp |
| Validation report | Score 0-100 · Errors · Warnings · Checks passed |
| Human approval | Approve / Reject with notes — both logged |
| Deployment simulator | Dev → QA → Prod with per-environment pre-checks |
| Audit log viewer | Last 25 actions, newest first |
| Config history | All generated configs with timestamps |
| Environment table | Runtime env vars (token masked) |
| Pipeline progress bar | Live step-by-step status indicator |

---

## Governance & Compliance Notes

- **Audit trail:** Every action (generate, approve, reject, deploy) written to `data/logs.json` with timestamp, actor, and config ID.
- **Versioning:** All configs saved to `data/configs.json` with `_saved_at` timestamp.
- **Explainability:** Validation errors and warnings are human-readable; fallback mode labels its source (`_source: fallback_parser`).
- **Human gate:** Deployment is only possible after the Approve button is clicked — the UI enforces human-in-the-loop.
- **No hallucination pass-through:** JSON extraction is deterministic; invalid LLM output falls back to the rule-based parser automatically.

---

## Evaluation Metrics (demo values)

| Metric | Value |
|---|---|
| Validation score | 0–100 per config |
| Error detection rate | Rules checked: schema (4 categories) |
| Human override rate | Tracked via approve/reject log ratio |
| Fallback rate | `_source: fallback_parser` in config |
| Time saved | Manual config: ~45 min → Agent: ~30 sec |
| Deployment check coverage | Dev: 3 · QA: 6 · Prod: 9 checks |

---

## License

MIT — free to use and modify for educational and commercial purposes.
