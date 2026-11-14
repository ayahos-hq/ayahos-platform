#!/usr/bin/env bash
# Live dual-lineage E2E against the deployed Render stack. Ported from the former
# .github/workflows/live-e2e.yml; formerly run by the CircleCI `live-e2e` job on main; now run by hand.
#
# Env: RUNTIME_API_KEY (required), BASE_URL, EXPECTED_SHA (empty: only require web and API to
# agree), RUN_TAG (unique per run, used in request ids), FORCE=1 to skip the path filter.
set -euo pipefail

BASE_URL="${BASE_URL:-https://goblin-dual-lineage-web-live.onrender.com}"
EXPECTED_SHA="${EXPECTED_SHA:-}"
RUN_TAG="${RUN_TAG:-local-$(date +%s)}"
: "${RUNTIME_API_KEY:?RUNTIME_API_KEY is required}"

WATCHED_PATHS=(
  render.yaml
  apps/api/src/dual_lineage/api/cognition.py
  apps/api/src/dual_lineage/runtime.py
  apps/api/src/dual_lineage/api/runtime_status.py
  apps/api/src/dual_lineage/api/rag.py
  apps/api/src/dual_lineage/coordinator.py
  apps/api/src/dual_lineage/rag/
  apps/api/src/dual_lineage/spine/
  apps/api/src/dual_lineage/compute/
  apps/api/src/dual_lineage/providers/
  apps/web/lib/server/backend.ts
  apps/web/app/api/build/
  apps/web/app/api/cognition/
  apps/web/app/page.tsx
  apps/web/lib/contracts.ts
  apps/web/lib/telemetry.ts
  scripts/live_e2e.sh
)

REQUEST_ID=""
SKIP_SMOKE_LABEL=false

auth() { printf 'X-Dual-Lineage-Key: %s' "$RUNTIME_API_KEY"; }

changed_watched_paths() {
  [ "${FORCE:-0}" = 1 ] && return 0
  # Squash merges put one commit on main, so the last commit is the change.
  git diff --quiet HEAD~1 HEAD -- "${WATCHED_PATHS[@]}" && return 1
  return 0
}

wait_for_deployed_commit() {
  local attempt web_status runtime_status readiness_status
  for attempt in $(seq 1 96); do
    web_status="$(curl --silent --show-error --max-time 20 -H "$(auth)" \
      -o web-build.json -w '%{http_code}' "$BASE_URL/api/build" || true)"
    runtime_status="$(curl --silent --show-error --max-time 20 -H "$(auth)" \
      -o runtime.json -w '%{http_code}' "$BASE_URL/api/runtime" || true)"
    readiness_status="$(curl --silent --show-error --max-time 20 -H "$(auth)" \
      -o readiness-before.json -w '%{http_code}' "$BASE_URL/api/cognition/learning/readiness" || true)"

    local web_synced=false api_synced=false runtime_ready=false readiness_ready=false

    if [ "$web_status" = "200" ]; then
      if [ -z "$EXPECTED_SHA" ] || jq -e --arg sha "$EXPECTED_SHA" '.build_sha == $sha' web-build.json >/dev/null 2>&1; then
        web_synced=true
      fi
    fi
    if [ "$runtime_status" = "200" ]; then
      if [ -z "$EXPECTED_SHA" ] || jq -e --arg sha "$EXPECTED_SHA" '.build_sha == $sha' runtime.json >/dev/null 2>&1; then
        api_synced=true
      fi
    fi
    if [ -z "$EXPECTED_SHA" ] && [ "$web_status" = "200" ] && [ "$runtime_status" = "200" ] \
      && jq -n -e --slurpfile web web-build.json --slurpfile api runtime.json \
        '$web[0].build_sha != null and $api[0].build_sha != null and $web[0].build_sha == $api[0].build_sha' >/dev/null 2>&1; then
      web_synced=true
      api_synced=true
    fi
    if [ "$runtime_status" = "200" ] \
      && jq -e '.shadow_enabled == false' runtime.json >/dev/null 2>&1 \
      && jq -e 'all(.provider_routes[]?; .local == false)' runtime.json >/dev/null 2>&1 \
      && jq -e '.operational_learning_enabled == true' runtime.json >/dev/null 2>&1 \
      && jq -e '.budgets.max_runtime_ms >= 90000' runtime.json >/dev/null 2>&1; then
      runtime_ready=true
    fi
    if [ "$readiness_status" = "200" ] \
      && jq -e '.record_count >= 0 and .family_count >= 0' readiness-before.json >/dev/null 2>&1; then
      readiness_ready=true
    fi

    if [ "$web_synced" = true ] && [ "$api_synced" = true ] \
      && [ "$runtime_ready" = true ] && [ "$readiness_ready" = true ]; then
      echo "Web and API are synchronized to ${EXPECTED_SHA:-a matching build}"
      jq '{build_sha}' web-build.json
      jq '{build_sha,provider_id,shadow_enabled,operational_learning_enabled,budgets}' runtime.json
      jq '{record_count,family_count,captured_observations,pending_human_review,ready_for_training,ready_for_promotion_evaluation}' readiness-before.json
      return 0
    fi

    echo "Stack not synchronized yet (attempt $attempt/96)"
    echo "web_status=$web_status api_status=$runtime_status readiness_status=$readiness_status expected_sha=$EXPECTED_SHA"
    cat web-build.json 2>/dev/null || true
    cat runtime.json 2>/dev/null || true
    sleep 5
  done
  exit 1
}

verify_aliyun_peer() {
  if ! jq -e 'any(.provider_routes[]?; .provider_id == "aliyun-overmind")' runtime.json >/dev/null 2>&1; then
    echo "aliyun-overmind is not registered in the live provider fabric"
    jq '{build_sha,provider_id,provider_routes}' runtime.json
    exit 1
  fi
  jq '[.provider_routes[] | select(.provider_id == "aliyun-overmind") | {provider_id,local}]' runtime.json
}

prove_nonstreaming_inference() {
  local attempt request_id status retryable
  for attempt in 1 2 3; do
    request_id="smoke-nonstream-$RUN_TAG-$attempt"
    cat > diag-request.json <<JSON
{
  "request_id": "$request_id",
  "messages": [{"role":"user","content":"Reply only: OK /no_think"}],
  "temperature": 0.0,
  "requested_max_tokens": 16,
  "requested_runtime_ms": 90000,
  "local_allowed": true,
  "cloud_allowed": true,
  "learning_consent": true
}
JSON
    status="$(curl --silent --show-error --max-time 120 --connect-timeout 20 \
      -H "$(auth)" -H 'Content-Type: application/json' --data @diag-request.json \
      -o diag-response.json -w '%{http_code}' "$BASE_URL/api/cognition" || true)"

    if [ "$status" = "200" ] \
      && jq -e '.status == "completed" and ((.node_id != null) or (.provider_id != null))' diag-response.json >/dev/null 2>&1 \
      && jq -e '.provider_id != "overmind-local"' diag-response.json >/dev/null 2>&1 \
      && test -n "$(jq -r '.text // empty' diag-response.json)"; then
      cat diag-response.json
      REQUEST_ID="$request_id"
      return 0
    fi

    echo "Non-streaming inference attempt $attempt failed: HTTP $status"
    cat diag-response.json 2>/dev/null || true

    retryable=false
    if [ "$status" = "200" ] \
      && jq -e '.status == "failed" and .error == "request exceeded runtime budget"' diag-response.json >/dev/null 2>&1; then
      retryable=true
    fi
    if [ "$retryable" = true ] && [ "$attempt" -lt 3 ]; then
      echo "Retrying after transient governed runtime timeout."
      sleep 10
      continue
    fi
    case "$status" in
      000|502|503|504) if [ "$attempt" -lt 3 ]; then sleep 10; continue; fi ;;
      *) exit 1 ;;
    esac
  done
  exit 1
}

prove_cloud_stream() {
  if ! jq -e '.provider_id != null and .provider_local == false' runtime.json >/dev/null 2>&1; then
    echo "No configured cloud provider is selected by the control plane; buffered external-compute E2E already passed, so streaming is skipped."
    return 0
  fi
  local attempt request_id status
  for attempt in 1 2 3; do
    request_id="smoke-live-main-$RUN_TAG-$attempt"
    cat > request.json <<JSON
{
  "request_id": "$request_id",
  "messages": [{"role":"user","content":"Reply only: OK /no_think"}],
  "temperature": 0.0,
  "requested_max_tokens": 512,
  "requested_runtime_ms": 90000,
  "local_allowed": false,
  "cloud_allowed": true,
  "learning_consent": true
}
JSON
    status="$(curl --silent --show-error --no-buffer --max-time 120 --connect-timeout 20 \
      -H "$(auth)" -H 'Content-Type: application/json' --data @request.json \
      -o stream.txt -w '%{http_code}' "$BASE_URL/api/cognition/stream" || true)"

    if [ "$status" = "200" ] && grep -q '"type":"delta"' stream.txt \
      && grep -q '"type":"done"' stream.txt && ! grep -q '"type":"error"' stream.txt; then
      cat stream.txt
      REQUEST_ID="$request_id"
      return 0
    fi

    echo "Streaming inference attempt $attempt failed: HTTP $status"
    cat stream.txt 2>/dev/null || true
    curl --silent --show-error --max-time 30 -H "$(auth)" -X DELETE \
      "$BASE_URL/api/cognition/$request_id/learning-consent" -o failed-withdrawal.json || true
    cat failed-withdrawal.json 2>/dev/null || true

    case "$status" in
      000|502|503|504) if [ "$attempt" -lt 3 ]; then sleep 10; continue; fi ;;
      *) exit 1 ;;
    esac
  done
  exit 1
}

verify_terminal_trace() {
  test -n "$REQUEST_ID"
  curl --fail --silent --show-error --max-time 30 -H "$(auth)" \
    "$BASE_URL/api/cognition/$REQUEST_ID/trace" -o trace.json
  jq '{
    phase:.state.phase,
    outcome_code:.state.outcome_code,
    terminal:.state.terminal,
    provider_id:.state.provider_id,
    model_id:.state.model_id,
    shadow_predictions:.state.shadow_predictions,
    usage:.state.usage
  }' trace.json
  jq -e '.state.terminal == true' trace.json >/dev/null
  jq -e '.state.outcome_code == "ok"' trace.json >/dev/null
  jq -e '(.state.provider_id != "overmind-local") or (.state.node_id != null)' trace.json >/dev/null
}

save_smoke_label() {
  # The lightweight Render control plane deliberately has no embedding shadow collector.
  # Do not manufacture a label when no consented operational observation could have been recorded.
  if ! jq -e '.operational_learning_enabled == true and .shadow_enabled == true and (.shadow_backend == "minilm" or .shadow_backend == "remote-minilm")' runtime.json >/dev/null 2>&1; then
    echo "Operational evidence lifecycle skipped: embedding-shadow collection is disabled."
    SKIP_SMOKE_LABEL=true
    return 0
  fi
  cat > label.json <<JSON
{
  "scenario_family":"general__smoke",
  "complexity_label":false,
  "risk_label":false,
  "uncertainty_label":false,
  "escalation_label":false,
  "task_class":"general"
}
JSON
  curl --fail-with-body --silent --show-error --max-time 30 -H "$(auth)" \
    -H 'Content-Type: application/json' --data @label.json \
    "$BASE_URL/api/cognition/$REQUEST_ID/learning-label" -o label-response.json
  cat label-response.json
  jq -e '.label_source == "smoke_test"' label-response.json >/dev/null
}

prove_smoke_excluded_from_readiness() {
  if [ "$SKIP_SMOKE_LABEL" = true ]; then
    echo "Operational evidence lifecycle was not active for this deployment."
    return 0
  fi
  curl --fail --silent --show-error --max-time 30 -H "$(auth)" \
    "$BASE_URL/api/cognition/learning/readiness" -o readiness-after.json
  test "$(jq -r '.record_count' readiness-before.json)" = "$(jq -r '.record_count' readiness-after.json)"
  test "$(jq -r '.family_count' readiness-before.json)" = "$(jq -r '.family_count' readiness-after.json)"
  jq '{record_count,family_count,captured_observations,pending_human_review,smoke_labeled,withdrawn,ready_for_training,ready_for_promotion_evaluation}' readiness-after.json
}

withdraw_smoke_evidence() {
  set +e
  if [ "$SKIP_SMOKE_LABEL" != true ] && [ -n "$REQUEST_ID" ]; then
    curl --silent --show-error --max-time 30 -H "$(auth)" -X DELETE \
      "$BASE_URL/api/cognition/$REQUEST_ID/learning-consent" -o withdrawal.json
    cat withdrawal.json 2>/dev/null || true
  fi
}

if ! changed_watched_paths; then
  echo "No live-E2E paths changed in the last commit; skipping."
  exit 0
fi

trap withdraw_smoke_evidence EXIT
wait_for_deployed_commit
verify_aliyun_peer
prove_nonstreaming_inference
prove_cloud_stream
verify_terminal_trace
save_smoke_label
prove_smoke_excluded_from_readiness
