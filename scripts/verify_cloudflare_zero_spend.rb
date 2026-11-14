#!/usr/bin/env ruby
# frozen_string_literal: true

# Read-only Cloudflare HTTP plumbing. Python remains the rule authority.
# No inference calls, mutations, token printing, retries or paid provider use.

require "json"
require "net/http"
require "open3"
require "uri"

ACCOUNT_PATTERN = /\A[0-9a-f]{32}\z/
BASE_URL = "https://api.cloudflare.com/client/v4"

def get_cloudflare(account_id, token, resource)
  uri = URI("#{BASE_URL}/accounts/#{account_id}/ai-gateway/#{resource}")
  req = Net::HTTP::Get.new(uri)
  req["Authorization"] = "Bearer #{token}"
  req["Accept"] = "application/json"
  response = Net::HTTP.start(
    uri.hostname, uri.port, use_ssl: true, open_timeout: 10, read_timeout: 12
  ) { |http| http.request(req) }
  raise "Cloudflare read failed" unless response.is_a?(Net::HTTPSuccess)
  raise "Cloudflare response too large" if response.body.to_s.bytesize > 262_144

  data = JSON.parse(response.body)
  raise "Cloudflare verification rejected" unless data.is_a?(Hash) && data["success"] == true

  data["result"]
end

def main
  account_id = ENV.fetch("CLOUDFLARE_ACCOUNT_ID", "").strip.downcase
  token = ENV.fetch("CLOUDFLARE_API_TOKEN", "")
  unless ACCOUNT_PATTERN.match?(account_id) && !token.strip.empty?
    warn "Missing scoped Cloudflare credentials; read-only verification unavailable."
    return 2
  end

  snapshot = {
    "gateway" => get_cloudflare(account_id, token, "gateways/ayahos-undermind"),
    "providers" => get_cloudflare(account_id, token, "custom-providers"),
    "topup" => get_cloudflare(account_id, token, "billing/topup/config")
  }
  python_rule = File.expand_path("verify_cloudflare_zero_spend.py", __dir__)
  stdout, stderr, status = Open3.capture3(
    "python3", python_rule, stdin_data: JSON.generate(snapshot)
  )
  puts stdout unless stdout.empty?
  warn stderr unless stderr.empty?
  status.exitstatus || 2
rescue JSON::ParserError, OpenSSL::SSL::SSLError, IOError, SystemCallError,
       Net::HTTPError, RuntimeError => e
  # Never echo remote response bodies, credentials, or raw exception details.
  warn "Cloudflare read-only verification unavailable; fail closed."
  2
end

exit(main) if $PROGRAM_NAME == __FILE__
