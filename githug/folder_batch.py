"""Reviewed batch operations, using the same per-folder safeguards as single deletion."""
from dataclasses import dataclass, field
from pathlib import Path
from .folder_removal import checked_removal, folder_key, hide_missing, identity, recycle_registered, RemovalError

@dataclass(frozen=True)
class Target:
    folder: str
    kind: str
    expected: tuple | None = None

@dataclass
class BatchPlan:
    operation: str
    selected: int
    targets: list = field(default_factory=list)
    untouched: list = field(default_factory=list)
    blocked: list = field(default_factory=list)

@dataclass
class BatchResult:
    succeeded: list = field(default_factory=list)
    failed: list = field(default_factory=list)


def is_missing(path):
    try:Path(path).lstat()
    except FileNotFoundError:return True
    return False


def check_console(folder,console_folder):
    if console_folder:
        path=Path(folder).resolve();current=Path(console_folder).resolve()
        if current==path or current in path.parents or path in current.parents:
            raise RemovalError('このフォルダーのPowerShellが動いています。終了してからやり直してください。')


def prepare_batch(project, entries, operation, projects=(), console_folder=None):
    if operation not in ('recycle','hide'):raise ValueError('Unknown folder operation')
    plan=BatchPlan(operation,len(entries));seen=set()
    for kind,folder in entries:
        try:
            path=Path(folder);key=folder_key(path)
            if key in seen:
                plan.untouched.append((folder,'同じ保存場所を重複して選択しています。'));continue
            seen.add(key)
            missing=is_missing(path)
            if operation=='hide':
                if missing:plan.targets.append(Target(str(path),kind))
                else:plan.untouched.append((folder,'見つかる項目は一覧に残します。'))
            elif missing:plan.untouched.append((folder,'見つからない項目は一覧に残します。'))
            else:
                path=checked_removal(project,path,projects)
                check_console(path,console_folder)
                plan.targets.append(Target(str(path),kind,identity(path)))
        except (OSError,ValueError,RuntimeError) as exc:plan.blocked.append((folder,str(exc)))
    if operation=='recycle':
        # Neither an ancestor nor its selected descendant may accidentally remove the other.
        nested=set()
        for i,target in enumerate(plan.targets):
            for j,other in enumerate(plan.targets[:i]):
                a,b=Path(target.folder),Path(other.folder)
                if a in b.parents or b in a.parents:nested.update((i,j))
        plan.blocked.extend((target.folder,'親フォルダーとその中のフォルダーを同時に選択しています。どちらか一方を選んでください。') for i,target in enumerate(plan.targets) if i in nested)
        plan.targets=[target for i,target in enumerate(plan.targets) if i not in nested]
    return plan


def execute_batch(project,plan,projects=(),progress=None,console_folder=None):
    result=BatchResult()
    for index,target in enumerate(plan.targets):
        if progress:progress(f'{index+1} / {len(plan.targets)} 件：{Path(target.folder).name}')
        try:
            if plan.operation=='recycle':
                check_console(target.folder,console_folder() if callable(console_folder) else console_folder)
                recycle_registered(project,target.folder,target.expected,projects)
            else:
                # Registration is updated on the GUI thread only after successful metadata writes.
                if not is_missing(target.folder):raise RemovalError('フォルダーが再び見つかりました。一覧に残します。')
                hide_missing(project,{'work':[]},target.folder)
            result.succeeded.append(target.folder)
        except (OSError,ValueError,RuntimeError) as exc:result.failed.append((target.folder,str(exc)))
    return result
