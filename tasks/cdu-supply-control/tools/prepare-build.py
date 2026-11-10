#!/usr/bin/env python3
"""Restore the pinned Harbor task; download dependencies outside the delivery."""
import argparse
import hashlib
import json
import shutil
import stat
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_path(name):
    return bool(name) and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and '\\' not in name


def inventory(root):
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Symlink not permitted: {path}')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = {
                'sha256': digest(path), 'mode': stat.S_IMODE(path.stat().st_mode)}
    return files


def validate(delivery):
    manifest = json.loads((delivery / 'metadata/file_manifest.json').read_text())['files']
    layout = json.loads((delivery / 'metadata/offline-build-layout.json').read_text())
    dependencies = json.loads((delivery / 'metadata/build-dependencies.json').read_text())['files']
    expected = set(manifest) | {'metadata/file_manifest.json'}
    if set(inventory(delivery)) != expected:
        raise ValueError('Delivery file set differs from manifest')
    for name, ref in manifest.items():
        if not safe_path(name) or (delivery / name).stat().st_size != ref['bytes'] or digest(delivery / name) != ref['sha256']:
            raise ValueError(f'Delivery integrity failure: {name}')
    dep_map = {d['path']: d for d in dependencies}
    if len(dep_map) != len(dependencies) or set(dep_map) & set(manifest):
        raise ValueError('Duplicate or bundled build dependency')
    for name, ref in dep_map.items():
        if (not safe_path(name) or not name.endswith(('.whl', '.deb')) or
                len(ref['sha256']) != 64 or any(c not in '0123456789abcdef' for c in ref['sha256']) or
                not ref['urls'] or any(not u.startswith('https://') for u in ref['urls'])):
            raise ValueError(f'Invalid dependency: {name}')
    logical = {**manifest, **dep_map}
    task_prefix = 'tasks/cdu-supply-control/'
    reconstructed = {n[len(task_prefix):]: ref['sha256'] for n, ref in logical.items() if n.startswith(task_prefix)}
    for name, targets in layout['shared'].items():
        if not safe_path(name) or name not in logical:
            raise ValueError(f'Missing shared source: {name}')
        for target in targets:
            if not safe_path(target) or target in reconstructed:
                raise ValueError(f'Invalid or duplicate layout target: {target}')
            reconstructed[target] = logical[name]['sha256']
    if any(not safe_path(n) for n in layout['task_files']):
        raise ValueError('Unsafe task path')
    if reconstructed != {n: ref['sha256'] for n, ref in layout['task_files'].items()}:
        raise ValueError('Task layout differs from pinned files/dependencies')
    return layout, dependencies


def download(ref, target, cache=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    if cache is not None:
        shutil.copyfile(cache / ref['sha256'], target)
        sources = ['local-sha256-cache']
    else:
        sources = ref['urls']
    errors = []
    for url in sources:
        try:
            if cache is None:
                with urllib.request.urlopen(url, timeout=60) as response, target.open('wb') as out:
                    shutil.copyfileobj(response, out, length=1024 * 1024)
            if target.stat().st_size != ref['bytes'] or digest(target) != ref['sha256']:
                raise ValueError('size/SHA-256 mismatch')
            return url
        except (OSError, ValueError, urllib.error.URLError) as error:
            errors.append(f'{url}: {error}')
            target.unlink(missing_ok=True)
    raise ValueError(f"Cannot restore {ref['path']}: " + '; '.join(errors))


def prepare(delivery, destination, cache=None, verify_only=False, pull_images=False):
    layout, dependencies = validate(delivery)
    if verify_only:
        return {'delivery_integrity': 'passed', 'task_layout': 'passed', 'downloads': 'not run'}
    if destination is None:
        raise ValueError('A new destination is required')
    destination = destination.absolute()
    if destination.is_symlink() or destination.exists() or destination.resolve().is_relative_to(delivery.resolve()):
        raise ValueError('Choose a new destination outside the delivery')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        work = Path(temporary)
        downloads = {}
        for ref in dependencies:
            target = work / 'dependencies' / ref['path']
            downloads[ref['path']] = download(ref, target, cache)
        task = work / 'task'
        shutil.copytree(delivery / 'tasks/cdu-supply-control', task)
        for ref in dependencies:
            prefix = 'tasks/cdu-supply-control/'
            if ref['path'].startswith(prefix):
                target = task / ref['path'][len(prefix):]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(work / 'dependencies' / ref['path'], target)
        for source, targets in layout['shared'].items():
            origin = work / 'dependencies' / source if source in downloads else delivery / source
            for relative in targets:
                target = task / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin, target)
        for relative, metadata in layout['task_files'].items():
            (task / relative).chmod(metadata['mode'])
        for directory in (task, *(p for p in task.rglob('*') if p.is_dir())):
            directory.chmod(0o755)
        if inventory(task) != layout['task_files']:
            raise ValueError('Reconstructed task differs from pinned bytes/modes')
        if pull_images:
            images = json.loads((delivery / 'metadata/image_manifest.json').read_text())
            subprocess.run(['docker', 'pull', '--platform', 'linux/amd64', images['task_base']], check=True)
        if destination.exists() or destination.is_symlink():
            raise ValueError('Destination appeared during preparation')
        task.rename(destination)
    return {'task_reconstruction': 'passed', 'downloads': downloads, 'image_pull': pull_images}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, nargs='?')
    parser.add_argument('--asset-dir', type=Path, help='Optional SHA-256 cache for pinned dependencies')
    parser.add_argument('--verify-only', action='store_true', help='Validate shipped bytes/layout without downloading')
    parser.add_argument('--pull-images', action='store_true', help='Pull the pinned task base image with Docker')
    args = parser.parse_args()
    try:
        result = prepare(Path(__file__).resolve().parents[1], args.destination, args.asset_dir,
                         args.verify_only, args.pull_images)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Preparation failed: {error}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
