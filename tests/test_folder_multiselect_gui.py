import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock,patch
from githug.__main__ import App
from githug.core import Project

class FolderSelectionTests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError:self.skipTest('Tk display unavailable')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.root._githug_smoke=True;self.root._githug_smoke_dir=str(self.base)
        self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.app=App(self.root);self.root.update()
        app=self.app;app.project=Project(self.base/'storage','https://github.com/example/test')
        app.project.base.mkdir(parents=True)
        app.current={'url':app.project.url,'work':[str(self.base/name) for name in ('a','b','c','d')]}
        app.config.update(root=str(self.base/'storage'),projects=[app.current])
        (self.base/'a').mkdir();(self.base/'b').mkdir()
        app.push_ui.begin=Mock();app.load_folders();self.root.update()

    def tearDown(self):
        if hasattr(self,'app'):
            self.root.update_idletasks()
            for timer in self.root.tk.call('after','info'):self.root.tk.call('after','cancel',timer)
            self.root.destroy()

    def click(self,item,state=0):
        self.app.folders.see(item);self.root.update_idletasks()
        box=self.app.folders.bbox(item);self.assertTrue(box)
        x,y=box[0]+10,box[1]+box[3]//2
        # Synthetic clicks must have distinct timestamps to avoid accidental double-click bindings after scrolling.
        self.click_time=getattr(self,'click_time',0)+1000
        self.app.folders.event_generate('<ButtonPress-1>',x=x,y=y,state=state,time=self.click_time)
        self.app.folders.event_generate('<ButtonRelease-1>',x=x,y=y,state=state,time=self.click_time+100)
        self.root.update()

    def test_ctrl_shift_selection_and_multiple_drag_cannot_send(self):
        tree=self.app.folders;rows=tree.get_children()
        self.click(rows[0]);self.click(rows[2],4)
        self.assertEqual(set(tree.selection()),{rows[0],rows[2]})
        self.click(rows[2],4);self.assertEqual(tree.selection(),(rows[0],))
        self.click(rows[3],1);self.assertEqual(set(tree.selection()),set(rows))
        tree.see(rows[0]);self.root.update_idletasks()
        box=tree.bbox(rows[0]);x,y=box[0]+10,box[1]+5
        tree.event_generate('<ButtonPress-1>',x=x,y=y,time=10000)
        tree.event_generate('<B1-Motion>',x=x+20,y=y-80,state=0x100)
        tree.event_generate('<ButtonRelease-1>',x=x+20,y=y-80)
        self.root.update()
        self.assertEqual(set(tree.selection()),set(rows));self.app.push_ui.begin.assert_not_called()
        self.assertIn('1つ',self.app.status.get());self.assertFalse(self.errors)

    def test_right_click_preserves_group_and_mixed_actions(self):
        tree=self.app.folders;rows=tree.get_children();tree.selection_set((rows[0],rows[2]));self.root.update()
        box=tree.bbox(rows[0]);event=type('Event',(),{'y':box[1]+5,'x_root':30,'y_root':30})()
        captured=[]
        with patch.object(tk.Menu,'tk_popup',lambda menu,*args:captured.append(menu)):
            self.app.folder_menu(event)
        self.assertEqual(set(tree.selection()),{rows[0],rows[2]})
        menu=captured[0]
        entries={menu.entrycget(i,'label'):menu.entrycget(i,'state') for i in range(menu.index('end')+1) if menu.type(i)=='command'}
        self.assertEqual(entries['フォルダーをごみ箱へ移動'],'normal')
        self.assertEqual(entries['見つからない項目を一覧から取り除く'],'normal')
        self.assertEqual(entries['変更を確認してGitHubへ送る'],'disabled')
        self.assertEqual(entries['自分用メモを編集'],'disabled')
        self.assertFalse(self.errors)

    def test_selection_survives_refresh_when_work_indices_change(self):
        tree=self.app.folders;tree.selection_set(('work:1','work:2'));tree.focus('work:2')
        self.app.current['work'].pop(0);self.app.load_folders();self.root.update()
        self.assertEqual({tree.item(item,'values')[1] for item in tree.selection()},{str(self.base/'b'),str(self.base/'c')})
        self.assertEqual(tree.item(tree.focus(),'values')[1],str(self.base/'c'))
