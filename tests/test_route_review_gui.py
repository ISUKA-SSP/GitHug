from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import Mock,patch
from githug.__main__ import App
from githug.core import Project,git
from githug.route_review import routes
from githug.route_review_ui import RouteReview

class RouteUiTests(unittest.TestCase):
    def test_review_direction_live_terms_and_browser_require_confirmation(self):
        try:root=tk.Tk()
        except tk.TclError:self.skipTest('Tk display unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root._githug_smoke=True;root._githug_smoke_dir=directory
            errors=[];root.report_callback_exception=lambda *args:errors.append(args)
            try:
                app=App(root);seed=Path(directory)/'seed';git('init','-b','main',seed)
                git('config','user.name','Test',cwd=seed);git('config','user.email','test@example.invalid',cwd=seed)
                (seed/'file.txt').write_text('base\n');git('add','.',cwd=seed);git('-c','commit.gpgsign=false','commit','-m','base',cwd=seed)
                git('checkout','-b','feature/gui',cwd=seed);(seed/'file.txt').write_text('feature\n');git('add','.',cwd=seed);git('-c','commit.gpgsign=false','commit','-m','feature',cwd=seed)
                project=Project(Path(directory)/'managed','https://github.com/example/test');project.base.mkdir(parents=True)
                git('clone','--mirror',seed,project.cache);project.refresh=Mock(return_value=[])
                app.current={'url':project.url,'work':[]};app.project=project
                view=RouteReview(app,project,routes(project))
                def wait():
                    end=time.monotonic()+30
                    while app.busy and time.monotonic()<end:root.update();time.sleep(.02)
                    root.update();self.assertFalse(app.busy)
                wait();self.assertTrue(view.plan.can_propose)
                self.assertEqual((view.head.get(),view.base.get()),('feature/gui','main'))
                app.terms.set_mode('git');root.update_idletasks()
                self.assertEqual((view.head.get(),view.base.get()),('feature/gui','main'))
                self.assertEqual(view.propose.cget('text'),'GitHubでプルリクエストへ進む')
                with patch('githug.route_review_ui.messagebox.askyesno',return_value=False) as ask,patch('githug.route_review_ui.webbrowser.open') as browser:
                    view.open_proposal();wait();browser.assert_not_called();self.assertEqual(ask.call_args.kwargs['default'],'no')
                with patch('githug.route_review_ui.messagebox.askyesno',return_value=True),patch('githug.route_review_ui.webbrowser.open',return_value=True) as browser:
                    view.open_proposal();wait();browser.assert_called_once_with('https://github.com/example/test/compare/main...feature%2Fgui?quick_pull=1')
                self.assertIn('自動判定しません',view.state.get())
                # An in-flight result must not re-enable a proposal for a previous selection.
                view.compare();view.head.set('main');wait()
                self.assertIsNone(view.plan);self.assertIn('disabled',view.propose.state())
                self.assertFalse(errors)
            finally:
                for timer in root.tk.call('after','info'):root.tk.call('after','cancel',timer)
                root.destroy()
