"""Reconnect a project to storage the user has already moved or copied."""
import json
import os
from pathlib import Path

from .core import GitError, git, validate_url
from .notes import folder_key
from .restoration import no_links
from .updating import atomic_json


def relocate_project(project, destination, work, other_bases):
    old = project.base.resolve()
    destination = Path(destination).absolute()
    no_links(destination)
    new = destination.resolve(strict=True)
    if new == old:
        return new, list(work)

    for base in (old, *other_bases):
        if new == base or new in base.parents or base in new.parents:
            raise ValueError('今の保存先や別のプロジェクトと重ならないフォルダーを選んでください。')

    cache = new / 'history.git'
    no_links(cache / 'config')
    try:
        if git('rev-parse', '--is-bare-repository', cwd=cache).strip() != 'true':
            raise ValueError('履歴の保管形式が異なります。')
        remote = git('config', '--file', cache / 'config', '--get', 'remote.origin.url').strip()
        origin, _ = validate_url(remote)
    except (GitError, OSError, ValueError) as exc:
        raise ValueError('移動先の履歴を確認できません。history.git が入っているプロジェクトフォルダーを選んでください。') from exc
    if origin.casefold() != project.url.casefold():
        raise ValueError('選んだフォルダーは別のGitHubプロジェクトの保存先です。')

    def moved_path(value):
        if not isinstance(value, str) or not value or not Path(value).is_absolute():
            return value
        path = Path(os.path.abspath(value))
        try:
            return str(new / path.relative_to(old))
        except ValueError:
            return value

    changes = []

    def read(path):
        no_links(path)
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError(f'管理データの形式を確認してください。\n{path}')
        return data

    groups = {
        'records/*.json': ('folder', 'restored_from', 'restored_original_folder'),
        'backups/*.json': ('folder', 'archive'),
        'local-records/*/record.json': ('folder',),
        'outbox/*/send.json': ('folder',),
        'updates/*.json': ('original', 'previous', 'staged', 'backup'),
    }
    for pattern, fields in groups.items():
        no_links(new / pattern.split('/')[0])
        for path in new.glob(pattern):
            data = read(path)
            if pattern == 'updates/*.json' and data.get('state') not in ('completed', 'rolled_back'):
                raise ValueError(f'完了していないフォルダー更新の記録があります。\n{path}')
            updated = {**data, **{key: moved_path(data[key]) for key in fields if key in data}}
            if updated != data:
                changes.append((path, data, updated))

    notes_path = new / 'personal_notes.json'
    no_links(notes_path)
    if notes_path.exists():
        data = read(notes_path)
        folders = data.get('folders', {})
        if not isinstance(folders, dict) or not isinstance(data.get('history', {}), dict):
            raise ValueError(f'自分用メモの形式を確認してください。\n{notes_path}')
        mapped = {}
        for key, value in folders.items():
            path = moved_path(key)
            key = folder_key(path) if path != key else key
            if key in mapped and mapped[key] != value:
                raise ValueError(f'移動元と移動先でフォルダーのメモが重複しています。\n{key}')
            mapped[key] = value
        if mapped != folders:
            changes.append((notes_path, data, {**data, 'folders': mapped}))

    # Validate all metadata before writing. Each write is atomic, and the
    # transformation can be retried if the app exits before switching settings.
    written = []
    try:
        for path, data, updated in changes:
            atomic_json(path, updated)
            written.append((path, data))
    except OSError:
        for path, data in reversed(written):
            atomic_json(path, data)
        raise

    return new, [moved_path(path) for path in work]
