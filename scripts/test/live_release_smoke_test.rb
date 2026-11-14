# frozen_string_literal: true

# Unit tests for the live release smoke's verdict helpers.
#
# These replace the helper-level tests that used to import scripts/live_release_smoke.py
# (test_live_smoke_script.py, test_simplify_regressions.py). The full-matrix test still lives
# in apps/api/tests/test_live_smoke_script.py, which now runs this script as a subprocess
# against the real app. Run with: ruby scripts/test/live_release_smoke_test.rb

require "minitest/autorun"
require "open3"
require_relative "../live_release_smoke"

S = LiveReleaseSmoke

class ShaResultTest < Minitest::Test
  def test_sha_verdicts_never_pass_on_missing_evidence
    assert_equal true, S.sha_result("x", "abc", "abc")["passed"]
    assert_equal false, S.sha_result("x", "abc", "def")["passed"]
    assert_nil S.sha_result("x", "abc", "")["passed"] # observed, not proven
    assert_nil S.sha_result("x", nil, "abc")["passed"] # UNAVAILABLE, not inferred
    assert_equal false, S.sha_result("x", "abc", "abc", extra_ok: false)["passed"]
  end
end

class TimeoutResultTest < Minitest::Test
  GOOD_BODY = { "status" => "failed", "error" => "request exceeded runtime budget" }.freeze
  GOOD_TRACE = {
    "state" => {
      "terminal" => true,
      "outcome_code" => "runtime_timeout",
      "interrupts" => [{ "reason" => "timeout" }]
    }
  }.freeze

  def test_timeout_verdict_requires_a_terminal_timeout_interrupt
    assert_equal true, S.timeout_result(200, GOOD_BODY, 200, GOOD_TRACE)["passed"]
    assert_equal false, S.timeout_result(200, GOOD_BODY.merge("status" => "completed"), 200, GOOD_TRACE)["passed"]
    bad_trace = { "state" => GOOD_TRACE["state"].merge("interrupts" => []) }
    assert_equal false, S.timeout_result(200, GOOD_BODY, 200, bad_trace)["passed"]
    assert_equal false, S.timeout_result(500, GOOD_BODY, 200, GOOD_TRACE)["passed"]
  end
end

class FailoverAndMetricsTest < Minitest::Test
  def test_failover_is_proven_only_by_observed_fallbacks
    quiet = { "mode" => "observe", "fallback_percent" => 5, "failovers" => {} }
    seen = { "mode" => "observe", "fallback_percent" => 5, "failovers" => { "a->b" => 2 } }
    assert_nil S.failover_result(200, quiet)["passed"]
    assert_equal true, S.failover_result(200, seen)["passed"]
    assert_equal true, S.metrics_window_result(200, { "retention" => { "comparable_24h" => true } })["passed"]
    assert_nil S.metrics_window_result(200, { "retention" => { "comparable_24h" => false } })["passed"]
    assert_nil S.metrics_window_result(404, {})["passed"]
    assert_nil S.failover_result(404, {})["passed"]
  end
end

class DatabaseResultTest < Minitest::Test
  CURRENT = {
    "state" => "healthy", "schema_version" => 15, "expected_schema_version" => 15,
    "retention_due_requests" => 2, "retention_due_archived_events" => 0, "error_type" => nil
  }.freeze

  def test_database_verdict_needs_a_healthy_store_on_the_builds_schema
    result = S.database_result(200, { "database" => CURRENT })
    assert_equal true, result["passed"]
    assert_equal 2, result["observed"]["retention_due_requests"]
    behind = CURRENT.merge("state" => "unhealthy", "schema_version" => 14,
                           "error_type" => "SchemaVersionMismatch")
    assert_equal false, S.database_result(200, { "database" => behind })["passed"]
    assert_equal false, S.database_result(200, { "database" => CURRENT.merge("state" => "disabled") })["passed"]
    assert_nil S.database_result(200, {})["passed"] # older API: observed, not proven
    assert_nil S.database_result(403, { "database" => CURRENT })["passed"]
  end
end

class JsonOrTextTest < Minitest::Test
  def test_json_or_text_parses_json_and_keeps_plain_text
    assert_equal({ "status" => "ok" }, S.json_or_text('{"status": "ok"}'))
    assert_equal "<html>blocked</html>", S.json_or_text("<html>blocked</html>")
  end
end

class RequestRetryTest < Minitest::Test
  # A GET to a closed loopback port fails fast with ECONNREFUSED; the smoke's
  # request helper must retry it via smoke_support and surface the attempt
  # count and elapsed time in the raised message (the collector records that
  # message into the failure evidence).
  def test_get_transport_failure_message_carries_attempts_and_elapsed
    ENV["SMOKE_RETRY_BASE_DELAY_MS"] = "1"
    server = TCPServer.new("127.0.0.1", 0)
    port = server.addr[1]
    server.close
    error = assert_raises(SmokeSupport::Failure) do
      S.request("http://127.0.0.1:#{port}/v1/runtime/health")
    end
    assert_equal 3, error.attempts
    assert_includes error.message, "(after 3 attempts,"
  ensure
    ENV.delete("SMOKE_RETRY_BASE_DELAY_MS")
  end
end

class CommitShaTest < Minitest::Test
  def commit_sha_for(env_value)
    script = File.expand_path("../live_release_smoke.rb", __dir__)
    out, status = Open3.capture2(
      { "LIVE_EXPECTED_SHA" => env_value },
      RbConfig.ruby, "-e",
      "require #{script.dump}; print LiveReleaseSmoke::COMMIT_SHA.inspect"
    )
    assert status.success?, out
    out
  end

  def test_commit_sha_follows_the_expected_sha
    assert_equal '"abc123"', commit_sha_for("  abc123  ")
    assert_equal "nil", commit_sha_for("   ")
  end
end
