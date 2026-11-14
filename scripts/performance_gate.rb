#!/usr/bin/env ruby
# frozen_string_literal: true

# Verify live Phase 5 latency evidence without changing routing.
# Ported from performance_gate.py; standard library only.

require "json"
require "net/http"
require "optparse"
require "uri"

def deep_sort(value)
  case value
  when Hash
    value.keys.sort_by(&:to_s).each_with_object({}) { |k, sorted| sorted[k] = deep_sort(value[k]) }
  when Array
    value.map { |item| deep_sort(item) }
  else
    value
  end
end

# Fixed timeouts, deliberately not retried: this gate measures live latency,
# so a retried request would falsify the evidence it reports.
OPEN_TIMEOUT = 20
READ_TIMEOUT = 20

def get_json(url, key, path)
  uri = URI("#{url.sub(%r{/+\z}, '')}#{path}")
  response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == "https",
                                                      open_timeout: OPEN_TIMEOUT, read_timeout: READ_TIMEOUT) do |http|
    request = Net::HTTP::Get.new(uri)
    request["Accept"] = "application/json"
    request["X-Dual-Lineage-Key"] = key
    http.request(request)
  end
  raise "performance gate: live request returned HTTP #{response.code}" unless response.is_a?(Net::HTTPSuccess)

  payload = JSON.parse(response.body.to_s)
  raise TypeError, "#{path} did not return an object" unless payload.is_a?(Hash)

  payload
rescue RuntimeError
  raise
end

def main(argv)
  options = {
    url: ENV.fetch("PROVIDER_METRICS_URL", ""),
    api_key_env: "LIVE_RUNTIME_API_KEY",
    target_ms: Float(ENV.fetch("DUAL_LINEAGE_WARM_P95_TARGET_MS", "15000"))
  }
  parser = OptionParser.new do |opts|
    opts.banner = "Usage: performance_gate.rb [options]"
    opts.on("--url URL") { |value| options[:url] = value }
    opts.on("--api-key-env ENV") { |value| options[:api_key_env] = value }
    opts.on("--target-ms MS", Float) { |value| options[:target_ms] = value }
  end
  begin
    parser.parse(argv)
  rescue OptionParser::ParseError => error
    warn error.message
    return 2
  end
  if options[:url].empty?
    warn "performance gate: --url or PROVIDER_METRICS_URL is required"
    return 2
  end
  key = ENV.fetch(options[:api_key_env], "").strip
  if key.empty?
    warn "performance gate: #{options[:api_key_env]} is not set"
    return 2
  end

  fetch_started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  failure_context = lambda do
    elapsed_ms = ((Process.clock_gettime(Process::CLOCK_MONOTONIC) - fetch_started) * 1000).round
    "(target #{options[:url]}, elapsed_ms=#{elapsed_ms}, " \
      "open_timeout=#{OPEN_TIMEOUT}s, read_timeout=#{READ_TIMEOUT}s)"
  end
  begin
    metrics = get_json(options[:url], key, "/v1/runtime/provider-metrics")
    runtime = get_json(options[:url], key, "/v1/runtime/status")
  rescue RuntimeError => error
    message = error.message.start_with?("performance gate:") ? error.message : "performance gate: live request failed: #{error.message}"
    warn "#{message} #{failure_context.call}"
    return 2
  rescue StandardError => error
    warn "performance gate: live request failed: #{error.message} #{failure_context.call}"
    return 2
  end

  summaries = metrics["summaries"] || []
  warm = summaries.select { |item| item.is_a?(Hash) && item["warm_request_count"].to_i.positive? }
  if warm.empty?
    warn "performance gate: no warm provider samples retained"
    return 1
  end
  slow = warm.select do |item|
    !item["p95_warm_latency_ms"].nil? && Float(item["p95_warm_latency_ms"]) > options[:target_ms]
  end
  phases = (metrics["performance"] || []).each_with_object([]) do |item, found|
    found << item["phase"] if item.is_a?(Hash) && item["sample_count"].to_i.positive?
  end.uniq
  required_phases = %w[provider_wait_ms retrieval_wait_ms model_generation_wait_ms]
  budgets = runtime["budgets"]
  runtime_budget = budgets.is_a?(Hash) ? budgets["max_runtime_ms"] : nil
  result = {
    "max_runtime_ms" => runtime_budget,
    "missing_phases" => (required_phases - phases).sort,
    "target_ms" => options[:target_ms],
    "warm_provider_summaries" => warm
  }
  puts JSON.generate(deep_sort(result))
  unless slow.empty?
    warn "performance gate: warm p95 exceeds target"
    return 1
  end
  unless (required_phases - phases).empty?
    warn "performance gate: required phase timings are missing"
    return 1
  end
  if !runtime_budget.is_a?(Numeric) || runtime_budget >= 90_000
    warn "performance gate: runtime budget is too close to the platform ceiling"
    return 1
  end
  puts "performance gate: warm p95, phase timings, and runtime ceiling verified"
  0
end

exit(main(ARGV)) if $PROGRAM_NAME == __FILE__
