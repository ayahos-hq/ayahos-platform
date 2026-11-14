#!/usr/bin/env ruby
# frozen_string_literal: true

# Exercise the deployed PostgreSQL-backed rate-limit boundaries.
# Ported from live_rate_limit_smoke.py; standard library only.

require "fileutils"
require "json"
require "net/http"
require "securerandom"
require "uri"

API = ENV.fetch("LIVE_API_URL", "https://goblin-dual-lineage-api.onrender.com").sub(%r{/+\z}, "")
RUNTIME_KEY = ENV.fetch("LIVE_RUNTIME_API_KEY", "").strip
SITE_KEY = ENV.fetch("LIVE_SITE_API_KEY", "").strip
OUTPUT = ENV.fetch("LIVE_RATE_LIMIT_OUTPUT", "artifacts/live-rate-limit.json")

# Timeouts default to the historical 30s/30s; SMOKE_* overrides exist for
# tightly bounded local runs only. There are deliberately no retries in this
# script: a retried request would corrupt the rate-limit counts it measures.
def timeout_env(name)
  value = Integer(ENV.fetch(name, "30"), exception: false)
  value&.positive? ? value : 30
end

OPEN_TIMEOUT = timeout_env("SMOKE_OPEN_TIMEOUT")
READ_TIMEOUT = timeout_env("SMOKE_READ_TIMEOUT")

def json_or_text(raw)
  JSON.parse(raw)
rescue JSON::ParserError
  raw
end

# Returns [status, headers (downcased keys), body]
def request(url, headers:, body: nil)
  uri = URI(url)
  response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == "https",
                                                      open_timeout: OPEN_TIMEOUT, read_timeout: READ_TIMEOUT) do |http|
    req = body ? Net::HTTP::Post.new(uri) : Net::HTTP::Get.new(uri)
    headers.each { |name, value| req[name] = value }
    req.body = body if body
    http.request(req)
  end
  downcased = {}
  response.each_header { |name, value| downcased[name.downcase] = value }
  [response.code.to_i, downcased, json_or_text(response.body.to_s)]
end

# Returns [results, errors]; per-request errors are captured (not raised out
# of the worker threads) so a transport failure can be reported with context
# instead of a raw stack trace.
def run_parallel(count)
  results = Array.new(count)
  errors = Array.new(count)
  threads = count.times.map do |index|
    Thread.new do
      begin
        results[index] = yield(index)
      rescue StandardError => error
        errors[index] = error
      end
    end
  end
  threads.each(&:join)
  [results, errors]
end

def phase_failure(phase, target, error, started)
  elapsed = ((Process.clock_gettime(Process::CLOCK_MONOTONIC) - started) * 1000).round
  warn "live rate-limit smoke: #{phase} phase failed: #{error.class}: #{error.message} " \
       "(target #{target}, after #{elapsed}ms)"
  1
end

def main
  if RUNTIME_KEY.empty? || SITE_KEY.empty?
    warn "LIVE_RUNTIME_API_KEY and LIVE_SITE_API_KEY are required"
    return 2
  end

  forwarded_probe = "live-rate-limit-forwarded"
  runtime_target = "#{API}/v1/runtime/status?probe=#{forwarded_probe}"
  phase_started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  runtime_results, runtime_errors = run_parallel(40) do |index|
    request(
      runtime_target,
      headers: {
        "Accept" => "application/json",
        "X-Dual-Lineage-Key" => RUNTIME_KEY,
        "X-Forwarded-For" => "203.0.113.#{(index % 200) + 1}"
      }
    )
  end
  if (error = runtime_errors.compact.first)
    return phase_failure("runtime", runtime_target, error, phase_started)
  end

  runtime_statuses = runtime_results.map(&:first)
  runtime_passed = (runtime_statuses.uniq - [200, 429]).empty? &&
                   runtime_statuses.include?(200) &&
                   runtime_statuses.include?(429) &&
                   runtime_results.any? { |_status, headers, _body| headers.key?("ratelimit-limit") }

  principal = "live-rate-limit-public-#{SecureRandom.hex(16)}"
  payload = JSON.generate("principal" => principal)
  public_target = "#{API}/v1/rate-limit/public"
  phase_started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  public_results, public_errors = run_parallel(15) do |_index|
    request(
      public_target,
      headers: {
        "Accept" => "application/json",
        "Content-Type" => "application/json",
        "X-Dual-Lineage-Key" => SITE_KEY
      },
      body: payload
    )
  end
  if (error = public_errors.compact.first)
    return phase_failure("public", public_target, error, phase_started)
  end

  public_statuses = public_results.map(&:first)
  public_passed = (public_statuses.uniq - [200, 429]).empty? &&
                  public_statuses.count(200) == 10 &&
                  public_statuses.count(429) == 5 &&
                  public_results.all? { |status, headers, _body| status != 429 || headers.key?("ratelimit-limit") }

  evidence = {
    "api" => API,
    "runtime_provider_cost" => {
      "passed" => runtime_passed,
      "status_counts" => runtime_statuses.tally.sort.to_h.transform_keys(&:to_s),
      "forwarded_ip_headers_varied" => true,
      "generic_forwarded_ip_trusted" => false
    },
    "public_postgres_bucket" => {
      "passed" => public_passed,
      "status_counts" => public_statuses.tally.sort.to_h.transform_keys(&:to_s),
      "principal_reused" => true
    },
    "passed" => runtime_passed && public_passed
  }
  FileUtils.mkdir_p(File.dirname(OUTPUT))
  File.write(OUTPUT, "#{JSON.pretty_generate(evidence)}\n", encoding: "UTF-8")
  puts JSON.generate(evidence)
  evidence["passed"] ? 0 : 1
end

exit(main) if $PROGRAM_NAME == __FILE__
