from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import rehearse_recovery


class RecoveryContractTest(unittest.TestCase):
    def test_rejects_without_disposable_acknowledgement(self) -> None:
        with self.assertRaises(rehearse_recovery.RehearsalError):
            rehearse_recovery.rehearse({})

    def test_rejects_local_or_traversal_object_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            identity = Path(directory) / "identity.txt"
            identity.write_text("operator escrow placeholder", encoding="utf-8")
            identity.chmod(0o600)
            env = {
                "AYAHOS_DISPOSABLE_RESTORE": "1",
                "AYAHOS_RESTORE_PROJECT_REF": "xgomhbuzawoqnwlzvavx",
                "AYAHOS_RESTORE_ARCHIVE_NAME": "ayahos-xgomhbuzawoqnwlzvavx-20261023T044912Z-a4bfe609.dump.age",
                "AYAHOS_RESTORE_SHA256": hashlib.sha256(b"archive").hexdigest(),
                "AYAHOS_RESTORE_AGE_IDENTITY_FILE": str(identity),
                "AYAHOS_RESTORE_DATABASE_URL": "postgresql://restore@localhost/ayahos_restore_rehearsal01",
            }
            for remote in ("local:/tmp/archive", "private-r2:bucket/../escape"):
                with self.subTest(remote=remote):
                    with self.assertRaises(rehearse_recovery.RehearsalError):
                        rehearse_recovery.rehearse({**env, "AYAHOS_RESTORE_RCLONE_REMOTE": remote})

    def test_missing_remote_does_not_invoke_rclone(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            with self.assertRaises(rehearse_recovery.RehearsalError):
                rehearse_recovery.rehearse({"AYAHOS_DISPOSABLE_RESTORE": "1"})


if __name__ == "__main__":
    unittest.main()
