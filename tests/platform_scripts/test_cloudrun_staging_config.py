"""Static gates for the optional zero-spend Cloud Run staging candidate.

These checks do not contact Google Cloud, build images, or incur cloud charges.
They intentionally don't claim production feature parity.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cloud_run_image_is_python_only_and_single_worker() -> None:
    dockerfile = _read("Dockerfile.cloudrun")
    commands = [
        line.strip()
        for line in dockerfile.splitlines()
        if line.startswith(("FROM ", "COPY ", "RUN ", "CMD ", "ADD "))
    ]
    assert "FROM python:3.15-slim-bookworm" in commands
    assert "COPY apps/api/src/ /app/apps/api/src/" in commands
    assert "COPY apps/api/pyproject.toml /app/apps/api/pyproject.toml" in commands
    assert 'apps/api[control]' in dockerfile
    assert "--workers 1" in dockerfile
    assert "0.0.0.0" in dockerfile
    assert "${PORT:-8080}" in dockerfile
    assert not any(
        forbidden in line
        for line in commands
        for forbidden in (
            "apt-get", "torch", "transformers", "sentence-transformers",
            "apps/rag-ruby", "apps/control-ruby", "apps/ruby_worker",
            "models/", "data/", "ml-requirements",
        )
    )


def test_cloud_run_staging_defaults_fail_closed() -> None:
    env = _read("deploy/cloudrun/staging-env.yaml")
    for key in (
        "DUAL_LINEAGE_RAG_ENABLED",
        "DUAL_LINEAGE_SHADOW_ENABLED",
        "DUAL_LINEAGE_AGENT_ENABLED",
        "DUAL_LINEAGE_ALLOW_CLOUD",
        "DUAL_LINEAGE_ALLOW_WRITES",
        "DUAL_LINEAGE_ALLOW_EXEC",
        "DUAL_LINEAGE_ALLOW_NETWORK",
        "DUAL_LINEAGE_ALLOW_SECRET_READ",
        "DUAL_LINEAGE_ALLOW_DELETE",
        "DUAL_LINEAGE_ALLOW_EXTERNAL_SIDE_EFFECTS",
        "DUAL_LINEAGE_ALLOW_UNAUTHENTICATED_LOCAL",
    ):
        assert f'{key}: "false"' in env
    assert "DUAL_LINEAGE_DATABASE_MODE: local" in env
    assert 'DUAL_LINEAGE_MAX_COST_USD: "0.00"' in env
    assert "DATABASE_URL:" not in env
    assert "API_KEY:" not in env


def test_cloud_build_config_does_not_deploy() -> None:
    config = _read("deploy/cloudrun/cloudbuild.yaml")
    assert "gcr.io/cloud-builders/docker" in config
    assert "run deploy" not in config
    assert "gcloud run" not in config
    assert "trigger:" not in config


def test_cloud_upload_excludes_secrets_heavy_apps_and_models() -> None:
    ignored = set(_read(".gcloudignore").splitlines())
    for path in (
        ".git/", ".env", "**/.env.*", "**/*.pem", "**/*.key",
        "models/", "data/", "apps/rag-ruby/", "apps/control-ruby/",
        "apps/ruby_worker/", "apps/site/", "apps/web/",
    ):
        assert path in ignored


def test_zero_spend_and_rollback_gates_are_explicit() -> None:
    runbook = _read("deploy/cloudrun/README.md")
    assert "strict $0" in runbook
    assert "Do not execute it under the current strict $0 policy." in runbook
    assert "Render" in runbook
    assert "Aliyun" in runbook
    assert "Undermind" in runbook
    assert "Supabase" in runbook


def test_staging_target_rejects_sample_public_architecture() -> None:
    target = json.loads(_read("deploy/cloudrun/staging-target.json"))
    assert target["project_id"] == "project-eec9b975-b6bd-4b41-bad"
    assert target["region"] == "us-central1"
    assert target["service"].startswith("ayahos-staging-")
    assert target["image"] == "REPLACE_WITH_AYAHOS_IMAGE_AT_SHA256_DIGEST"
    assert target["ingress"] == "internal"
    assert target["allow_unauthenticated"] is False
    assert target["min_instances"] == 0
    assert target["max_instances"] == 1
    assert target["cpu"] == "1"
    assert target["memory"] == "512Mi"
    assert target["concurrency"] == 2
    assert target["timeout_seconds"] == 60
    assert target["request_based_billing"] is True
    assert target["no_traffic"] is True
