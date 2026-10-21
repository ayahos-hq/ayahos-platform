"""Offline contract tests for the primary public release target.

Never calls the real Cloudflare, Vercel, Render APIs or paid model endpoints.

The two live probes are Ruby scripts (repo language rule: Ruby for ops/smoke
tooling), so their SITE default is read by requiring them in a Ruby subprocess
instead of importing them as Python modules.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CLOUDFLARE = "https://ayahos.pages.dev"
BACKUP = "https://ayahos.vercel.app"
VALID_SHA = "a" * 40
RUBY = shutil.which("ruby")


def ruby_site(script: Path, *, site_url: str | None = None) -> str:
    """The SITE constant a Ruby probe resolves to, with a minimal environment."""
    if script.name == "public_chat_smoke.rb":
        expression = "require ARGV[0]; print SITE"
    else:
        expression = "require ARGV[0]; print LiveReleaseSmoke::SITE"
    env = {"PATH": os.environ.get("PATH", "")}
    if site_url is not None:
        env["LIVE_PUBLIC_SITE_URL"] = site_url
    result = subprocess.run(
        [RUBY, "-e", expression, str(script)],
        env=env, text=True, capture_output=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@unittest.skipIf(RUBY is None, "the live probes are Ruby scripts; ruby is required")
class PublicSiteReleaseTargetTests(unittest.TestCase):
    def test_all_live_probe_defaults_point_at_cloudflare(self):
        ruby_files = (
            ROOT / "scripts/public_chat_smoke.rb",
            ROOT / "scripts/live_release_smoke.rb",
        )
        for filename in ruby_files:
            with self.subTest(file=filename.name):
                self.assertEqual(ruby_site(filename), CLOUDFLARE)

        for filename in (
            ROOT / "scripts/ci/post-deploy.sh",
            ROOT / "scripts/ci/canary.sh",
            ROOT / "scripts/ci/public_site_browser_smoke.py",
            ROOT / "scripts/verify_public_site.sh",
        ):
            with self.subTest(file=filename.name):
                source = filename.read_text(encoding="utf-8")
                self.assertIn(CLOUDFLARE, source)
                self.assertNotIn(BACKUP, source)

    def test_explicit_override_is_still_supported_for_rollback(self):
        for path in ("scripts/public_chat_smoke.rb", "scripts/live_release_smoke.rb"):
            with self.subTest(path=path):
                self.assertEqual(ruby_site(ROOT / path, site_url=BACKUP), BACKUP)

    def test_public_browser_probe_sends_a_cloudflare_compatible_agent(self):
        source = (ROOT / "scripts/ci/public_site_browser_smoke.py").read_text()
        self.assertIn('"User-Agent": "AyahOS-live-smoke/1"', source)
        self.assertIn("urllib.request.urlopen(build_request", source)
        self.assertIn('page.route("**/api/chat", mock_chat)', source)
        self.assertIn("EXPECTED_SHA", source)

    def test_public_sha_evidence_is_provider_neutral(self):
        source = (ROOT / "scripts/live_release_smoke.rb").read_text()
        self.assertIn('"served_sha_public_site"', source)
        self.assertNotIn('"served_sha_vercel"', source)

    def run_fake_canary(self, build: dict, *, expected: str = "", url: str = ""):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script = root / "scripts/ci/canary.sh"
            script.parent.mkdir(parents=True)
            script.write_text((ROOT / "scripts/ci/canary.sh").read_text())
            (root / "scripts/public_chat_smoke.rb").write_text(
                "# This script is stubbed by the fake ruby below.\n"
            )
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_curl = fake_bin / "curl"
            fake_curl.write_text(
                "#!/bin/sh\n"
                'output=""\nlast=""\n'
                'while [ "$#" -gt 0 ]; do\n'
                '  if [ "$1" = "-o" ]; then shift; output="$1"; fi\n'
                '  last="$1"\n'
                '  shift\n'
                'done\n'
                'printf "%s" "$FAKE_BUILD_JSON" > "$output"\n'
                'printf "%s" "$last" > "$FAKE_CURL_TRACE"\n'
                'printf "200"\n'
            )
            fake_curl.chmod(0o755)
            fake_ruby = fake_bin / "ruby"
            fake_ruby.write_text(
                "#!/bin/sh\n"
                'if [ "$1" = "scripts/public_chat_smoke.rb" ]; then exit 0; fi\n'
                f'exec "{RUBY}" "$@"\n'
            )
            fake_ruby.chmod(0o755)
            trace = root / "curl-target.txt"
            env = dict(os.environ)
            env.update({
                "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
                "FAKE_BUILD_JSON": json.dumps(build),
                "FAKE_CURL_TRACE": str(trace),
            })
            env.pop("LIVE_PUBLIC_SITE_URL", None)
            env.pop("EXPECTED_SHA", None)
            if url:
                env["LIVE_PUBLIC_SITE_URL"] = url
            if expected:
                env["EXPECTED_SHA"] = expected
            result = subprocess.run(
                ["bash", str(script)],
                cwd=root, env=env, text=True, capture_output=True, timeout=12,
                check=False,
            )
            return result, trace.read_text()

    def test_canary_attests_main_even_without_expected_sha(self):
        ok, destination = self.run_fake_canary(
            {"build_sha": VALID_SHA, "source_branch": "main"}
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(destination, CLOUDFLARE + "/api/build")

        fallback, destination = self.run_fake_canary(
            {"build_sha": VALID_SHA, "source_branch": "main"}, url=BACKUP,
        )
        self.assertEqual(fallback.returncode, 0, fallback.stderr)
        self.assertEqual(destination, BACKUP + "/api/build")

    def test_canary_rejects_missing_sha_wrong_branch_and_mismatch(self):
        for build, expected in (
            ({"source_branch": "main"}, ""),
            ({"build_sha": "short", "source_branch": "main"}, ""),
            ({"build_sha": VALID_SHA, "source_branch": "preview"}, ""),
            ({"build_sha": VALID_SHA, "source_branch": "main"}, "b" * 40),
            ({"build_sha": VALID_SHA, "source_branch": "main"}, "not-a-sha"),
        ):
            with self.subTest(build=build, expected=expected):
                result, _ = self.run_fake_canary(build, expected=expected)
                self.assertNotEqual(result.returncode, 0)

    def test_canary_accepts_matching_expected_sha(self):
        result, _ = self.run_fake_canary(
            {"build_sha": VALID_SHA, "source_branch": "main"}, expected=VALID_SHA,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
