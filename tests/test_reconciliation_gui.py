from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock,patch
from githug.__main__ import App
from githug.reconciliation_ui import ResolutionDialog
from githug.updating import inventory
import test_reconciliation as fixture

class ResolutionUiTests(unittest.TestCase):
    commit=fixture.ReconciliationTests.commit
    advance=fixture.ReconciliationTests.advance

    def test_existing_push_opens_choices_hold_blocks_and_cancel_does_not_send(self):
        try:root=tk.Tk()
        except tk.TclError:self.skipTest('Tk display unavailable')
        try:
            fixture.ReconciliationTests.setUp(self);self.advance()
            root._githug_smoke=True;root._githug_smoke_dir=str(self.root/'settings')
            errors=[];root.report_callback_exception=lambda *args:errors.append(args)
            app=App(root);app.config.update(root=str(self.root/'managed'),author_name='Test',author_email='test@example.invalid')
            app.current={'url':self.project.url,'work':[str(self.folder)]};app.project=self.project
            original=inventory(self.folder)
            popup=app.push_ui.dialog(self.project,self.source,self.base)
            def descendants(widget):return [child for direct in widget.winfo_children() for child in [direct,*descendants(direct)]]
            widgets=descendants(popup)
            next(w for w in widgets if isinstance(w,tk.Text)).insert('1.0','chosen result')
            button=next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='記録してGitHubへ送る')
            captured=[]
            def create(*args,**kwargs):
                view=ResolutionDialog(*args,**kwargs);captured.append(view);return view
            def wait():
                deadline=time.monotonic()+45
                while time.monotonic()<deadline:
                    root.update()
                    if not app.busy:return
                    time.sleep(.02)
                self.fail('GUI did not finish its background work')
            with patch('githug.push_ui.ResolutionDialog',side_effect=create):button.invoke();wait()
            self.assertEqual(len(captured),1);view=captured[0]
            self.assertEqual(view.choices,{'code.py':'hold'});self.assertIn('disabled',view.proceed.state())
            with patch('githug.reconciliation_ui.publish_resolution') as send:
                view.confirm();send.assert_not_called()
                view.choose('pc');self.assertNotIn('disabled',view.proceed.state())
                with patch('githug.reconciliation_ui.review',return_value=False):view.confirm();wait()
                send.assert_not_called()
            app.terms.set_mode('git');root.update_idletasks()
            self.assertEqual(view.choices,{'code.py':'pc'})
            self.assertEqual(inventory(self.folder),original)
            view.cancel();self.assertFalse(view.window.winfo_exists());self.assertTrue(popup.winfo_exists())
            self.assertEqual(inventory(self.folder),original);self.assertFalse(errors)
        finally:
            for timer in root.tk.call('after','info'):root.tk.call('after','cancel',timer)
            root.destroy()
