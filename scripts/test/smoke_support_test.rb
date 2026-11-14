# frozen_string_literal: true

# Unit tests for the shared smoke/gate retry support (scripts/smoke_support.rb).
#
# All request blocks are fakes: no network, and retry delays are pinned to
# 1ms via the environment, so the suite runs in milliseconds. Run with:
# ruby scripts/test/smoke_support_test.rb

require "minitest/autorun"
require_relative "../smoke_support"

FakeResponse = Struct.new(:code)

class SmokeSupportTest < Minitest::Test
  ENV_KEYS = %w[SMOKE_MAX_ATTEMPTS SMOKE_RETRY_BASE_DELAY_MS SMOKE_DEADLINE_SECONDS].freeze

  def setup
    @saved_env = ENV_KEYS.to_h { |key| [key, ENV[key]] }
    ENV["SMOKE_RETRY_BASE_DELAY_MS"] = "1"
    ENV.delete("SMOKE_MAX_ATTEMPTS")
    ENV.delete("SMOKE_DEADLINE_SECONDS")
  end

  def teardown
    ENV_KEYS.each do |key|
      @saved_env[key].nil? ? ENV.delete(key) : ENV[key] = @saved_env[key]
    end
  end

  def test_transient_error_then_success_returns_success_with_attempt_count
    calls = 0
    result = SmokeSupport.fetch(retry_statuses: true) do
      calls += 1
      raise Errno::ECONNREFUSED, "Connection refused" if calls == 1

      FakeResponse.new("200")
    end
    assert_equal "200", result.response.code
    assert_equal 2, result.attempts
    assert_equal 2, calls
    assert_kind_of Integer, result.elapsed_ms
    assert_includes result.last_error, "Errno::ECONNREFUSED"
  end

  def test_persistent_503_exhausts_attempts_and_returns_last_response
    calls = 0
    result = SmokeSupport.fetch(retry_statuses: true) do
      calls += 1
      FakeResponse.new("503")
    end
    assert_equal "503", result.response.code
    assert_equal 3, result.attempts
    assert_equal 3, calls
    assert_equal "HTTP 503", result.last_error
  end

  def test_400_response_is_not_retried
    calls = 0
    result = SmokeSupport.fetch(retry_statuses: true) do
      calls += 1
      FakeResponse.new("400")
    end
    assert_equal "400", result.response.code
    assert_equal 1, result.attempts
    assert_equal 1, calls
    assert_nil result.last_error
  end

  def test_503_is_not_retried_without_the_status_opt_in
    calls = 0
    result = SmokeSupport.fetch do
      calls += 1
      FakeResponse.new("503")
    end
    assert_equal 1, result.attempts
    assert_equal 1, calls
  end

  def test_non_transient_exception_is_not_retried
    calls = 0
    error = assert_raises(SmokeSupport::Failure) do
      SmokeSupport.fetch(retry_statuses: true) do
        calls += 1
        raise ArgumentError, "bad argument"
      end
    end
    assert_equal 1, calls
    assert_equal 1, error.attempts
    assert_includes error.message, "bad argument"
    assert_includes error.message, "(after 1 attempt,"
    assert_kind_of ArgumentError, error.original_error
  end

  def test_persistent_transient_error_raises_failure_with_diagnostics
    error = assert_raises(SmokeSupport::Failure) do
      SmokeSupport.fetch(retry_statuses: true) { raise Errno::ECONNRESET, "Connection reset" }
    end
    assert_equal 3, error.attempts
    assert_includes error.message, "Connection reset"
    assert_includes error.message, "(after 3 attempts,"
  end

  def test_max_attempts_one_disables_retries
    ENV["SMOKE_MAX_ATTEMPTS"] = "1"
    calls = 0
    assert_raises(SmokeSupport::Failure) do
      SmokeSupport.fetch(retry_statuses: true) do
        calls += 1
        raise Net::ReadTimeout, "timed out"
      end
    end
    assert_equal 1, calls
  end

  def test_deadline_stops_further_attempts
    ENV["SMOKE_DEADLINE_SECONDS"] = "0"
    calls = 0
    error = assert_raises(SmokeSupport::Failure) do
      SmokeSupport.fetch(retry_statuses: true) do
        calls += 1
        raise SocketError, "name resolution failed"
      end
    end
    assert_equal 1, calls
    assert_equal 1, error.attempts
  end
end

# Contract tests for the public-chat provider allowlist
# (SmokeSupport.expected_public_providers / public_provider_ok?).
class PublicProviderContractTest < Minitest::Test
  ENV_KEY = "PUBLIC_CHAT_EXPECTED_PROVIDERS"

  def setup
    @saved = ENV[ENV_KEY]
    ENV.delete(ENV_KEY)
  end

  def teardown
    @saved.nil? ? ENV.delete(ENV_KEY) : ENV[ENV_KEY] = @saved
  end

  def test_default_is_the_current_public_route
    assert_equal ["aliyun-overmind"], SmokeSupport.expected_public_providers
    assert SmokeSupport.public_provider_ok?("aliyun-overmind")
  end

  def test_default_rejects_the_retired_label_and_anything_else
    refute SmokeSupport.public_provider_ok?("public-knowledge")
    refute SmokeSupport.public_provider_ok?("unknown")
    refute SmokeSupport.public_provider_ok?(nil)
    refute SmokeSupport.public_provider_ok?(:"aliyun-overmind")
    refute SmokeSupport.public_provider_ok?(42)
  end

  def test_env_override_replaces_the_default_list
    ENV[ENV_KEY] = "a, b"
    assert_equal %w[a b], SmokeSupport.expected_public_providers
    assert SmokeSupport.public_provider_ok?("a")
    assert SmokeSupport.public_provider_ok?("b")
    refute SmokeSupport.public_provider_ok?("aliyun-overmind")
  end

  def test_env_override_ignores_blank_entries_and_empty_value
    ENV[ENV_KEY] = " , a,, "
    assert_equal ["a"], SmokeSupport.expected_public_providers

    ENV[ENV_KEY] = "  "
    assert_equal ["aliyun-overmind"], SmokeSupport.expected_public_providers
  end
end
