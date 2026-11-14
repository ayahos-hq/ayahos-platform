#!/usr/bin/env ruby
# frozen_string_literal: true

# Minimal production smoke test for the public AyahOS chat proxy.
#
# This check intentionally uses the public surface only. It verifies the full
# Cloudflare Pages -> Render rate-limit -> cognition path without requiring a runtime key
# or exposing any server-side credential.
#
# Ported from public_chat_smoke.py; standard library only.

require "fileutils"
require "json"
require "net/http"
require "uri"
require_relative "smoke_support"

SITE = ENV.fetch("LIVE_PUBLIC_SITE_URL", "https://ayahos.pages.dev").sub(%r{/+\z}, "")
OUTPUT = ENV.fetch("PUBLIC_CHAT_SMOKE_OUTPUT", "artifacts/public-chat-smoke.json")
# Cloudflare rejects the HTTP library's default user agent on the public site.
USER_AGENT = "AyahOS-live-smoke/1"

def main
  payload = JSON.generate(
    "messages" => [
      {
        "role" => "user",
        "content" => "What happened to the supermodel after CoolSculpting caused disfigurement?"
      }
    ]
  )
  uri = URI("#{SITE}/api/chat")
  status = 0
  body = ""
  attempts = 0
  duration_ms = 0
  begin
    # A duplicate smoke chat is acceptable, so transient transport failures
    # and 502/503/504 responses are retried (see smoke_support.rb).
    result = SmokeSupport.fetch(retry_statuses: true) do
      Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == "https",
                                               open_timeout: 30, read_timeout: 120) do |http|
        request = Net::HTTP::Post.new(uri)
        request["Accept"] = "application/json"
        request["Content-Type"] = "application/json"
        request["User-Agent"] = USER_AGENT
        request.body = payload
        http.request(request)
      end
    end
    attempts = result.attempts
    duration_ms = result.elapsed_ms
    response = result.response
    status = response.code.to_i
    raw = response.body.to_s
    begin
      body = JSON.parse(raw)
    rescue JSON::ParserError
      body = raw
    end
  rescue StandardError => error # live-only failure path
    body = { "error" => error.message }
    if error.is_a?(SmokeSupport::Failure)
      attempts = error.attempts
      duration_ms = error.elapsed_ms
    end
  end

  passed = status == 200 &&
           body.is_a?(Hash) &&
           body["status"] == "completed" &&
           SmokeSupport.public_provider_ok?(body["provider"]) &&
           body["code"] != "PUBLIC_RATE_LIMIT_UNAVAILABLE"
  evidence = {
    "site" => SITE,
    "status" => status,
    "passed" => passed,
    "attempts" => attempts,
    "duration_ms" => duration_ms,
    "observed" => body.is_a?(Hash) ? body.reject { |key, _| %w[text error].include?(key) } : body
  }
  FileUtils.mkdir_p(File.dirname(OUTPUT))
  File.write(OUTPUT, "#{JSON.pretty_generate(evidence)}\n", encoding: "UTF-8")
  puts JSON.generate(evidence)
  passed ? 0 : 1
end

exit(main) if $PROGRAM_NAME == __FILE__
