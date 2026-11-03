"""Optional Gemini panel: prepare, inspect, explicitly send. No conversation or automatic calls."""
import queue
import threading
import tkinter as tk
from tkinter import ttk
from .explaining import explain
from .inspection import file_input,history_input


class ExplanationPanel:
    def __init__(self,parent,app):
        self.app=app;self.frame=ttk.Frame(parent,padding=12,style='Card.TFrame');self.target=None;self.pending=queue.Queue();self.busy=False
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
        ttk.Label(self.frame,text='Geminiモデル名',style='Muted.TLabel').pack(anchor='w')
        self.model=tk.StringVar(value=app.config.get('explanation_model',''))
        ttk.Entry(self.frame,textvariable=self.model).pack(fill='x')
        ttk.Label(self.frame,text='APIキー（終了時に破棄・保存しません）',style='Muted.TLabel').pack(anchor='w',pady=(6,0))
        self.key=tk.StringVar();ttk.Entry(self.frame,textvariable=self.key,show='•').pack(fill='x')
        self.prepare=ttk.Button(self.frame,text='送信内容を確認',command=self.prepare_input);self.prepare.pack(fill='x',pady=(8,4))
        self.send=ttk.Button(self.frame,text='Geminiへ送って説明する',command=self.request,style='Primary.TButton',state='disabled');self.send.pack(fill='x')
        self.state=tk.StringVar(value='選択だけでは送信しません。説明はAIの推測を含みます。')
        ttk.Label(self.frame,textvariable=self.state,wraplength=300,style='Muted.TLabel').pack(fill='x',pady=8)
        tabs=ttk.Notebook(self.frame);tabs.pack(fill='both',expand=True)
        self.output=self.text_area(tabs,'説明');self.preview=self.text_area(tabs,'送信内容')
        self.tabs=tabs
        ttk.Button(self.frame,text='説明をコピー',command=self.copy).pack(anchor='e',pady=(4,0))
        self.frame.after(80,self.poll)

    def text_area(self,tabs,title):
        frame=ttk.Frame(tabs);tabs.add(frame,text=title)
        bar=ttk.Scrollbar(frame);bar.pack(side='right',fill='y')
        text=tk.Text(frame,width=28,height=6,wrap='word',state='disabled',yscrollcommand=bar.set)
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
        self.prepared_target=target;self.payload=None
        self.state.set('送信する内容を準備中…（まだ通信しません）')
        def build():
            text=file_input(target['path'],detail) if target['kind']=='file' else history_input(target['project'],target['sha'],base if mode=='枝の変更' else None,detail)
            return text
        self.launch('prepare',build)

    def request(self):
        if not self.payload or self.busy:return
        if not self.key.get().strip() or not self.model.get().strip():self.state.set('モデル名とAPIキーを入力してください。');return
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
                self.state.set(error);self.send.configure(state='normal' if self.payload else 'disabled');continue
            if kind=='prepare':
                # A selection change during preparation invalidates the prepared send action.
                if self.target!=self.prepared_target:
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
