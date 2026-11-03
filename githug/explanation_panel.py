"""Optional Gemini panel: prepare, inspect, explicitly send. No conversation or automatic calls."""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from .explaining import explain, normalize_api_key
from .inspection import file_input,history_input


class ExplanationPanel:
    def __init__(self,parent,app):
        self.app=app;self.frame=ttk.Frame(parent,padding=12,width=350,style='Card.TFrame');self.frame.pack_propagate(False);self.target=None;self.pending=queue.Queue();self.busy=False
        self.payload=None;self.prepared_target=None
        top=ttk.Frame(self.frame);top.pack(fill='x')
        ttk.Label(top,text='選んだものを説明',style='Heading.TLabel').pack(side='left')
        ttk.Button(top,text='閉じる',command=app.toggle_explanation).pack(side='right')
        self.caption=tk.StringVar(value='履歴か左下のファイルを選択')
        ttk.Label(self.frame,textvariable=self.caption,wraplength=300).pack(fill='x',pady=8)
        self.mode=tk.StringVar(value='一つの履歴')
        ttk.Combobox(self.frame,textvariable=self.mode,values=('一つの履歴','枝の変更'),state='readonly').pack(fill='x')
        ttk.Label(self.frame,text='枝の比較元（例: main）',style='Muted.TLabel').pack(anchor='w',pady=(6,0))
        self.base=tk.StringVar(value='main');ttk.Entry(self.frame,textvariable=self.base).pack(fill='x')
        self.detail=tk.BooleanVar(value=False)
        ttk.Checkbutton(self.frame,text='内容・差分の本文も含める',variable=self.detail).pack(anchor='w',pady=4)
        self.model=tk.StringVar(value=app.config.get('explanation_model',''))
        self.key=tk.StringVar()
        ttk.Button(top,text='接続設定',command=self.settings_dialog).pack(side='right',padx=4)
        self.prepare=ttk.Button(self.frame,text='送信内容を確認',command=self.prepare_input);self.prepare.pack(fill='x',pady=(8,4))
        self.send=ttk.Button(self.frame,text='Geminiへ送って説明する',command=self.request,style='Primary.TButton',state='disabled');self.send.pack(fill='x')
        self.state=tk.StringVar(value='選択だけでは送信しません。説明はAIの推測を含みます。')
        ttk.Label(self.frame,textvariable=self.state,wraplength=300,style='Muted.TLabel').pack(fill='x',pady=8)
        tabs=ttk.Notebook(self.frame);tabs.pack(fill='both',expand=True)
        self.output=self.text_area(tabs,'説明');self.preview=self.text_area(tabs,'送信内容')
        self.tabs=tabs
        ttk.Button(self.frame,text='説明をコピー',command=self.copy).pack(anchor='e',pady=(4,0))
        for variable in (self.mode,self.base,self.detail):variable.trace_add('write',self.invalidate)
        self.frame.after(80,self.poll)

    def settings_dialog(self):
        existing=getattr(self,'settings_window',None)
        if existing is not None and existing.winfo_exists():existing.lift();return existing
        popup=tk.Toplevel(self.frame);self.settings_window=popup
        popup.title('Gemini 接続設定');popup.geometry('620x360');popup.minsize(480,340)
        area=ttk.Frame(popup,padding=18);area.pack(fill='both',expand=True)
        ttk.Label(area,text='Geminiへの接続',style='Heading.TLabel').pack(anchor='w',pady=(0,12))
        ttk.Label(area,text='モデル名（Google AI Studioで利用できる名前）').pack(anchor='w')
        model=tk.StringVar(value=self.model.get());ttk.Entry(area,textvariable=model).pack(fill='x',pady=(4,12))
        ttk.Label(area,text='APIキー（このアプリを閉じるまでだけ保持）').pack(anchor='w')
        key=tk.StringVar(value=self.key.get());entry=ttk.Entry(area,textvariable=key,show='•');entry.pack(fill='x',pady=4)
        ttk.Label(area,text='モデル名だけ設定ファイルに保存します。キーは保存しません。\n設定を適用しても通信しません。送信前に内容を確認してください。',style='Muted.TLabel',wraplength=540).pack(anchor='w',pady=8)
        status=tk.StringVar();ttk.Label(area,textvariable=status,wraplength=540).pack(fill='x')
        buttons=ttk.Frame(area);buttons.pack(side='bottom',fill='x')
        def close():
            key.set('');popup.destroy()
        def apply():
            try:value=normalize_api_key(key.get()) if key.get().strip() else ''
            except ValueError as exc:status.set(str(exc));return
            self.model.set(model.get().strip());self.key.set(value)
            self.app.config['explanation_model']=self.model.get();self.app.save()
            self.state.set('接続設定を適用しました。送信内容を確認して依頼してください。')
            close()
        ttk.Button(buttons,text='キャンセル',command=close).pack(side='right')
        ttk.Button(buttons,text='適用',command=apply,style='Primary.TButton').pack(side='right',padx=8)
        popup.protocol('WM_DELETE_WINDOW',close)
        return popup

    def text_area(self,tabs,title):
        frame=ttk.Frame(tabs);tabs.add(frame,text=title)
        bar=ttk.Scrollbar(frame);bar.pack(side='right',fill='y')
        text=tk.Text(frame,width=28,height=6,wrap='word',state='disabled',yscrollcommand=bar.set,font=('Yu Gothic UI',11),padx=8,pady=8,spacing3=3)
        bar.configure(command=text.yview);text.pack(fill='both',expand=True)
        return text

    @staticmethod
    def write(widget,value):
        widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',value);widget.configure(state='disabled')

    def choose(self,target):
        self.target=target
        self.caption.set(target['label'] if target else '履歴か左下のファイルを選択')
        if not self.busy:
            self.payload=None;self.send.configure(state='disabled')
            self.write(self.preview,'');self.state.set('送信内容を確認してから依頼します。前の説明の対象は説明欄の先頭に表示します。')

    def invalidate(self,*args):
        self.payload=None;self.send.configure(state='disabled')
        if not self.busy:self.state.set('条件を変更しました。送信内容をもう一度確認してください。')

    def launch(self,kind,function):
        if self.busy:return
        self.busy=True;self.prepare.configure(state='disabled');self.send.configure(state='disabled')
        def work():
            try:self.pending.put((kind,function(),None))
            except Exception as exc:self.pending.put((kind,None,str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def prepare_input(self):
        if not self.target:self.state.set('履歴かファイルを選択してください。');return
        target=dict(self.target);mode=self.mode.get();base=self.base.get().strip();detail=self.detail.get()
        if target['kind']=='history' and mode=='枝の変更' and not base:
            self.state.set('枝の比較元を入力してください。');return
        self.prepared_target=target;self.prepared_options=(mode,base,detail);self.payload=None
        self.state.set('送信する内容を準備中…（まだ通信しません）')
        def build():
            text=file_input(target['path'],detail) if target['kind']=='file' else history_input(target['project'],target['sha'],base if mode=='枝の変更' else None,detail)
            return text
        self.launch('prepare',build)

    def request(self):
        if not self.payload or self.busy:return
        if not self.key.get().strip() or not self.model.get().strip():
            self.state.set('接続設定でモデル名とAPIキーを入力してください。');self.settings_dialog();return
        # Snapshot exactly the preview, key, model and target before starting any network request.
        payload=self.payload;key=self.key.get();model=self.model.get().strip()
        self.answer_label=self.prepared_target['label']
        self.app.config['explanation_model']=model;self.app.save()
        self.state.set('Geminiに説明を依頼中… 対象: '+self.answer_label)
        self.launch('answer',lambda:explain(key,model,payload))

    def poll(self):
        if not self.frame.winfo_exists():return
        while not self.pending.empty():
            kind,value,error=self.pending.get();self.busy=False;self.prepare.configure(state='normal')
            if error:
                label=self.answer_label if kind=='answer' else (self.prepared_target or {}).get('label','')
                self.write(self.output,'今回の説明は取得できませんでした。\n対象: '+label+'\n\n'+error+'\n\n接続設定や入力を確認して再度お試しください。自動再試行はしません。')
                self.tabs.select(0)
                self.state.set('説明を取得できませんでした。詳しくは説明欄を確認してください。')
                self.send.configure(state='normal' if self.payload else 'disabled');continue
            if kind=='prepare':
                # A selection change during preparation invalidates the prepared send action.
                if self.target!=self.prepared_target or self.prepared_options!=(self.mode.get(),self.base.get().strip(),self.detail.get()):
                    self.payload=None;self.state.set('選択が変わりました。もう一度送信内容を確認してください。');continue
                self.payload=value;self.write(self.preview,value);self.tabs.select(1)
                self.state.set(str(len(value))+'文字をGoogle Geminiへ送信します。内容を確認してください。')
                self.send.configure(state='normal')
            else:
                self.write(self.output,'対象: '+self.answer_label+'\n\n'+value);self.tabs.select(0)
                self.payload=None;self.state.set('説明を受信しました。再依頼には送信内容を確認してください。')
        self.frame.after(80,self.poll)

    def copy(self):
        text=self.output.get('1.0','end-1c')
        if text:self.frame.clipboard_clear();self.frame.clipboard_append(text)
