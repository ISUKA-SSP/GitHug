"""Browse retained local commits and explicitly send the chosen immutable record."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from .core import git
from .local_records import records,record_changes,send_record,send_preview
from .listing import date_value
from .publishing import PushPlan,destination_expected,RemoteChanged
from .reconciliation import prepare_resolution,cancel_resolution
from .reconciliation_ui import ResolutionDialog
from .terminology import messagebox
from .folder_batch_ui import review


def show_records(app):
    if app.busy or not app.project:return
    project=app.project
    popup=tk.Toplevel(app.window);popup.title('PCの記録 — '+project.name);popup.geometry('980x580')
    ttk.Label(popup,text='このPCに保存した記録です。元の作業フォルダーを編集・削除しても、記録した内容は残ります。',padding=12).pack(anchor='w')
    controls=ttk.Frame(popup,padding=12);controls.pack(side='bottom',fill='x')
    table=app.table(popup,('date','sha','message','folder','state'),('記録日時','履歴番号','変更の説明','元のフォルダー','状態'))
    by_item={}
    def reload():
        if not popup.winfo_exists():return
        table.delete(*table.get_children());by_item.clear()
        for record in records(project):
            item=table.insert('','end',values=(date_value(record['created'])[0],record['commit'][:12],record['message'],record['folder'],'送信済み' if record['state']=='sent' else 'PCに保存'))
            by_item[item]=record
    def selected():
        items=table.selection()
        if not items:messagebox.showinfo('記録を選択','一覧から記録を1つ選んでください。',parent=popup);return None
        return by_item[items[0]]
    def inspect():
        record=selected()
        if record and not app.busy:app.run('PCの記録を確認しています…',lambda:record_changes(record),lambda text:app.push_ui.text_view('PCの記録：'+record['commit'][:12],text))
    def send():
        record=selected()
        if not record or app.busy:return
        # Network access is explicit and only required to choose/check a send destination.
        def ready(_):send_dialog(app,project,record,popup,reload)
        app.run('GitHubの送信先を確認しています…',project.refresh,ready)
    ttk.Button(controls,text='変更を見る',command=inspect).pack(side='left',padx=4)
    ttk.Button(controls,text='この記録をGitHubへ送る',command=send).pack(side='left',padx=4)
    ttk.Button(controls,text='一覧を再表示',command=reload).pack(side='left',padx=4)
    ttk.Button(controls,text='閉じる',command=popup.destroy).pack(side='right')
    reload();return popup


def send_dialog(app,project,record,parent,reload):
    branches={}
    for line in git('for-each-ref','--format=%(refname:strip=2)\t%(objectname)','refs/heads',cwd=project.cache).splitlines():
        name,sha=line.split('\t',1);branches[name]=sha
    popup=tk.Toplevel(parent);popup.title('PCの記録をGitHubへ送る');popup.geometry('620x340');popup.transient(parent)
    area=ttk.Frame(popup,padding=16);area.pack(fill='both',expand=True)
    ttk.Label(area,text=record['commit'][:12]+'：'+record['message'],wraplength=560).pack(anchor='w',pady=8)
    mode=ttk.Combobox(area,values=('新しい分岐として送る','既存の分岐へ送る'),state='readonly');mode.current(0);mode.pack(fill='x',pady=4);app.terms.bind_choices(mode)
    branch=ttk.Combobox(area,values=sorted(branches));branch.set('work/local-'+record['commit'][:8]);branch.pack(fill='x',pady=4)
    ttk.Label(area,text='選んだ記録につながる以前の記録も送信に含まれます。送信前に内容を確認します。元のフォルダーの現在の内容は送りません。',wraplength=560).pack(anchor='w',pady=8)
    def send():
        if app.busy:return
        destination=branch.get().strip();is_new=mode.current()==0
        if not destination:messagebox.showinfo('送信先を入力','作業ルート名を入力してください。',parent=popup);return
        baseline=record.get('root_base',record['base']) if is_new else branches.get(destination)
        if not baseline:messagebox.showinfo('送信先を確認','既存の作業ルートを選んでください。',parent=popup);return
        def prepare():
            # Only ancestral destinations can be advanced; divergent changes are never overwritten.
            plan=PushPlan(Path(record['folder']),record['commit'],[],branches,'','',Path(record['_repo']))
            try:destination_expected(project,plan,destination,is_new)
            except RemoteChanged:
                if is_new:raise
                return prepare_resolution(project,destination,record=record)
            return send_preview(record,baseline)
        def confirmed(text):
            if not popup.winfo_exists():
                if not isinstance(text,str):cancel_resolution(text)
                return
            if not isinstance(text,str):
                def finished(result):
                    if popup.winfo_exists():popup.destroy()
                    reload();messagebox.showinfo('変更はありません' if result.get('unchanged') else 'GitHubへ送りました',result['sha'][:12]+'\n'+result['warning'])
                    if app.project is project:app.refresh()
                ResolutionDialog(app,project,text,record['message'],record['author_name'],record['author_email'],popup,finished,lambda:prepare_resolution(project,destination,record=record))
                return
            if not review(popup,'GitHubへ送る記録を確認',project.url+'\n送信先：'+destination+'\n\n'+text+'\n\nこの内容をGitHubへ送りますか？',confirm=True):return
            def done(result):
                if popup.winfo_exists():popup.destroy()
                reload();messagebox.showinfo('GitHubへ送りました',result['sha'][:12]+'\n'+result['warning'])
                if app.project is project:app.refresh()
            app.run('保存済みの記録をGitHubへ送っています…',lambda:send_record(project,record,destination,is_new,branches),done)
        app.run('送信する記録を確認しています…',prepare,confirmed)
    ttk.Button(area,text='送信内容を確認',command=send).pack(side='right',pady=8)
    ttk.Button(area,text='キャンセル',command=popup.destroy).pack(side='right',padx=8)
    popup.grab_set();return popup
