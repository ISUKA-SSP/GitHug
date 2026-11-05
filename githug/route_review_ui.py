"""Choose destination/source explicitly and inspect changes before opening GitHub."""
import tkinter as tk
from tkinter import ttk
import webbrowser
from .route_review import routes,default_routes,compare_routes,file_patch,checked_proposal_url
from .terminology import messagebox

class RouteReview:
    def __init__(self,app,project,branches,preferred_sha=None):
        self.app=app;self.project=project;self.plan=None;self.generation=0
        base,head=default_routes(branches,preferred_sha)
        popup=tk.Toplevel(app.window);self.window=popup
        popup.title('作業ルートを比べて取り込む — '+project.name);popup.geometry('1060x800');popup.minsize(840,650)
        popup.transient(app.window)
        top=ttk.Frame(popup,padding=12);top.pack(fill='x')
        ttk.Label(top,text=project.name,style='Heading.TLabel').pack(anchor='w')
        ttk.Label(top,text='GitHub上の作業ルート同士を比較します。PCの記録や作業フォルダーは変更しません。',wraplength=850).pack(anchor='w',pady=(4,8))
        choices=ttk.Frame(top);choices.pack(fill='x');choices.columnconfigure(0,weight=1);choices.columnconfigure(2,weight=1)
        ttk.Label(choices,text='取り込み元の作業ルート').grid(row=0,column=0,sticky='w')
        ttk.Label(choices,text='取り込み先の作業ルート').grid(row=0,column=2,sticky='w')
        self.base=tk.StringVar(master=popup,value=base);self.head=tk.StringVar(master=popup,value=head)
        self.head_box=ttk.Combobox(choices,textvariable=self.head,values=sorted(branches),state='readonly')
        self.base_box=ttk.Combobox(choices,textvariable=self.base,values=sorted(branches),state='readonly')
        self.head_box.grid(row=1,column=0,sticky='ew');ttk.Label(choices,text=' → ',font=('',14,'bold')).grid(row=1,column=1)
        self.base_box.grid(row=1,column=2,sticky='ew')
        buttons=ttk.Frame(top);buttons.pack(fill='x',pady=8)
        ttk.Button(buttons,text='内容を比較',command=self.compare).pack(side='left',padx=(0,4))
        ttk.Button(buttons,text='GitHubの履歴を更新',command=self.refresh).pack(side='left',padx=4)
        ttk.Button(buttons,text='取り込み元と先を入れ替える',command=self.swap).pack(side='left',padx=4)
        self.state=tk.StringVar(master=popup,value='取り込み元 → 取り込み先を確認し、「内容を比較」を押してください。')
        ttk.Label(top,textvariable=self.state,wraplength=950,style='Muted.TLabel').pack(fill='x')
        footer=ttk.Frame(popup,padding=12);footer.pack(side='bottom',fill='x')
        self.propose=ttk.Button(footer,text='GitHubで取り込み提案へ進む',command=self.open_proposal,state='disabled',style='Primary.TButton')
        self.propose.pack(side='right',padx=4)
        ttk.Button(footer,text='閉じる',command=popup.destroy).pack(side='right',padx=4)
        ttk.Label(footer,text='このボタンでは提案を送信・合流しません。\n作成と合流の確定はGitHubで行います。',style='Muted.TLabel').pack(side='left')
        body=ttk.Panedwindow(popup,orient='vertical');body.pack(fill='both',expand=True,padx=12,pady=(0,8))
        files=ttk.Frame(body);details=ttk.Frame(body);body.add(files,weight=2);body.add(details,weight=3)
        self.files=app.table(files,('kind','path'),('変更','ファイル'))
        self.files.column('kind',width=90,stretch=False);self.files.column('path',width=800)
        self.output=tk.Text(details,wrap='none',font=('Consolas',10),state='disabled')
        xbar=ttk.Scrollbar(details,orient='horizontal',command=self.output.xview);xbar.pack(side='bottom',fill='x')
        ybar=ttk.Scrollbar(details,command=self.output.yview);ybar.pack(side='right',fill='y')
        self.output.configure(xscrollcommand=xbar.set,yscrollcommand=ybar.set);self.output.pack(fill='both',expand=True)
        self.files.bind('<<TreeviewSelect>>',self.load_file)
        for variable in (self.base,self.head):variable.trace_add('write',self.invalidate)
        app.tooltips.add(self.base_box,'変更を受け取る側です。例：main。GitHubではbase（ベース）と表示されます。')
        app.tooltips.add(self.head_box,'変更を持ってくる側です。GitHubではcompare／headと表示されます。')
        app.terms.refresh();self.compare()

    def alive(self):return bool(self.window.winfo_exists())

    def write(self,text):
        self.output.configure(state='normal');self.output.delete('1.0','end');self.output.insert('1.0',text);self.output.configure(state='disabled')

    def invalidate(self,*args):
        if not self.alive():return
        self.generation+=1;self.plan=None;self.propose.configure(state='disabled')
        self.files.delete(*self.files.get_children());self.write('')
        self.state.set('選択を変更しました。もう一度「内容を比較」を押してください。')

    def swap(self):
        a,b=self.base.get(),self.head.get();self.base.set(b);self.head.set(a)

    def compare(self):
        if self.app.busy or not self.alive():return
        self.invalidate();generation=self.generation;base,head=self.base.get(),self.head.get()
        self.state.set('変更を比較しています…')
        def done(plan):
            if not self.alive() or generation!=self.generation:return
            self.plan=plan;self.state.set(plan.head+' → '+plan.base+'\n'+plan.summary)
            self.write('取り込み元だけにある履歴\n\n'+plan.commits)
            for index,(kind,path) in enumerate(plan.files):
                self.files.insert('','end',iid=str(index),values=({'A':'追加','M':'変更','D':'削除'}.get(kind,kind),path))
            self.propose.configure(state='normal' if plan.can_propose else 'disabled')
        self.app.run('作業ルートを比較しています…',lambda:compare_routes(self.project,base,head),done)

    def refresh(self):
        if self.app.busy or not self.alive():return
        self.invalidate()
        def done(_):
            if not self.alive():return
            branches=routes(self.project)
            self.base_box.configure(values=sorted(branches));self.head_box.configure(values=sorted(branches))
            if self.base.get() not in branches or self.head.get() not in branches:
                try:base,head=default_routes(branches)
                except ValueError as exc:self.state.set(str(exc));return
                self.base.set(base);self.head.set(head)
            self.compare()
        self.app.run('GitHubの履歴を確認しています…',self.project.refresh,done)

    def load_file(self,event=None):
        if not self.plan or not self.alive():return
        selected=self.files.selection()
        if not selected:return
        if self.app.busy:return
        plan=self.plan;path=self.files.item(selected[0],'values')[1]
        self.write('選んだファイルの差分を確認しています…')
        def done(text):
            if not self.alive() or self.plan is not plan:return
            items=self.files.selection()
            if not items:return
            if self.files.item(items[0],'values')[1]!=path:self.load_file();return
            self.write(path+'\n\n'+text)
        self.app.run('ファイルの違いを確認しています…',lambda:file_patch(self.project,plan,path),done)

    def open_proposal(self):
        if self.app.busy or not self.plan or not self.plan.can_propose:return
        plan=self.plan;generation=self.generation
        def task():
            self.project.refresh()
            return checked_proposal_url(self.project,plan)
        def done(url):
            if not self.alive() or self.plan is not plan or generation!=self.generation:return
            text=plan.head+' → '+plan.base+'\n\nGitHubをブラウザーで開きます。作成前に送信元・送信先と差分をもう一度確認してください。\nブラウザーには、その時点のGitHubの内容が表示されます。\n\nこの操作では提案の送信や合流は確定しません。進みますか？'
            if not messagebox.askyesno('GitHubで取り込み提案へ進む',text,parent=self.window,default='no'):return
            try:opened=webbrowser.open(url)
            except Exception as exc:messagebox.showinfo('ブラウザーを開けませんでした',str(exc)+'\n'+url,parent=self.window);return
            if not opened:messagebox.showinfo('ブラウザーを開けませんでした',url,parent=self.window);return
            self.state.set('GitHubを開きました。比較画面が表示された場合は「Create pull request」から作成へ進めます。GitTotteは作成・合流の完了を自動判定しません。')
        self.app.run('取り込み提案の前に履歴を確認しています…',task,done)


def open_route_review(app):
    if app.busy:return
    if not app.project:messagebox.showinfo('プロジェクトを選択','先にプロジェクトを選んでください。');return
    project=app.project;items=app.history.selection();preferred=items[0] if items else None
    def done(_):
        branches=routes(project)
        try:default_routes(branches,preferred)
        except ValueError as exc:messagebox.showinfo('作業ルートを確認',str(exc));return
        RouteReview(app,project,branches,preferred)
    app.run('GitHubの作業ルートを確認しています…',project.refresh,done)
