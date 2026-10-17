"""Read local resource bodies or immutable Git objects; never run upstream code."""
import io
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess

from resource_catalog import require


def git(root, *args, data=None):
    result = subprocess.run(['git', '--literal-pathspecs', '-c', 'core.hooksPath=/dev/null',
                             '-c', 'core.fsmonitor=false', '-C', str(root), *args],
                            input=data, capture_output=True, timeout=60,
                            env={**{k: v for k, v in os.environ.items() if not k.startswith('GIT_')},
                                 'GIT_TERMINAL_PROMPT': '0'})
    if result.returncode:
        operation = next((arg for arg in args if arg in ('fetch', 'init', 'remote', 'rev-parse', 'ls-tree', 'cat-file', 'clone', 'bundle', 'push')), 'read')
        reason = 'Cannot read the requested Git source or fixed commit'
        if b'Failed to connect' in result.stderr or b'Could not resolve' in result.stderr:
            reason = 'Network or configured proxy is unavailable; check the Git connection settings'
        raise ValueError('Git ' + operation + ' failed: ' + reason)
    return result.stdout


def local_files(root):
    root = Path(root)
    require(root.exists(), 'Resource body is missing: ' + str(root))
    base = root.parent.resolve() if root.is_file() else root.resolve()
    files = {}
    for file in [root] if root.is_file() else sorted(root.rglob('*')):
        relative = file.relative_to(root.parent if root.is_file() else root)
        if any(part in ('.git', '__pycache__', '.DS_Store') for part in relative.parts):
            continue
        actual = file.resolve()
        require(actual.is_relative_to(base), 'Resource link escapes its package: ' + str(relative))
        if file.is_dir():
            require(not file.is_symlink(), 'Directory links are not resource bodies: ' + str(relative))
            continue
        require(actual.is_file(), 'Resource body is not a regular file: ' + str(relative))
        files[relative.as_posix()] = (actual.read_bytes(), bool(actual.stat().st_mode & 0o111))
    require(files, 'Resource body is empty: ' + str(root))
    return files


def git_files(root, commit, selected):
    selected = PurePosixPath(selected).as_posix()
    listing = git(root, 'ls-tree', '-r', '-z', commit, '--', selected)
    rows = []
    for row in listing.split(b'\0'):
        if not row:
            continue
        meta, raw_path = row.split(b'\t', 1)
        mode, kind, oid = meta.decode().split()
        require(kind == 'blob' and mode in ('100644', '100755', '120000'),
                'Nested submodules or special Git entries need a separate resource declaration')
        full = raw_path.decode()
        name = PurePosixPath(full).name if full == selected else str(PurePosixPath(full).relative_to(selected))
        rows.append((name, mode, oid))
    require(rows, 'Pinned resource path is missing from the Git commit: ' + selected)
    blobs = io.BytesIO(git(root, 'cat-file', '--batch', data=''.join(row[2] + '\n' for row in rows).encode()))
    raw = {}
    for name, mode, oid in rows:
        header = blobs.readline().decode().split()
        require(len(header) == 3 and header[:2] == [oid, 'blob'], 'Pinned Git blob is unavailable')
        content = blobs.read(int(header[2]))
        require(blobs.read(1) == b'\n', 'Invalid Git object response')
        raw[name] = (content, mode)
    def resolve(name, seen):
        require(name in raw and name not in seen, 'Missing or cyclic package link: ' + name)
        content, mode = raw[name]
        if mode != '120000':
            return content, mode == '100755'
        target = content.decode()
        require(not target.startswith('/'), 'Absolute package link: ' + name)
        target = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
        require(target != '..' and not target.startswith('../'), 'Package link escapes its root: ' + name)
        return resolve(target, seen | {name})
    return {name: resolve(name, set()) for name in raw}


class Sources:
    """Reuse each explicitly prepared/fetched repository within one build only."""
    def __init__(self, directory, prepared=None, fetch=False):
        self.directory, self.prepared, self.fetch = Path(directory), dict(prepared or {}), fetch
        self.resolved = {}

    def repository(self, repo, commit, local=None):
        key = repo, commit
        if key in self.resolved:
            return self.resolved[key]
        root = self.prepared.get(repo)
        if root is None and local is not None and (Path(local) / '.git').exists():
            root = Path(local)
        if root is None:
            require(self.fetch, 'Prepare source with --source ' + repo + '=DIR or explicitly use --fetch')
            root = self.directory / repo.replace('/', '--') / commit
            root.mkdir(parents=True)
            git(root, 'init', '--quiet')
            git(root, 'remote', 'add', 'origin', 'https://github.com/' + repo + '.git')
            git(root, '-c', 'protocol.file.allow=never', 'fetch', '--quiet', '--depth=1', 'origin', commit)
        root = Path(root).resolve()
        require(Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == root,
                'Prepared source must be a repository root')
        remote = git(root, 'remote', 'get-url', 'origin').decode().strip()
        match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?', remote)
        require(match and match[1].lower() == repo.lower(), 'Prepared source has the wrong repository identity: ' + repo)
        require(git(root, 'rev-parse', commit + '^{commit}').decode().strip() == commit, 'Fixed commit is unavailable')
        self.resolved[key] = root
        return root

    def files(self, repo, commit, selected, local=None):
        return git_files(self.repository(repo, commit, local), commit, selected)

    def is_file(self, repo, commit, selected):
        root = self.repository(repo, commit)
        return git(root, 'cat-file', '-t', commit + ':' + selected).strip() == b'blob'
