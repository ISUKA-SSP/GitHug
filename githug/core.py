"""Non-destructive repository browsing and snapshot creation."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime
from uuid import uuid4

class ComparisonCancelled(Exception):
    pass

class GitError(RuntimeError):
    pass

def git(*args, cwd=None, env=None, input_text=None, allowed_returncodes=(0,)):
    try:
        result = subprocess.run(['git', *map(str, args)], cwd=cwd, capture_output=True,
                                encoding='utf-8', errors='replace', timeout=180, input=input_text,
                                env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', **(env or {})},
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except FileNotFoundError as exc:
        raise GitError('Gitが見つかりません。Git for Windowsをインストールしてください。') from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError('通信が時間内に終わりませんでした。接続を確認して再度お試しください。') from exc
    if result.returncode not in allowed_returncodes:
        raise GitError(result.stderr.strip() or 'Gitの操作を完了できませんでした。')
    return result.stdout

def validate_url(url):
    match = re.fullmatch(r'https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?', url.strip())
    if not match:
        raise ValueError('https://github.com/所有者/プロジェクト の形式で入力してください。')
    owner, name = match.groups()
    if owner in ('.', '..') or name in ('.', '..'):
        raise ValueError('プロジェクト名が正しくありません。')
    return f'https://github.com/{owner}/{name}.git', f'{owner}__{name}'

class Project:
    def __init__(self, root, url):
        self.url, self.name = validate_url(url)
        self.base = Path(root) / self.name
        self.cache = self.base / 'history.git'

    def refresh(self):
        self.base.mkdir(parents=True, exist_ok=True)
        if not self.cache.exists():
            # Clone into a temporary directory: interrupted downloads cannot become a valid cache.
            temporary = self.base / ('download-' + uuid4().hex)
            git('clone', '--mirror', self.url, temporary)
            temporary.rename(self.cache)
        else:
            git('fetch', '--prune', 'origin', cwd=self.cache)
        return self.history()

    def history(self):
        raw = git('log', '--all', '--date=iso-strict', '--pretty=format:%H%x09%P%x09%aI%x09%D%x09%s', '-n', '400', cwd=self.cache)
        return [dict(zip(('sha', 'parents', 'date', 'refs', 'message'), line.split('\t', 4)))
                for line in raw.splitlines() if line]

    def snapshot(self, sha):
        if not re.fullmatch(r'[0-9a-f]{40,64}', sha):
            raise ValueError('履歴の識別番号が正しくありません。')
        git('cat-file', '-e', sha + '^{commit}', cwd=self.cache)
        folder = self.base / 'snapshots' / (datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + sha[:8] + '_' + uuid4().hex[:6])
        folder.parent.mkdir(parents=True, exist_ok=True)
        # Independent clone; no checkout/reset/pull ever runs in the user's work folder.
        git('clone', '--no-hardlinks', '--no-checkout', self.cache, folder)
        git('checkout', '--detach', sha, cwd=folder)
        # Replace local-cache remote with the real origin for future editing workflows.
        git('remote', 'set-url', 'origin', self.url, cwd=folder)
        record = {'folder': str(folder), 'sha': sha, 'created': datetime.now().isoformat(), 'kind': 'snapshot'}
        metadata = self.base / 'records'
        metadata.mkdir(exist_ok=True)
        (metadata / (folder.name + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        return str(folder)

    def folder_versions(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((self.base / 'records').glob('*.json'), reverse=True)]

    def snapshots(self):
        return [record for record in self.folder_versions() if record.get('kind') != 'work']

    def compare(self, sha, folder, progress=None, cancelled=None):
        """Compare tracked commit contents with a folder without modifying that folder."""
        folder = Path(folder)
        if not folder.is_dir():
            raise ValueError('比較するフォルダーが見つかりません。')
        def report(stage, count, total, name):
            if cancelled and cancelled():
                raise ComparisonCancelled()
            if progress:
                progress(stage, count, total, name)
        report('履歴のファイル一覧を取得', 0, None, '')
        entries = list(filter(None, git('ls-tree', '-r', '-z', sha, cwd=self.cache).split('\0')))
        differences = []
        known = set()
        for index, entry in enumerate(entries):
            header, name = entry.split('\t', 1)
            mode, kind, blob = header.split()
            report('履歴と内容を比較', index, len(entries), name)
            known.add(name)
            path = folder / name
            if kind != 'blob' or mode == '120000':
                differences.append(('要確認（リンク／外部参照）', name))
            elif not path.exists():
                differences.append(('手元にない', name))
            elif path.is_symlink() or not path.is_file():
                differences.append(('種類が異なる', name))
            elif git('hash-object', '--no-filters', '--', path.absolute(), cwd=self.cache).strip() != blob:
                differences.append(('内容が異なる', name))
        report('履歴と内容を比較', len(entries), len(entries), '')
        scanned = 0
        for parent, dirs, files in os.walk(folder, followlinks=False):
            report('手元だけのファイルを確認', scanned, None, str(Path(parent).relative_to(folder)))
            dirs[:] = [d for d in dirs if d != '.git' and not (Path(parent) / d).is_symlink()]
            for name in files:
                relative = (Path(parent) / name).relative_to(folder).as_posix()
                scanned += 1
                report('手元だけのファイルを確認', scanned, None, relative)
                if relative not in known:
                    differences.append(('手元のみ', relative))
        report('比較完了', scanned, None, '')
        return differences
