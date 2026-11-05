"""Optional, non-modal guidance. Real operations retain their existing confirmations."""
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import weakref

PURPOSES=(('copy','GitHubのファイルをPCで使いたい'),('save','PCで編集した内容を残したい'),('compare','ファイルの違いを確認したい'),('routes','別の作業ルートの変更を取り込みたい'),('restore','前の状態を取り出したい'))
CHOICES={
 'copy':(('copy','新しいフォルダーへコピー'),('update','登録済みのフォルダーを更新')),
 'save':(('record','PCだけに記録を残す'),('send','GitHubにも送る')),
 'compare':(('compare','GitHubの履歴とPCを比べる'),('routes','作業ルート同士を比べる')),
 'restore':(('copy','GitHubの履歴から取り出す'),('restore-local','PCに残した記録から取り出す'),('restore-backup','更新前のバックアップから取り出す'))}
GOALS={
 'copy':('履歴からPCへコピー',('history',),'copy','コピーする','上の履歴を下のPC欄の空いている場所へドラッグしてください。下のボタンでも同じ操作ができます。新しいフォルダーを作り、既存のファイルは変更しません。'),
 'update':('選んだ履歴へフォルダーを更新',('history','folder'),'update','更新方法を確認する','上の履歴を下の更新先の行へドラッグするか、下のボタンを押してください。手元の変更を調べたあと、バックアップなどの更新方法を選びます。まだ更新は確定しません。'),
 'record':('編集内容をPCだけに記録',('folder',),'record','記録する内容を確認する','下のフォルダーを右クリック →「PCに記録だけ残す」、または下のボタンで進みます。次の画面でファイル・変更の説明・名前を確認します。GitHubへは送りません。'),
 'send':('編集内容をGitHubへ送る',('folder',),'send','送る内容を確認する','下のフォルダーを上の履歴へドラッグするか、下のボタンを押してください。次の画面でファイル・送信先・変更の説明を確認します。ドラッグだけでは送信しません。'),
 'compare':('履歴とPCのファイルを比較',('history','folder'),'compare','比較する','選んだ履歴とPCのフォルダーを比較します。ファイルは変更しません。通常は「比べる・取り込む → 作業フォルダーと比較」から開けます。'),
 'routes':('作業ルート同士を比較',(),'routes','比較画面を開く','比較画面で「取り込み元 → 取り込み先」を選びます。取り込み提案が必要なら、内容を確認してGitHubへ進めます。提案の作成・合流の確定はGitHubで行います。'),
 'restore-local':('PCの記録から復元',(),'restore-local','PCの記録を開く','一覧で記録を1つ選び、「新しいフォルダーへ復元」を押してください。保存場所を確認して実行します。元のフォルダーや記録は変更しません。'),
 'restore-backup':('更新前バックアップから復元',(),'restore-backup','バックアップを開く','一覧でバックアップを1つ選び、「新しいフォルダーへ復元」を押してください。保存場所を確認して実行します。復元後に記録していない編集は戻りません。')}


def required_step(goal, project, history_count, folder_count, folder_exists=True):
    if not project:return 'project'
    needs=GOALS[goal][1]
    if 'history' in needs and history_count!=1:return 'history'
    if 'folder' in needs:
        if folder_count!=1:return 'folder'
        if not folder_exists:return 'missing'
    return 'act'

@dataclass(frozen=True)
class Ticket:
    guide: object
    generation: int
    project: object
    kind: str


def begin(app,kind,project):
    guide=getattr(app,'operation_guide',None)
    if guide and guide.alive() and guide.goal and not guide.completed and app.project is project and guide.project is project and guide.step=='act' and GOALS[guide.goal][2]==kind:
        return Ticket(weakref.ref(guide),guide.generation,project,kind)
    return None


def finish(ticket,detail):
    if not ticket:return
    guide=ticket.guide()
    if guide and guide.alive() and guide.generation==ticket.generation and guide.app.project is ticket.project and guide.project is ticket.project:
        guide.complete(detail)


def handoff(app,window,kind,text):
    guide=getattr(app,'operation_guide',None)
    if guide and begin(app,kind,app.project):
        guide.handoff_window=window;guide.handoff_text=text;guide.signature=None;guide.tick_now()


class Highlight:
    """Thin edges inside the target; no grab or overlay over the usable area."""
    def __init__(self):self.edges=[];self.target=None
    def clear(self):
        for edge in self.edges:
            try:edge.destroy()
            except tk.TclError:pass
        self.edges=[];self.target=None
    def show(self,target):
        if self.target is target:return
        self.clear()
        if target is None or not target.winfo_exists():return
        self.target=target
        for position in ('top','bottom','left','right'):
            edge=tk.Frame(target,background='#54d9ec',borderwidth=0,takefocus=False)
            if position=='top':edge.place(x=0,y=0,relwidth=1,height=3)
            elif position=='bottom':edge.place(x=0,rely=1,y=-3,relwidth=1,height=3)
            elif position=='left':edge.place(x=0,y=0,width=3,relheight=1)
            else:edge.place(relx=1,x=-3,y=0,width=3,relheight=1)
            self.edges.append(edge)


class OperationGuide:
    def __init__(self,app):
        self.app=app;self.goal=None;self.page='home';self.stack=[];self.generation=0
        self.project=app.project;self.completed=False;self.step=None;self.signature=None;self.timer=None;self.highlight=Highlight();self.handoff_window=None;self.handoff_text=''
        self.window=tk.Toplevel(app.window);self.window.title('GitTotte — 操作ガイド')
        self.window.geometry('460x610');self.window.minsize(390,540)
        # Owned, but never modal: clicking the main screen must still work.
        self.window.transient(app.window)
        x=max(0,min(app.window.winfo_rootx()+app.window.winfo_width()-470,app.window.winfo_screenwidth()-470))
        y=max(0,min(app.window.winfo_rooty()+80,app.window.winfo_screenheight()-650))
        self.window.geometry(f'460x610+{x}+{y}')
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self.window.bind('<Destroy>',self.destroyed,add='+')
        outer=ttk.Frame(self.window,padding=18);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='操作ガイド',style='Heading.TLabel').pack(anchor='w')
        self.context=tk.StringVar(master=self.window)
        ttk.Label(outer,textvariable=self.context,style='Muted.TLabel',wraplength=400).pack(fill='x',pady=(8,12))
        area=ttk.Frame(outer);area.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(area,background='#252525',borderwidth=0,highlightthickness=0)
        scrollbar=ttk.Scrollbar(area,orient='vertical',command=self.canvas.yview)
        scrollbar.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.body=ttk.Frame(self.canvas)
        body_id=self.canvas.create_window(0,0,window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda event:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        def resized(event):
            self.canvas.itemconfigure(body_id,width=event.width)
            for widget in self.body.winfo_children():
                if isinstance(widget,ttk.Label):widget.configure(wraplength=max(100,event.width-4))
        self.canvas.bind('<Configure>',resized)
        def wheel(event):
            self.canvas.yview_scroll(-1 if event.delta>0 else 1,'units');return 'break'
        self.window.bind('<MouseWheel>',wheel,add='+')
        footer=ttk.Frame(outer);footer.pack(fill='x',pady=(12,0))
        self.back_button=ttk.Button(footer,text='戻る',command=self.back);self.back_button.pack(side='left')
        ttk.Button(footer,text='閉じる',command=self.close).pack(side='right')
        self.show_page();self.tick()

    def alive(self):
        try:return bool(self.window.winfo_exists())
        except tk.TclError:return False

    def destroyed(self,event):
        if event.widget is self.window:
            if self.timer:
                self.app.window.after_cancel(self.timer);self.timer=None
            self.highlight.clear()

    def close(self):
        self.generation+=1;self.highlight.clear()
        if self.timer:self.app.window.after_cancel(self.timer);self.timer=None
        if self.alive():self.window.destroy()

    def navigate(self,page,goal=None):
        self.stack.append((self.page,self.goal));self.page=page;self.goal=goal
        self.generation+=1;self.completed=False;self.signature=None;self.handoff_window=None;self.highlight.clear();self.show_page();self.tick_now()

    def back(self):
        if not self.stack:return
        self.page,self.goal=self.stack.pop();self.generation+=1;self.completed=False;self.signature=None;self.handoff_window=None
        self.highlight.clear();self.show_page();self.tick_now()

    def clear_body(self):
        for widget in self.body.winfo_children():widget.destroy()
        self.canvas.yview_moveto(0)

    def label(self,text,heading=False):
        label=ttk.Label(self.body,text=text,wraplength=max(100,self.canvas.winfo_width()-4) if self.canvas.winfo_width()>10 else 380,justify='left',style='Heading.TLabel' if heading else 'TLabel')
        label.pack(fill='x',pady=(0,12));return label

    def button(self,text,command,primary=False):
        button=ttk.Button(self.body,text=text,command=command,style='Primary.TButton' if primary else 'TButton')
        button.pack(fill='x',pady=4);return button

    def show_page(self):
        self.clear_body();self.back_button.configure(state='normal' if self.stack else 'disabled')
        if self.page=='home':
            self.label('何をしたいですか？',True)
            for key,text in PURPOSES:
                self.button(text,lambda key=key:self.navigate('steps','routes') if key=='routes' else self.navigate(key))
            self.label('実際の画面で操作しながら進めます。途中で閉じても、行った操作はそのままです。ガイドだけでコピー・更新・送信が始まることはありません。')
        elif self.page in CHOICES:
            self.label(dict(PURPOSES)[self.page],True)
            for goal,title in CHOICES[self.page]:self.button(title,lambda goal=goal:self.navigate('steps',goal))
        else:self.signature=None

    def snapshot(self):
        history=self.app.history.selection();folders=self.app.folders.selection()
        folder=self.app.folders.item(folders[0],'values')[1] if len(folders)==1 else ''
        return history,folders,folder

    def tick(self):
        self.timer=None
        if not self.alive():return
        self.tick_now();self.timer=self.app.window.after(200,self.tick)

    def tick_now(self):
        if not self.alive():return
        if self.project is not self.app.project:
            self.project=self.app.project;self.generation+=1;self.completed=False;self.signature=None;self.handoff_window=None
        self.context.set('プロジェクト：'+(self.app.project.name if self.app.project else '未選択'))
        if self.page!='steps' or self.completed:return
        history,folders,folder=self.snapshot()
        step=required_step(self.goal,bool(self.app.project),len(history),len(folders),bool(folder) and Path(folder).is_dir())
        if self.handoff_window is not None and not self.handoff_window.winfo_exists():self.handoff_window=None
        signature=(step,history,folders,folder,self.app.busy,self.app.terms.mode,self.handoff_window)
        if signature==self.signature:return
        self.signature=signature;self.step=step;self.render_step(history,folders,folder)

    def render_step(self,history,folders,folder):
        self.clear_body();title,needs,kind,action,hint=GOALS[self.goal]
        self.label(title,True)
        if self.app.busy:
            self.label('処理中です。終わるまでお待ちください。');self.highlight.clear();return
        if self.handoff_window is not None:
            self.label(self.handoff_text)
            self.label('開いた画面で操作を続けてください。キャンセルして戻ることもできます。完了した場合だけ、この案内も完了になります。')
            self.button('開いた画面を手前に表示',self.handoff_window.lift)
            self.highlight.clear();return
        if self.step=='project':
            self.label('① 左の一覧からプロジェクトを選んでください。登録がなければ「＋ プロジェクト」でGitHubのURLを追加します。')
            self.button('プロジェクトを追加する',self.app.add)
            self.highlight.show(self.app.projects);return
        if self.step=='history':
            self.label('上の「GitHubの履歴」から、使いたい時点を1つ選んでください。選ぶと次へ進みます。')
            self.label('最新版を使う場合は履歴を更新し、使いたい作業ルートの先頭を選びます。検索中や別ページにも履歴があるので、日時と作業ルートを確認してください。')
            self.button('GitHubの履歴を更新する',self.app.refresh)
            self.highlight.show(self.app.history);return
        if self.step in ('folder','missing'):
            self.label('下の「PCのフォルダー」から、対象を1つ選んでください。' if self.step=='folder' else '選んだフォルダーが見つかりません。移動先を登録するか、別の利用できるフォルダーを選んでください。')
            if len(folders)>1:self.label('複数選択されています。Ctrlキーを離して、対象の行を1回クリックしてください。')
            self.button('作業フォルダーを登録する',self.app.register_folder)
            self.highlight.show(self.app.folders);return
        if 'history' in needs:
            record=self.app.records.get(history[0],{})
            self.label('履歴：'+history[0][:12]+'\n'+record.get('date','')+'\n'+record.get('message','')[:200])
        if 'folder' in needs:self.label('PCのフォルダー：\n'+folder)
        self.label(hint)
        self.execute_button=self.button(action,self.execute,True)
        if kind=='routes':self.label('比較ができたら、この案内は完了です。取り込みが終わったことを示すものではありません。')
        self.label('確認画面を閉じたり中止した場合は、この案内からやり直せます。')
        target=self.app.folders if self.goal in ('copy','update') else self.app.history if self.goal=='send' else getattr(self.app,'compare_menu',self.app.folders) if self.goal in ('compare','routes') else self.app.folders if self.goal=='record' else getattr(self.app,'storage_button',None)
        self.highlight.show(target)

    def execute(self):
        # Recheck live selections and project before every click; never use stale IDs.
        if self.app.busy:return
        if self.handoff_window is not None and self.handoff_window.winfo_exists():self.handoff_window.lift();return
        self.signature=None;self.tick_now()
        if self.step!='act' or self.completed:return
        goal=self.goal
        if goal=='copy':self.app.reproduce()
        elif goal=='update':self.app.update_selected()
        elif goal in ('record','send'):
            self.app.with_selected_folder(lambda folder:self.app.push_ui.begin(folder,local_only=goal=='record'))
        elif goal=='compare':self.app.compare()
        elif goal=='routes':
            from .route_review_ui import open_route_review
            open_route_review(self.app)
        elif goal=='restore-local':
            from .local_records_ui import show_records
            show_records(self.app)
        else:self.app.backups_dialog()

    def complete(self,detail):
        self.completed=True;self.highlight.clear();self.clear_body()
        self.label('できました',True);self.label(detail)
        self.label('この操作は、普段のボタンや右クリックからも使えます。ガイドを閉じても作業は続けられます。')
        self.button('別の操作を案内する',self.home,True)
        # Context changes must not make old work look completed for another project.
        self.step='done'

    def home(self):
        self.page='home';self.goal=None;self.stack=[];self.completed=False;self.generation+=1;self.handoff_window=None
        self.highlight.clear();self.show_page()


def open_guide(app):
    existing=getattr(app,'operation_guide',None)
    if existing and existing.alive():existing.window.deiconify();existing.window.lift();return existing
    app.operation_guide=OperationGuide(app);return app.operation_guide
