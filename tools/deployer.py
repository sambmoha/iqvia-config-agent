from datetime import datetime, timezone


ENVIRONMENT_CHECKS = {
    "dev": [
        "Schema integrity check",
        "Required fields present",
        "Syntax validation",
    ],
    "qa": [
        "Schema integrity check",
        "Required fields present",
        "Syntax validation",
        "Business rule consistency",
        "Cross-field dependency check",
        "Regression test suite",
    ],
    "prod": [
        "Schema integrity check",
        "Required fields present",
        "Syntax validation",
        "Business rule consistency",
        "Cross-field dependency check",
        "Regression test suite",
        "Change advisory board sign-off",
        "Rollback plan verified",
        "Audit trail complete",
    ],
}


def _simulate_checks(env: str) -> list[dict]:
    return [
        {"check": name, "result": "PASS", "duration_ms": (i + 1) * 12}
        for i, name in enumerate(ENVIRONMENT_CHECKS[env])
    ]


def deploy_config(config: dict, target_env: str, reviewer_notes: str = "") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    config_id = config.get("config_id", "UNKNOWN")
    version = config.get("version", "1.0")

    if target_env not in ENVIRONMENT_CHECKS:
        return {
            "success": False,
            "error": f"Unknown environment: {target_env}",
        }

    checks = _simulate_checks(target_env)
    failed = [c for c in checks if c["result"] != "PASS"]

    pipeline_stages = []
    environments = ["dev", "qa", "prod"]
    reached = environments[: environments.index(target_env) + 1]

    for env in reached:
        pipeline_stages.append({
            "environment": env.upper(),
            "status": "DEPLOYED" if env != target_env else ("SUCCESS" if not failed else "FAILED"),
            "timestamp": now,
            "checks_run": len(ENVIRONMENT_CHECKS[env]),
            "checks_passed": len(ENVIRONMENT_CHECKS[env]) - len(failed) if env == target_env else len(ENVIRONMENT_CHECKS[env]),
        })

    return {
        "success": not failed,
        "config_id": config_id,
        "version": version,
        "target_environment": target_env.upper(),
        "deployed_at": now,
        "reviewer_notes": reviewer_notes or "None",
        "pre_deploy_checks": checks,
        "pipeline": pipeline_stages,
        "rollback_available": True,
        "audit_ref": f"AUD-{config_id}-{target_env.upper()}",
    }
