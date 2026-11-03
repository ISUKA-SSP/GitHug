"""Equal-size view selectors without notebook selected-tab expansion."""
from tkinter import ttk

class ViewSwitch(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.bar=ttk.Frame(self);self.bar.pack(fill='x',pady=(0,6))
        self.body=ttk.Frame(self);self.body.pack(fill='both',expand=True)
        self.body.columnconfigure(0,weight=1);self.body.rowconfigure(0,weight=1)
        self.pages=[];self.buttons=[];self.labels=[];self.current=0

    def add(self,frame,text):
        index=len(self.pages);self.pages.append(frame);self.labels.append(text)
        frame.grid(row=0,column=0,sticky='nsew')
        button=ttk.Button(self.bar,text=text,command=lambda:self.select(index),style='View.TButton')
        button.grid(row=0,column=index,sticky='ew',padx=(0,3) if not index else (3,0))
        self.bar.columnconfigure(index,weight=1,uniform='views')
        self.buttons.append(button);self.select(self.current)

    def select(self,index):
        self.current=index;self.pages[index].tkraise()
        for i,button in enumerate(self.buttons):
            button.configure(text=('● ' if i==index else '')+self.labels[i],style='SelectedView.TButton' if i==index else 'View.TButton')
