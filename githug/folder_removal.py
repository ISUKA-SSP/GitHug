"""Guard folder recycling and hide only the selected folder's local listing record."""
import json
import os
from pathlib import Path
from .platform_support import app_directory
from .updating import checked_folder, atomic_json, UpdateConflict
from .recycle import recycle_folder

class RemovalError(RuntimeError):
    pass


def folder_key(folder):return os.path.normcase(str(Path(folder).resolve()))


def checked_removal(project,folder,projects=()):
    try:path=checked_folder(project,folder)
    except UpdateConflict as exc:
        raise RemovalError(str(exc).replace('更新先','削除対象').replace('更新できません','削除できません').replace('入れ替えできません','削除できません').replace('別フォルダーへのコピーを使ってください。','')) from None
    # Protect the running installation, settings, and every registered project's management data.
    app=app_directory().resolve()
    homes=[Path.home()/name for name in ('Desktop','Documents','Downloads','Pictures','Music','Videos','OneDrive')]
    containers=[app,*homes]
    for name in ('SystemRoot','ProgramFiles','ProgramFiles(x86)','APPDATA','LOCALAPPDATA','OneDrive'):
        value=os.environ.get(name)
        if value:
            root=Path(value).resolve()
            protected_tree=name in ('SystemRoot','ProgramFiles','ProgramFiles(x86)')
            if path==root or path in root.parents or (protected_tree and root in path.parents):
                raise RemovalError('Windows・アプリ・個人設定の保存場所は削除できません。')
    for root in containers:
        root=root.resolve()
        if path==root or path in root.parents or (root==app and root in path.parents):
            raise RemovalError('アプリ本体や個人フォルダー全体は削除できません。')
    for other in (project,*projects):
        base=other.base.resolve()
        roots=[base,base/'snapshots']
        if any(path==root or path in root.parents for root in roots):
            raise RemovalError('プロジェクト全体やコピーの保存先全体は削除できません。')
        for name in ('history.git','records','backups','updates'):
            root=base/name
            if path==root or root in path.parents or path in root.parents:
                raise RemovalError('GitHugの管理用フォルダーは削除できません。')
    return path


def identity(path):
    stat=Path(path).stat()
    return stat.st_dev,stat.st_ino,stat.st_ctime_ns


def recycle_registered(project,folder,expected,projects=()):
    path=checked_removal(project,folder,projects)
    if identity(path)!=expected:raise RemovalError('確認後にフォルダーが変わりました。一覧を再表示してからやり直してください。')
    return recycle_folder(path)


def hide_missing(project,registration,folder):
    """Retain baseline and personal notes; never touch the folder or its contents."""
    path=Path(folder)
    if path.exists() or path.is_symlink():raise RemovalError('フォルダーが再び見つかりました。一覧を再表示してください。')
    key=folder_key(folder)
    # Do not derive metadata filenames from the folder name. Different paths can share a name.
    records=[]
    for file in (project.base/'records').glob('*.json'):
        data=json.loads(file.read_text(encoding='utf-8'))
        if folder_key(data['folder'])==key:records.append((file,data))
    for file,data in records:atomic_json(file,{**data,'hidden_from_list':True})
    registration['work']=[value for value in registration.get('work',[]) if folder_key(value)!=key]
