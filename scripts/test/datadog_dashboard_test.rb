# frozen_string_literal: true

require "minitest/autorun"
require "minitest/mock"
require "time"
require_relative "../datadog_dashboard"

class DatadogDashboardTest < Minitest::Test
  class FakeClient
    attr_reader :calls

    def initialize(responses)
      @responses = responses
      @calls = []
    end

    def request(method, path, body = nil, params = {})
      @calls << [method, path, body, params]
      raise "unexpected API call" if @responses.empty?
      @responses.shift
    end
  end

  def setup
    @definition = JSON.parse(File.read(AyahOSDatadog::DASHBOARD))
    @owned = { "id" => "abc-def-123", "description" => AyahOSDatadog::MARKER }
  end

  def test_validate_requires_no_credentials_or_network
    assert_equal @definition, AyahOSDatadog.validate!(@definition)
    out, = capture_io { assert_equal 0, AyahOSDatadog.main(["validate"], {}) }
    assert JSON.parse(out).fetch("valid")
  end

  def test_plan_is_read_only
    client = FakeClient.new([{ "dashboards" => [@owned] }])
    result = AyahOSDatadog::Dashboard.new(client, @definition).run("plan")
    assert_equal "update", result[:action]
    assert_equal ["GET"], client.calls.map(&:first)
  end

  def test_apply_creates_only_when_no_owned_dashboard_exists
    client = FakeClient.new([{ "dashboards" => [{ "id" => "unrelated" }] }, @owned])
    result = AyahOSDatadog::Dashboard.new(client, @definition).run("apply")
    assert_equal "create", result[:action]
    assert_equal ["GET", "POST"], client.calls.map(&:first)
    assert_equal @definition, client.calls.last[2]
  end

  def test_apply_updates_owned_dashboard_instead_of_creating_duplicate
    client = FakeClient.new([{ "dashboards" => [@owned] }, @owned])
    result = AyahOSDatadog::Dashboard.new(client, @definition).run("apply")
    assert_equal "update", result[:action]
    assert_equal "/api/v1/dashboard/abc-def-123", client.calls.last[1]
    assert_equal "PUT", client.calls.last[0]
  end

  def test_ownership_discovery_checks_later_pages_before_creating
    first_page = Array.new(100) { |index| { "id" => "unrelated-#{index}" } }
    client = FakeClient.new([{ "dashboards" => first_page }, { "dashboards" => [@owned] }, @owned])
    result = AyahOSDatadog::Dashboard.new(client, @definition).run("apply")
    assert_equal "update", result[:action]
    assert_equal 100, client.calls[1][3][:start]
    assert_equal ["GET", "GET", "PUT"], client.calls.map(&:first)
  end

  def test_ambiguous_ownership_refuses_write
    client = FakeClient.new([{ "dashboards" => [@owned, @owned.merge("id" => "def-123-abc")] }])
    assert_raises(AyahOSDatadog::Error) { AyahOSDatadog::Dashboard.new(client, @definition).run("apply") }
    assert_equal ["GET"], client.calls.map(&:first)
  end

  def test_explicit_id_must_be_owned
    client = FakeClient.new([{ "id" => "abc-def-123", "description" => "another team" }])
    tool = AyahOSDatadog::Dashboard.new(client, @definition, dashboard_id: "abc-def-123")
    assert_raises(AyahOSDatadog::Error) { tool.run("apply") }
    assert_equal ["GET"], client.calls.map(&:first)
  end

  def test_unknown_site_rejected_before_credentials_can_leave_host
    assert_raises(AyahOSDatadog::Error) do
      AyahOSDatadog::Client.new("DD_SITE" => "attacker.invalid", "DD_API_KEY" => "private", "DD_APP_KEY" => "private")
    end
  end

  def test_missing_key_error_names_variables_without_values
    error = assert_raises(AyahOSDatadog::Error) { AyahOSDatadog::Client.new("DD_API_KEY" => "private") }
    assert_includes error.message, "DD_APP_KEY"
    refute_includes error.message, "private"
  end

  def test_remote_error_never_echoes_response_body_or_credentials
    response = Net::HTTPForbidden.new("1.1", "403", "Forbidden")
    response.body = "private remote diagnostic"
    http = Minitest::Mock.new
    http.expect(:request, response, [Net::HTTP::Get])
    client = AyahOSDatadog::Client.new("DD_API_KEY" => "private", "DD_APP_KEY" => "private")
    transport = ->(*_args, **_options, &block) { block.call(http) }
    Net::HTTP.stub(:start, transport) do
      error = assert_raises(AyahOSDatadog::Error) { client.request("GET", "/api/v1/dashboard") }
      assert_includes error.message, "HTTP 403"
      refute_includes error.message, "private"
    end
    http.verify
  end

  def test_redirect_is_not_followed_with_credentials
    response = Net::HTTPFound.new("1.1", "302", "Found")
    response["Location"] = "https://attacker.invalid/"
    http = Minitest::Mock.new
    http.expect(:request, response, [Net::HTTP::Get])
    client = AyahOSDatadog::Client.new("DD_API_KEY" => "private", "DD_APP_KEY" => "private")
    transport = ->(*_args, **_options, &block) { block.call(http) }
    Net::HTTP.stub(:start, transport) do
      assert_raises(AyahOSDatadog::Error) { client.request("GET", "/api/v1/dashboard") }
    end
    http.verify
  end

  def test_missing_feedback_signal_cannot_be_reported_as_verified
    client = FakeClient.new([
      { "dashboards" => [@owned] },
      { "series" => [{ "pointlist" => [[1, 2.0]] }] },
      { "series" => [{ "pointlist" => [[1, nil], [2, 0]] }] }
    ])
    result = AyahOSDatadog::Dashboard.new(client, @definition).run("check")
    refute result[:verified]
    assert result[:signals]["cognition.requests"]
    refute result[:signals]["feedback.responses"]
    assert_equal ["GET", "GET", "GET"], client.calls.map(&:first)
    assert_includes client.calls.last[3][:query], AyahOSDatadog::SCOPE
  end

  def test_real_positive_signals_are_required_for_both_metrics
    data = { "series" => [{ "pointlist" => [[1, 1.0]] }] }
    client = FakeClient.new([{ "dashboards" => [@owned] }, data, data])
    assert AyahOSDatadog::Dashboard.new(client, @definition).run("check")[:verified]
  end

  def test_null_series_is_no_data_and_not_success
    client = FakeClient.new([{ "dashboards" => [@owned] }, { "series" => nil }, { "series" => nil }])
    refute AyahOSDatadog::Dashboard.new(client, @definition).run("check")[:verified]
  end

  def test_cli_check_returns_nonzero_for_missing_live_signals
    client = FakeClient.new([{ "dashboards" => [@owned] }, { "series" => nil }, { "series" => [] }])
    out, = capture_io do
      AyahOSDatadog::Client.stub(:new, client) do
        assert_equal 1, AyahOSDatadog.main(["check"], {})
      end
    end
    refute JSON.parse(out).fetch("verified")
  end

  def test_cli_missing_credentials_returns_configuration_error
    out, err = capture_io { assert_equal 2, AyahOSDatadog.main(["plan"], {}) }
    assert_empty out
    assert_includes err, "DD_API_KEY, DD_APP_KEY"
  end

  def test_wrong_metric_scope_is_rejected
    @definition["widgets"][1]["definition"]["requests"][0]["q"] = "sum:system.cpu.user{*}"
    assert_raises(AyahOSDatadog::Error) { AyahOSDatadog.validate!(@definition) }
  end

  def test_pup_auth_needs_no_manually_exported_keys
    assert_instance_of AyahOSDatadog::PupClient, AyahOSDatadog.build_client("DD_AUTH_METHOD" => "pup")
  end

  def test_pup_sends_json_on_stdin_and_keeps_query_and_org_in_argv
    calls = []
    success = Struct.new(:exitstatus) { def success? = exitstatus.zero? }.new(0)
    invoke = lambda do |*args, **options|
      calls << [args, options]
      [JSON.generate("id" => "abc-def-123"), "", success]
    end
    client = AyahOSDatadog::PupClient.new("PUP_BIN" => "pup.exe", "DD_PUP_ORG" => "AyahOS")
    Open3.stub(:capture3, invoke) do
      assert_equal "abc-def-123", client.request("POST", "/api/v1/dashboard", @definition).fetch("id")
      client.request("GET", "/api/v1/query", nil, { query: "sum:metric{env:production}" })
    end
    assert_equal @definition, JSON.parse(calls[0][1][:stdin_data])
    assert_includes calls[0][0], "--input"
    assert_includes calls[0][0], "--yes"
    assert_includes calls[0][0], "AyahOS"
    assert_includes calls[1][0][2], "query=sum%3Ametric%7Benv%3Aproduction%7D"
    refute_includes calls[1][0], "--yes"
    refute calls[0][0].any? { |arg| arg.include?("TOKEN") || arg.include?("KEY") }
  end

  def test_pup_failure_does_not_echo_diagnostics_or_response
    failure = Struct.new(:exitstatus) { def success? = exitstatus.zero? }.new(1)
    invoke = ->(*_args, **_options) { ["private response", "private diagnostic", failure] }
    Open3.stub(:capture3, invoke) do
      error = assert_raises(AyahOSDatadog::Error) { AyahOSDatadog::PupClient.new({}).request("GET", "/api/v1/dashboard") }
      assert_includes error.message, "pup auth status"
      refute_includes error.message, "private"
    end
  end
end
