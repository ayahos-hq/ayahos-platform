#!/usr/bin/env ruby
# frozen_string_literal: true

# Authenticated live check of Overmind retrieval: the Ruby RAG sidecar behind the API, document
# embeddings, and the pgvector index. It ingests one probe document, finds it, deletes it, and
# checks that it is gone. Python owns every rule; this script only calls the API and reports.
#
# The probe is temporary data in the live Overmind corpus. Its content is one random token, so no
# real query scores it lexically; its vector is a random token's, so a real query embedded for
# cognition can still rank it weakly during the few seconds it exists. It is deleted even when a
# check fails, and the run fails if the delete does not succeed.
#
# The smoke also runs grounded cognition with cloud permission enabled. That exercises the remote
# DashScope query-embedding path (when configured), and its trace records vector versus lexical
# retrieval mode. Each networked stage records latency so a slow embedding or sidecar fallback is
# visible in the retained evidence.
#
# Required: LIVE_API_URL, LIVE_RUNTIME_API_KEY. Optional: LIVE_EXPECTED_SHA (the API must serve
# it), LIVE_RAG_REQUIRE_EMBEDDINGS, LIVE_RAG_REQUIRE_PGVECTOR, and LIVE_RAG_REQUIRE_POSTGRES
# ("1" by default; "0" records the state without requiring it), LIVE_RAG_SMOKE_OUTPUT (where to
# write the JSON evidence).
# Standard library only.

require "fileutils"
require "json"
require "net/http"
require "securerandom"
require "time"
require "uri"

# Runtime status shares the provider-cost rate-limit bucket that the rate-limit smoke fills on
# purpose, so a 429 is waited out (Retry-After, bounded) rather than reported as a failure.
class LiveApi
  RATE_LIMIT_WAITS = 3
  MAX_WAIT_SECONDS = 65

  def initialize(base_url, runtime_key)
    @base_url = base_url.chomp("/")
    @runtime_key = runtime_key
  end

  def call(method, path, body: nil, query: nil)
    uri = URI("#{@base_url}#{path}")
    uri.query = URI.encode_www_form(query) if query
    waits = 0
    loop do
      response = Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == "https",
                                                         open_timeout: 10, read_timeout: 90) do |http|
        http.request(build(method, uri, body))
      end
      if response.code == "429" && waits < RATE_LIMIT_WAITS
        waits += 1
        sleep(retry_after(response))
        next
      end
      return [response.code.to_i, parse(response.body)]
    end
  end

  private

  def build(method, uri, body)
    request = { get: Net::HTTP::Get, post: Net::HTTP::Post, delete: Net::HTTP::Delete }.fetch(method).new(uri)
    request["Accept"] = "application/json"
    request["X-Dual-Lineage-Key"] = @runtime_key
    if body
      request["Content-Type"] = "application/json"
      request.body = JSON.generate(body)
    end
    request
  end

  def retry_after(response)
    Integer(response["Retry-After"].to_s, exception: false).to_i.clamp(1, MAX_WAIT_SECONDS)
  end

  def parse(raw)
    raw.to_s.empty? ? {} : JSON.parse(raw)
  rescue JSON::ParserError
    { "raw" => raw.to_s[0, 500] }
  end
end

class LiveRagSmoke
  def initialize(api:, expected_sha:, require_embeddings:, require_pgvector:, require_postgres:)
    @api = api
    @expected_sha = expected_sha
    @require_embeddings = require_embeddings
    @require_pgvector = require_pgvector
    @require_postgres = require_postgres
    @checks = []
  end

  def run
    started_at = Time.now.utc.iso8601
    probe = nil
    begin
      runtime = runtime_status
      stats = rag_stats
      probe = ingest_probe(runtime, stats) if runtime && stats
      verify_retrieval(probe) if probe
    rescue StandardError => error
      record("error", false, { "error_type" => error.class.name, "message" => error.message[0, 300] })
    ensure
      begin
        remove(probe) if probe
      rescue StandardError => error
        record("delete", false, { "error_type" => error.class.name })
        warn JSON.generate(event: "live_rag_smoke.probe_left_behind", source: probe["source"],
                           document_id: probe["document_id"])
      end
    end
    {
      "status" => @checks.all? { |check| check["passed"] } ? "passed" : "failed",
      "started_at" => started_at, "finished_at" => Time.now.utc.iso8601,
      "required" => { "embeddings" => @require_embeddings, "pgvector" => @require_pgvector,
                       "postgres" => @require_postgres },
      "checks" => @checks
    }
  end

  private

  def record(name, passed, observed = {})
    @checks << { "check" => name, "passed" => passed ? true : false, "observed" => observed }
    passed
  end

  def timed
    started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    result = yield
    [result, ((Process.clock_gettime(Process::CLOCK_MONOTONIC) - started) * 1000).round(1)]
  end

  def runtime_status
    status, body = @api.call(:get, "/v1/runtime/status")
    return nil unless record("runtime_status", status == 200, { "status" => status })

    sha = body["build_sha"]
    unless @expected_sha.empty?
      record("served_sha", sha == @expected_sha, { "build_sha" => sha, "expected" => @expected_sha })
    end
    record("rag_enabled", body["rag_enabled"] == true, { "rag_enabled" => body["rag_enabled"] })
    embedder = body["rag_embedding_backend"]
    record("embedder_configured", embedder || !@require_embeddings, { "rag_embedding_backend" => embedder })
    body["rag_enabled"] == true ? body : nil
  end

  def rag_stats
    (response, duration_ms) = timed { @api.call(:get, "/v1/rag/stats") }
    status, body = response
    observed = { "status" => status, "pgvector" => body["pgvector"],
                 "database" => body["database"], "database_source" => body["database_source"],
                 "duration_ms" => duration_ms }
    return nil unless record("rag_stats", status == 200, observed)

    postgres = body["database"] == "postgres"
    source = %w[explicit_rag_url shared_database_url].include?(body["database_source"])
    record("postgres_database", (postgres && source) || !@require_postgres,
           observed.merge("required" => @require_postgres))
    record("pgvector_enabled", body["pgvector"] == true || !@require_pgvector, observed)
    body
  end

  def ingest_probe(runtime, stats)
    token = "rgprobe#{SecureRandom.hex(12)}"
    source = "live-rag-smoke/#{token}"
    (response, duration_ms) = timed do
      @api.call(:post, "/v1/rag/documents", body: {
      "source" => source, "title" => "live-rag-smoke #{token}", "content" => token,
      "metadata" => { "probe" => "live-rag-smoke" }
      })
    end
    status, body = response
    counts = body.slice("chunks", "embedded_chunks", "indexed_chunks")
    # 503 here means the embedding endpoint refused the document; nothing was stored.
    return nil unless record("ingest", status == 200 && body["document_id"],
                             { "status" => status, "duration_ms" => duration_ms, **counts })

    probe = { "document_id" => body["document_id"], "source" => source, "token" => token }
    chunks = body["chunks"].to_i
    embedded = runtime["rag_embedding_backend"] ? body["embedded_chunks"] == chunks && chunks.positive? : nil
    record("document_embedded", embedded || (embedded.nil? && !@require_embeddings), counts)
    indexed = stats["pgvector"] == true ? body["indexed_chunks"] == chunks && chunks.positive? : nil
    record("document_indexed", indexed || (indexed.nil? && !@require_pgvector), counts)
    probe
  end

  def verify_retrieval(probe)
    (response, duration_ms) = timed { search(probe) }
    status, body = response
    sources = Array(body["citations"]).map { |citation| citation["source"] }
    record("retrieval", status == 200 && sources.include?(probe["source"]),
           { "status" => status, "found" => sources.include?(probe["source"]),
             "query_embedded" => body["query_embedded"], "duration_ms" => duration_ms })
    grounded_cognition(probe)
  end

  def grounded_cognition(probe)
    request_id = "live-rag-cognition-#{SecureRandom.hex(10)}"
    (response, duration_ms) = timed do
      @api.call(:post, "/v1/cognition", body: {
        "request_id" => request_id,
        "messages" => [{ "role" => "user", "content" => "What does #{probe['token']} establish?" }],
        "local_allowed" => false, "cloud_allowed" => true, "rag_enabled" => true
      })
    end
    status, body = response
    citations = Array(body["citations"])
    cited = citations.any? { |citation| citation["source"] == probe["source"] }
    completed = body["status"] == "completed"
    record("grounded_cognition", status == 200 && completed && cited,
           { "status" => status, "run_status" => body["status"], "cited" => cited,
             "citation_sources" => citations.map { |citation| citation["source"] },
             "duration_ms" => duration_ms, "request_id" => request_id })

    (trace_response, trace_duration_ms) = timed do
      @api.call(:get, "/v1/cognition/#{URI.encode_www_form_component(request_id)}/trace")
    end
    trace_status, trace = trace_response
    retrieval = Array(trace["events"]).find { |event| event["kind"] == "retrieval_performed" }
    labels = retrieval && retrieval["labels"]
    mode = labels && labels["retrieval_mode"]
    vector_required = @require_embeddings
    trace_passed = trace_status == 200 && retrieval && labels.is_a?(Hash) &&
                   (!vector_required || mode == "vector")
    record("grounded_trace", trace_passed,
           { "status" => trace_status, "retrieval_mode" => mode,
             "vector_required" => vector_required, "citation_count" => labels && labels["citation_count"],
             "duration_ms" => trace_duration_ms })
  end

  def remove(probe)
    status, body = @api.call(:delete, "/v1/rag/documents/#{URI.encode_www_form_component(probe['document_id'])}")
    deleted = record("delete", status == 200 && body["deleted"] == true, { "status" => status })
    unless deleted
      warn JSON.generate(event: "live_rag_smoke.probe_left_behind", source: probe["source"],
                         document_id: probe["document_id"])
      return
    end
    status, body = search(probe)
    sources = Array(body["citations"]).map { |citation| citation["source"] }
    record("deleted_not_retrievable", status == 200 && !sources.include?(probe["source"]), { "status" => status })
  end

  def search(probe)
    @api.call(:post, "/v1/rag/search", query: { "query" => probe["token"], "top_k" => 4 })
  end
end

if $PROGRAM_NAME == __FILE__
  api_url = ENV.fetch("LIVE_API_URL", "").strip
  runtime_key = ENV.fetch("LIVE_RUNTIME_API_KEY", "").strip
  missing = []
  missing << "LIVE_API_URL" if api_url.empty?
  missing << "LIVE_RUNTIME_API_KEY" if runtime_key.empty?
  abort("missing required live RAG environment: #{missing.join(', ')}") unless missing.empty?
  parsed_url = URI.parse(api_url)
  unless %w[http https].include?(parsed_url.scheme) && parsed_url.host
    abort("LIVE_API_URL must be an http(s) URL")
  end

  evidence = LiveRagSmoke.new(
    api: LiveApi.new(api_url, runtime_key),
    expected_sha: ENV.fetch("LIVE_EXPECTED_SHA", "").strip,
    require_embeddings: ENV.fetch("LIVE_RAG_REQUIRE_EMBEDDINGS", "1") != "0",
    require_pgvector: ENV.fetch("LIVE_RAG_REQUIRE_PGVECTOR", "1") != "0",
    require_postgres: ENV.fetch("LIVE_RAG_REQUIRE_POSTGRES", "1") != "0"
  ).run
  output = ENV.fetch("LIVE_RAG_SMOKE_OUTPUT", "").strip
  unless output.empty?
    FileUtils.mkdir_p(File.dirname(output))
    File.write(output, JSON.pretty_generate(evidence))
  end
  puts JSON.generate(evidence)
  exit(evidence["status"] == "passed" ? 0 : 1)
end
