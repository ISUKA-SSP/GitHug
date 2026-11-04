"""A one-row heading and search field, leaving height for the actual list."""
import tkinter as tk
from tkinter import ttk

class SearchHeader(ttk.Frame):
    def __init__(self,parent,title):
        super().__init__(parent)
        self.columnconfigure(1,weight=1)
        self.title=ttk.Label(self,text=title,style='Heading.TLabel')
        self.title.grid(row=0,column=0,sticky='w',padx=(0,12))
        self.query=tk.StringVar();self.count=tk.StringVar()
        search=ttk.Frame(self);search.grid(row=0,column=1,sticky='ew')
        search.columnconfigure(1,weight=1)
        ttk.Label(search,text='検索',style='Muted.TLabel').grid(row=0,column=0,padx=(0,6))
        self.entry=ttk.Entry(search,textvariable=self.query,width=10)
        self.entry.grid(row=0,column=1,sticky='ew')
        self.clear_button=ttk.Button(search,text='×',width=2,command=self.clear)
        self.clear_button.grid(row=0,column=2,padx=(4,8))
        self.counter=ttk.Label(search,textvariable=self.count,style='Muted.TLabel')
        self.counter.grid(row=0,column=3,sticky='e')
        self.entry.bind('<Escape>',lambda event:self.clear())

    def clear(self):
        self.query.set('');self.entry.focus_set()
