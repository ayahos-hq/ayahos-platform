# frozen_string_literal: true

# Shared retry and diagnostics support for the Ruby smoke/gate scripts.
#
# Standard library only. The helpers here add bounded retries for transient
# transport failures (and, when the caller opts in, for HTTP 502/503/504
# responses) without changing any script's verdict logic, evidence shape, or
# exit codes: callers keep deciding what a response or a failure means.
#
# Result contract: SmokeSupport.fetch never hides a failure.
# - HTTP outcomes (success, a non-retryable status, or an exhausted retryable
#   status) are returned as a Result carrying the last response.
# - Transport failures are raised as SmokeSupport::Failure once retries are
#   exhausted (or immediately for non-transient errors). The Failure message
#   keeps the original message and appends " (after N attempts, Xms)", and
#   the attempt count / elapsed time ride along as attributes, so a caller's
#   existing `rescue => error.message` evidence path gains the diagnostics
#   with no shape change.
# - Result#last_error names the most recent failure observed along the way
#   ("ClassName: message" or "HTTP 503"), or nil when the first attempt
#   succeeded outright.
#
# Configuration is read from the environment on every call:
# - SMOKE_MAX_ATTEMPTS: total attempts per fetch (default 3; 1 disables).
# - SMOKE_RETRY_BASE_DELAY_MS: first retry delay, doubling per attempt,
#   capped at 2000ms (default 250).
# - SMOKE_DEADLINE_SECONDS: when set, no new attempt starts past the
#   deadline (default unset: no deadline).

require "net/http"

module SmokeSupport
  RETRYABLE_STATUSES = [502, 503, 504].freeze
  MAX_DELAY_MS = 2000

  RETRYABLE_ERRORS = [
    Net::OpenTimeout,
    Net::ReadTimeout,
    Errno::ECONNREFUSED,
    Errno::ECONNRESET,
    Errno::EPIPE,
    Errno::ETIMEDOUT,
    Errno::EHOSTUNREACH,
    SocketError,
    EOFError
  ].tap { |list| list << Net::WriteTimeout if defined?(Net::WriteTimeout) }.freeze

  # The default public-chat provider allowlist (see expected_public_providers).
  DEFAULT_PUBLIC_PROVIDERS = ["aliyun-overmind"].freeze

  # A transport failure after retries were exhausted (or a non-transient
  # failure on its first occurrence). Carries the retry diagnostics so
  # callers can record them without parsing the message.
  class Failure < StandardError
    attr_reader :attempts, :elapsed_ms, :original_error

    def initialize(message, attempts:, elapsed_ms:, original_error: nil)
      super(message)
      @attempts = attempts
      @elapsed_ms = elapsed_ms
      @original_error = original_error
    end
  end

  # The outcome of a fetch that produced an HTTP response.
  Result = Struct.new(:response, :attempts, :elapsed_ms, :last_error, keyword_init: true)

  module_function

  def retryable_error?(error)
    RETRYABLE_ERRORS.any? { |klass| error.is_a?(klass) }
  end

  def fetch(retry_statuses: false)
    max_attempts = env_integer("SMOKE_MAX_ATTEMPTS", 3)
    max_attempts = 1 if max_attempts < 1
    base_delay_ms = env_integer("SMOKE_RETRY_BASE_DELAY_MS", 250)
    base_delay_ms = 0 if base_delay_ms.negative?
    deadline_seconds = env_seconds("SMOKE_DEADLINE_SECONDS")

    started = monotonic
    deadline_at = deadline_seconds.nil? ? nil : started + deadline_seconds
    attempts = 0
    last_error = nil
    loop do
      attempts += 1
      response = nil
      error = nil
      begin
        response = yield
      rescue StandardError => caught
        error = caught
      end

      if error.nil?
        if retry_statuses && RETRYABLE_STATUSES.include?(response.code.to_i)
          last_error = "HTTP #{response.code.to_i}"
        else
          return Result.new(response: response, attempts: attempts,
                            elapsed_ms: elapsed_ms(started), last_error: last_error)
        end
      else
        raise failure_for(error, attempts, started) unless retryable_error?(error)

        last_error = "#{error.class}: #{error.message}"
      end

      # A retry would come next; stop when out of attempts or past deadline.
      if attempts >= max_attempts || deadline_reached?(deadline_at)
        return Result.new(response: response, attempts: attempts,
                          elapsed_ms: elapsed_ms(started), last_error: last_error) if error.nil?

        raise failure_for(error, attempts, started)
      end
      sleep(backoff_ms(attempts, base_delay_ms) / 1000.0)
    end
  end

  # The single source of truth for which providers may answer public chat.
  #
  # The public site proxies chat to the FastAPI runtime and passes through
  # its provider_id, a route id from
  # apps/api/src/dual_lineage/providers/profiles.py. The current public
  # route id is "aliyun-overmind", so it is the default. ("public-knowledge"
  # was the label of a retired architecture in which public chat answered
  # directly from the knowledge base; nothing can emit it anymore.)
  #
  # The allowlist exists so public traffic stays on sanctioned public
  # routes: an unexpected provider — a paid route leaking into the public
  # surface, or an error placeholder — must fail the smoke, not pass it.
  # Override with PUBLIC_CHAT_EXPECTED_PROVIDERS (comma-separated) when the
  # sanctioned public routes change; never invent provider names here that
  # the runtime cannot emit.
  def expected_public_providers(env = ENV)
    raw = env["PUBLIC_CHAT_EXPECTED_PROVIDERS"]
    providers = raw.to_s.split(",").map(&:strip).reject(&:empty?)
    providers.empty? ? DEFAULT_PUBLIC_PROVIDERS.dup : providers
  end

  def public_provider_ok?(provider, env = ENV)
    provider.is_a?(String) && expected_public_providers(env).include?(provider)
  end

  def failure_for(error, attempts, started)
    elapsed = elapsed_ms(started)
    noun = attempts == 1 ? "attempt" : "attempts"
    Failure.new(
      "#{error.message} (after #{attempts} #{noun}, #{elapsed}ms)",
      attempts: attempts, elapsed_ms: elapsed, original_error: error
    )
  end

  def backoff_ms(attempts_done, base_delay_ms)
    [base_delay_ms * (2**(attempts_done - 1)), MAX_DELAY_MS].min
  end

  def deadline_reached?(deadline_at)
    !deadline_at.nil? && monotonic >= deadline_at
  end

  def monotonic
    Process.clock_gettime(Process::CLOCK_MONOTONIC)
  end

  def elapsed_ms(started)
    ((monotonic - started) * 1000).round
  end

  def env_integer(name, default)
    raw = ENV[name]
    return default if raw.nil? || raw.strip.empty?

    Integer(raw.strip, 10)
  rescue ArgumentError
    default
  end

  def env_seconds(name)
    raw = ENV[name]
    return nil if raw.nil? || raw.strip.empty?

    value = Float(raw.strip)
    value.negative? ? nil : value
  rescue ArgumentError
    nil
  end
end
