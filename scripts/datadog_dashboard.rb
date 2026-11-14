# frozen_string_literal: true

require "json"
require "net/http"
require "open3"
require "time"
require "uri"

# Operator tooling only: never imported by the runtime or its authority paths.
module AyahOSDatadog
  MARKER = "ayahos-managed:observability-v1"
  DASHBOARD = File.expand_path("../deploy/datadog/ayahos-dashboard.json", __dir__)
  SITES = %w[datadoghq.com datadoghq.eu us3.datadoghq.com us5.datadoghq.com
             ap1.datadoghq.com ap2.datadoghq.com uk1.datadoghq.com].freeze
  SCOPE = "env:production,service:goblin-dual-lineage-api"
  SIGNALS = %w[cognition.requests feedback.responses].freeze
  class Error < StandardError; end

  def self.validate!(dashboard)
    raise Error, "dashboard ownership marker is missing" unless dashboard.fetch("description").include?(MARKER)
    raise Error, "dashboard must use ordered layout" unless dashboard["layout_type"] == "ordered"
    widgets = dashboard.fetch("widgets")
    raise Error, "dashboard has no widgets" if widgets.empty?
    widgets.each do |widget|
      definition = widget.fetch("definition")
      next if definition["type"] == "note"

      definition.fetch("requests").each do |request|
        query = request.fetch("q")
        unless query.match?(/\A(?:sum|avg|max):goblin\.dual_lineage\./) && query.include?("{#{SCOPE}}")
          raise Error, "dashboard query must use the AyahOS metric prefix and production service scope"
        end
      end
    end
    dashboard
  end

  class Client
    def initialize(env = ENV)
      @site = env.fetch("DD_SITE", "datadoghq.com")
      raise Error, "unsupported DD_SITE" unless SITES.include?(@site)
      @api_key = env.fetch("DD_API_KEY", "").strip
      @app_key = env.fetch("DD_APP_KEY", "").strip
      missing = []
      missing << "DD_API_KEY" if @api_key.empty?
      missing << "DD_APP_KEY" if @app_key.empty?
      raise Error, "missing credentials: #{missing.join(', ')}" unless missing.empty?
    end

    def request(method, path, body = nil, params = {})
      uri = URI("https://api.#{@site}#{path}")
      uri.query = URI.encode_www_form(params) unless params.empty?
      klass = { "GET" => Net::HTTP::Get, "POST" => Net::HTTP::Post, "PUT" => Net::HTTP::Put }.fetch(method)
      request = klass.new(uri)
      request["DD-API-KEY"] = @api_key
      request["DD-APPLICATION-KEY"] = @app_key
      request["Content-Type"] = "application/json"
      request.body = JSON.generate(body) if body
      response = Net::HTTP.start(uri.host, uri.port, use_ssl: true, open_timeout: 5, read_timeout: 20) do |http|
        http.request(request)
      end
      # Do not follow redirects or print remote error bodies, headers, or credentials.
      raise Error, "Datadog #{method} #{path} failed with HTTP #{response.code}" unless response.is_a?(Net::HTTPSuccess)
      JSON.parse(response.body)
    rescue JSON::ParserError
      raise Error, "Datadog returned invalid JSON"
    rescue IOError, SystemCallError, Timeout::Error, OpenSSL::SSL::SSLError, SocketError
      raise Error, "Datadog connection failed"
    end
  end

  class Dashboard
    def initialize(client, definition, dashboard_id: nil)
      @client = client
      @definition = AyahOSDatadog.validate!(definition)
      @dashboard_id = dashboard_id.to_s.strip
      unless @dashboard_id.empty? || @dashboard_id.match?(/\A[a-z0-9-]{1,64}\z/)
        raise Error, "invalid DD_DASHBOARD_ID"
      end
    end

    def run(mode)
      existing = find_owned
      if mode == "check"
        raise Error, "managed AyahOS dashboard has not been published" unless existing
        now = Time.now.to_i
        signals = SIGNALS.to_h do |metric|
          result = @client.request("GET", "/api/v1/query", nil,
            { from: now - 3600, to: now, query: "sum:goblin.dual_lineage.#{metric}{#{SCOPE}}.as_count()" })
          present = Array(result["series"]).any? do |series|
            Array(series["pointlist"]).any? { |point| point[1].is_a?(Numeric) && point[1].positive? }
          end
          [metric, present]
        end
        return { mode: mode, dashboard_id: existing.fetch("id"), signals: signals,
                 verified: signals.values.all?, checked_at: Time.now.utc.iso8601 }
      end
      action = existing ? "update" : "create"
      return { mode: mode, action: action, dashboard_id: existing && existing.fetch("id") } if mode == "plan"
      raise Error, "unsupported mode" unless mode == "apply"
      result = if existing
                 @client.request("PUT", "/api/v1/dashboard/#{existing.fetch('id')}", @definition)
               else
                 @client.request("POST", "/api/v1/dashboard", @definition)
               end
      { mode: mode, action: action, dashboard_id: result.fetch("id"), url: result["url"] }
    end

    private

    def find_owned
      unless @dashboard_id.empty?
        dashboard = @client.request("GET", "/api/v1/dashboard/#{@dashboard_id}")
        raise Error, "refusing to replace a dashboard without the AyahOS ownership marker" unless owned?(dashboard)
        return dashboard
      end
      matches = []
      seen = {}
      start = 0
      loop do
        page = @client.request("GET", "/api/v1/dashboard", nil, { count: 100, start: start }).fetch("dashboards")
        page.each do |item|
          id = item.fetch("id")
          raise Error, "dashboard pagination returned a repeated ID" if seen[id]
          seen[id] = true
          matches << item if owned?(item)
        end
        break if page.length < 100
        start += page.length
      end
      raise Error, "multiple managed AyahOS dashboards found; set DD_DASHBOARD_ID" if matches.length > 1
      matches.first
    end

    def owned?(dashboard)
      dashboard.fetch("description", "").to_s.include?(MARKER)
    end
  end

  # Pup keeps OAuth credentials in the OS credential store; never export its token.
  class PupClient
    def initialize(env = ENV)
      @executable = env.fetch("PUP_BIN", "pup")
      @org = env.fetch("DD_PUP_ORG", "AyahOS")
    end

    def request(method, path, body = nil, params = {})
      endpoint = params.empty? ? path : "#{path}?#{URI.encode_www_form(params)}"
      args = [@executable, "api", endpoint, "-X", method, "--org", @org, "--no-envelope", "-o", "json"]
      args << "--yes" unless method == "GET"
      args.concat(["--input", "-"]) if body
      output, _diagnostic, status = Open3.capture3(*args, stdin_data: body ? JSON.generate(body) : "")
      unless status.success?
        raise Error, "Pup #{method} #{path} failed (exit #{status.exitstatus}); check pup auth status --org #{@org}"
      end
      JSON.parse(output)
    rescue Errno::ENOENT
      raise Error, "Pup CLI is not installed or PUP_BIN is invalid"
    rescue JSON::ParserError
      raise Error, "Pup returned invalid JSON"
    end
  end

  def self.build_client(env)
    case env.fetch("DD_AUTH_METHOD", "keys")
    when "keys" then Client.new(env)
    when "pup" then PupClient.new(env)
    else raise Error, "DD_AUTH_METHOD must be keys or pup"
    end
  end

  def self.main(args, env = ENV)
    mode = args.first || "validate"
    raise Error, "usage: ruby scripts/datadog_dashboard.rb [validate|plan|apply|check]" unless %w[validate plan apply check].include?(mode) && args.length <= 1
    definition = validate!(JSON.parse(File.read(DASHBOARD)))
    result = if mode == "validate"
               { mode: mode, valid: true, widgets: definition.fetch("widgets").length }
             else
               Dashboard.new(build_client(env), definition, dashboard_id: env["DD_DASHBOARD_ID"]).run(mode)
             end
    puts JSON.generate(result)
    result[:verified] == false ? 1 : 0
  rescue Error, KeyError, JSON::ParserError => error
    warn "Datadog setup: #{error.message}"
    2
  end
end

if $PROGRAM_NAME == __FILE__
  exit AyahOSDatadog.main(ARGV)
end
