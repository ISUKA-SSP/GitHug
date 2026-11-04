"""Optional Gemini panel: prepare, inspect, explicitly send. No conversation or automatic calls."""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from .explaining import explain, normalize_api_key
from .inspection import file_input,history_input
from .view_switch import ViewSwitch
from .reading import write_explanation
from .credentials import CredentialStore, CredentialError


class ExplanationPanel:
    def __init__(self,parent,app):
        self.app=app;self.frame=ttk.Frame(parent,padding=12,width=350,style='Card.TFrame');self.frame.pack_propagate(False);self.target=None;self.pending=queue.Queue();self.busy=False
        self.payload=None;self.prepared_target=None
        top=ttk.Frame(self.frame);top.pack(fill='x')
        top.columnconfigure(0,weight=1)
        ttk.Label(top,text='説明',style='Heading.TLabel').grid(row=0,column=0,sticky='w')
        close_button=ttk.Button(top,text='✖',width=3,command=app.toggle_explanation,style='Icon.TButton')
        close_button.grid(row=0,column=2,sticky='e')
        self.tooltip(close_button,'説明パネルを閉じる')
        self.caption=tk.StringVar(value='履歴か左下のファイルを選択')
        ttk.Label(self.frame,textvariable=self.caption,wraplength=300).pack(fill='x',pady=8)
        self.mode=tk.StringVar(value='一つの履歴')
        self.mode_picker=ttk.Combobox(self.frame,textvariable=self.mode,values=('一つの履歴','分岐の変更'),state='readonly')
        self.mode_picker.pack(fill='x')
        self.base_area=ttk.Frame(self.frame)
        ttk.Label(self.base_area,text='どこからの変更を説明する？',style='Muted.TLabel').pack(anchor='w',pady=(6,0))
        self.base=tk.StringVar(value='main')
        self.base_picker=ttk.Combobox(self.base_area,textvariable=self.base,values=('main',))
        self.base_picker.pack(fill='x')
        self.tooltip(self.base_picker,'説明の出発点を選びます。例：mainから選んだ履歴までの変更。名前の入力もできます。')
        self.detail=tk.BooleanVar(value=False)
        self.detail_checkbox=ttk.Checkbutton(self.frame,text='内容・差分の本文も含める',variable=self.detail)
        self.detail_checkbox.pack(anchor='w',pady=4)
        self.model=tk.StringVar(value=app.config.get('explanation_model',''))
        self.key=tk.StringVar()
        self.key_store=CredentialStore('GitHug/Smoke/unused' if getattr(app.window,'_githug_smoke',False) else 'GitHug/Gemini/APIKey')
        self.key_store_error=''
        try:self.key.set(self.key_store.read())
        except CredentialError as exc:self.key_store_error=str(exc)
        self.key_saved=bool(self.key.get())
        settings_button=ttk.Button(top,text='⚙',width=3,command=self.settings_dialog,style='Icon.TButton')
        settings_button.grid(row=0,column=1,sticky='e',padx=(4,4))
        self.tooltip(settings_button,'Geminiの接続設定')
        self.header_buttons=(settings_button,close_button)
        self.prepare=ttk.Button(self.frame,text='送信内容を確認',command=self.prepare_input);self.prepare.pack(fill='x',pady=(8,4))
        self.send=ttk.Button(self.frame,text='Geminiへ送って説明する',command=self.request,style='Primary.TButton',state='disabled');self.send.pack(fill='x')
        self.state=tk.StringVar(value='選択だけでは送信しません。説明はAIの推測を含みます。')
        ttk.Label(self.frame,textvariable=self.state,wraplength=300,style='Muted.TLabel').pack(fill='x',pady=8)
        tabs=ViewSwitch(self.frame);tabs.pack(fill='both',expand=True)
        self.output=self.text_area(tabs,'説明');self.preview=self.text_area(tabs,'送信内容')
        self.tabs=tabs
        ttk.Button(self.frame,text='説明をコピー',command=self.copy).pack(anchor='e',pady=(4,0))
        for variable in (self.mode,self.base,self.detail):variable.trace_add('write',self.invalidate)
        self.frame.after(80,self.poll)

    def tooltip(self,widget,label):
        self.app.tooltips.add(widget,label)

    def settings_dialog(self):
        existing=getattr(self,'settings_window',None)
        if existing is not None and existing.winfo_exists():existing.lift();return existing
        popup=tk.Toplevel(self.frame);self.settings_window=popup
        popup.title('Gemini 接続設定');popup.geometry('650x490');popup.minsize(520,470)
        area=ttk.Frame(popup,padding=18);area.pack(fill='both',expand=True)
        ttk.Label(area,text='Geminiへの接続',style='Heading.TLabel').pack(anchor='w',pady=(0,12))
        ttk.Label(area,text='モデル名（Google AI Studioで利用できる名前）').pack(anchor='w')
        model=tk.StringVar(value=self.model.get());ttk.Entry(area,textvariable=model).pack(fill='x',pady=(4,12))
        ttk.Label(area,text='APIキー').pack(anchor='w')
        key=tk.StringVar(value=self.key.get());entry=ttk.Entry(area,textvariable=key,show='•');entry.pack(fill='x',pady=4)
        remember=tk.BooleanVar(value=self.key_saved)
        checkbox=ttk.Checkbutton(area,text='このPCにAPIキーを保存する',variable=remember)
        checkbox.pack(anchor='w',pady=(8,4))
        if not self.key_store.available:checkbox.configure(state='disabled')
        ttk.Label(area,text='保存先はWindowsの資格情報マネージャーです。\n保存しない場合は、このアプリを閉じるまでだけ保持します。\nチェックを外して適用すると、保存済みキーを削除します。\n設定を適用しても通信しません。',style='Muted.TLabel',wraplength=540).pack(anchor='w',pady=8)
        status=tk.StringVar(value=self.key_store_error or ('APIキーはこのPCに保存されています。' if self.key_saved else 'APIキーは保存されていません。'));ttk.Label(area,textvariable=status,wraplength=540).pack(fill='x')
        buttons=ttk.Frame(area);buttons.pack(side='bottom',fill='x')
        def close():
            key.set('');popup.destroy()
        def apply():
            try:value=normalize_api_key(key.get()) if key.get().strip() else ''
            except ValueError as exc:status.set(str(exc));return
            try:
                if remember.get():
                    if not value:status.set('保存するAPIキーを入力してください。');return
                    self.key_store.write(value)
                elif self.key_saved:self.key_store.delete()
            except CredentialError as exc:status.set(str(exc));return
            self.key_saved=remember.get();self.key_store_error=''
            self.model.set(model.get().strip());self.key.set(value)
            self.app.config['explanation_model']=self.model.get();self.app.save()
            self.state.set('接続設定を適用しました。送信内容を確認して依頼してください。')
            close()
        def forget():
            try:self.key_store.delete()
            except CredentialError as exc:status.set(str(exc));return
            self.key_saved=False;self.key_store_error='';remember.set(False);key.set('');self.key.set('')
            status.set('保存済みキーを削除しました。使用中のキーもクリアしました。')
        ttk.Button(area,text='保存済みキーを削除',command=forget).pack(anchor='w',pady=4)
        ttk.Button(buttons,text='キャンセル',command=close).pack(side='right')
        ttk.Button(buttons,text='適用',command=apply,style='Primary.TButton').pack(side='right',padx=8)
        popup.protocol('WM_DELETE_WINDOW',close)
        return popup

    def text_area(self,tabs,title):
        frame=ttk.Frame(tabs.body);tabs.add(frame,text=title)
        bar=ttk.Scrollbar(frame);bar.pack(side='right',fill='y')
        text=tk.Text(frame,width=28,height=6,wrap='word',state='disabled',yscrollcommand=bar.set,font=('Yu Gothic UI',11),padx=8,pady=8,spacing3=3)
        bar.configure(command=text.yview);text.pack(fill='both',expand=True)
        return text

    @staticmethod
    def write(widget,value):
        widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',value);widget.configure(state='disabled')

    def choose(self,target):
        self.target=target
        history=bool(target and target['kind']=='history')
        self.mode_picker.configure(state='readonly' if history else 'disabled')
        refs={'main'}
        for record in getattr(self.app,'records',{}).values():
            for ref in record.get('refs','').split(', '):
                ref=ref.removeprefix('HEAD -> ').strip()
                if ref and not ref.startswith('tag:'):refs.add(ref)
        self.base_picker.configure(values=sorted(refs))
        self.update_base_visibility()
        self.caption.set((target['label'][:100]+('…' if len(target['label'])>100 else '')) if target else '履歴か左下のファイルを選択')
        self.payload=None;self.send.configure(state='disabled')
        if not self.busy:
            self.write(self.preview,'');self.state.set('送信前に内容を確認してください。')

    def update_base_visibility(self):
        visible=self.target and self.target['kind']=='history' and self.mode.get()=='分岐の変更'
        if visible:self.base_area.pack(fill='x',before=self.detail_checkbox)
        else:self.base_area.pack_forget()

    def invalidate(self,*args):
        self.update_base_visibility()
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
        if target['kind']=='history' and mode=='分岐の変更' and not base:
            self.state.set('比べる作業の分岐名（例: main）を入力してください。');return
        self.prepared_target=target;self.prepared_options=(mode,base,detail);self.payload=None
        self.state.set('送信する内容を準備中…（まだ通信しません）')
        def build():
            text=file_input(target['path'],detail) if target['kind']=='file' else history_input(target['project'],target['sha'],base if mode=='分岐の変更' else None,detail)
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
        self.state.set('Geminiに説明を依頼中…')
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
                write_explanation(self.output,'対象: '+self.answer_label+'\n\n'+value);self.tabs.select(0)
                self.payload=None;self.state.set('説明を受信しました。再依頼には送信内容を確認してください。')
        self.frame.after(80,self.poll)

    def copy(self):
        text=self.output.get('1.0','end-1c')
        if text:self.frame.clipboard_clear();self.frame.clipboard_append(text)
