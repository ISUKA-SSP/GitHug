"""Restore recorded bytes to an exclusively-created folder; never execute restored code."""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from uuid import uuid4
import zipfile
from .core import git,GitError
from .platform_support import git_executable
from .updating import atomic_json,remove_temporary

class RestoreError(RuntimeError):pass

@dataclass(frozen=True)
class RestorePlan:
    kind: str
    source: Path
    destination: Path
    items: tuple
    count: int
    size: int
    identity: tuple | None
    metadata: dict


def file_identity(path):
    s=Path(path).stat();return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns


def no_links(path):
    for component in (Path(path),*Path(path).parents):
        try:s=component.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(s.st_mode) or getattr(s,'st_file_attributes',0)&0x400:
            raise RestoreError('リンクやジャンクションを含む保存場所には復元しません。保存場所を確認してください。')


def safe_name(name,allow_git=True):
    if not name or name.startswith('/') or '\\' in name or '\ufffd' in name:raise RestoreError('対応していない保存場所が含まれています：'+repr(name))
    parts=name.split('/')
    devices={'CON','PRN','AUX','NUL',*(f'{prefix}{n}' for prefix in ('COM','LPT') for n in '123456789¹²³')}
    for part in parts:
        if not part or part in ('.','..') or part.endswith((' ','.')) or any(ord(c)<32 or c in '<>:"|?*' for c in part) or part.split('.')[0].upper() in devices:
            raise RestoreError('Windowsで安全に復元できない名前です：'+repr(name))
        if not allow_git and part.casefold()=='.git':raise RestoreError('PCの記録にGit管理用の名前が含まれています。')
    return '/'.join(parts)


def validate_items(items):
    seen={}
    for name,directory,*_ in items:
        key=name.casefold()
        if key in seen:raise RestoreError('同じ保存場所になる項目が重複しています：'+name)
        seen[key]=directory
    for name,directory,*_ in items:
        pieces=name.casefold().split('/')
        if any('/'.join(pieces[:i]) in seen and not seen['/'.join(pieces[:i])] for i in range(1,len(pieces))):
            raise RestoreError('ファイルとフォルダーの保存場所が重なっています：'+name)


def destination(project,kind):
    return project.base/'snapshots'/('restored-'+kind+'-'+datetime.now().strftime('%Y%m%d_%H%M%S')+'-'+uuid4().hex[:8])


def local_record(project,identifier):
    from .local_records import records
    if not re.fullmatch(r'[0-9a-f]{32}',identifier):raise RestoreError('PCの記録の番号が正しくありません。')
    record=next((r for r in records(project) if Path(r['_path']).parent.name==identifier),None)
    if not record:raise RestoreError('PCの記録が見つかりません。元の記録の保存場所を確認してください。')
    no_links(record['_repo']);return record


def prepare_local(project,identifier):
    record=local_record(project,identifier);repo=Path(record['_repo']);commit=record['commit']
    items=[];ids=[]
    for entry in filter(None,git('--no-replace-objects','ls-tree','-r','-z','--full-tree',commit,cwd=repo).split('\0')):
        header,name=entry.split('\t',1);mode,kind,oid=header.split()
        if kind!='blob' or mode not in ('100644','100755'):raise RestoreError('リンクや外部参照を含むPCの記録は、この復元では扱えません。')
        name=safe_name(name,allow_git=False);items.append((name,False,oid,mode));ids.append(oid)
    sizes={}
    if ids:
        raw=git('--no-replace-objects','cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize)',cwd=repo,input_text='\n'.join(ids)+'\n')
        for line in raw.splitlines():
            fields=line.split()
            if len(fields)!=3 or fields[1]!='blob':raise RestoreError('PCの記録のファイルを読み出せません。')
            sizes[fields[0]]=int(fields[2])
    validate_items(items)
    total=sum(sizes[oid] for oid in ids)
    return RestorePlan('local',repo,destination(project,'local'),tuple((name,directory,oid,mode,sizes[oid]) for name,directory,oid,mode in items),len(items),total,None,record)


def prepare_backup(project,archive):
    archive=Path(archive);root=(project.base/'backups').resolve()
    no_links(archive)
    if archive.suffix.lower()!='.zip' or archive.resolve().parent!=root:raise RestoreError('このプロジェクトのバックアップを選んでください。')
    before=file_identity(archive);items=[];count=0;total=0
    with zipfile.ZipFile(archive) as zipped:
        for entry in zipped.infolist():
            name=safe_name(entry.filename[:-1] if entry.is_dir() else entry.filename)
            mode=entry.external_attr>>16;kind=stat.S_IFMT(mode)
            if kind not in (0,stat.S_IFREG,stat.S_IFDIR) or entry.external_attr&0x400:raise RestoreError('リンクなどの特殊な項目を含むバックアップには対応していません。')
            if entry.flag_bits&1:raise RestoreError('暗号化されたバックアップには対応していません。')
            items.append((name,entry.is_dir(),entry))
            if not entry.is_dir():count+=1;total+=entry.file_size
    validate_items(items)
    if file_identity(archive)!=before:raise RestoreError('確認中にバックアップが変わりました。選び直してください。')
    metadata={}
    try:metadata=json.loads(archive.with_suffix('.json').read_text(encoding='utf-8'))
    except FileNotFoundError:pass
    except ValueError:metadata={'_restore_warning':'バックアップの説明データを読めなかったため、もとの履歴とメモは引き継いでいません。ファイルの内容は復元しました。'}
    if not isinstance(metadata,dict):metadata={'_restore_warning':'説明データの形式が不明なため、もとの履歴とメモは引き継いでいません。ファイルの内容は復元しました。'}
    return RestorePlan('backup',archive,destination(project,'backup'),tuple(items),count,total,before,metadata)


def write_blobs(plan,progress):
    if not plan.items:return
    with tempfile.TemporaryFile() as errors:
        process=subprocess.Popen([git_executable(),'--no-replace-objects','cat-file','--batch'],cwd=plan.source,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,
            env={**os.environ,'GIT_TERMINAL_PROMPT':'0'},creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            for index,(name,_,oid,mode,size) in enumerate(plan.items):
                if progress:progress(f'{index+1} / {plan.count} 件：{name}')
                target=plan.destination.joinpath(*name.split('/'));target.parent.mkdir(parents=True,exist_ok=True)
                no_links(target.parent)
                process.stdin.write((oid+'\n').encode('ascii'));process.stdin.flush()
                fields=process.stdout.readline(4096).decode('ascii',errors='replace').split()
                if fields!=[oid,'blob',str(size)]:raise RestoreError('記録の読み出しに失敗しました：'+name)
                with target.open('xb') as output:
                    left=size
                    while left:
                        chunk=process.stdout.read(min(left,1024*1024))
                        if not chunk:raise RestoreError('ファイルの読み出しが途中で止まりました：'+name)
                        output.write(chunk);left-=len(chunk)
                if process.stdout.read(1)!=b'\n':raise RestoreError('記録の読み出し形式を確認できません。')
                if os.name!='nt':target.chmod(0o755 if mode=='100755' else 0o644)
            process.stdin.close();process.wait(timeout=15)
            if process.returncode:
                errors.seek(0);raise RestoreError(errors.read(3000).decode('utf-8',errors='replace'))
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=15)
            for stream in (process.stdin,process.stdout):
                try:stream.close()
                except OSError:pass


def write_backup(plan,progress):
    with plan.source.open('rb') as stream:
        s=os.fstat(stream.fileno())
        if (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)!=plan.identity:raise RestoreError('確認後にバックアップが変わりました。選び直してください。')
        with zipfile.ZipFile(stream) as zipped:
            for index,(name,directory,entry) in enumerate(plan.items):
                if progress:progress(f'{index+1} / {len(plan.items)} 項目：{name}')
                target=plan.destination.joinpath(*name.split('/'))
                if directory:target.mkdir(parents=True,exist_ok=True);continue
                target.parent.mkdir(parents=True,exist_ok=True);no_links(target.parent)
                with zipped.open(entry) as source,target.open('xb') as output:shutil.copyfileobj(source,output,1024*1024)
                if target.stat().st_size!=entry.file_size:raise RestoreError('復元したファイルのサイズを確認できません：'+name)
                try:
                    stamp=datetime(*entry.date_time).timestamp();os.utime(target,(stamp,stamp))
                except (OSError,ValueError,OverflowError):pass
        if file_identity(plan.source)!=plan.identity:raise RestoreError('復元中にバックアップが変わりました。選び直してください。')


def execute_restore(project,plan,progress=None):
    parent=project.base/'snapshots'
    if plan.destination.parent!=parent or not plan.destination.name.startswith('restored-'):raise RestoreError('復元先を確認できません。')
    no_links(parent);parent.mkdir(parents=True,exist_ok=True)
    if plan.size>shutil.disk_usage(parent).free:raise RestoreError('復元に必要な空き容量が足りません。保存場所の空き容量を確認してください。')
    # The destination is claimed exclusively. Existing folders, including empty ones, are never reused.
    try:plan.destination.mkdir()
    except FileExistsError:raise RestoreError('同じ保存場所が既にあります。確認をやり直して新しいフォルダーを作成してください。') from None
    try:
        if plan.kind=='local':write_blobs(plan,progress)
        elif plan.kind=='backup':write_backup(plan,progress)
        else:raise RestoreError('復元元の種類を確認できません。')
    except Exception as exc:
        extra=''
        try:remove_temporary(plan.destination)
        except OSError:extra='\n途中のコピーは次の場所に残っています：'+str(plan.destination)
        raise RestoreError('復元を完了できませんでした。元のデータは変更していません。\n'+str(exc)+extra) from exc
    source=plan.metadata
    baseline=source.get('root_base',source.get('base','')) if plan.kind=='local' else source.get('sha') or ''
    if not isinstance(baseline,str) or not re.fullmatch(r'[0-9a-f]{40,64}',baseline):baseline=''
    data={'kind':'restored','restore_kind':plan.kind,'folder':str(plan.destination),'created':datetime.now(timezone.utc).isoformat(),'sha':baseline,'update_allowed':False,
          'restored_from':str(plan.source),'restored_original_folder':source.get('folder','')}
    if plan.kind=='local':
        s=plan.destination.stat();data.update(local_record_id=Path(source['_path']).parent.name,restore_commit=source['commit'],restore_baseline=baseline,restore_identity=[s.st_dev,s.st_ino])
    else:data['restore_archive']=plan.source.name
    warning=source.get('_restore_warning','');registered=True
    try:atomic_json(project.base/'records'/(plan.destination.name+'.json'),data)
    except OSError as exc:registered=False;warning='ファイルの復元は完了しましたが、一覧への登録に失敗しました。フォルダーを手動で登録してください。\n'+str(exc)
    try:
        from .notes import Notes
        notes=Notes(project.base);origin=source.get('folder')
        memo=notes.get('folders',origin) if isinstance(origin,str) and origin else ''
        if memo:notes.set('folders',plan.destination,memo)
    except (OSError,ValueError) as exc:warning+='\nメモの引き継ぎを完了できませんでした。元のメモは残っています。\n'+str(exc)
    return {'folder':str(plan.destination),'registered':registered,'warning':warning,'record':data}


def prepare_again(project,record):
    from dataclasses import replace
    if record.get('restore_kind')=='local':plan=prepare_local(project,record['local_record_id'])
    elif record.get('restore_kind')=='backup':plan=prepare_backup(project,project.base/'backups'/record['restore_archive'])
    else:raise RestoreError('この項目の復元元が分かりません。「保管した内容」から選び直してください。')
    return replace(plan,metadata={**plan.metadata,'folder':record['folder']})
