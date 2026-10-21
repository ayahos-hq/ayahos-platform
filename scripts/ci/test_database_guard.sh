# Sourced by scripts/ci/verify.sh and by apps/api/tests/test_ci_database_guard.py.
# Defines the guard only; running this file executes nothing.

# A plain local URL only: no query string and no host list. libpq reads host, hostaddr and
# service from a query string, so `localhost?host=remote` would connect to the remote host, and a
# comma in the authority is a multi-host list. Anything else counts as remote.
LOCAL_DATABASE_URL_PATTERN='^postgres(ql)?://([^@/?#,]*@)?(localhost|127\.0\.0\.1|\[::1\]|db)(:[0-9]+)?(/[^?#,]*)?$'

require_test_database() {
  if [ -z "${TEST_DATABASE_URL:-}" ]; then
    echo "TEST_DATABASE_URL is required for the '$1' gate" >&2
    exit 2
  fi
  if [[ "$TEST_DATABASE_URL" =~ $LOCAL_DATABASE_URL_PATTERN ]]; then
    return 0
  fi
  if [ "${CI_TEST_DATABASE_IS_DISPOSABLE:-}" != "1" ]; then
    echo "Refusing to run the '$1' gate against a non-local test database." >&2
    echo "A local URL must be plain: no query string and no host list." >&2
    echo "Set CI_TEST_DATABASE_IS_DISPOSABLE=1 only for a disposable Supabase branch: some tests drop the public schema." >&2
    exit 2
  fi
}
