import tkinter as tk
from tkinter import ttk
import unittest
from githug.terminology import Terminology

class TerminologyTests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError:self.skipTest('Tk display unavailable')
        self.root.withdraw();self.saved=[]
        self.terms=Terminology(self.root,on_change=self.saved.append)

    def tearDown(self):
        if hasattr(self,'root'):
            self.root.update_idletasks();self.root.destroy()

    def test_switch_preserves_inputs_selection_and_data(self):
        button=ttk.Button(self.root,text='記録してGitHubへ送る')
        menu_button=ttk.Menubutton(self.root,text='比べる・取り込む')
        copy=ttk.Button(self.root,text='この時点のファイルをPCへコピー')
        entry=ttk.Entry(self.root);entry.insert(0,'分岐の変更');entry.icursor(2);entry.selection_range(0,2)
        output=tk.Text(self.root);output.insert('1.0','GitHubの履歴を更新\nLLMの回答・自分用メモ')
        tree=ttk.Treeview(self.root,columns=('refs',));tree.heading('refs',text='作業の分岐・目印')
        tree.insert('', 'end',iid='sha',text='分岐の変更',values=('新しい分岐として送る',));tree.selection_set('sha')
        self.terms.refresh();self.assertEqual(tree.heading('refs','text'),'作業ルート・目印')
        for mode in ('git','operations','git'):
            self.terms.set_mode(mode)
            self.assertEqual(entry.get(),'分岐の変更');self.assertEqual(entry.index('insert'),2)
            self.assertTrue(entry.selection_present());self.assertEqual(tree.selection(),('sha',))
            self.assertEqual(tree.item('sha','values'),('新しい分岐として送る',))
            self.assertEqual(output.get('1.0','end-1c'),'GitHubの履歴を更新\nLLMの回答・自分用メモ')
            self.assertEqual(copy.cget('text'),'この時点のファイルをPCへコピー')
        self.assertEqual(button.cget('text'),'コミットしてプッシュ')
        self.assertEqual(menu_button.cget('text'),'比較・プルリクエスト')
        self.assertEqual(self.saved,['git','operations','git'])

    def test_choice_uses_same_semantics_after_repeated_switch(self):
        value=tk.StringVar(value='新しい分岐として送る')
        combo=ttk.Combobox(self.root,textvariable=value,values=('新しい分岐として送る','既存の分岐へ送る'),state='readonly')
        self.terms.bind_choices(combo);combo.current(1)
        for mode in ('git','operations','git','operations'):
            self.terms.set_mode(mode)
            self.assertEqual(combo.current(),1)
            self.assertEqual(self.terms.original(value.get()),'既存の分岐へ送る')
        # A branch name is an editable value, not an operation choice.
        branch=ttk.Combobox(self.root,values=('分岐の変更',));branch.set('分岐の変更')
        self.terms.set_mode('git');self.assertEqual(branch.get(),'分岐の変更')

    def test_new_menu_matches_mode_and_preserves_command(self):
        self.terms.set_mode('git');calls=[]
        menu=tk.Menu(self.root,tearoff=False)
        menu.add_command(label='変更を確認してGitHubへ送る',command=lambda:calls.append('send'))
        self.terms.refresh(menu)
        self.assertEqual(menu.entrycget(0,'label'),'変更を確認してプッシュ')
        self.assertEqual(calls,[]);menu.invoke(0);self.assertEqual(calls,['send'])

class FacingTests(unittest.TestCase):
    def test_boundary_stop_sit_and_think_keep_last_travel_direction(self):
        from githug.mascot import MascotModel
        for direction in (-1,1):
            m=MascotModel(seed=1);a=m.actors[0]
            a.direction=direction;a.facing=direction;a.state='walk';a.next_action=100
            a.x=a.left+.1 if direction==-1 else a.right-.1
            pose=m.advance(.1)[0]
            self.assertEqual(a.direction,-direction) # next walk reverses
            self.assertEqual(pose[4],direction) # last actual step does not
            self.assertEqual(m.advance(.2)[0][4],direction)
            a.state='down';a.since=.2
            self.assertEqual(m.advance(.3)[0][4],direction)
            self.assertEqual(m.advance(.7)[0][4],direction);self.assertTrue(a.sitting)
            m.begin('read','think');self.assertEqual(m.advance(.8)[0][4],direction)
            m.end('read');m.begin('copy','carry')
            self.assertEqual(m.advance(.9)[0][4],direction) # standing-up transition
            m.advance(1.2)
            self.assertEqual(m.advance(1.3)[0][4],-direction) # now actually moving

class ApplicationTerminologyTests(unittest.TestCase):
    def test_existing_settings_live_panel_and_new_mode_persist(self):
        import json,tempfile
        from pathlib import Path
        from githug.__main__ import App
        try:root=tk.Tk()
        except tk.TclError:self.skipTest('Tk display unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root._githug_smoke=True;root._githug_smoke_dir=directory
            path=Path(directory)/'settings.json'
            legacy={'root':'D:/existing-projects','projects':[],'author_name':'existing user','terminology':'git'}
            path.write_text(json.dumps(legacy),encoding='utf-8')
            errors=[];root.report_callback_exception=lambda *args:errors.append(args)
            try:
                app=App(root);root.update_idletasks()
                self.assertTrue(root.title().startswith('GitTotte '))
                self.assertEqual(app.history.heading('refs','text'),'ブランチ・目印')
                def button_texts(w):
                    return ([str(w.cget('text'))] if isinstance(w,ttk.Button) else [])+sum((button_texts(c) for c in w.winfo_children()),[])
                self.assertNotIn('PowerShell',button_texts(root))
                self.assertIn('PowerShell／コマンド',button_texts(root))
                panel=app.explanation
                panel.mode_picker.current(1)
                panel.base.set('my/分岐の変更')
                panel.payload='prepared payload';panel.write(panel.output,'LLM answer')
                for mode in ('operations','git','operations'):
                    app.term_mode.set(mode);app.terms.set_mode(mode);root.update_idletasks()
                    self.assertEqual(panel.payload,'prepared payload')
                    self.assertEqual(panel.base.get(),'my/分岐の変更')
                    self.assertEqual(panel.output.get('1.0','end-1c'),'LLM answer')
                    self.assertEqual(app.terms.original(panel.mode.get()),'分岐の変更')
                saved=json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(saved['root'],legacy['root']);self.assertEqual(saved['author_name'],legacy['author_name'])
                self.assertEqual(saved['terminology'],'operations');self.assertFalse(errors)
            finally:
                root.destroy()
