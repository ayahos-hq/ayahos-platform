#!/usr/bin/env ruby
# frozen_string_literal: true

# Bounded live release smoke test; secrets are read from the environment only.
#
# Required: LIVE_API_URL, LIVE_PUBLIC_SITE_URL, LIVE_RUNTIME_API_KEY.
# Optional: LIVE_WEB_URL, LIVE_EXPECTED_SHA (API + operator web), LIVE_EXPECTED_SITE_SHA
# (public site; set it to the commit the site is meant to serve, since it can trail `main`).
# Results are JSON and contain no credentials. A check with `passed: nil` is evidence that
# was observed but not proven (for example no expected SHA given); it never counts as a pass.
#
# Ported from live_release_smoke.py; standard library only. Python owns every rule this
# script exercises; it only calls the live surfaces and reports their verdicts.

require "fileutils"
require "json"
require "net/http"
require "securerandom"
require "time"
require "uri"
require_relative "smoke_support"

module LiveReleaseSmoke
  API = ENV.fetch("LIVE_API_URL", "https://goblin-dual-lineage-api.onrender.com").sub(%r{/+\z}, "")
  SITE = ENV.fetch("LIVE_PUBLIC_SITE_URL", "https://ayahos.pages.dev").sub(%r{/+\z}, "")
  WEB = ENV.fetch("LIVE_WEB_URL", "https://goblin-dual-lineage-web-live.onrender.com").sub(%r{/+\z}, "")
  KEY = ENV.fetch("LIVE_RUNTIME_API_KEY", "")
  EXPECTED_SHA = ENV.fetch("LIVE_EXPECTED_SHA", "").strip
  EXPECTED_SITE_SHA = ENV.fetch("LIVE_EXPECTED_SITE_SHA", "").strip
  COMMIT_SHA = EXPECTED_SHA.empty? ? nil : EXPECTED_SHA
  OUT = ENV.fetch("LIVE_SMOKE_OUTPUT", "artifacts/live-smoke-latest.json")
  # Cloudflare rejects the HTTP library's default user agent on the public site.
  USER_AGENT = "AyahOS-live-smoke/1"

  module_function

  def utc_now
    Time.now.utc.strftime("%Y-%m-%dT%H:%M:%S.%6N+00:00")
  end

  # Parse a response body as JSON when possible; otherwise keep the raw text.
  def json_or_text(raw)
    JSON.parse(raw)
  rescue JSON::ParserError
    raw
  end

  def request(url, method: "GET", body: nil, auth: false, timeout: 30)
    headers = { "Accept" => "application/json", "User-Agent" => USER_AGENT }
    if auth
      raise "LIVE_RUNTIME_API_KEY is required for authenticated smoke checks" if KEY.empty?

      headers["X-Dual-Lineage-Key"] = KEY
    end
    data = nil
    unless body.nil?
      headers["Content-Type"] = "application/json"
      data = JSON.generate(body)
    end
    uri = URI(url)
    perform = lambda do
      Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == "https",
                                                 open_timeout: [timeout, 10].min,
                                                 read_timeout: timeout) do |http|
        req = case method
              when "POST" then Net::HTTP::Post.new(uri)
              when "PUT" then Net::HTTP::Put.new(uri)
              when "DELETE" then Net::HTTP::Delete.new(uri)
              else Net::HTTP::Get.new(uri)
              end
        headers.each { |name, value| req[name] = value }
        req.body = data if data
        http.request(req)
      end
    end
    # GETs are read-only: retry transient transport failures and 502/503/504
    # via smoke_support. Mutating methods stay single-attempt. An exhausted
    # GET raises SmokeSupport::Failure, whose message carries the attempt
    # count and elapsed time into the collector's evidence.
    response = if method == "GET"
                 SmokeSupport.fetch(retry_statuses: true) { perform.call }.response
               else
                 perform.call
               end
    [response.code.to_i, json_or_text(response.body.to_s)]
  end

  # Served-SHA verdict. A missing SHA or missing expectation is never a pass.
  def sha_result(name, observed, expected, extra_ok: true)
    sha = observed.is_a?(String) && !observed.empty? ? observed : nil
    if sha.nil?
      return { "check" => name, "passed" => nil, "observed" => { "build_sha" => nil },
               "note" => "surface reported no SHA (UNAVAILABLE); not inferred" }
    end
    if expected.nil? || expected.empty?
      return { "check" => name, "passed" => nil, "observed" => { "build_sha" => sha },
               "note" => "no expected SHA supplied; observed only" }
    end
    { "check" => name, "passed" => sha == expected && extra_ok,
      "observed" => { "build_sha" => sha, "expected" => expected } }
  end

  # A 1ms runtime budget must end terminally with a TIMEOUT interrupt, not hang or pass.
  def timeout_result(status, body, trace_status, trace)
    state = trace.is_a?(Hash) ? trace["state"] || {} : {}
    interrupts = (state["interrupts"] || []).select { |i| i.is_a?(Hash) }.map { |i| i["reason"] }
    passed = status == 200 &&
             body.is_a?(Hash) &&
             body["status"] == "failed" &&
             body["error"] == "request exceeded runtime budget" &&
             trace_status == 200 &&
             state["terminal"] == true &&
             state["outcome_code"] == "runtime_timeout" &&
             interrupts.include?("timeout")
    {
      "check" => "timeout_terminal",
      "status" => status,
      "passed" => passed,
      "observed" => {
        "status" => body.is_a?(Hash) ? body["status"] : nil,
        "outcome_code" => state["outcome_code"],
        "interrupts" => interrupts
      }
    }
  end

  # Failover is only proven by observed failovers; its absence is not a failure.
  def failover_result(status, body)
    if status != 200 || !body.is_a?(Hash)
      return { "check" => "failover_observed", "passed" => nil,
               "note" => "routing status unavailable; failover not evaluable" }
    end
    failovers = body["failovers"]
    moved = failovers.is_a?(Hash) ? failovers.values.sum { |v| v.to_i } : 0
    result = {
      "check" => "failover_observed",
      "passed" => moved.positive? ? true : nil,
      "observed" => {
        "mode" => body["mode"],
        "fallback_percent" => body["fallback_percent"],
        "failovers" => failovers
      }
    }
    result["note"] = "no failover observed in the window; failover not proven" unless moved.positive?
    result
  end

  # The provider-metrics gate: a comparable 24h window must exist before routing changes.
  def metrics_window_result(status, body)
    retention = body.is_a?(Hash) ? body["retention"] || {} : {}
    comparable = status == 200 ? retention["comparable_24h"] ? true : false : nil
    passed = comparable ? true : nil
    result = {
      "check" => "provider_metrics_window",
      "status" => status,
      "passed" => passed,
      "observed" => {
        "comparable_24h" => retention["comparable_24h"],
        "coverage_hours" => retention["coverage_hours"],
        "storage" => retention["storage"],
        "provider_ids" => retention["provider_ids"]
      }
    }
    result["note"] = "no comparable 24h window; routing must stay unchanged" unless comparable
    result
  end

  # Live schema and retention backlog from authenticated health.
  #
  # The health check reads the applied schema version from the live store, so a healthy report
  # whose version matches the build's is the live migration proof. A health response without
  # the field (an API older than this check) is observed, not proven.
  def database_result(status, body)
    database = status == 200 && body.is_a?(Hash) ? body["database"] : nil
    unless database.is_a?(Hash)
      return { "check" => "database_schema", "status" => status, "passed" => nil,
               "note" => "health reported no database status; live schema not proven" }
    end
    {
      "check" => "database_schema",
      "status" => status,
      "passed" => database["state"] == "healthy" &&
                  database["schema_version"] == database["expected_schema_version"],
      "observed" => {
        "state" => database["state"],
        "schema_version" => database["schema_version"],
        "expected_schema_version" => database["expected_schema_version"],
        "retention_due_requests" => database["retention_due_requests"],
        "retention_due_archived_events" => database["retention_due_archived_events"],
        "error_type" => database["error_type"]
      }
    }
  end

  def write_evidence(evidence)
    FileUtils.mkdir_p(File.dirname(OUT))
    File.write(OUT, "#{JSON.pretty_generate(evidence)}\n", encoding: "UTF-8")
  end

  def main
    if KEY.empty?
      started = utc_now
      write_evidence(
        "evidence_id" => "live-release-#{SecureRandom.hex(16)}",
        "started_at" => started,
        "finished_at" => utc_now,
        "commit_sha" => COMMIT_SHA,
        "source" => "live_release_smoke",
        "status" => "completed",
        "decision" => "HOLD",
        "missing_credentials" => ["LIVE_RUNTIME_API_KEY"],
        "results" => []
      )
      puts "HOLD: missing credentials: LIVE_RUNTIME_API_KEY; evidence=#{OUT}"
      return 0
    end
    started = utc_now
    request_id = "release-smoke-#{SecureRandom.hex(16)}"
    payload = {
      "request_id" => request_id,
      "messages" => [{ "role" => "user", "content" => "Reply only: OK" }],
      "requested_max_tokens" => 16,
      "requested_runtime_ms" => 90_000,
      "local_allowed" => true,
      "cloud_allowed" => true
    }
    results = []

    check = lambda do |name, url, expect: nil, **kwargs|
      status, body = request(url, **kwargs)
      passed = expect ? expect.call(status, body) ? true : false : (status >= 200 && status < 300)
      observed = if body.is_a?(Hash)
                   body.reject { |key, _| %w[text error].include?(key) }
                 else
                   body
                 end
      results << { "check" => name, "status" => status, "passed" => passed, "observed" => observed }
      [status, body]
    end

    check.call(
      "public_chat", "#{SITE}/api/chat", method: "POST",
      body: {
        "messages" => [
          {
            "role" => "user",
            "content" => "What happened to the supermodel after CoolSculpting caused disfigurement?"
          }
        ]
      },
      timeout: 120,
      expect: lambda do |status, body|
        status == 200 && body.is_a?(Hash) && body["status"] == "completed" &&
          SmokeSupport.public_provider_ok?(body["provider"])
      end
    )
    check.call(
      "auth_missing", "#{API}/v1/cognition", method: "POST", body: payload,
      expect: ->(status, _body) { status == 401 }
    )
    status, run = check.call(
      "authenticated_cognition", "#{API}/v1/cognition", method: "POST", body: payload,
      auth: true, timeout: 120,
      expect: lambda do |s, body|
        s == 200 && body.is_a?(Hash) && body["status"] == "completed"
      end
    )
    health_status, health = check.call(
      "runtime_health", "#{API}/v1/runtime/health", auth: true,
      expect: ->(s, body) { s == 200 && body.is_a?(Hash) }
    )
    results << database_result(health_status, health)
    _storage_status, runtime_status = check.call(
      "runtime_storage_mode", "#{API}/v1/runtime/status", auth: true,
      expect: lambda do |s, body|
        s == 200 && body.is_a?(Hash) && body["spine_storage"] == "postgres"
      end
    )
    check.call(
      "trace_retrieval", "#{API}/v1/cognition/#{request_id}/trace", auth: true,
      expect: lambda do |s, body|
        s == 200 && body.is_a?(Hash) && (body["state"] || {})["terminal"] == true
      end
    )
    stream_id = "release-stream-#{SecureRandom.hex(16)}"
    stream_payload = payload.merge("request_id" => stream_id)
    check.call(
      "streaming", "#{API}/v1/cognition/stream", method: "POST", body: stream_payload,
      auth: true, timeout: 120,
      expect: lambda do |s, body|
        s == 200 && body.is_a?(String) && body.include?("event: done") &&
          body.include?('"status":"completed"')
      end
    )
    failed_id = "release-failure-#{SecureRandom.hex(16)}"
    check.call(
      "provider_failure", "#{API}/v1/cognition", method: "POST",
      body: payload.merge(
        "request_id" => failed_id,
        "provider_id" => "release-provider-that-does-not-exist",
        "local_allowed" => false,
        "cloud_allowed" => false
      ),
      auth: true,
      expect: lambda do |s, body|
        s == 200 && body.is_a?(Hash) && %w[failed denied].include?(body["status"]) &&
          (body["status"] == "failed" || body["decision"] == "deny")
      end
    )
    cancel_id = "release-cancel-#{SecureRandom.hex(16)}"
    cancel_payload = payload.merge(
      "request_id" => cancel_id,
      "requested_max_tokens" => 2048,
      "local_allowed" => false,
      "cloud_allowed" => true,
      "messages" => [
        { "role" => "user", "content" => "Continue this bounded cancellation probe. " * 200 }
      ]
    )
    future = Thread.new do
      request("#{API}/v1/cognition", method: "POST", body: cancel_payload, auth: true, timeout: 120)
    end
    sleep(0.5)
    # A 409 means the request is not active (yet, or any more). Retry while it is still
    # running so a slow first byte over the network is not mistaken for a failed cancel.
    cancel_deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + 15
    cancel_status = nil
    cancel_body = nil
    loop do
      cancel_status, cancel_body = request(
        "#{API}/v1/cognition/#{cancel_id}/cancel", method: "POST", auth: true
      )
      break if (cancel_status == 200 && cancel_body.is_a?(Hash) && cancel_body["accepted"]) ||
               !future.alive? ||
               Process.clock_gettime(Process::CLOCK_MONOTONIC) > cancel_deadline

      sleep(0.25)
    end
    cancellation_passed = cancel_status == 200 && cancel_body.is_a?(Hash) &&
                          cancel_body["accepted"] == true
    results << {
      "check" => "cancellation_endpoint",
      "status" => cancel_status,
      "passed" => cancellation_passed,
      "observed" => cancel_body.is_a?(Hash) ? { "accepted" => cancel_body["accepted"] } : cancel_body
    }
    future.value
    timeout_id = "release-timeout-#{SecureRandom.hex(16)}"
    timeout_status, timeout_body = request(
      "#{API}/v1/cognition", method: "POST",
      body: payload.merge("request_id" => timeout_id, "requested_runtime_ms" => 1),
      auth: true, timeout: 60
    )
    trace_status, timeout_trace = request("#{API}/v1/cognition/#{timeout_id}/trace", auth: true)
    results << timeout_result(timeout_status, timeout_body, trace_status, timeout_trace)
    routing_status, routing_body = request("#{API}/v1/runtime/routing", auth: true)
    results << {
      "check" => "routing_status",
      "status" => routing_status,
      "passed" => routing_status == 200 && routing_body.is_a?(Hash) &&
                  %w[observe enforce].include?(routing_body["mode"]),
      "observed" => if routing_body.is_a?(Hash)
                      {
                        "mode" => routing_body["mode"],
                        "fallback_percent" => routing_body["fallback_percent"],
                        "fallback_max_attempts" => routing_body["fallback_max_attempts"],
                        "metrics_comparable_24h" => routing_body["metrics_comparable_24h"]
                      }
                    else
                      routing_body
                    end
    }
    results << failover_result(routing_status, routing_body)
    metrics_status, metrics_body = request("#{API}/v1/runtime/provider-metrics?limit=1", auth: true)
    results << metrics_window_result(metrics_status, metrics_body)
    web_status, web_build = request("#{WEB}/api/build")
    site_status, site_build = request("#{SITE}/api/build")
    results << sha_result(
      "served_sha_render_api",
      runtime_status.is_a?(Hash) ? runtime_status["build_sha"] : nil,
      EXPECTED_SHA
    )
    results << sha_result(
      "served_sha_render_web",
      web_build.is_a?(Hash) && web_status == 200 ? web_build["build_sha"] : nil,
      EXPECTED_SHA
    )
    results << sha_result(
      "served_sha_public_site",
      site_build.is_a?(Hash) && site_status == 200 ? site_build["build_sha"] : nil,
      EXPECTED_SITE_SHA,
      extra_ok: site_build.is_a?(Hash) && site_build["source_branch"] == "main"
    )
    check.call(
      "incident_recovery", "#{API}/v1/runtime/incidents?limit=5", auth: true,
      expect: ->(s, body) { s == 200 && body.is_a?(Hash) }
    )
    check.call(
      "database_persistence_trace", "#{API}/v1/cognition/#{request_id}/trace", auth: true,
      expect: lambda do |s, body|
        s == 200 && body.is_a?(Hash) && (body["state"] || {})["terminal"] == true
      end
    )
    results << {
      "check" => "authenticated_run_terminal",
      "passed" => status == 200 && run.is_a?(Hash) && %w[completed failed].include?(run["status"])
    }

    write_evidence(
      "evidence_id" => "live-release-#{SecureRandom.hex(16)}",
      "started_at" => started,
      "finished_at" => utc_now,
      "commit_sha" => COMMIT_SHA,
      "source" => "live_release_smoke",
      "status" => "completed",
      "decision" => results.any? { |item| item["passed"] == false } ? "HOLD" : "RELEASE",
      "api" => API,
      "site" => SITE,
      "request_ids" => [request_id, stream_id, failed_id, cancel_id, timeout_id],
      "expected_sha" => EXPECTED_SHA.empty? ? nil : EXPECTED_SHA,
      "expected_site_sha" => EXPECTED_SITE_SHA.empty? ? nil : EXPECTED_SITE_SHA,
      "results" => results
    )
    puts OUT
    unproven = results.select { |item| item["passed"].nil? }.map { |item| item["check"] }
    puts "Observed but not proven (not a pass): #{unproven.join(', ')}" unless unproven.empty?
    failed = results.select { |item| item["passed"] == false }.map { |item| item["check"] }
    unless failed.empty?
      puts "Live release smoke failed: #{failed.join(', ')}"
      return 1
    end
    0
  end
end

if $PROGRAM_NAME == __FILE__
  begin
    exit(LiveReleaseSmoke.main)
  rescue StandardError => error # convert collector failures into retained evidence
    LiveReleaseSmoke.write_evidence(
      "evidence_id" => "live-release-#{SecureRandom.hex(16)}",
      "started_at" => LiveReleaseSmoke.utc_now,
      "finished_at" => LiveReleaseSmoke.utc_now,
      "commit_sha" => LiveReleaseSmoke::COMMIT_SHA,
      "source" => "live_release_smoke",
      "status" => "operational_failure",
      "decision" => "HOLD",
      "missing_credentials" => [],
      "results" => [],
      "error" => "#{error.class.name}: #{error.message}"
    )
    warn "operational failure: #{error.class.name}: #{error.message}; evidence=#{LiveReleaseSmoke::OUT}"
    exit(2)
  end
end
