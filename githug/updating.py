"""Explicit, staged folder replacement with backups and rollback."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from uuid import uuid4
import zipfile
from .core import git, GitError


class UpdateConflict(RuntimeError):
    pass


class UpdateNotAllowed(UpdateConflict):
    pass


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def remove_temporary(path):
    def writable(function, filename, error):
        os.chmod(filename, stat.S_IWRITE | stat.S_IREAD)
        function(filename)
    shutil.rmtree(path, onerror=writable)


def checked_folder(project, folder):
    path = Path(folder).absolute()
    # A junction/symlink in any component can redirect the replacement target.
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part.lstat(), 'st_file_attributes', 0) & 0x400:
            raise UpdateConflict('リンク先のフォルダーは更新できません。別フォルダーへのコピーを使ってください。')
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise UpdateConflict('更新先がフォルダーではありません。')
    protected = (Path.home().resolve(), Path.cwd().resolve(), project.base.resolve(), project.base.parent.resolve())
    if any(path == p or path in p.parents for p in protected):
        raise UpdateConflict('アプリ本体・保存先全体・ホームフォルダーは更新先にできません。')
    for name in ('history.git', 'records', 'backups', 'updates'):
        protected_path = (project.base / name).resolve()
        if path == protected_path or protected_path in path.parents:
            raise UpdateConflict('GitHugの管理用フォルダーは入れ替えできません。')
    if path == Path(path.anchor):
        raise UpdateConflict('ドライブ全体は更新先にできません。')
    return path


def inventory(folder, progress=None):
    """Full bytes + names + timestamps, including ignored files and .git; never follow links."""
    root = Path(folder)
    result = []
    for parent, dirs, files in os.walk(root, followlinks=False, onerror=lambda error: (_ for _ in ()).throw(error)):
        for name in sorted(dirs + files):
            path = Path(parent) / name
            info = path.lstat()
            relative = path.relative_to(root).as_posix()
            if progress:
                progress('変更を確認: ' + relative)
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise UpdateConflict('リンクを含むため入れ替えできません: ' + relative + '\n別フォルダーへのコピーを使ってください。')
            if stat.S_ISDIR(info.st_mode):
                result.append((relative, 'directory', info.st_mtime_ns))
            elif stat.S_ISREG(info.st_mode):
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    before = os.fstat(stream.fileno())
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                    after = os.fstat(stream.fileno())
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise UpdateConflict('確認中にファイルが変更されました。関連アプリを閉じてやり直してください。')
                result.append((relative, 'file', after.st_size, after.st_mtime_ns, digest.hexdigest()))
            else:
                raise UpdateConflict('通常のファイルではないため更新できません: ' + relative)
    return tuple(sorted(result))


def record_for_folder(project, folder):
    metadata = project.base / 'records'
    for path in metadata.glob('*.json'):
        record = json.loads(path.read_text(encoding='utf-8'))
        if Path(record['folder']).resolve() == Path(folder).resolve():
            return path, record
    return None, None


@dataclass
class UpdatePlan:
    folder: Path
    sha: str
    baseline: str | None
    differences: list
    unknown: bool
    fingerprint: tuple
    record_path: Path | None
    record: dict | None
    local_files: tuple
    local_directories: tuple
    collisions: tuple


def require_update_permission(project, folder, baseline):
    _, record = record_for_folder(project, folder)
    if not record or record.get('sha') != baseline:
        raise UpdateNotAllowed('この作業用フォルダーは同じ場所への更新が無効です。作成元を確認し、右クリックから更新を有効にするか、別フォルダーへコピーしてください。')
    if record.get('kind', 'snapshot') != 'snapshot' and not record.get('update_allowed', False):
        raise UpdateNotAllowed('この作業用フォルダーは同じ場所への更新が無効です。右クリックから明示的に有効にするか、別フォルダーへコピーしてください。')


def authorize_update(project, plan):
    target = checked_folder(project, plan.folder)
    if not plan.baseline or plan.unknown:
        raise UpdateNotAllowed('作成元の版が分からないフォルダーは有効にできません。')
    if inventory(target) != plan.fingerprint:
        raise UpdateConflict('確認後に内容が変わりました。もう一度確認してください。')
    path, record = record_for_folder(project, target)
    if record and record.get('kind', 'snapshot') == 'snapshot': return
    path = path or project.base / 'records' / ('work-' + uuid4().hex + '.json')
    atomic_json(path, {**(record or {}), 'folder': str(target), 'sha': plan.baseline, 'kind': 'work', 'update_allowed': True})


def disable_update(project, folder):
    path, record = record_for_folder(project, folder)
    if path and record.get('kind') == 'work':
        atomic_json(path, {**record, 'update_allowed': False})


def tree_paths(project, sha):
    raw = git('ls-tree', '-r', '-z', '--name-only', sha, cwd=project.cache)
    return set(filter(None, raw.split('\0')))


def local_additions(project, baseline, sha, fingerprint):
    if not baseline:
        return (), (), ()
    old_files = tree_paths(project, baseline)
    new_files = tree_paths(project, sha)
    # Windows paths are case-insensitive. Refuse collisions even when tested elsewhere.
    old_keys = {name.casefold() for name in old_files}
    new_keys = {name.casefold() for name in new_files}
    def parents(name):
        parts = name.split('/')
        return ['/'.join(parts[:i]) for i in range(1, len(parts))]
    old_directories = {parent for name in old_keys for parent in parents(name)}
    new_directories = {parent for name in new_keys for parent in parents(name)}
    files, directories, conflicts = [], [], []
    for row in fingerprint:
        name, kind = row[:2]
        key = name.casefold()
        if key == '.git' or key.startswith('.git/'):
            continue
        if key in old_keys or any(parent in old_keys for parent in parents(key)):
            continue
        if kind == 'directory':
            if key in old_directories:
                continue
            directories.append(name)
            if key in new_keys or any(parent in new_keys for parent in parents(key)):
                conflicts.append(name)
        else:
            files.append(name)
            if key in new_keys or key in new_directories or any(parent in new_keys for parent in parents(key)):
                conflicts.append(name)
    return tuple(files), tuple(directories), tuple(conflicts)


def copy_local_additions(source, destination, plan, progress=None):
    # All collisions were checked before copying. Also refuse a link introduced by checkout.
    for name in (*plan.local_directories, *plan.local_files):
        target = destination / name
        for ancestor in (target, *target.parents):
            if ancestor == destination.parent: break
            if ancestor.is_symlink() or (ancestor.exists() and getattr(ancestor.lstat(), 'st_file_attributes', 0) & 0x400):
                raise UpdateConflict('手元のファイルの引き継ぎ先にリンクがあります: ' + name)
    for name in sorted(plan.local_directories, key=lambda value: value.count('/')):
        (destination / name).mkdir(parents=True, exist_ok=True)
    for name in plan.local_files:
        if progress: progress('手元だけのファイルを引き継いでいます: ' + name)
        target = destination / name
        if target.exists():
            raise UpdateConflict('引き継ぎ先と衝突しています: ' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)


def inspect_update(project, folder, sha, progress=None, *, for_authorization=False):
    if not re.fullmatch(r'[0-9a-f]{40,64}', sha):
        raise ValueError('履歴の識別番号が正しくありません。')
    git('cat-file', '-e', sha + '^{commit}', cwd=project.cache)
    target = checked_folder(project, folder)
    for journal in (project.base / 'updates').glob('*.json'):
        entry = json.loads(journal.read_text(encoding='utf-8'))
        if entry.get('state') not in ('completed', 'rolled_back'):
            raise UpdateConflict('未完了の更新記録があります。追加の入れ替えは行いません。\n' + str(journal) +
                                 '\n記録の original / previous / staged の場所を確認してください。')
    record_path, record = record_for_folder(project, target)
    baseline = record.get('sha') if record else None
    unknown = False
    # Only accept a work folder's HEAD when it belongs to this exact GitHub project.
    if not baseline and (target / '.git').is_dir():
        try:
            remote = git('remote', 'get-url', 'origin', cwd=target).strip().removesuffix('.git').rstrip('/')
            if remote.casefold() == project.url.removesuffix('.git').casefold():
                candidate = git('rev-parse', 'HEAD', cwd=target).strip()
                git('cat-file', '-e', candidate + '^{commit}', cwd=project.cache)
                baseline = candidate
        except GitError:
            pass
    if not baseline:
        raise UpdateNotAllowed('このフォルダーの作成元の版が分からないため、同じ場所への更新は行いません。新しいフォルダーへコピーしてください。')
    if not for_authorization:
        require_update_permission(project, target, baseline)
    fingerprint = inventory(target, progress)
    if baseline:
        if (target / '.git').is_dir():
            # Git normalizes CRLF according to the repository's attributes on Windows.
            # Disable external diff/textconv and optional index writes during inspection.
            with tempfile.TemporaryDirectory(prefix='inspect-', dir=project.base) as inspection:
                index = Path(inspection) / 'index'
                if (target / '.git' / 'index').exists():
                    shutil.copyfile(target / '.git' / 'index', index)
                read_env = {'GIT_INDEX_FILE': str(index), 'GIT_OPTIONAL_LOCKS': '0'}
                changes = git('--no-optional-locks', 'diff', '--no-ext-diff', '--no-textconv',
                              '--no-renames', '--name-status', '-z', baseline, '--', cwd=target, env=read_env).split('\0')
                differences = [("手元の変更（" + changes[i] + "）", changes[i+1])
                               for i in range(0, len(changes)-1, 2)]
                for options, label in ((['--others', '--exclude-standard'], '手元だけのファイル'),
                                       (['--others', '--ignored', '--exclude-standard'], '手元だけのファイル（無視対象も含む）')):
                    names = git('--no-optional-locks', 'ls-files', *options, '-z', cwd=target, env=read_env)
                    differences.extend((label, name) for name in names.split('\0') if name)
        else:
            differences = project.compare(baseline, target, progress=(lambda stage, count, total, name:
                                          progress(f'{stage}: {count} 件 {name}')) if progress else None)
        if (target / '.git').is_dir():
            try:
                if git('rev-parse', 'HEAD', cwd=target).strip() != baseline:
                    differences.append(('手もとにした履歴が変更されています', '.git'))
                refs = git('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads', 'refs/stash', cwd=target)
                for line in refs.splitlines():
                    ref, commit = line.split(' ', 1)
                    try:
                        upstream = git('rev-parse', '--verify', ref, cwd=project.cache).strip()
                    except GitError:
                        upstream = None
                    if upstream != commit:
                        differences.append(('手元に保持された枝・履歴', ref))
            except GitError:
                differences.append(('Git管理情報の状態を確認できません', '.git'))
    else:
        unknown = True
        differences = [('もとにした履歴が不明（変更の有無を判定できません）', '')]
    if inventory(target, progress) != fingerprint:
        raise UpdateConflict('確認中にフォルダーの内容が変更されました。処理中のアプリを閉じてやり直してください。')
    files, directories, collisions = local_additions(project, baseline, sha, fingerprint)
    return UpdatePlan(target, sha, baseline, differences, unknown, fingerprint, record_path, record, files, directories, collisions)


def archive_folder(folder, destination, progress=None):
    temporary = destination.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
            for parent, dirs, files in os.walk(folder, followlinks=False):
                for name in sorted(dirs + files):
                    path = Path(parent) / name
                    relative = path.relative_to(folder).as_posix()
                    if progress:
                        progress('保管しています: ' + relative)
                    archive.write(path, relative + ('/' if path.is_dir() else ''))
        temporary.replace(destination)
    except BaseException:
        if temporary.exists(): temporary.unlink()
        raise


def apply_update(project, plan, keep_backup=True, progress=None, preserve_local_only=True):
    """Prepare first, then rename on the same filesystem. Never copy over a live target."""
    target = checked_folder(project, plan.folder)
    require_update_permission(project, target, plan.baseline)
    if target != plan.folder or inventory(target, progress) != plan.fingerprint:
        raise UpdateConflict('確認後にフォルダーの内容が変わりました。変更は行いませんでした。もう一度確認してください。')
    if preserve_local_only and plan.unknown:
        raise UpdateConflict('もとにした履歴が不明なため、手元だけのファイルを判別できません。別フォルダーへのコピー、または保管付きの完全な入れ替えを選んでください。')
    if preserve_local_only and plan.collisions:
        raise UpdateConflict('手元だけのファイルと選んだ版が衝突しています。更新は行いませんでした。\n' +
                             '\n'.join(plan.collisions[:20]) + '\n別フォルダーへのコピーか、ファイルの移動後に再度更新してください。')
    token = uuid4().hex
    staged = target.parent / ('.githug-staged-' + token)
    previous = target.parent / ('.githug-previous-' + token)
    journal_path = project.base / 'updates' / (token + '.json')
    journal = {'original': str(target), 'previous': str(previous), 'staged': str(staged),
               'sha': plan.sha, 'state': 'preparing', 'preserve_local_only': preserve_local_only}
    backup = None
    swapped = False
    moved = False
    metadata_written = False
    warning = ''
    metadata_path = plan.record_path or (project.base / 'records' / ('work-' + token + '.json'))
    try:
        if progress: progress('選んだ版を準備しています…')
        git('clone', '--no-hardlinks', '--no-checkout', project.cache, staged)
        git('checkout', '--detach', plan.sha, cwd=staged)
        git('remote', 'set-url', 'origin', project.url, cwd=staged)
        if preserve_local_only:
            copy_local_additions(target, staged, plan, progress)
        if inventory(target, progress) != plan.fingerprint:
            raise UpdateConflict('準備中にファイルが変更されました。変更は行いませんでした。もう一度確認してください。')
        require_update_permission(project, target, plan.baseline)
        atomic_json(journal_path, journal)
        target.rename(previous)
        moved = True
        journal['state'] = 'previous_moved'
        atomic_json(journal_path, journal)
        if inventory(previous, progress) != plan.fingerprint:
            raise UpdateConflict('入れ替え直前にファイルが変更されました。元の場所へ戻します。')
        if keep_backup:
            directory = project.base / 'backups'
            directory.mkdir(parents=True, exist_ok=True)
            backup = directory / (datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + token[:8] + '.zip')
            archive_folder(previous, backup, progress)
            atomic_json(backup.with_suffix('.json'), {'folder': str(target), 'sha': plan.baseline,
                        'created': datetime.now().isoformat(), 'archive': str(backup)})
            journal['backup'] = str(backup)
        if inventory(previous, progress) != plan.fingerprint:
            raise UpdateConflict('保管中にファイルが変更されました。元の場所へ戻します。')
        staged.rename(target)
        swapped = True
        journal['state'] = 'installed'
        atomic_json(journal_path, journal)
        updated = {**(plan.record or {}), 'folder': str(target), 'sha': plan.sha,
                   'created': datetime.now().isoformat(), 'kind': plan.record.get('kind', 'snapshot') if plan.record else 'work',
                   'previous_sha': plan.baseline}
        atomic_json(metadata_path, updated)
        metadata_written = True
        journal['state'] = 'completed'
        atomic_json(journal_path, journal)
    except BaseException as exc:
        try:
            if moved:
                if swapped: target.rename(staged)
                previous.rename(target)
            if metadata_written:
                if plan.record is None: metadata_path.unlink()
                else: atomic_json(metadata_path, plan.record)
            if journal_path.exists():
                journal['state'] = 'rolled_back'
                atomic_json(journal_path, journal)
        except BaseException as rollback_error:
            raise UpdateConflict('入れ替えを完了できず、元へ戻す処理にも失敗しました。ファイルは削除していません。\n'
                                 + str(journal_path) + '\n元の内容: ' + str(previous) + '\n新しい内容: ' + str(staged)
                                 + '\n' + str(rollback_error)) from exc
        if staged.exists():
            try: remove_temporary(staged)
            except OSError: pass
        raise
    try:
        remove_temporary(previous)
    except OSError:
        warning = '更新前の一時フォルダーを片付けられませんでした: ' + str(previous)
    return {'folder': str(target), 'sha': plan.sha, 'backup': str(backup) if backup else '', 'warning': warning, 'retained': len(plan.local_files) if preserve_local_only else 0}
