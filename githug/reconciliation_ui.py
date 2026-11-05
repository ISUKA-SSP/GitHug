"""Choose entire PC/GitHub files explicitly; unresolved choices cannot be sent."""
import tkinter as tk
from tkinter import ttk
from .reconciliation import (initial_choices,blob_text,preview_result,publish_resolution,cancel_resolution)
from .folder_batch_ui import review
from .terminology import messagebox

LABELS={'pc':'PC側を使う','github':'GitHub側を使う','hold':'保留'}

class ResolutionDialog:
    def __init__(self,app,project,plan,message,name,email,parent,done,rebuild):
        self.app=app;self.project=project;self.plan=plan;self.message=message;self.name=name;self.email=email;self.done=done;self.rebuild=rebuild
        self.window=tk.Toplevel(parent);popup=self.window;popup.title('PCとGitHubの変更を選ぶ — '+project.name)
        popup.geometry('1120x820');popup.minsize(900,680);popup.transient(parent)
        self.previous=parent;self.choices=initial_choices(plan)
        top=ttk.Frame(popup,padding=12);top.pack(fill='x')
        ttk.Label(top,text='両方で変更されたファイルを確認',style='Heading.TLabel').pack(anchor='w')
        self.caption=tk.StringVar(master=popup);ttk.Label(top,textvariable=self.caption,wraplength=1020).pack(anchor='w',pady=6)
        ttk.Label(top,text='ファイル全体を選ぶ操作です。行ごとの合成はしません。PCのフォルダーと保存済みのPCの記録は変更しません。',wraplength=1020,style='Muted.TLabel').pack(anchor='w')
        footer=ttk.Frame(popup,padding=12);footer.pack(side='bottom',fill='x')
        self.state=tk.StringVar(master=popup);ttk.Label(footer,textvariable=self.state).pack(side='left')
        self.proceed=ttk.Button(footer,text='選んだ結果を確認',command=self.confirm,style='Primary.TButton');self.proceed.pack(side='right',padx=4)
        ttk.Button(footer,text='キャンセル',command=self.cancel).pack(side='right',padx=4)
        ttk.Button(footer,text='確認をやり直す',command=self.restart).pack(side='right',padx=4)
        split=ttk.Panedwindow(popup,orient='vertical');split.pack(fill='both',expand=True,padx=12)
        files=ttk.Frame(split);detail=ttk.Frame(split);split.add(files,weight=2);split.add(detail,weight=3)
        self.table=app.table(files,('path','pc','github','reason','choice'),('ファイル','PC側','GitHub側','状態','使う側'))
        self.table.column('path',width=280);self.table.column('pc',width=90);self.table.column('github',width=90);self.table.column('reason',width=240);self.table.column('choice',width=130)
        controls=ttk.Frame(detail);controls.pack(fill='x',pady=8)
        self.pc_button=ttk.Button(controls,text='PC側を使う',command=lambda:self.choose('pc'));self.pc_button.pack(side='left',padx=4)
        ttk.Button(controls,text='GitHub側を使う',command=lambda:self.choose('github')).pack(side='left',padx=4)
        ttk.Button(controls,text='保留',command=lambda:self.choose('hold')).pack(side='left',padx=4)
        ttk.Button(controls,text='共通だった内容を見る',command=self.common).pack(side='left',padx=4)
        self.reason=tk.StringVar(master=popup);ttk.Label(detail,textvariable=self.reason,wraplength=1020,style='Muted.TLabel').pack(fill='x')
        sides=ttk.Panedwindow(detail,orient='horizontal');sides.pack(fill='both',expand=True,pady=6)
        self.outputs=[]
        for label in ('PC側の内容','GitHub側の内容'):
            frame=ttk.Frame(sides);sides.add(frame,weight=1);ttk.Label(frame,text=label,style='Heading.TLabel').pack(anchor='w')
            bar=ttk.Scrollbar(frame);bar.pack(side='right',fill='y')
            output=tk.Text(frame,width=40,height=10,wrap='none',font=('Consolas',10),state='disabled',yscrollcommand=bar.set)
            horizontal=ttk.Scrollbar(frame,orient='horizontal',command=output.xview);horizontal.pack(side='bottom',fill='x')
            output.configure(xscrollcommand=horizontal.set);output.pack(fill='both',expand=True);bar.configure(command=output.yview);self.outputs.append(output)
        self.table.bind('<<TreeviewSelect>>',self.select)
        popup.protocol('WM_DELETE_WINDOW',self.cancel);popup.grab_set();self.fill();app.terms.refresh()

    def alive(self):return bool(self.window.winfo_exists())

    def fill(self):
        self.table.delete(*self.table.get_children())
        for index,entry in enumerate(self.plan.files):
            kind=lambda value:'なし／削除' if value is None else 'ファイル'
            self.table.insert('','end',iid=str(index),values=(entry.path,kind(entry.pc),kind(entry.github),'両方で変更' if entry.conflict else '同じ内容' if entry.pc==entry.github else 'PC側だけ変更',LABELS[self.choices[entry.path]]))
        note='PC側は選んだ保存済み記録の内容です。現在の作業フォルダーではありません。' if self.plan.saved_record is not None else 'PC側は比較を始めた時点の内容です。変更した場合は確認し直してください。'
        self.caption.set(note+'\n送信先：'+self.plan.branch+'（'+self.plan.expected[:12]+'）\nGitHubの最新版を土台に、選んだ結果を別の記録として送ります。GitHub側だけの変更 '+str(self.plan.remote_only)+' 件は残します。')
        self.update_state()
        if self.plan.files:
            first=next((index for index,entry in enumerate(self.plan.files) if entry.conflict),0)
            self.table.selection_set(str(first));self.table.focus(str(first))

    def update_state(self):
        count=sum(value=='hold' for value in self.choices.values())
        self.state.set(f'保留：{count} 件 ／ 対象：{len(self.choices)} 件')
        self.proceed.configure(state='disabled' if count else 'normal')

    def entry(self):
        items=self.table.selection()
        return self.plan.files[int(items[0])] if items else None

    def choose(self,value):
        if self.app.busy:return
        entry=self.entry()
        if not entry or value=='pc' and not entry.pc_allowed:return
        self.choices[entry.path]=value;self.table.set(self.table.selection()[0],'choice',LABELS[value]);self.update_state()

    def select(self,event=None):
        if not self.alive() or not self.entry():return
        entry=self.entry();self.reason.set(entry.path+'\n'+entry.reason);self.pc_button.configure(state='normal' if entry.pc_allowed else 'disabled')
        if self.app.busy:return
        plan=self.plan
        def done(values):
            if not self.alive() or self.plan is not plan:return
            current=self.entry()
            if not current:return
            if current.path!=entry.path:self.select();return
            for output,text in zip(self.outputs,values):
                output.configure(state='normal');output.delete('1.0','end');output.insert('1.0',text);output.configure(state='disabled')
        self.app.run('PC側とGitHub側の内容を確認しています…',lambda:(blob_text(plan,entry.pc),blob_text(plan,entry.github)),done)

    def common(self):
        if self.app.busy or not self.entry():return
        entry=self.entry();plan=self.plan
        self.app.run('共通だった内容を確認しています…',lambda:blob_text(plan,entry.base),lambda text:self.app.push_ui.text_view('共通だった内容：'+entry.path,text) if self.alive() else None)

    def confirm(self):
        if self.app.busy or any(value=='hold' for value in self.choices.values()):return
        plan=self.plan;choices=dict(self.choices)
        def checked(result):
            if not self.alive() or self.plan is not plan:return
            text='送信先：'+plan.branch+'\nファイル全体を次の側に合わせます。\n'+ '\n'.join(path+'：'+LABELS[value] for path,value in choices.items())
            text+='\n\nGitHubの最新版に対する変更\n'+result['summary']+'\n'+result['patch']
            text+='\n\nGitHubの最新版を土台に、新しい記録として送ります。PCのフォルダーと元のPCの記録は変更しません。実行しますか？'
            if not review(self.window,'選んだ結果を確認',text,confirm=True):return
            def task():
                try:return publish_resolution(self.project,plan,choices,self.message,self.name,self.email,lambda note:setattr(self.app,'operation_note',note)),None
                except (OSError,ValueError,RuntimeError) as exc:return None,str(exc)
            def sent(value):
                if not self.alive():return
                result,error=value
                if error:
                    self.proceed.configure(state='disabled');self.state.set('送信していません（通信エラー時は未確認）。「確認をやり直す」で再比較してください。')
                    messagebox.showinfo('送信結果を確認してください',error,parent=self.window);return
                self.window.destroy();self.done(result)
            self.app.run('選んだ結果をGitHubへ送っています…',task,sent)
        self.app.run('選んだ結果の差分を確認しています…',lambda:preview_result(plan,choices),checked)

    def restart(self):
        if self.app.busy:return
        old=self.plan
        def done(plan):
            if not self.alive():cancel_resolution(plan);return
            self.plan=plan;self.choices=initial_choices(plan);self.fill();cancel_resolution(old)
        self.app.run('PCとGitHubの変更を確認し直しています…',self.rebuild,done)

    def cancel(self):
        if self.app.busy:
            messagebox.showinfo('処理中です','処理が終わってから閉じてください。',parent=self.window);return
        cancel_resolution(self.plan);self.window.destroy()
        if self.previous.winfo_exists():self.previous.grab_set()
