"""Deterministic, fail-closed artifact builder regression tests (no network)."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

p = Path(__file__).with_name('build-hq-artifacts.py')
spec = importlib.util.spec_from_file_location('hq_build_artifacts', p)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
NAMES = ('ayahos-site','ayahos-core','ayahos-admin','ayahos-platform','ayahos-workloads')


def git(root, *args):
    return subprocess.check_output(['git','-C',str(root),*args], text=True).strip()

class ArtifactsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.heads = {}
        for name in NAMES:
            repo = self.workspace / name
            subprocess.run(['git','init','-q',str(repo)],check=True)
            git(repo,'config','user.email','test@example.invalid')
            git(repo,'config','user.name','Test')
            (repo/'README.md').write_text(name+'\n')
            git(repo,'add','README.md')
            git(repo,'commit','-qm','source')
            self.heads[name] = git(repo,'rev-parse','HEAD')
        self.manifest = self.root / 'release-manifest.json'
        self.manifest.write_text(json.dumps({'schema_version':1,'release_status':'candidate','components':{
            name:{'repository':'ayahos-hq/'+name,'git_sha':sha} for name,sha in self.heads.items()}}))
        (self.workspace/'ayahos-platform'/'release-manifest.json').write_bytes(self.manifest.read_bytes())
        # Manifest presence is checked separately; fake preflight only in isolated unit tests.
        self.receipt = self.workspace/'CANDIDATE-SOURCE-EVIDENCE.json'
        self.receipt.write_text(json.dumps({'schema_version':1,'cutover_ready':False,
            'manifest_sha256':hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            'platform_checkout_sha':self.heads['ayahos-platform'],
            'component_checkout_shas':self.heads}))
        self.output = self.root/'artifacts'

    def build(self, output=None, oci=None):
        with patch.object(module,'verify_source'):
            return module.build(self.manifest,self.workspace,output or self.output,oci)

    def test_builds_five_reproducible_archives_and_checks_sha(self):
        self.build()
        record = module.verify_output(self.output)
        self.assertFalse(record['release_authorized'])
        self.assertEqual(record['oci_status'],'pending')
        self.assertEqual(set(record['source_archives']), set(NAMES))
        second = self.root/'again'
        self.build(second)
        self.assertEqual(record['source_archives'], module.verify_output(second)['source_archives'])

    def test_tampering_with_archive_is_detected(self):
        self.build()
        with (self.output/'ayahos-site.tar').open('ab') as f: f.write(b'junk')
        with self.assertRaisesRegex(ValueError,'digest|size'):
            module.verify_output(self.output)

    def test_receipt_manifest_mismatch_rejected(self):
        data = json.loads(self.receipt.read_text())
        data['manifest_sha256'] = 'f'*64
        self.receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'manifest'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_source_commit_advance_rejected(self):
        repo = self.workspace/'ayahos-core'
        (repo/'README.md').write_text('changed')
        git(repo,'add','.');git(repo,'commit','-qm','changed')
        with self.assertRaisesRegex(ValueError,'HEAD'):
            self.build()

    def test_existing_output_and_symlink_cannot_be_replaced(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError,'exists'):
            self.build()
        self.output.rmdir()
        self.output.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'exists'):
            self.build()

    def test_forged_oci_lock_fails_closed_without_network(self):
        lock = self.root/'oci.json'
        lock.write_text(json.dumps({'images':[{'component':'ayahos-core',
            'reference':'example.com/ayahos/core@sha256:'+'a'*64,
            'source_sha':self.heads['ayahos-core']}]}))
        with patch.object(module,'inspect_oci',side_effect=ValueError('OCI digest not found')):
            with self.assertRaisesRegex(ValueError,'OCI'):
                self.build(oci=lock)
        self.assertFalse(self.output.exists())

    def test_rejects_unpinned_oci_reference(self):
        lock = self.root/'oci.json'
        lock.write_text(json.dumps({'images':[{'component':'ayahos-core',
            'reference':'example.com/ayahos/core:latest',
            'source_sha':self.heads['ayahos-core']}]}))
        with self.assertRaisesRegex(ValueError,'immutable OCI'):
            self.build(oci=lock)

    def test_reject_archive_escaping_symlink(self):
        repo = self.workspace/'ayahos-site'
        (repo/'escape').symlink_to('../../../outside')
        git(repo,'add','.');git(repo,'commit','-qm','unsafe symlink')
        self.heads['ayahos-site']=git(repo,'rev-parse','HEAD')
        data=json.loads(self.manifest.read_text())
        data['components']['ayahos-site']['git_sha']=self.heads['ayahos-site']
        self.manifest.write_text(json.dumps(data))
        (self.workspace/'ayahos-platform'/'release-manifest.json').write_bytes(self.manifest.read_bytes())
        evidence=json.loads(self.receipt.read_text())
        evidence['component_checkout_shas']=self.heads
        evidence['manifest_sha256']=hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        self.receipt.write_text(json.dumps(evidence))
        with self.assertRaisesRegex(ValueError,'unsafe archive'):
            self.build()
        self.assertFalse(self.output.exists())


    def test_rejects_forged_oci_receipt_without_images(self):
        self.build()
        path = self.output / module.EVIDENCE
        data = json.loads(path.read_text())
        data['oci_status'] = 'registry-verified'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'OCI'):
            module.verify_output(self.output)

    def test_skopeo_registry_manifest_and_revision_are_independently_compared(self):
        raw = b'{"schemaVersion":2}'
        expected = hashlib.sha256(raw).hexdigest()
        ref = 'registry.example.invalid/ayahos/core@sha256:' + expected
        revision = 'b' * 40
        results = [
            subprocess.CompletedProcess([], 0, stdout=raw),
            subprocess.CompletedProcess([], 0, stdout=json.dumps({
                'config': {'Labels': {'org.opencontainers.image.revision': revision}}
            }).encode())
        ]
        with patch.object(module.subprocess, 'run', side_effect=results):
            record = module.inspect_oci(ref, revision)
        self.assertTrue(record['registry_verified'])
        self.assertEqual(record['manifest_sha256'], expected)

    def test_skopeo_rejects_registry_digest_or_revision_mismatch(self):
        ref = 'registry.example.invalid/ayahos/core@sha256:' + 'a' * 64
        with patch.object(module.subprocess, 'run', return_value=
                          subprocess.CompletedProcess([], 0, stdout=b'wrong bytes')):
            with self.assertRaisesRegex(ValueError, 'digest'):
                module.inspect_oci(ref, 'b' * 40)

if __name__=='__main__':unittest.main()
