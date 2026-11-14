# frozen_string_literal: true

# Operator-only setup helper. It never prints environment-variable values.
require "json"
require "net/http"
require "securerandom"
require "uri"

module RenderDatadogSetup
  SERVICE_ID = ENV.fetch("RENDER_SERVICE_ID", "srv-dasd3ajbc2fs73eos5jg")
  BASE_URL = "https://api.render.com/v1"
  REQUIRED = {
    "DD_SITE" => "datadoghq.com",
    "DD_ENV" => "production",
    "DD_SERVICE" => "goblin-dual-lineage-api",
    "DUAL_LINEAGE_RAG_URL" => "http://127.0.0.1:8102",
  }.freeze

  class Error < StandardError; end

  class Client
    def initialize
      @token = ENV.fetch("RENDER_API_KEY").strip
      raise Error, "RENDER_API_KEY is empty" if @token.empty?
    end

    def get(path)
      request(Net::HTTP::Get, path)
    end

    def list
      Array(get("/env-vars?limit=100")).to_h do |item|
        variable = item.fetch("envVar", item)
        [variable.fetch("key"), true]
      end
    end

    def put(path, value)
      request(Net::HTTP::Put, path, value: value)
    end

    private

    def request(klass, path, body = nil)
      uri = URI("#{BASE_URL}/services/#{SERVICE_ID}#{path}")
      request = klass.new(uri)
      request["Authorization"] = "Bearer #{@token}"
      if body
        request["Content-Type"] = "application/json"
        request.body = JSON.generate(body)
      end
      response = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: 10, read_timeout: 30) do |http|
        http.request(request)
      end
      return nil if response.code == "404"
      raise Error, "Render #{klass::METHOD} #{path} failed (HTTP #{response.code})" unless response.is_a?(Net::HTTPSuccess)

      JSON.parse(response.body)
    rescue JSON::ParserError
      raise Error, "Render returned invalid JSON"
    rescue Timeout::Error, SocketError, IOError
      raise Error, "Render connection failed"
    end
  end

  def self.run(env = ENV)
    client = Client.new
    existing_names = client.list
    desired = REQUIRED.merge(
      "DD_API_KEY" => env.fetch("AYAHOS_DD_API_KEY", "").strip,
      "DUAL_LINEAGE_RUNTIME_API_KEY" => env.fetch("AYAHOS_RUNTIME_API_KEY", "").strip,
      "DUAL_LINEAGE_RAG_SERVICE_TOKEN" => env.fetch("AYAHOS_RAG_SERVICE_TOKEN", "").strip,
    )
    changed = []
    retained = []
    desired.each do |name, value|
      existing = existing_names[name] || client.get("/env-vars/#{URI.encode_www_form_component(name)}")
      if existing
        retained << name
      elsif name == "DUAL_LINEAGE_RAG_SERVICE_TOKEN" && value.empty?
        client.put("/env-vars/#{URI.encode_www_form_component(name)}", SecureRandom.hex(32))
        changed << name
      elsif value.empty?
        raise Error, "missing setup input for #{name}"
      else
        client.put("/env-vars/#{URI.encode_www_form_component(name)}", value)
        changed << name
      end
    end
    puts JSON.generate({service_id: SERVICE_ID, changed: changed, retained: retained, secrets_written: changed & %w[DD_API_KEY DUAL_LINEAGE_RUNTIME_API_KEY DUAL_LINEAGE_RAG_SERVICE_TOKEN]})
  rescue KeyError
    raise Error, "RENDER_API_KEY is required"
  end
end

if $PROGRAM_NAME == __FILE__
  begin
    RenderDatadogSetup.run
  rescue RenderDatadogSetup::Error => error
    warn "Render Datadog setup: #{error.message}"
    exit 2
  end
end
