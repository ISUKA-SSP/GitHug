"""Read-only, asynchronous one-level folder browser."""
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox


def children(folder, limit=20000):
    entries=[]
    with os.scandir(folder) as stream:
        for entry in stream:
            if entry.name == '.git': continue
            if len(entries)>=limit: raise ValueError('項目が多すぎます。エクスプローラーで開いてください。')
            # Never traverse symlinks or Windows junctions.
            path=Path(entry.path)
            linked=entry.is_symlink() or getattr(path,'is_junction',lambda:False)()
            entries.append((entry.name,str(path),entry.is_dir(follow_symlinks=False) and not linked,linked))
    return sorted(entries,key=lambda x:(not x[2],x[0].casefold()))


class FolderTree:
    def __init__(self,parent,on_file):
        self.frame=ttk.Frame(parent,padding=(0,8,0,0))
        self.frame.pack(fill='both',expand=True)
        ttk.Label(self.frame,text='フォルダーの中身',style='Heading.TLabel').pack(anchor='w')
        self.caption=tk.StringVar(value='下のPC一覧から選択')
        ttk.Label(self.frame,textvariable=self.caption,wraplength=210,style='Muted.TLabel').pack(fill='x',pady=4)
        area=ttk.Frame(self.frame);area.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(area,show='tree',selectmode='browse',height=7)
        self.tree.column('#0',width=180,minwidth=90)
        scroll=ttk.Scrollbar(area,command=self.tree.yview);scroll.pack(side='right',fill='y')
        self.tree.configure(yscrollcommand=scroll.set);self.tree.pack(fill='both',expand=True)
        self.on_file=on_file;self.paths={};self.loaded=set();self.generation=0;self.pending=queue.Queue();self.root=None
        self.tree.bind('<<TreeviewOpen>>',self.expand)
        self.tree.bind('<<TreeviewSelect>>',self.select)
        self.tree.bind('<Double-1>',self.open_selected)
        ttk.Button(self.frame,text='中身を更新',command=lambda:self.set_folder(self.root)).pack(anchor='w',pady=(4,0))
        self.tree.after(80,self.poll)

    def set_folder(self,folder):
        self.generation+=1;self.root=folder;self.paths.clear();self.loaded.clear()
        self.tree.delete(*self.tree.get_children())
        self.caption.set(str(folder) if folder else '下のPC一覧から選択')
        if not folder:return
        path=Path(folder)
        if not path.is_dir():self.caption.set('削除または移動されています');return
        item=self.tree.insert('','end',text=path.name or str(path),open=True)
        self.paths[item]=(str(path),True,False);self.load(item)

    def load(self,item):
        if item in self.loaded or item not in self.paths:return
        self.loaded.add(item);generation=self.generation;folder=self.paths[item][0]
        self.tree.delete(*self.tree.get_children(item))
        self.tree.insert(item,'end',text='読み込み中…')
        def work():
            try:result=children(folder);error=None
            except (OSError,ValueError) as exc:result=[];error=str(exc)
            self.pending.put((generation,item,result,error))
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        if not self.tree.winfo_exists():return
        while not self.pending.empty():
            generation,item,entries,error=self.pending.get()
            if generation!=self.generation or not self.tree.exists(item):continue
            self.tree.delete(*self.tree.get_children(item))
            if error:
                self.loaded.discard(item);self.tree.insert(item,'end',text='読み込めません（開き直して再試行）');self.caption.set(error);continue
            for name,path,is_dir,linked in entries:
                child=self.tree.insert(item,'end',text=('▸ ' if is_dir else '')+name+('（リンク）' if linked else ''))
                self.paths[child]=(path,is_dir,linked)
                if is_dir:self.tree.insert(child,'end',text='')
        self.tree.after(80,self.poll)

    def expand(self,event=None):self.load(self.tree.focus())

    def select(self,event=None):
        item=self.tree.focus()
        if item in self.paths:
            path,is_dir,linked=self.paths[item]
            if not is_dir and not linked:self.on_file(path)

    def open_selected(self,event=None):
        item=self.tree.identify_row(event.y) if event else self.tree.focus()
        if item not in self.paths:return
        path,is_dir,linked=self.paths[item]
        if is_dir:return
        if linked:return 'break'
        if Path(path).suffix.lower() in {'.exe','.com','.bat','.cmd','.ps1','.msi','.vbs','.js','.scr','.lnk','.py','.pyw'}:
            if not messagebox.askyesno('実行可能なファイル',Path(path).name+' を関連付けられたアプリで開きますか？実行される可能性があります。',parent=self.frame):return 'break'
        try:
            if os.name=='nt':os.startfile(path)
            else:messagebox.showinfo('ファイル',path,parent=self.frame)
        except OSError as exc:messagebox.showinfo('開けませんでした',str(exc),parent=self.frame)
        return 'break'
