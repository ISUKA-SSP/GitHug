"""Whole-file choices on an isolated copy; resolved commits are children of the reviewed remote tip."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from copy import copy
from uuid import uuid4
from .core import git,GitError
from .publishing import (prepare_selected,make_repo,selected_changes,remote_head,RemoteChanged)
from .local_records import validate_author
from .updating import atomic_json,remove_temporary,UpdateConflict

@dataclass(frozen=True)
class FileChoice:
    path: str
    base: tuple | None
    pc: tuple | None
    github: tuple | None
    conflict: bool
    pc_allowed: bool
    reason: str

    @property
    def initial(self):return 'hold' if self.conflict else 'github' if self.pc==self.github else 'pc'

@dataclass
class ResolutionPlan:
    directory: Path
    repo: Path
    branch: str
    expected: str
    common: str
    candidate_tree: str
    files: tuple
    remote_only: int
    source_plan: object = None
    paths: tuple = ()
    saved_record: object = None


def tree(repo,revision):
    result={}
    for entry in filter(None,git('ls-tree','-r','-z',revision,cwd=repo).split('\0')):
        header,path=entry.split('\t',1);mode,kind,oid=header.split()
        result[path]=(mode,oid,kind)
    return result


def prepare_resolution(project,branch,source_plan=None,paths=(),record=None,progress=None):
    if (source_plan is None)==(record is None):raise ValueError('送信する内容を1つ指定してください。')
    if not branch or branch.startswith('-'):raise ValueError('既存の作業ルートを選んでください。')
    git('check-ref-format','--branch',branch)
    project.refresh()
    known=git('for-each-ref','--format=%(refname:strip=2)\t%(objectname)','refs/heads',cwd=project.cache)
    branches=dict(line.split('\t',1) for line in known.splitlines())
    expected=branches.get(branch)
    if not expected or remote_head(project,branch)!=expected:raise RemoteChanged('送信先が更新または削除されています。履歴を確認し直してください。')
    directory=project.base/'outbox'/('resolve-'+uuid4().hex);directory.mkdir(parents=True)
    repo=directory/'repo'
    atomic_json(directory/'resolution.json',{'branch':branch,'expected':expected,'state':'preparing'})
    try:
        if progress:progress('PC側とGitHub側の比較用コピーを準備しています…')
        if source_plan is not None:
            prepare_selected(project,source_plan,paths,repo);local=source_plan.base
        else:
            base_project=copy(project);base_project.cache=Path(record['_repo']);local=record['commit']
            make_repo(base_project,local,repo)
        git('fetch','--no-tags',project.cache,expected,cwd=repo)
        common=git('merge-base',local,expected,cwd=repo,allowed_returncodes=(0,1)).strip()
        if not common:raise ValueError('共通の出発点が見つかりません。別の作業ルートへ送ってください。')
        candidate=git('write-tree',cwd=repo).strip()
        base,pc,github=tree(repo,common),tree(repo,candidate),tree(repo,expected)
        files=[]
        for path in sorted(base.keys()|pc.keys()):
            before,ours,theirs=base.get(path),pc.get(path),github.get(path)
            if before==ours:continue
            allowed=ours is None or ours[0] in ('100644','100755')
            if theirs is not None and theirs[0] not in ('100644','100755'):allowed=False
            if any(other!=path and (path.startswith(other+'/') or other.startswith(path+'/')) for other in github):allowed=False
            conflict=theirs!=before and ours!=theirs
            reason='両方で変更されています。ファイル全体をどちらにするか選んでください。' if conflict else '同じ内容です。' if ours==theirs else 'PC側だけで変更されています。'
            if not allowed:
                conflict=True;reason='ファイルとフォルダー、リンクなどの構成が異なります。今回はGitHub側か保留を選ぶか、別の作業ルートへ送ってください。'
            files.append(FileChoice(path,before,ours,theirs,conflict,allowed,reason))
        remote_only=sum(1 for path in base.keys()|github.keys() if base.get(path)!=github.get(path) and pc.get(path)==base.get(path))
        return ResolutionPlan(directory,repo,branch,expected,common,candidate,tuple(files),remote_only,source_plan,tuple(paths),record)
    except Exception:
        atomic_json(directory/'resolution.json',{'branch':branch,'expected':expected,'state':'not_ready'})
        raise


def initial_choices(plan):return {entry.path:entry.initial for entry in plan.files}


def validate_choices(plan,choices):
    if set(choices)!={entry.path for entry in plan.files}:raise ValueError('一覧の全ファイルについて確認してください。')
    for entry in plan.files:
        value=choices[entry.path]
        if value=='hold':raise ValueError('保留のファイルが残っています。選び直すか、今回は送信をやめてください。')
        if value not in ('pc','github'):raise ValueError('PC側またはGitHub側を選んでください。')
        if value=='pc' and not entry.pc_allowed:raise ValueError('このファイルの構成はPC側への置き換えに対応していません。')


def stage_result(plan,choices):
    validate_choices(plan,choices)
    # This checkout is restricted to the newly-created internal review copy, never the work folder.
    git('checkout','--detach','--force',plan.expected,cwd=plan.repo)
    for entry in plan.files:
        if choices[entry.path]!='pc':continue
        if entry.pc is None:git('update-index','--force-remove','--',entry.path,cwd=plan.repo)
        else:
            mode,oid,_=entry.pc
            git('update-index','--add','--cacheinfo',mode+','+oid+','+entry.path,cwd=plan.repo)
    return git('write-tree',cwd=plan.repo).strip()


def preview_result(plan,choices):
    result=stage_result(plan,choices)
    summary=git('diff','--stat',plan.expected,result,'--',cwd=plan.repo)
    patch=git('diff','--no-ext-diff','--no-textconv','--no-renames',plan.expected,result,'--',cwd=plan.repo)
    return {'tree':result,'summary':summary,'patch':patch,'unchanged':not bool(summary)}


def blob_text(plan,value,limit=120000):
    if value is None:return 'この側ではファイルが存在しません（削除、または未追加）。'
    mode,oid,kind=value
    if kind!='blob' or mode not in ('100644','100755'):return 'リンクや外部参照です。内容の直接表示には対応していません。'
    size=int(git('cat-file','-s',oid,cwd=plan.repo).strip())
    if size>512000:return f'ファイルサイズ：{size:,} bytes。大きいため本文の表示を省略しています。'
    text=git('cat-file','blob',oid,cwd=plan.repo)
    if '\x00' in text or '\ufffd' in text:return f'バイナリ、または表示できない文字コードです。サイズ：{size:,} bytes。'
    return text[:limit]+('\n（本文の表示を制限しています。）' if len(text)>limit else '')


def cancel_resolution(plan):
    try:atomic_json(plan.directory/'resolution.json',{'branch':plan.branch,'expected':plan.expected,'state':'cancelled'})
    except OSError:pass
    if plan.repo.exists():
        try:remove_temporary(plan.repo)
        except OSError:pass


def publish_resolution(project,plan,choices,message,name,email,progress=None):
    validate_author(message,name,email);validate_choices(plan,choices)
    if plan.source_plan is not None:selected_changes(plan.source_plan,plan.paths)
    if remote_head(project,plan.branch)!=plan.expected:raise RemoteChanged('GitHubが比較後に更新されています。「確認をやり直す」で再比較してください。')
    preview=preview_result(plan,choices)
    if preview['unchanged']:return {'sha':plan.expected,'branch':plan.branch,'warning':'選んだ結果は既にGitHubと同じです。新しい記録は送信していません。','unchanged':True}
    info={'branch':plan.branch,'expected':plan.expected,'choices':dict(choices),'state':'preparing','common':plan.common}
    atomic_json(plan.directory/'resolution.json',info)
    git('-c','commit.gpgsign=false','-c','user.name='+name,'-c','user.email='+email,'commit','-m',message,cwd=plan.repo)
    commit=git('rev-parse','HEAD',cwd=plan.repo).strip()
    if git('rev-parse',commit+'^',cwd=plan.repo).strip()!=plan.expected:raise ValueError('送信用の記録のつながりを確認できませんでした。')
    info.update(commit=commit,state='ready');atomic_json(plan.directory/'resolution.json',info)
    if plan.source_plan is not None:selected_changes(plan.source_plan,plan.paths)
    if progress:progress('選んだ結果をGitHubへ送っています…')
    try:
        git('push','--porcelain','--force-with-lease=refs/heads/'+plan.branch+':'+plan.expected,project.url,commit+':refs/heads/'+plan.branch,cwd=plan.repo)
    except GitError:
        if remote_head(project,plan.branch)!=commit:
            info['state']='not_confirmed';atomic_json(plan.directory/'resolution.json',info);raise
    info['state']='sent';atomic_json(plan.directory/'resolution.json',info)
    warning='PCのフォルダーは変更していません。GitHub側を選んだファイルも、PCには元の内容が残っています。'
    try:project.refresh()
    except GitError:warning+=' 履歴一覧を更新できませんでした。後で更新してください。'
    # Do not mark the unsynchronised working folder as based on the new remote tree.
    return {'sha':commit,'branch':plan.branch,'warning':warning,'unchanged':False}
