"""Horizontal panes with minimum widths, independent of child requested sizes."""
import tkinter as tk

class SidebarSplitter(tk.PanedWindow):
    def __init__(self,parent,orient='horizontal'):
        super().__init__(parent,orient=orient,background='#383838',borderwidth=0,
                         sashwidth=7,sashrelief='flat',opaqueresize=True,showhandle=False)

    def add(self,child,weight=0,**kwargs):
        index=len(self.panes())
        minimum=(180,400,300)[min(index,2)]
        super().add(child,minsize=minimum,stretch='always' if weight else 'never',**kwargs)

    def sashpos(self,index,newpos=None):
        if newpos is None:return self.sash_coord(index)[0]
        self.sash_place(index,newpos,0)
        return self.sash_coord(index)[0]


class SectionSplitter(tk.PanedWindow):
    """Keep both lists visible when their requested sizes change at startup."""
    def __init__(self,parent):
        super().__init__(parent,orient='vertical',background='#383838',borderwidth=0,
                         sashwidth=7,sashrelief='flat',opaqueresize=True,showhandle=False)

    def add(self,child,weight=0,**kwargs):
        minimum=320 if not self.panes() else 220
        super().add(child,minsize=minimum,stretch='always',**kwargs)

    def sashpos(self,index,newpos=None):
        if newpos is None:return self.sash_coord(index)[1]
        self.sash_place(index,0,newpos)
        return self.sash_coord(index)[1]
