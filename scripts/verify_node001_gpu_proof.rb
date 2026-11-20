#!/usr/bin/env ruby
# frozen_string_literal: true

# Live Milestone 3 proof for Physical Node 001.
#
# This is intentionally an operator-run verifier. It never starts or stops a node
# unless the operator supplies explicit hooks, and it writes a JSON artifact that
# contains no credentials.
#
# Ported from verify_node001_gpu_proof.py; standard library only.

require "json"
require "net/http"
require "open3"
require "optparse"
require "securerandom"
require "timeout"
require "uri"

PROBE_PROMPT = "Reply with exactly: NODE001_GPU_PROOF_OK"

class ProofError < RuntimeError; end

def utc_now
  Time.now.utc.strftime("%Y-%m-%dT%H:%M:%S.%6N+00:00")
end

def request_json(url, method: "GET", headers: nil, body: nil, timeout: 30.0, expected: nil)
  request_headers = { "Accept" => "application/json" }.merge(headers || {})
  payload = nil
  unless body.nil?
    payload = JSON.generate(body)
    request_headers["Content-Type"] = "application/json"
  end
  uri = URI(url)
  status = nil
  raw = nil
  begin
    response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == "https",
                                                       open_timeout: timeout, read_timeout: timeout) do |http|
      req = method == "POST" ? Net::HTTP::Post.new(uri) : Net::HTTP::Get.new(uri)
      request_headers.each { |name, value| req[name] = value }
      req.body = payload if payload
      http.request(req)
    end
    status = response.code.to_i
    raw = response.body.to_s
  rescue StandardError => error
    raise ProofError, "#{method} #{url}: #{error.message}"
  end
  value = if raw.nil? || raw.empty?
            {}
          else
            begin
              JSON.parse(raw)
            rescue JSON::ParserError
              { "raw" => raw }
            end
          end
  if !expected.nil? && !expected.include?(status)
    raise ProofError, "#{method} #{url}: HTTP #{status}: #{value}"
  end
  [status, value]
end

def require_env(name)
  value = ENV.fetch(name, "").strip
  raise ProofError, "required environment variable is missing: #{name}" if value.empty?

  value
end

def auth_header(value)
  { "Authorization" => "Bearer #{value}" }
end

def validate_node_endpoint(endpoint)
  parsed = URI.parse(endpoint)
  if !%w[http https].include?(parsed.scheme) || parsed.userinfo
    raise ProofError, "node endpoint must be an http(s) URL without userinfo"
  end
  host = (parsed.hostname || "").downcase
  raise ProofError, "node endpoint must include a host" if host.empty?

  loopback = %w[127.0.0.1 ::1 localhost].include?(host)
  if parsed.scheme != "https" && !loopback
    raise ProofError, "non-loopback node inference must use HTTPS"
  end
end

def run_hook(command, label)
  raise ProofError, "#{label} is required for the offline test" if command.empty?

  stdout, stderr, status = nil
  begin
    Timeout.timeout(120) do
      stdout, stderr, status = Open3.capture3(command)
    end
  rescue Timeout::Error
    raise ProofError, "#{label} timed out"
  end
  _ = stdout
  return if status.success?

  raise ProofError, "#{label} failed with #{status.exitstatus}: #{stderr.to_s[-1000..]}"
end

def wait_for_node(control_plane, node_id, operator_secret, timeout:)
  deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + timeout
  url = "#{control_plane.sub(%r{/+\z}, '')}/compute/nodes/#{URI.encode_www_form_component(node_id)}"
  last = nil
  while Process.clock_gettime(Process::CLOCK_MONOTONIC) < deadline
    begin
      status, value = request_json(url, headers: auth_header(operator_secret), expected: [200, 404])
      last = value
      return value if status == 200
    rescue ProofError => error
      last = error.message
    end
    sleep(2)
  end
  raise ProofError, "node #{node_id} did not register in time: #{last}"
end

def deep_sort(value)
  case value
  when Hash
    value.keys.sort_by(&:to_s).each_with_object({}) { |key, sorted| sorted[key] = deep_sort(value[key]) }
  when Array
    value.map { |item| deep_sort(item) }
  else
    value
  end
end

def main(argv)
  options = {
    node_id: "node-001", autonomic_model: "", registration_wait_seconds: 60.0,
    offline_command: "", restore_command: "", fallback_provider: ""
  }
  parser = OptionParser.new do |opts|
    opts.banner = "Usage: verify_node001_gpu_proof.rb [options]"
    opts.on("--control-plane URL") { |v| options[:control_plane] = v }
    opts.on("--runtime URL") { |v| options[:runtime] = v }
    opts.on("--node-endpoint URL") { |v| options[:node_endpoint] = v }
    opts.on("--node-id ID") { |v| options[:node_id] = v }
    opts.on("--cognitive-model MODEL") { |v| options[:cognitive_model] = v }
    opts.on("--autonomic-model MODEL", "Optional lightweight critic model advertised by node-001.") { |v| options[:autonomic_model] = v }
    opts.on("--commit-sha SHA") { |v| options[:commit_sha] = v }
    opts.on("--artifact PATH") { |v| options[:artifact] = v }
    opts.on("--registration-wait-seconds N", Float) { |v| options[:registration_wait_seconds] = v }
    opts.on("--offline-command CMD") { |v| options[:offline_command] = v }
    opts.on("--restore-command CMD") { |v| options[:restore_command] = v }
    opts.on("--fallback-provider ID", "Expected non-node provider_id after the node is taken offline.") { |v| options[:fallback_provider] = v }
  end
  begin
    parser.parse(argv)
  rescue OptionParser::ParseError => error
    warn error.message
    return 2
  end
  %i[control_plane runtime node_endpoint cognitive_model commit_sha artifact].each do |required|
    if options[required].nil? || options[required].to_s.empty?
      warn "verify_node001_gpu_proof.rb: missing required argument --#{required.to_s.tr('_', '-')}"
      return 2
    end
  end
  args = options

  registration_secret = require_env("DUAL_LINEAGE_NODE_OPERATOR_SECRET")
  runtime_key = require_env("DUAL_LINEAGE_RUNTIME_API_KEY")
  inference_secret = args[:autonomic_model].empty? ? "" : require_env("DUAL_LINEAGE_NODE_INFERENCE_SECRET")
  validate_node_endpoint(args[:node_endpoint])

  evidence = {
    "schema" => "physical-node-001-proof/v1",
    "started_at" => utc_now,
    "commit_sha" => args[:commit_sha],
    "node_id" => args[:node_id],
    "expected_cognitive_model" => args[:cognitive_model],
    "expected_autonomic_model" => args[:autonomic_model].empty? ? nil : args[:autonomic_model],
    "node_endpoint" => args[:node_endpoint],
    "checks" => {}
  }

  node = wait_for_node(args[:control_plane], args[:node_id], registration_secret,
                       timeout: args[:registration_wait_seconds])
  evidence["registration"] = node
  models = node["models"] || []
  matching = models.select { |item| item.is_a?(Hash) && item["id"] == args[:cognitive_model] && item["brain_role"] == "cognitive" }
  if node["status"] != "online" || matching.empty?
    raise ProofError, "registered node is not online with the expected model: #{node}"
  end
  unless args[:autonomic_model].empty?
    critic_matching = models.select { |item| item.is_a?(Hash) && item["id"] == args[:autonomic_model] && item["brain_role"] == "autonomic" }
    if critic_matching.empty?
      raise ProofError, "registered node does not advertise critic model #{args[:autonomic_model]}: #{node}"
    end
  end
  unless node["gpu"].to_s.include?("RTX 3060")
    raise ProofError, "registered node does not advertise RTX 3060: #{node['gpu']}"
  end
  unless %w[llama.cpp llama-swap].include?(node["backend"].to_s.downcase)
    raise ProofError, "registered backend is not llama.cpp-compatible: #{node['backend']}"
  end
  evidence["checks"]["secure_registration"] = true
  evidence["checks"]["independent_critic_advertised"] = !args[:autonomic_model].empty?

  unauth_status, _unauth = request_json(
    "#{args[:node_endpoint].sub(%r{/+\z}, '')}/inference",
    method: "POST",
    body: {
      "job_id" => "unauthenticated-proof-check",
      "brain_role" => "cognitive",
      "model" => args[:cognitive_model],
      "prompt" => PROBE_PROMPT
    },
    expected: [401, 403, 503]
  )
  evidence["checks"]["unauthenticated_inference_rejected"] = [401, 403, 503].include?(unauth_status)

  if !args[:autonomic_model].empty?
    critic_status, critic_response = request_json(
      "#{args[:node_endpoint].sub(%r{/+\z}, '')}/inference",
      method: "POST",
      headers: auth_header(inference_secret),
      body: {
        "job_id" => "critic-proof-#{SecureRandom.hex(16)}",
        "brain_role" => "autonomic",
        "model" => args[:autonomic_model],
        "prompt" => "Return a one-word risk assessment for: read-only status check",
        "options" => { "max_tokens" => 8, "temperature" => 0.0 }
      },
      timeout: 120,
      expected: [200]
    )
    evidence["critic_probe"] = {
      "http_status" => critic_status,
      "model" => args[:autonomic_model],
      "response" => critic_response
    }
    if critic_response["model"] != args[:autonomic_model]
      raise ProofError, "unexpected critic model: #{critic_response}"
    end
    evidence["checks"]["independent_critic_inference"] = true
  else
    evidence["checks"]["independent_critic_inference"] = false
  end

  request_id = "milestone-3-node001-#{SecureRandom.hex(16)}"
  started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  status, response = request_json(
    "#{args[:runtime].sub(%r{/+\z}, '')}/v1/cognition",
    method: "POST",
    headers: { "X-Dual-Lineage-Key" => runtime_key },
    body: {
      "request_id" => request_id,
      "messages" => [{ "role" => "user", "content" => PROBE_PROMPT }],
      "model" => args[:cognitive_model],
      "temperature" => 0.0,
      "requested_max_tokens" => 16,
      "requested_runtime_ms" => 90_000,
      "local_allowed" => true,
      "cloud_allowed" => false,
      "workload_class" => "heavy",
      "learning_consent" => false
    },
    timeout: 120,
    expected: [200]
  )
  elapsed_ms = ((Process.clock_gettime(Process::CLOCK_MONOTONIC) - started) * 1000).round(2)
  evidence["routed_request"] = {
    "request_id" => request_id,
    "http_status" => status,
    "client_latency_ms" => elapsed_ms,
    "response" => response
  }
  trace_status, trace = request_json(
    "#{args[:runtime].sub(%r{/+\z}, '')}/v1/cognition/#{URI.encode_www_form_component(request_id)}/trace",
    headers: { "X-Dual-Lineage-Key" => runtime_key },
    expected: [200]
  )
  evidence["routed_trace"] = { "http_status" => trace_status, "trace" => trace }
  if response["status"] != "completed" || response["node_id"] != args[:node_id]
    raise ProofError, "cognition was not routed through #{args[:node_id]}: #{response}"
  end
  raise ProofError, "unexpected routed model: #{response['model']}" if response["model"] != args[:cognitive_model]

  usage = response["usage"]
  tokens = usage.is_a?(Hash) ? usage["tokens"] : nil
  raise ProofError, "routed response has no token usage: #{response}" unless tokens && tokens != 0

  evidence["checks"]["routed_gpu_cognition"] = true

  if !args[:offline_command].empty?
    run_hook(args[:offline_command], "offline command")
    begin
      offline_id = "milestone-3-node001-offline-#{SecureRandom.hex(16)}"
      offline_status, offline_response = request_json(
        "#{args[:runtime].sub(%r{/+\z}, '')}/v1/cognition",
        method: "POST",
        headers: { "X-Dual-Lineage-Key" => runtime_key },
        body: {
          "request_id" => offline_id,
          "messages" => [{ "role" => "user", "content" => PROBE_PROMPT }],
          "model" => args[:cognitive_model],
          "temperature" => 0.0,
          "requested_max_tokens" => 16,
          "requested_runtime_ms" => 90_000,
          "local_allowed" => true,
          "cloud_allowed" => true,
          "workload_class" => "heavy",
          "learning_consent" => false
        },
        timeout: 120,
        expected: [200]
      )
      evidence["offline_test"] = {
        "request_id" => offline_id,
        "http_status" => offline_status,
        "response" => offline_response
      }
      raise ProofError, "offline request still used node-001" if offline_response["node_id"] == args[:node_id]

      if !args[:fallback_provider].empty? && offline_response["provider_id"] != args[:fallback_provider]
        raise ProofError, "unexpected fallback provider: #{offline_response['provider_id']}"
      end
      evidence["checks"]["controlled_offline_fallback"] = true
    ensure
      run_hook(args[:restore_command], "restore command") unless args[:restore_command].empty?
    end
  else
    evidence["checks"]["controlled_offline_fallback"] = false
    evidence["offline_test"] = {
      "status" => "not_run",
      "reason" => "--offline-command not supplied"
    }
  end

  evidence["checks"]["all_repository_exit_criteria_observed"] = evidence["checks"].values.all?
  evidence["finished_at"] = utc_now
  artifact = args[:artifact]
  require "fileutils"
  FileUtils.mkdir_p(File.dirname(artifact))
  File.write(artifact, "#{JSON.pretty_generate(deep_sort(evidence))}\n", encoding: "UTF-8")
  puts JSON.pretty_generate(deep_sort(evidence))
  evidence["checks"]["all_repository_exit_criteria_observed"] ? 0 : 2
end

if $PROGRAM_NAME == __FILE__
  begin
    exit(main(ARGV))
  rescue ProofError => error
    warn "milestone-3 proof failed: #{error.message}"
    exit(1)
  end
end
