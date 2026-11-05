"""Batch confirmation and results. Confirmed selection and project are captured before work."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from .core import Project
from .folder_removal import folder_key
from .folder_batch import prepare_batch, execute_batch
from .terminology import messagebox


def review(window,title,text,confirm=False):
    if len(text.splitlines())<=28:
        if confirm:return messagebox.askyesno(title,text,parent=window,default='no')
        messagebox.showinfo(title,text,parent=window);return False
    popup=tk.Toplevel(window);popup.title(title);popup.geometry('780x540');popup.minsize(560,360)
    popup.transient(window);popup.grab_set();answer=False
    area=ttk.Frame(popup,padding=16);area.pack(fill='both',expand=True)
    body=ttk.Frame(area);body.pack(fill='both',expand=True)
    bar=ttk.Scrollbar(body);bar.pack(side='right',fill='y')
    reader=tk.Text(body,wrap='word',yscrollcommand=bar.set,font=('Yu Gothic UI',11),padx=10,pady=10)
    reader.insert('1.0',text);reader.configure(state='disabled');reader.pack(fill='both',expand=True)
    bar.configure(command=reader.yview)
    controls=ttk.Frame(area);controls.pack(fill='x',pady=(12,0))
    def close(value=False):
        nonlocal answer
        answer=value;popup.destroy()
    cancel=ttk.Button(controls,text='キャンセル' if confirm else '閉じる',command=close)
    cancel.pack(side='right');cancel.focus_set()
    if confirm:ttk.Button(controls,text='実行する',command=lambda:close(True),style='Primary.TButton').pack(side='right',padx=8)
    popup.bind('<Escape>',lambda e:close());popup.protocol('WM_DELETE_WINDOW',close)
    window.wait_window(popup)
    return answer


def remove_selected(app,operation):
    if app.busy or not app.project:return
    items=app.folders.selection()
    if not items:return
    entries=tuple(tuple(app.folders.item(item,'values')[:2]) for item in items)
    project=app.project
    registration=getattr(app,'current',None)
    projects=tuple(Project(app.config['root'],p['url']) for p in app.config['projects'])
    console=getattr(app,'console',None)
    console_folder=console.folder if console and console.active else None
    plan=prepare_batch(project,entries,operation,projects,console_folder)
    action='フォルダーをごみ箱へ移動' if operation=='recycle' else '見つからない項目を一覧から取り除く'
    text=f'選択した {plan.selected} 件のうち、{len(plan.targets)} 件を対象にします。\n'
    text+=f'そのまま残す項目：{len(plan.untouched)} 件 ／ 実行できない項目：{len(plan.blocked)} 件\n'
    text+='\n【実行する対象】\n'+'\n'.join(f'{t.kind}：{t.folder}' for t in plan.targets)
    for label,entries_to_show in (('そのまま残す',plan.untouched),('実行できない',plan.blocked)):
        if entries_to_show:text+='\n\n【'+label+'】\n'+'\n'.join(folder+'\n  '+reason for folder,reason in entries_to_show)
    if not plan.targets:
        review(app.window,action+'：対象はありません',text);return
    if operation=='recycle':
        text+='\n\n対象の中のファイルと手元の編集も、ごみ箱へ移動します。\nGitHubの履歴・更新前のバックアップ・自分用メモは残します。\n移動後も記録は一覧に残します。'
    else:text+='\n\n一覧の項目だけを取り除きます。移動先のファイル・GitHubの履歴・自分用メモは残します。'
    text+='\n途中で実行できなくなった項目は処理せず、残りを続けます。\n\n実行しますか？'
    if not review(app.window,action,text,confirm=True):return
    def done(result):
        if operation=='hide' and registration is not None:
            keys={folder_key(path) for path in result.succeeded}
            registration['work']=[path for path in registration.get('work',[]) if folder_key(path) not in keys]
            app.save()
        if app.project is project:
            app.load_folders()
            root=app.folder_browser.root
            if root:
                path=Path(root).resolve()
                if any(path==Path(folder).resolve() or Path(folder).resolve() in path.parents for folder in result.succeeded):app.folder_browser.set_folder(None)
        summary=f'{action}：完了 {len(result.succeeded)} 件 ／ 実行できなかった項目 {len(result.failed)} 件'
        app.status.set(summary)
        details=project.name+'\n'+summary
        if result.succeeded:details+='\n\n【完了】\n'+'\n'.join(result.succeeded)
        if result.failed:details+='\n\n【実行できませんでした】\n'+'\n'.join(path+'\n  '+reason for path,reason in result.failed)
        if plan.untouched or plan.blocked:details+='\n\n確認画面で対象外とした項目は、そのまま残しています。'
        review(app.window,'整理の結果',details)
    description='フォルダーをごみ箱へ移動しています…' if operation=='recycle' else '見つからない項目を一覧から取り除いています…'
    app.run(description,lambda:execute_batch(project,plan,projects,lambda note:setattr(app,'operation_note',note),
            lambda:console.folder if console and console.active else None),done)
