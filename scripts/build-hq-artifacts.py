#!/usr/bin/env python3
"""Build deterministic, checksum-verifiable source artifacts from a pinned HQ workspace.

Source archives are NOT deployable images. Optional OCI lock entries are accepted
only after registry manifest bytes and their source revision labels are verified.
No pushes, deployments, token persistence, or Octopus acceptance are performed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('hq_verify_source', HERE / 'verify-release-manifest.py')
if SPEC and SPEC.loader and SPEC.origin and Path(SPEC.origin).exists():
    PREFLIGHT = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(PREFLIGHT)
    verify_source = PREFLIGHT.verify
    REPOSITORIES = PREFLIGHT.REPOSITORIES
else:
    REPOSITORIES = {name: 'ayahos-hq/' + name for name in
                    ('ayahos-site', 'ayahos-core', 'ayahos-admin', 'ayahos-platform', 'ayahos-workloads')}
    def verify_source(*_args):
        raise ValueError('source preflight is unavailable')

SHA = re.compile(r'\A[0-9a-f]{40}\Z')
OCI = re.compile(r'\A[a-z0-9][a-z0-9._:/-]+@sha256:([0-9a-f]{64})\Z')
EVIDENCE = 'RELEASE-ARTIFACT-EVIDENCE.json'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def checked_archive(path: Path) -> None:
    """Reject path traversal, devices, hard links and escaping symlinks."""
    with tarfile.open(path, 'r:') as tar:
        for entry in tar:
            name = PurePosixPath(entry.name)
            if name.is_absolute() or '..' in name.parts or not entry.name or '\\' in entry.name:
                raise ValueError('unsafe archive path')
            if entry.issym():
                target = entry.linkname
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(entry.name), target))
                if posixpath.isabs(target) or resolved == '..' or resolved.startswith('../'):
                    raise ValueError('unsafe archive symlink')
            elif not (entry.isfile() or entry.isdir()):
                raise ValueError('unsafe archive member type')


def inspect_oci(reference: str, revision: str) -> dict:
    """Read exact registry digest bytes and immutable image-config revision label."""
    match = OCI.fullmatch(reference)
    if not match:
        raise ValueError('immutable OCI image reference required')
    try:
        raw = subprocess.run(['skopeo', 'inspect', '--raw', 'docker://' + reference],
                             capture_output=True, check=False, timeout=120)
        if raw.returncode or hashlib.sha256(raw.stdout).hexdigest() != match.group(1):
            raise ValueError('OCI registry manifest digest mismatch')
        config = subprocess.run(['skopeo', 'inspect', '--config', 'docker://' + reference],
                                capture_output=True, check=False, timeout=120)
        if config.returncode:
            raise ValueError('OCI image config inaccessible')
        labels = json.loads(config.stdout).get('config', {}).get('Labels') or {}
        if labels.get('org.opencontainers.image.revision') != revision:
            raise ValueError('OCI image revision label disagrees with pinned Git SHA')
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('OCI registry verification unavailable') from exc
    return {'reference': reference, 'source_sha': revision,
            'manifest_sha256': match.group(1), 'registry_verified': True}


def verify_output(directory: Path) -> dict:
    """Rehash portable output; never infer Octopus, smoke, or release approval."""
    if directory.is_symlink():
        raise ValueError('artifact output cannot be symlinked')
    evidence = json.loads((directory / EVIDENCE).read_text(encoding='utf-8'))
    if (evidence.get('schema_version') != 1 or evidence.get('release_authorized') is not False
        or set(evidence.get('source_archives', {})) != set(REPOSITORIES)
        or evidence.get('oci_status') not in ('pending', 'registry-verified')):
        raise ValueError('invalid artifact evidence contract')
    manifest = directory / 'release-manifest.json'
    if manifest.is_symlink() or sha256(manifest) != evidence.get('manifest_sha256'):
        raise ValueError('manifest digest mismatch')
    components = json.loads(manifest.read_text())['components']
    for name, info in evidence['source_archives'].items():
        archive = directory / (name + '.tar')
        if archive.is_symlink() or (name != 'ayahos-platform' and info.get('git_sha') != components[name]['git_sha']):
            raise ValueError('archive source revision mismatch')
        if archive.stat().st_size != info.get('bytes') or sha256(archive) != info.get('sha256'):
            raise ValueError('source archive digest or size mismatch: ' + name)
        checked_archive(archive)
    images = evidence.get('oci_images')
    if not isinstance(images, dict) or any(name not in REPOSITORIES for name in images):
        raise ValueError('invalid OCI evidence components')
    if (evidence['oci_status'] == 'pending') != (not images):
        raise ValueError('OCI status and evidence disagree')
    for name, item in images.items():
        ref = item.get('reference')
        match = OCI.fullmatch(ref) if isinstance(ref, str) else None
        if (not match or item.get('registry_verified') is not True
            or item.get('manifest_sha256') != match.group(1)
            or item.get('source_sha') != evidence['source_archives'][name]['git_sha']):
            raise ValueError('invalid immutable OCI evidence: ' + name)
    return evidence


def build(manifest_path: Path, workspace: Path, destination: Path,
          oci_lock: Path | None = None) -> dict:
    if destination.exists() or destination.is_symlink():
        raise ValueError('artifact destination already exists')
    if not destination.parent.is_dir():
        raise ValueError('artifact destination parent is missing')
    if workspace.is_symlink():
        raise ValueError('workspace symlink is forbidden')
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    receipt = json.loads((workspace / 'CANDIDATE-SOURCE-EVIDENCE.json').read_text())
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if (manifest.get('release_status') != 'candidate' or receipt.get('schema_version') != 1
        or receipt.get('cutover_ready') is not False or receipt.get('manifest_sha256') != manifest_hash
        or set(receipt.get('component_checkout_shas', {})) != set(REPOSITORIES)):
        raise ValueError('untrusted workspace manifest or source receipt')
    platform_head = receipt.get('platform_checkout_sha')
    if not isinstance(platform_head, str) or not SHA.fullmatch(platform_head):
        raise ValueError('invalid platform release SHA')
    if (workspace / 'ayahos-platform' / 'release-manifest.json').read_bytes() != manifest_bytes:
        raise ValueError('platform manifest differs from assembled candidate')
    verify_source(manifest_path, workspace)
    for name in REPOSITORIES:
        actual = subprocess.check_output(['git', '-C', str(workspace / name), 'rev-parse', 'HEAD'],
                                         text=True, stderr=subprocess.DEVNULL).strip()
        expected = platform_head if name == 'ayahos-platform' else manifest['components'][name]['git_sha']
        if not SHA.fullmatch(expected) or receipt['component_checkout_shas'][name] != expected or actual != expected:
            raise ValueError('checkout HEAD and manifest receipt disagree: ' + name)
    oci_images = {}
    if oci_lock is not None:
        lock = json.loads(oci_lock.read_text(encoding='utf-8'))
        images = lock.get('images')
        if not isinstance(images, list) or not images:
            raise ValueError('OCI lock must list pinned images')
        for item in images:
            name = item.get('component')
            if name not in REPOSITORIES or name in oci_images:
                raise ValueError('duplicate or unauthorized OCI component')
            expected = platform_head if name == 'ayahos-platform' else manifest['components'][name]['git_sha']
            if item.get('source_sha') != expected:
                raise ValueError('OCI lock source commit drift')
            reference = item.get('reference')
            if not isinstance(reference, str) or not OCI.fullmatch(reference):
                raise ValueError('immutable OCI image reference required')
            oci_images[name] = inspect_oci(reference, expected)
    staging = Path(tempfile.mkdtemp(prefix='.' + destination.name + '-', dir=destination.parent))
    try:
        (staging / 'release-manifest.json').write_bytes(manifest_bytes)
        archives = {}
        for name in REPOSITORIES:
            ref = receipt['component_checkout_shas'][name]
            archive = staging / (name + '.tar')
            with archive.open('wb') as output:
                proc = subprocess.run(['git', '-C', str(workspace / name), 'archive',
                                       '--format=tar', ref], stdout=output,
                                      stderr=subprocess.DEVNULL, check=False, timeout=180)
            if proc.returncode:
                raise ValueError('Git archive failed for ' + name)
            checked_archive(archive)
            archives[name] = {'repository': REPOSITORIES[name], 'git_sha': ref,
                              'file': name + '.tar', 'sha256': sha256(archive),
                              'bytes': archive.stat().st_size}
        evidence = {'schema_version': 1, 'release_authorized': False,
                    'manifest_sha256': manifest_hash, 'source_archives': archives,
                    'oci_status': 'registry-verified' if oci_images else 'pending',
                    'oci_images': oci_images,
                    'octopus_exact_sha': 'pending', 'database_restore': 'pending',
                    'live_smoke': 'pending', 'rollback': 'pending'}
        (staging / EVIDENCE).write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
        verify_output(staging)
        if destination.exists() or destination.is_symlink():
            raise ValueError('artifact destination appeared before promotion')
        staging.rename(destination)
        return evidence
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('release-manifest.json'))
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--oci-lock', type=Path, help='registry pins, independently checked using skopeo')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.verify_only:
            verify_output(args.output)
            print('Verified artifact SHA-256 records; no release authorization')
        elif args.workspace:
            build(args.manifest, args.workspace, args.output, args.oci_lock)
            print('Built exact-SHA source artifacts; OCI and Octopus gates remain independent')
        else:
            parser.error('--workspace is required unless --verify-only is set')
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, json.JSONDecodeError, tarfile.TarError) as exc:
        print('HQ ARTIFACT GATE BLOCKED: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
