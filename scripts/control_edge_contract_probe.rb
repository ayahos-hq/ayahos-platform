#!/usr/bin/env ruby
# frozen_string_literal: true

# Read-only contract probe for the Ruby public gateway and the Python core behind it.
# It checks correlation propagation, health forwarding, authenticated Python routing,
# and safe status handling without invoking cognition or an action.

require "json"
require "net/http"
require "securerandom"
require "uri"

base_url = ENV.fetch("LIVE_CONTROL_URL", "").strip
runtime_key = ENV.fetch("LIVE_RUNTIME_API_KEY", "").strip
expected_sha = ENV.fetch("LIVE_EXPECTED_SHA", "").strip
abort("LIVE_CONTROL_URL is required") if base_url.empty?
abort("LIVE_RUNTIME_API_KEY is required") if runtime_key.empty?

def get_json(base_url, path, headers = {})
  uri = URI.join("#{base_url.chomp('/')}/", path.sub(%r{^/}, ""))
  request = Net::HTTP::Get.new(uri)
  headers.each { |name, value| request[name] = value }
  response = Net::HTTP.start(uri.host, uri.port, use_ssl: uri.scheme == "https", open_timeout: 10, read_timeout: 30) do |http|
    http.request(request)
  end
  [response, response.body.to_s.empty? ? {} : JSON.parse(response.body)]
end

correlation_id = "control-contract-#{SecureRandom.uuid}"
health, health_body = get_json(base_url, "/health", "X-Correlation-ID" => correlation_id)
abort("health status was #{health.code}") unless health.code.to_i == 200
abort("health correlation was not echoed") unless health["x-correlation-id"] == correlation_id
abort("unexpected gateway service") unless health_body["service"] == "ayahos-control-ruby"

status, status_body = get_json(base_url, "/v1/runtime/status", {
  "X-Dual-Lineage-Key" => runtime_key,
  "X-Correlation-ID" => correlation_id
})
abort("runtime status was #{status.code}: #{status_body["detail"] || status_body["error"]}") unless status.code.to_i == 200
served_sha = status_body["build_sha"] || status_body.dig("runtime", "build_sha")
abort("served SHA #{served_sha.inspect} did not match #{expected_sha}") unless expected_sha.empty? || served_sha == expected_sha

puts JSON.generate(
  status: "passed",
  gateway: health_body["service"],
  correlation_id: correlation_id,
  api_status: status.code.to_i,
  api_build_sha: served_sha
)
