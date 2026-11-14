#!/usr/bin/env ruby
# frozen_string_literal: true

# Publish a redacted live-release evidence artifact to the operator evidence surface.
# Ported from publish_release_evidence.py; standard library only.

require "json"
require "net/http"
require "uri"

def main
  output = ENV.fetch("LIVE_SMOKE_OUTPUT", "artifacts/live-smoke.json")
  api = ENV.fetch("LIVE_API_URL", "").strip.sub(%r{/+\z}, "")
  key = ENV.fetch("LIVE_RUNTIME_API_KEY", "").strip
  if api.empty? || key.empty?
    puts "HOLD: LIVE_API_URL and LIVE_RUNTIME_API_KEY are required to publish release evidence"
    return 0
  end
  unless File.file?(output)
    warn "operational failure: release evidence artifact is missing: #{output}"
    return 2
  end
  evidence = JSON.parse(File.read(output, encoding: "UTF-8"))
  uri = URI("#{api}/v1/runtime/release-evidence")
  begin
    response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == "https",
                                                       open_timeout: 30, read_timeout: 30) do |http|
      request = Net::HTTP::Post.new(uri)
      request["Accept"] = "application/json"
      request["Content-Type"] = "application/json"
      request["X-Dual-Lineage-Key"] = key
      request.body = JSON.generate(evidence)
      http.request(request)
    end
    unless response.is_a?(Net::HTTPSuccess)
      warn "operational failure: release evidence publication failed: HTTPError"
      return 2
    end
  rescue StandardError => error
    warn "operational failure: release evidence publication failed: #{error.class.name}"
    return 2
  end
  puts "published release evidence: #{output}"
  0
end

exit(main) if $PROGRAM_NAME == __FILE__
