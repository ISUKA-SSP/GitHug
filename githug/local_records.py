"""Immutable commits retained in independent local repositories, never mirror-only refs."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json
import re
from .core import git, GitError
from .updating import atomic_json, record_for_folder


def source_stamp(project,folder):
    folder=Path(folder).resolve(strict=True);stat=folder.stat()
    _,record=record_for_folder(project,folder)
    head=None
    if (folder/'.git').exists():
        try:head=git('rev-parse','HEAD',cwd=folder).strip()
        except GitError:pass
    return {'identity':[stat.st_dev,stat.st_ino], 'head':head,
            'sha':(record or {}).get('sha'),'last_sent':(record or {}).get('last_sent_sha')}


def records(project):
    result=[]
    for path in sorted((project.base/'local-records').glob('*/record.json'),reverse=True):
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            if not re.fullmatch(r'[0-9a-f]{32}',path.parent.name):continue
            if data.get('state') not in ('saved','sent'):continue
            if not re.fullmatch(r'[0-9a-f]{40,64}',data.get('commit','')):continue
            if path.parent.is_symlink() or (path.parent/'repo').is_symlink():continue
            data['_path']=str(path);data['_repo']=str(path.parent/'repo');result.append(data)
        except (OSError,ValueError,TypeError):continue
    return sorted(result,key=lambda data:data['created'],reverse=True)


def latest_for_folder(project,folder):
    from .folder_removal import folder_key
    from .publishing import local_base
    stamp=source_stamp(project,folder)
    for record in records(project):
        if folder_key(record['folder'])!=folder_key(folder):continue
        previous=record.get('source_stamp',{})
        if previous.get('identity')!=stamp['identity'] or previous.get('head')!=stamp['head']:continue
        if previous!=stamp:
            # A successful send may advance only the stored baseline, while the work folder stays intact.
            base=local_base(project,Path(folder))
            if not base:continue
            try:git('merge-base','--is-ancestor',base,record['commit'],cwd=record['_repo'])
            except GitError:continue
        try:git('cat-file','-e',record['commit']+'^{commit}',cwd=record['_repo'])
        except GitError:continue
        return record
    return None


def validate_author(message,name,email):
    if not message.strip():raise ValueError('変更を記録する説明を入力してください。')
    if not name.strip() or not email.strip() or '\n' in name+email or '\r' in name+email:
        raise ValueError('記録する名前とメールアドレスを入力してください。')


def save_local(project,plan,paths,message,name,email,progress=None):
    from .publishing import prepare_selected,selected_changes
    validate_author(message,name,email);selected_changes(plan,paths)
    stamp=source_stamp(project,plan.folder)
    if plan.source_stamp is not None and stamp!=plan.source_stamp:
        raise ValueError('比較後に作業フォルダーの基準が変わりました。確認し直してください。')
    directory=project.base/'local-records'/uuid4().hex;directory.mkdir(parents=True)
    repo=directory/'repo';metadata=directory/'record.json'
    root_base=plan.base
    if plan.repository is not None:
        root_base=json.loads((Path(plan.repository).parent/'record.json').read_text(encoding='utf-8')).get('root_base',plan.base)
    data={'root_base':root_base,'folder':str(plan.folder),'base':plan.base,'created':datetime.now(timezone.utc).isoformat(),
          'message':message.strip(),'author_name':name.strip(),'author_email':email.strip(),
          'files':list(paths),'source_stamp':stamp,'state':'preparing'}
    atomic_json(metadata,data)
    try:
        if progress:progress('このPCだけに保存する記録を準備しています…')
        prepare_selected(project,plan,paths,repo)
        git('-c','commit.gpgsign=false','-c','user.name='+name,'-c','user.email='+email,'commit','-m',message,cwd=repo)
        commit=git('rev-parse','HEAD',cwd=repo).strip()
        selected_changes(plan,paths)
        if source_stamp(project,plan.folder)!=stamp:raise ValueError('記録中に作業フォルダーの基準が変わりました。確認し直してください。')
        data.update(commit=commit,state='saved');atomic_json(metadata,data)
    except Exception:
        data['state']='incomplete';atomic_json(metadata,data);raise
    return {**data,'_repo':str(repo),'_path':str(metadata)}


def record_changes(record):
    return git('show','--format=fuller','--stat','--patch','--no-ext-diff','--no-textconv',record['commit'],'--',cwd=record['_repo'])


def send_record(project,record,branch,is_new,known_branches,progress=None):
    from .publishing import PushPlan,destination_expected,remote_head
    plan=PushPlan(Path(record['folder']),record['commit'],[],known_branches,'','',Path(record['_repo']))
    expected=destination_expected(project,plan,branch,is_new)
    commit=record['commit'];git('cat-file','-e',commit+'^{commit}',cwd=record['_repo'])
    if progress:progress('保存済みの記録をGitHubへ送っています…')
    try:
        git('push','--porcelain','--force-with-lease=refs/heads/'+branch+':'+expected,
            project.url,commit+':refs/heads/'+branch,cwd=record['_repo'])
    except GitError:
        if remote_head(project,branch)!=commit:raise
    warning=''
    try:
        data={key:value for key,value in record.items() if not key.startswith('_')}
        data.update(state='sent',sent_branch=branch);atomic_json(Path(record['_path']),data)
        project.refresh()
    except (OSError,ValueError,GitError):warning='送信は完了しましたが、PC側の記録または履歴一覧を更新できませんでした。'
    return {'sha':commit,'branch':branch,'warning':warning}
