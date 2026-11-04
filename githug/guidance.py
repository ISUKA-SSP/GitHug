"""Optional, short-lived hover help. No extra permanent screen area."""
import tkinter as tk
from tkinter import ttk

class HoverHelp:
    def __init__(self,root,enabled=True,delay=650,duration=4500):
        self.root=root;self.enabled=enabled;self.delay=delay;self.duration=duration
        self.tip=None;self.timer=None;self.expiry=None;self.owner=None
        root.bind('<Unmap>',lambda e:self.hide() if e.widget is root else None,add='+')
        root.bind('<FocusOut>',lambda e:self.hide() if e.widget is root else None,add='+')
        root.bind('<MouseWheel>',lambda e:self.hide(),add='+')

    def set_enabled(self,value):
        self.enabled=bool(value)
        if not self.enabled:self.hide()

    def hide(self,event=None):
        for name in ('timer','expiry'):
            timer=getattr(self,name)
            if timer is not None:
                try:self.root.after_cancel(timer)
                except tk.TclError:pass
                setattr(self,name,None)
        if self.tip is not None:
            try:self.tip.destroy()
            except tk.TclError:pass
        self.tip=None;self.owner=None

    def add(self,widget,text):
        if getattr(widget,'_hug_help',False):return
        widget._hug_help=True
        def enter(event=None):
            self.hide()
            if self.enabled:
                self.owner=widget
                self.timer=self.root.after(self.delay,lambda:self.show(widget,text))
        widget.bind('<Enter>',enter,add='+')
        for event in ('<Leave>','<ButtonPress>','<Destroy>'):
            widget.bind(event,lambda e:self.hide() if self.owner is widget else None,add='+')

    def show(self,widget,text):
        self.timer=None
        if not self.enabled or self.owner is not widget:return
        try:
            if not widget.winfo_exists() or not widget.winfo_ismapped():return
            self.tip=tk.Toplevel(self.root);self.tip.overrideredirect(True)
            ttk.Label(self.tip,text=text,padding=10,wraplength=360,justify='left').pack()
            self.tip.update_idletasks()
            width,height=self.tip.winfo_reqwidth(),self.tip.winfo_reqheight()
            x=max(0,min(widget.winfo_rootx(),self.root.winfo_screenwidth()-width-8))
            y=widget.winfo_rooty()+widget.winfo_height()+6
            if y+height>self.root.winfo_screenheight():y=max(0,widget.winfo_rooty()-height-6)
            self.tip.geometry(f'+{x}+{y}')
            self.expiry=self.root.after(self.duration,self.hide)
        except tk.TclError:self.hide()

BUTTON_HELP={
 'GitHubの履歴を更新':'GitHubの新しい履歴を取得します。PCの作業ファイルは変更しません。',
 '＋ プロジェクト':'GitHubのURLを登録して、履歴やファイルを扱えるようにします。',
 '更新前のバックアップ':'フォルダーの更新前に残したバックアップを確認します。',
 'コピー・履歴の保存先':'新しく登録するプロジェクトの履歴とコピーフォルダーの保存先を選びます。',
 'この時点のファイルをPCへコピー':'選んだ履歴のファイルを、新しいフォルダーにコピーします。',
 '作業フォルダーと比較':'選んだ履歴と作業フォルダーのファイルの違いを確認します。',
 '作業フォルダーを登録':'普段編集しているフォルダーを一覧に追加します。登録だけではファイルを変更しません。',
 'フォルダーを開く':'選んだPCのフォルダーをエクスプローラーで開きます。',
 'PowerShell／コマンド':'選んだフォルダーを作業場所にして、PowerShellや複数行のコマンドを実行します。',
 '一覧を再表示':'PCのフォルダーの現在の状態を確認して、一覧に反映します。',
 '説明パネル':'選んだ履歴やファイルについて、Geminiに説明を頼めるパネルを開閉します。',
 '送信内容を確認':'Geminiに送る情報を準備して表示します。この操作では送信しません。',
 'Geminiへ送って説明する':'確認した情報をGoogle Geminiへ送信します。選ぶだけでは送信されません。',
 '説明をコピー':'表示されている説明をクリップボードにコピーします。',
 '選んだ履歴をグラフで見る':'検索や並べ替えを解除し、選んだ履歴をつながり順のグラフで表示します。',
 '設定':'マウスを重ねたときの説明と、操作案内の表示を切り替えます。',
 '使い方・環境':'基本操作と、使用中のGitや設定ファイルの場所を確認します。',
}

def register_buttons(root,help):
    for child in root.winfo_children():
        if isinstance(child,ttk.Button):
            text=str(child.cget('text'))
            if text in BUTTON_HELP:help.add(child,BUTTON_HELP[text])
        register_buttons(child,help)
