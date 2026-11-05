from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import Mock,patch
from githug.__main__ import App
from githug.core import Project,git
from githug.operation_guide import open_guide,begin,finish

class GuideUiTests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError:self.skipTest('Tk display unavailable')
        self.tmp=tempfile.TemporaryDirectory();self.root._githug_smoke=True;self.root._githug_smoke_dir=self.tmp.name
        self.errors=[];self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.app=App(self.root);self.root.update()
    def tearDown(self):
        if not hasattr(self,'root'):return
        for timer in self.root.tk.splitlist(self.root.tk.call('after','info')):
            self.root.tk.call('after','cancel',timer)
        self.root.destroy();self.tmp.cleanup()
    def wait(self):
        end=time.monotonic()+30
        while self.app.busy and time.monotonic()<end:self.root.update();time.sleep(.02)
        self.root.update();self.assertFalse(self.app.busy)
    def fixture(self):
        root=Path(self.tmp.name).resolve();seed=root/'seed';git('init','-b','main',seed)
        git('config','user.name','Test',cwd=seed);git('config','user.email','test@example.invalid',cwd=seed)
        (seed/'file.txt').write_text('saved content');git('add','.',cwd=seed);git('-c','commit.gpgsign=false','commit','-m','base',cwd=seed)
        project=Project(root/'managed','https://github.com/example/test');project.base.mkdir(parents=True);git('clone','--mirror',seed,project.cache)
        self.app.project=project;self.app.current={'url':project.url,'work':[]};self.app.show_history(project.history());self.root.update()
        return project,project.history()[0]['sha']
    def test_home_back_singleton_and_close_preserve_main_state(self):
        guide=open_guide(self.app);self.root.update();self.assertIs(open_guide(self.app),guide)
        self.assertIsNone(self.root.grab_current())
        guide.navigate('copy');guide.navigate('steps','copy');guide.tick_now()
        self.assertEqual(guide.step,'project');self.assertIs(guide.highlight.target,self.app.projects)
        guide.back();self.assertEqual(guide.page,'copy');guide.back();self.assertEqual(guide.page,'home')
        guide.close();self.assertFalse(guide.alive());self.assertIsNone(guide.timer);self.assertFalse(guide.highlight.edges)
        self.assertFalse(self.errors)
    def test_actual_copy_and_compare_complete_only_after_success(self):
        project,sha=self.fixture();guide=open_guide(self.app);guide.navigate('steps','copy');guide.tick_now()
        self.assertEqual(guide.step,'history');self.app.history.selection_set(sha);self.root.update();guide.tick_now()
        self.assertEqual(guide.step,'act');self.assertIs(guide.highlight.target,self.app.folders)
        with patch('githug.__main__.messagebox.showinfo'):
            guide.execute();self.wait()
        self.assertTrue(guide.completed);self.assertEqual(len(project.snapshots()),1)
        folder=Path(project.snapshots()[0]['folder']);self.assertEqual((folder/'file.txt').read_text(),'saved content')
        guide.home();guide.navigate('steps','compare');guide.tick_now();self.assertEqual(guide.step,'act')
        with patch('githug.__main__.filedialog.askdirectory') as picker:
            guide.execute();self.wait();picker.assert_not_called()
        self.assertTrue(guide.completed);self.assertFalse(self.errors)
    def test_cancel_handoff_and_changed_context_do_not_complete(self):
        project,sha=self.fixture();self.app.history.selection_set(sha)
        guide=open_guide(self.app);guide.navigate('steps','copy');guide.tick_now()
        ticket=begin(self.app,'copy',project);guide.back();finish(ticket,'old operation');self.assertFalse(guide.completed)
        guide.navigate('steps','copy');guide.tick_now();ticket=begin(self.app,'copy',project)
        self.app.project=None;guide.tick_now();finish(ticket,'old project');self.assertEqual(guide.step,'project');self.assertFalse(guide.completed)
        self.app.project=project;guide.tick_now();guide.close();finish(ticket,'closed');self.assertFalse(self.errors)
