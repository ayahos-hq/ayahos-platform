"""Co-located Ruby RAG startup must not depend on missing Render secrets."""
from pathlib import Path
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "db" / "rag_env_bootstrap.sh"


class TestLocalRagBootstrap(unittest.TestCase):
    def run_bootstrap(self, url=None, token=None):
        env = {**os.environ, "PATH": os.environ["PATH"]}
        env.pop("DUAL_LINEAGE_RAG_URL", None)
        env.pop("DUAL_LINEAGE_RAG_SERVICE_TOKEN", None)
        if url is not None:
            env["DUAL_LINEAGE_RAG_URL"] = url
        if token is not None:
            env["DUAL_LINEAGE_RAG_SERVICE_TOKEN"] = token
        snippet = f'source "{SCRIPT}"; ayahos_bootstrap_rag_env || exit 19; printf "%s\n%s\n" "$DUAL_LINEAGE_RAG_URL" "$DUAL_LINEAGE_RAG_SERVICE_TOKEN"'
        return subprocess.run(["bash", "-c", snippet], capture_output=True, text=True, env=env)

    def test_default_loopback_generates_strong_ephemeral_key(self):
        r = self.run_bootstrap()
        self.assertEqual(0, r.returncode, r.stderr)
        url, secret = r.stdout.splitlines()
        self.assertEqual("http://127.0.0.1:8102", url)
        self.assertGreaterEqual(len(secret), 60)
        self.assertEqual("", r.stderr)

    def test_existing_operator_secret_preserved(self):
        r = self.run_bootstrap(url="https://rag.internal", token="secure-configured-key")
        self.assertEqual(0, r.returncode)
        self.assertEqual(["https://rag.internal", "secure-configured-key"], r.stdout.splitlines())

    def test_missing_remote_key_is_refused(self):
        r = self.run_bootstrap(url="https://rag.internal")
        self.assertEqual(19, r.returncode)
        self.assertEqual("", r.stdout)
        self.assertIn("remote_token_missing", r.stderr)

    def test_local_explicit_secret_preserved(self):
        r = self.run_bootstrap(token="long-enough-private-key-1234")
        self.assertEqual(0, r.returncode)
        self.assertEqual("long-enough-private-key-1234", r.stdout.splitlines()[1])


if __name__ == "__main__":
    unittest.main()
