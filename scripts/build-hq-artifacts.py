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
ARTIFACT = re.compile(r'\A[0-9a-f]{64}\Z')
OCI = re.compile(r'\A[a-z0-9][a-z0-9._:/-]+@sha256:([0-9a-f]{64})\Z')
EVIDENCE = 'RELEASE-ARTIFACT-EVIDENCE.json'


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def archive_directory(source: Path, destination: Path) -> None:
    """Create a deterministic tar archive of a reviewed runtime context."""
    if source.is_symlink() or not source.is_dir():
        raise ValueError("runtime context must be a real directory")
    with tarfile.open(destination, "w:", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
            relative = path.relative_to(source).as_posix()
            if path.is_symlink():
                raise ValueError("runtime context contains a symlink")
            if not path.is_dir() and not path.is_file():
                raise ValueError("runtime context contains a special file")
            info = tar.gettarinfo(str(path), arcname=relative)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            if info.isreg():
                with path.open("rb") as stream:
                    tar.addfile(info, stream)
            else:
                tar.addfile(info)


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


def inspect_runtime_image(reference: str, source_shas: dict[str, str], manifest_hash: str) -> dict:
    """Verify an immutable composite image digest and all source-lineage labels."""
    match = OCI.fullmatch(reference)
    if not match:
        raise ValueError('immutable composite OCI image reference required')
    try:
        raw = subprocess.run(['skopeo', 'inspect', '--raw', 'docker://' + reference],
                             capture_output=True, check=False, timeout=120)
        if raw.returncode or hashlib.sha256(raw.stdout).hexdigest() != match.group(1):
            raise ValueError('composite OCI registry manifest digest mismatch')
        config = subprocess.run(['skopeo', 'inspect', '--config', 'docker://' + reference],
                                capture_output=True, check=False, timeout=120)
        if config.returncode:
            raise ValueError('composite OCI image config inaccessible')
        labels = json.loads(config.stdout).get('config', {}).get('Labels') or {}
        expected_labels = {
            'org.opencontainers.image.revision': source_shas['ayahos-platform'],
            'com.ayahos.source.ayahos-core': source_shas['ayahos-core'],
            'com.ayahos.source.ayahos-workloads': source_shas['ayahos-workloads'],
            'com.ayahos.source.ayahos-platform': source_shas['ayahos-platform'],
            'com.ayahos.release-manifest-sha256': manifest_hash,
        }
        for label, expected in expected_labels.items():
            if labels.get(label) != expected:
                raise ValueError('composite OCI provenance label mismatch: ' + label)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('composite OCI registry verification unavailable') from exc
    return {
        'reference': reference,
        'manifest_sha256': match.group(1),
        'source_shas': {
            'ayahos-core': source_shas['ayahos-core'],
            'ayahos-workloads': source_shas['ayahos-workloads'],
            'ayahos-platform': source_shas['ayahos-platform'],
        },
        'release_manifest_sha256': manifest_hash,
        'registry_verified': True,
    }


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
    runtime_image = evidence.get('runtime_image')
    runtime_image_status = evidence.get('runtime_image_status', 'pending')
    if runtime_image_status not in ('pending', 'registry-verified'):
        raise ValueError('invalid runtime image status')
    if (runtime_image_status == 'pending') != (runtime_image is None):
        raise ValueError('runtime image status and evidence disagree')
    if runtime_image is not None:
        reference = runtime_image.get('reference')
        match = OCI.fullmatch(reference) if isinstance(reference, str) else None
        platform_sha = evidence['source_archives']['ayahos-platform']['git_sha']
        expected_sources = {
            'ayahos-core': components['ayahos-core']['git_sha'],
            'ayahos-workloads': components['ayahos-workloads']['git_sha'],
            'ayahos-platform': platform_sha,
        }
        if (not match or runtime_image.get('registry_verified') is not True
            or runtime_image.get('manifest_sha256') != match.group(1)
            or runtime_image.get('source_shas') != expected_sources
            or runtime_image.get('release_manifest_sha256') != evidence['manifest_sha256']):
            raise ValueError('invalid composite OCI evidence')

    runtime = evidence.get('runtime_context')
    if runtime is not None:
        if not isinstance(runtime, dict) or runtime.get('file') != 'runtime-context.tar':
            raise ValueError('invalid runtime context evidence')
        runtime_archive = directory / 'runtime-context.tar'
        if (runtime_archive.is_symlink() or
            runtime_archive.stat().st_size != runtime.get('bytes') or
            sha256(runtime_archive) != runtime.get('sha256') or
            runtime.get('source_manifest') != 'COMPOSITE-SOURCE-MANIFEST.json' or
            not ARTIFACT.fullmatch(runtime.get('source_manifest_sha256', ''))):
            raise ValueError('runtime context digest or provenance mismatch')
        checked_archive(runtime_archive)
        with tarfile.open(runtime_archive, 'r:') as tar:
            provenance_members = [
                entry for entry in tar.getmembers()
                if entry.name == 'COMPOSITE-SOURCE-MANIFEST.json'
            ]
            if len(provenance_members) != 1 or not provenance_members[0].isfile():
                raise ValueError('runtime context provenance member is missing')
            provenance = tar.extractfile(provenance_members[0])
            if provenance is None or sha256_bytes(provenance.read()) != runtime['source_manifest_sha256']:
                raise ValueError('runtime context provenance digest mismatch')

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
          oci_lock: Path | None = None,
          runtime_context: Path | None = None,
          runtime_image_ref: str | None = None) -> dict:
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
    runtime_image = None
    if runtime_image_ref is not None:
        runtime_image = inspect_runtime_image(
            runtime_image_ref,
            {
                'ayahos-core': manifest['components']['ayahos-core']['git_sha'],
                'ayahos-workloads': manifest['components']['ayahos-workloads']['git_sha'],
                'ayahos-platform': platform_head,
            },
            manifest_hash,
        )
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
        runtime_record = None
        if runtime_context is not None:
            provenance = runtime_context / 'COMPOSITE-SOURCE-MANIFEST.json'
            if provenance.is_symlink() or not provenance.is_file():
                raise ValueError('runtime context provenance is missing')
            runtime_archive = staging / 'runtime-context.tar'
            archive_directory(runtime_context, runtime_archive)
            checked_archive(runtime_archive)
            runtime_record = {
                'file': 'runtime-context.tar',
                'sha256': sha256(runtime_archive),
                'bytes': runtime_archive.stat().st_size,
                'source_manifest': 'COMPOSITE-SOURCE-MANIFEST.json',
                'source_manifest_sha256': sha256(provenance),
            }
        evidence = {'schema_version': 1, 'release_authorized': False,
                    'manifest_sha256': manifest_hash, 'source_archives': archives,
                    'runtime_context': runtime_record,
                    'runtime_image_status': 'registry-verified' if runtime_image else 'pending',
                    'runtime_image': runtime_image,
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
    parser.add_argument('--runtime-context', type=Path,
                        help='reviewed Core + Workloads context to archive as a separate source artifact')
    parser.add_argument('--runtime-image-ref',
                        help='immutable composite image reference, verified with skopeo')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.verify_only:
            verify_output(args.output)
            print('Verified artifact SHA-256 records; no release authorization')
        elif args.workspace:
            build(args.manifest, args.workspace, args.output, args.oci_lock, args.runtime_context, args.runtime_image_ref)
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
