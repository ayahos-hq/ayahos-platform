#!/usr/bin/env bash
# Octopus Runbook entry point for the single canonical encrypted PostgreSQL backup.
# Never execute through GitHub Actions, CI verification steps, or a web request.
set -euo pipefail
set +x
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

die() { printf 'Octopus database backup: %s\n' "$1" >&2; exit 2; }

# Runbook/process variables must be scoped to the dedicated backup runbook.
# Never print variable values: Octopus's get_octopusvariable returns secrets.
command -v get_octopusvariable >/dev/null 2>&1 ||
  die "Octopus variable provider unavailable; refusing backup"

octopus_value() { get_octopusvariable "$1" 2>/dev/null || true; }
required_value() {
  local result
  result="$(octopus_value "$1")"
  [[ -n "$result" ]] || die "missing Octopus runbook setting: $1"
  printf '%s' "$result"
}

# Separate approvals keep the runbook inert until recovery and cost gates pass.
# Variables are provisioned outside Git, on the trusted Octopus project.
[[ "$(octopus_value 'AyahOS.Backup.RunApproved')" == "YES" ]] ||
  die "runbook not activated: approval gate is closed"
[[ "$(octopus_value 'AyahOS.Backup.RestoreGatePassed')" == "YES" ]] ||
  die "real isolated restore has not been approved"

export DATABASE_URL
DATABASE_URL="$(required_value 'AyahOS.Backup.DatabaseUrl')"
export AYAHOS_BACKUP_PROJECT_REF
AYAHOS_BACKUP_PROJECT_REF="$(required_value 'AyahOS.Backup.ProjectRef')"
[[ "$AYAHOS_BACKUP_PROJECT_REF" == "xgomhbuzawoqnwlzvavx" ]] ||
  die "backup target project does not match authorized source"

export AYAHOS_BACKUP_AGE_RECIPIENT
AYAHOS_BACKUP_AGE_RECIPIENT="$(required_value 'AyahOS.Backup.AgeRecipient')"
export AYAHOS_PGSSLROOTCERT
AYAHOS_PGSSLROOTCERT="$(required_value 'AyahOS.Backup.CAFile')"
[[ -f "$AYAHOS_PGSSLROOTCERT" && -r "$AYAHOS_PGSSLROOTCERT" ]] ||
  die "trusted PostgreSQL certificate authority unavailable"

# Environment-backed rclone configuration avoids placing access keys in argv,
# persistent config files, shell history, logs or Git.
export RCLONE_CONFIG_AYAHOS_R2_TYPE="s3"
export RCLONE_CONFIG_AYAHOS_R2_PROVIDER="Cloudflare"
export RCLONE_CONFIG_AYAHOS_R2_ACCESS_KEY_ID
RCLONE_CONFIG_AYAHOS_R2_ACCESS_KEY_ID="$(required_value 'AyahOS.Backup.R2AccessKeyId')"
export RCLONE_CONFIG_AYAHOS_R2_SECRET_ACCESS_KEY
RCLONE_CONFIG_AYAHOS_R2_SECRET_ACCESS_KEY="$(required_value 'AyahOS.Backup.R2SecretAccessKey')"
export RCLONE_CONFIG_AYAHOS_R2_ENDPOINT="https://a9c52e892f7361bab3bfd084c6ffaccb.r2.cloudflarestorage.com"
export RCLONE_CONFIG_AYAHOS_R2_NO_CHECK_BUCKET="true"
export AYAHOS_BACKUP_RCLONE_REMOTE="ayahos-r2:ayahos-db-backups-private"

# Fail before data access if toolchain is not installed on the approved,
# separately enrolled backup worker. Never install packages at run time.
for tool in pg_dump age rclone python3; do
  command -v "$tool" >/dev/null 2>&1 ||
    die "required backup tool is unavailable: $tool"
done
pg_dump --version | grep -Eq 'PostgreSQL\) 17\.' ||
  die "PostgreSQL 17 client is required"

# The canonical Python runner performs encrypted streaming, upload + readback.
# It returns a sanitized JSON receipt only after SHA-256 verification.
python3 scripts/db/backup_postgres.py
