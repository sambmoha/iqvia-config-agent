import json
import os
from datetime import datetime, timezone

LOGS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "logs.json")
CONFIGS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "configs.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_action(action_type: str, actor: str, config_id: str, details: dict) -> None:
    entry = {
        "timestamp": _now(),
        "action": action_type,
        "actor": actor,
        "config_id": config_id,
        "details": details,
    }
    logs_path = os.path.abspath(LOGS_PATH)
    with open(logs_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def save_config(config: dict) -> None:
    configs_path = os.path.abspath(CONFIGS_PATH)
    try:
        with open(configs_path, "r") as f:
            configs = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        configs = []

    config["_saved_at"] = _now()
    configs.append(config)

    with open(configs_path, "w") as f:
        json.dump(configs, f, indent=2)


def get_recent_logs(n: int = 20) -> list[dict]:
    logs_path = os.path.abspath(LOGS_PATH)
    try:
        with open(logs_path, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
        return [json.loads(l) for l in lines[-n:]][::-1]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def get_config_history() -> list[dict]:
    configs_path = os.path.abspath(CONFIGS_PATH)
    try:
        with open(configs_path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
