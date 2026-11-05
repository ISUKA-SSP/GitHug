"""Live terminology presentation. Never changes data, commands, or editable content."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox as native_messagebox
from weakref import WeakKeyDictionary

CATALOG=json.loads((Path(__file__).parent/'assets'/'terminology.json').read_text(encoding='utf-8'))

class Terminology:
    def __init__(self,root,mode='operations',on_change=None):
        self.root=root;self.mode=mode if mode in ('operations','git') else 'operations'
        self.on_change=on_change;self.updating=False;self.pending=None
        self.labels=WeakKeyDictionary();self.choices=WeakKeyDictionary();self.variables=[]
        root._gittotte_terms=self
        root.bind_all('<Map>',self.on_map,add='+')

    def text(self,value):
        return CATALOG.get(value,{}).get(self.mode,value)

    def original(self,value):
        if value in CATALOG:return value
        return next((raw for raw,pair in CATALOG.items() if value in pair.values()),value)

    def on_map(self,event):
        if self.pending is None:self.pending=self.root.after_idle(self.refresh)

    def bind_choices(self,widget):
        self.choices[widget]=tuple(widget.cget('values'))
        self.refresh()

    def bind_variable(self,variable):
        def changed(*args):
            if self.updating:return
            raw=self.original(variable.get())
            self.updating=True
            try:variable.set(self.text(raw))
            finally:self.updating=False
        variable.trace_add('write',changed)
        self.variables.append((variable,changed))
        changed()

    def set_mode(self,mode):
        if mode not in ('operations','git'):raise ValueError('Unknown terminology mode')
        if mode==self.mode:return
        self.mode=mode;self.refresh()
        if self.on_change:self.on_change(mode)

    def refresh(self,subtree=None):
        self.pending=None
        self.updating=True
        try:
            for widget,values in list(self.choices.items()):
                if not widget.winfo_exists():continue
                # Translate display values, retaining their semantic selection.
                index=widget.current()
                if index<0:
                    raw=self.original(widget.get())
                    index=values.index(raw) if raw in values else -1
                widget.configure(values=tuple(self.text(value) for value in values))
                if index>=0:widget.current(index)
            for variable,_ in self.variables:
                variable.set(self.text(self.original(variable.get())))
            self._walk(subtree or self.root)
        finally:self.updating=False

    def _display(self,widget,key,current,setter):
        saved=self.labels.setdefault(widget,{})
        raw,last=saved.get(key,(current,current))
        if current!=last:raw=current
        value=self.text(raw);saved[key]=(raw,value)
        if value!=current:setter(value)

    def _walk(self,widget):
        if isinstance(widget,(ttk.Label,ttk.Button,ttk.Menubutton,ttk.Checkbutton,ttk.Radiobutton,ttk.LabelFrame)):
            # Dynamic labels can contain commit messages, paths, or user notes.
            if 'textvariable' not in widget.keys() or not str(widget.cget('textvariable')):
                self._display(widget,'text',str(widget.cget('text')),lambda value:widget.configure(text=value))
        if isinstance(widget,ttk.Treeview):
            for column in ('#0',*widget.cget('columns')):
                self._display(widget,column,widget.heading(column,'text'),lambda value,c=column:widget.heading(c,text=value))
        if isinstance(widget,tk.Menu):
            end=widget.index('end')
            for index in range((end if end is not None else -1)+1):
                if widget.type(index) in ('command','cascade','checkbutton','radiobutton'):
                    self._display(widget,index,widget.entrycget(index,'label'),lambda value,i=index:widget.entryconfigure(i,label=value))
        if isinstance(widget,tk.Toplevel):
            self._display(widget,'title',widget.title(),widget.title)
        for child in widget.winfo_children():self._walk(child)

class MessageBoxes:
    """Translate app-authored modal messages at creation; no global Tk monkey patch."""
    def __getattr__(self,name):
        native=getattr(native_messagebox,name)
        def show(*args,**kwargs):
            parent=kwargs.get('parent') or tk._default_root
            terms=getattr(parent.winfo_toplevel(),'_gittotte_terms',None) if parent else None
            if terms is None and tk._default_root is not None:terms=getattr(tk._default_root,'_gittotte_terms',None)
            if terms:
                args=tuple(terms.text(arg) if isinstance(arg,str) else arg for arg in args)
                kwargs={key:terms.text(value) if key in ('title','message','detail') and isinstance(value,str) else value for key,value in kwargs.items()}
            return native(*args,**kwargs)
        return show

messagebox=MessageBoxes()
