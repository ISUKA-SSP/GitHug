"""Personal annotations live outside all reproduced source folders."""
import json
import os
from pathlib import Path
import re
from .updating import atomic_json


def folder_key(folder):
    return os.path.normcase(str(Path(folder).resolve()))


class Notes:
    def __init__(self, project_base):
        self.path = Path(project_base) / 'personal_notes.json'
        self.reload()

    def reload(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            data = {'history': {}, 'folders': {}}
        if not isinstance(data, dict) or any(not isinstance(data.get(scope, {}), dict) for scope in ('history', 'folders')):
            raise ValueError('自分用メモのファイル形式を確認してください: ' + str(self.path))
        self.data = data

    def key(self, scope, identity):
        if scope == 'history':
            if not re.fullmatch(r'[0-9a-f]{40,64}', identity): raise ValueError('履歴番号が正しくありません。')
            return identity
        if scope == 'folders': return folder_key(identity)
        raise ValueError('メモの保存先が正しくありません。')

    def get(self, scope, identity):
        value = self.data.get(scope, {}).get(self.key(scope, identity), '')
        if not isinstance(value, str): raise ValueError('メモの内容を確認してください: ' + str(self.path))
        return value

    def set(self, scope, identity, text):
        # Merge against the latest file rather than overwriting the other list's notes.
        self.reload()
        key = self.key(scope, identity)
        section = self.data.setdefault(scope, {})
        if text.strip(): section[key] = text
        else: section.pop(key, None)
        atomic_json(self.path, self.data)


def short_note(text):
    return ' '.join(text.split())[:100]
