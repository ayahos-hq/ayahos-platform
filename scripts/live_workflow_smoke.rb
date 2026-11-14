#!/usr/bin/env ruby
# frozen_string_literal: true

# Authenticated Ruby queue -> Python workflow-inbox smoke.  It intentionally
# submits only an audit-only provider-failure envelope and never performs an action.
#
# With LIVE_WORKFLOW_DATABASE_URL set to the deployment's database, the job goes through the
# shared PostgreSQL queue instead of a temporary JSON file, the worker claims only this job (a
# deployed worker's jobs are never taken), and the smoke then reads the inbox receipt Python
# stored in that same database.
#
# With LIVE_EXPECTED_SHA set, the API must report that build in authenticated health before the
# job is queued, so a pass is tied to the revision it ran against.

require "json"
require "rbconfig"
require "tmpdir"
require "securerandom"

ROOT = File.expand_path("..", __dir__)
$LOAD_PATH.unshift(File.join(ROOT, "apps", "ruby_worker", "lib"))

require "goblin_workflow/api_client"
require "goblin_workflow/http_client"
require "goblin_workflow/job"
require "goblin_workflow/queue"
require "goblin_workflow/runner"
require "goblin_workflow/worker"

api_url = ENV.fetch("LIVE_API_URL", "").strip
runtime_key = ENV.fetch("LIVE_RUNTIME_API_KEY", "").strip
database_url = ENV.fetch("LIVE_WORKFLOW_DATABASE_URL", "").strip
expected_sha = ENV.fetch("LIVE_EXPECTED_SHA", "").strip
abort("LIVE_API_URL is required for authenticated workflow smoke") if api_url.empty?
abort("LIVE_RUNTIME_API_KEY is required for authenticated workflow smoke") if runtime_key.empty?

def inbox_receipt(database_url, message_id)
  require "pg"
  connection = PG.connect(database_url)
  connection.exec_params(
    "SELECT message_type, status, result FROM dual_lineage_workflow_inbox_messages WHERE message_id = $1",
    [message_id]
  ).first
ensure
  connection&.close
end

# Health shares the provider-cost rate-limit bucket that the rate-limit smoke fills on purpose, so
# a 429 is waited out (bounded) rather than reported as a failed delivery.
def served_sha(client)
  waits = 0
  begin
    client.runtime_health["build_sha"]
  rescue GoblinWorkflow::HttpError => error
    raise unless error.status == 429 && (waits += 1) <= 3

    sleep(Integer(error.headers["retry-after"].to_s, exception: false).to_i.clamp(1, 65))
    retry
  end
end

request_id = "ruby-workflow-smoke-#{SecureRandom.uuid}"
job_id = "ruby-workflow-smoke:#{SecureRandom.uuid}"
Dir.mktmpdir("ruby-workflow-smoke-") do |directory|
  queue = if database_url.empty?
    GoblinWorkflow::QueueStore.new(path: File.join(directory, "queue.json"))
  else
    require "goblin_workflow/postgres_queue"
    GoblinWorkflow::PostgresQueueStore.new(database_url: database_url)
  end
  client = GoblinWorkflow::ApiV1::Client.new(
    http: GoblinWorkflow::HttpClient.new(base_url: api_url), runtime_key: runtime_key
  )
  api_build_sha = expected_sha.empty? ? nil : served_sha(client)
  unless expected_sha.empty? || api_build_sha == expected_sha
    raise "the API serves #{api_build_sha.inspect}, not LIVE_EXPECTED_SHA #{expected_sha}"
  end
  runner = GoblinWorkflow::Runner.new(root: ROOT, python: RbConfig.ruby, api_client: client)
  # One attempt: a failed probe dead-letters (visible to operators) rather than leaving a retry
  # scheduled on a shared queue for some other worker to pick up.
  queue.enqueue(GoblinWorkflow::Job.new(
    id: job_id,
    type: "provider_failure",
    arguments: { "request_id" => request_id, "provider_id" => "workflow-smoke", "error_type" => "SmokeProbe" }
  ), max_attempts: 1)
  processed = GoblinWorkflow::Worker.new(queue: queue, runner: runner, worker_id: "live-smoke")
    .work(once: true, job_id: job_id)
  settled = queue.get(job_id)
  unless processed == 1 && settled["status"] == "succeeded" && settled.dig("result", "status") == "accepted"
    raise "authenticated workflow did not settle: #{settled.slice("status", "error", "result").to_json}"
  end

  evidence = {
    "status" => "passed", "request_id" => request_id, "job_id" => job_id,
    "workflow_id" => settled.dig("arguments", "observability", "workflow_id"),
    "spine_event_id" => settled.dig("arguments", "observability", "spine_event_id"),
    "queue" => database_url.empty? ? "json" : "postgres"
  }
  evidence["api_build_sha"] = api_build_sha if api_build_sha
  unless database_url.empty?
    receipt = inbox_receipt(database_url, job_id)
    unless receipt && receipt["message_type"] == "provider_failure" && receipt["status"] == "completed"
      raise "Python accepted the delivery but its receipt is not in LIVE_WORKFLOW_DATABASE_URL: #{receipt.to_json}"
    end
    stored = JSON.parse(receipt.fetch("result"))
    unless stored.dig("observability", "spine_event_id") == evidence["spine_event_id"]
      raise "the stored inbox receipt does not carry this delivery's spine_event_id"
    end
    evidence["inbox_receipt"] = "postgres"
  end
  puts JSON.generate(evidence)
end
