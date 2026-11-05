from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from githug.core import Project,git,GitError
from githug.local_records import save_local,records,latest_for_folder,send_record,record_changes
from githug.publishing import inspect_push,publish,remote_head,RemoteChanged,preview_changes
from githug.updating import inventory,UpdateConflict

class LocalRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.seed=self.root/'seed'
        git('init','-b','main',self.seed)
        git('config','user.name','Test',cwd=self.seed);git('config','user.email','test@example.invalid',cwd=self.seed)
        (self.seed/'code.py').write_text('original\n');(self.seed/'other.txt').write_text('keep\n')
        git('add','.',cwd=self.seed);git('-c','commit.gpgsign=false','commit','-m','base',cwd=self.seed)
        self.base=git('rev-parse','HEAD',cwd=self.seed).strip()
        self.remote=self.root/'remote.git';git('clone','--bare',self.seed,self.remote)
        self.project=Project(self.root/'managed','https://github.com/example/test');self.project.url=str(self.remote)
        self.project.base.mkdir(parents=True);git('clone','--mirror',self.remote,self.project.cache)
        self.folder=Path(self.project.snapshot(self.base));(self.folder/'code.py').write_text('first\n')

    def save(self,message='local',paths=('code.py',)):
        return save_local(self.project,inspect_push(self.project,self.folder),paths,message,'Test','test@example.invalid')

    def test_local_save_never_contacts_remote_or_changes_source(self):
        before=inventory(self.folder)
        from githug import core,publishing,local_records
        real_git=git;calls=[]
        def offline(*args,**kwargs):
            calls.append(args)
            if args[0] in ('ls-remote','push','fetch'):raise AssertionError('network-related command during local save')
            return real_git(*args,**kwargs)
        with patch.object(publishing,'git',side_effect=offline),patch.object(local_records,'git',side_effect=offline):record=self.save()
        self.assertEqual(record['state'],'saved');self.assertEqual(inventory(self.folder),before)
        self.assertEqual(remote_head(self.project,'main'),self.base)
        self.assertIn('+first',record_changes(record))
        self.assertEqual(git('show',record['commit']+':other.txt',cwd=record['_repo']),'keep\n')

    def test_second_record_is_child_and_has_only_new_changes(self):
        first=self.save('first');(self.folder/'other.txt').write_text('second\n')
        plan=inspect_push(self.project,self.folder)
        self.assertEqual(plan.base,first['commit']);self.assertEqual([change.path for change in plan.changes],['other.txt'])
        second=save_local(self.project,plan,['other.txt'],'second','Test','test@example.invalid')
        self.assertEqual(git('rev-parse',second['commit']+'^',cwd=second['_repo']).strip(),first['commit'])
        self.assertEqual(second['root_base'],self.base)
        self.assertEqual(latest_for_folder(self.project,self.folder)['commit'],second['commit'])

    def test_mirror_prune_and_source_removal_do_not_lose_saved_record(self):
        record=self.save();self.project.refresh()
        git('gc','--prune=now',cwd=self.project.cache)
        shutil.rmtree(self.folder)
        self.assertIn('+first',record_changes(records(self.project)[0]))
        result=send_record(self.project,record,'work/saved',True,{'main':self.base})
        self.assertEqual(remote_head(self.project,'work/saved'),record['commit']);self.assertEqual(result['sha'],record['commit'])

    def test_delayed_send_uses_saved_bytes_not_current_working_files(self):
        record=self.save();(self.folder/'code.py').write_text('later private edit\n')
        result=send_record(self.project,record,'work/local',True,{'main':self.base})
        self.assertEqual(git('show',result['sha']+':code.py',cwd=self.remote),'first\n')
        self.assertEqual((self.folder/'code.py').read_text(),'later private edit\n')

    def test_saved_chain_fast_forward_and_cumulative_preview(self):
        first=self.save();(self.folder/'other.txt').write_text('next\n')
        plan=inspect_push(self.project,self.folder)
        preview=preview_changes(self.project,plan,['other.txt'],self.base)
        self.assertIn('+first',preview['patch']);self.assertIn('+next',preview['patch'])
        sent=publish(self.project,plan,['other.txt'],'main',False,'second','Test','test@example.invalid')
        self.assertEqual(remote_head(self.project,'main'),sent['sha'])
        self.assertEqual(git('rev-parse',sent['sha']+'^',cwd=self.remote).strip(),first['commit'])

    def test_remote_advance_is_not_overwritten(self):
        record=self.save();(self.seed/'code.py').write_text('someone else\n')
        git('add','.',cwd=self.seed);git('-c','commit.gpgsign=false','commit','-m','remote change',cwd=self.seed)
        git('push',self.remote,'main',cwd=self.seed)
        current=remote_head(self.project,'main')
        with self.assertRaises(RemoteChanged):send_record(self.project,record,'main',False,{'main':self.base})
        self.assertEqual(remote_head(self.project,'main'),current)
        with self.assertRaises(RemoteChanged):send_record(self.project,record,'main',False,{'main':current})

    def test_reused_folder_path_does_not_adopt_old_local_head(self):
        record=self.save();self.folder.rename(self.folder.with_name('original-copy'))
        self.folder.mkdir();(self.folder/'code.py').write_text('different folder\n')
        self.assertIsNone(latest_for_folder(self.project,self.folder))

    def test_changed_file_after_preview_is_refused(self):
        plan=inspect_push(self.project,self.folder);(self.folder/'code.py').write_text('changed\n')
        with self.assertRaises(UpdateConflict):save_local(self.project,plan,['code.py'],'saved','Test','test@example.invalid')
        self.assertEqual(records(self.project),[])

    def test_new_branch_collision_preserves_record_and_remote(self):
        record=self.save()
        with self.assertRaises(RemoteChanged):send_record(self.project,record,'main',True,{'main':self.base})
        self.assertEqual(remote_head(self.project,'main'),self.base)
        self.assertEqual(records(self.project)[0]['commit'],record['commit'])

    def test_send_review_includes_deleted_content_in_intermediate_commits(self):
        from githug.local_records import send_preview
        (self.folder/'.env').write_text('LOCAL_ONLY_SECRET=example\n')
        first=self.save('private checkpoint',('code.py','.env'))
        (self.folder/'.env').unlink()
        second=self.save('remove config',('.env',))
        net=git('diff',self.base,second['commit'],'--',cwd=second['_repo'])
        self.assertNotIn('LOCAL_ONLY_SECRET',net)
        self.assertIn('LOCAL_ONLY_SECRET',send_preview(second,self.base))
        (self.folder/'other.txt').write_text('more work\n')
        plan=inspect_push(self.project,self.folder)
        self.assertIn('LOCAL_ONLY_SECRET',preview_changes(self.project,plan,['other.txt'],self.base)['history'])

class LocalRecordUiTests(unittest.TestCase):
    def test_local_entry_does_not_refresh_remote(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from githug.push_ui import PushUI
        with tempfile.TemporaryDirectory() as directory:
            project=SimpleNamespace(cache=Path(directory),refresh=Mock(side_effect=AssertionError('unexpected network')))
            app=SimpleNamespace(busy=False,project=project,history=Mock(),run=Mock())
            ui=PushUI(app);ui.dialog=Mock()
            with patch('githug.push_ui.local_base',return_value='a'*40),patch('githug.push_ui.inspect_push',return_value='plan') as inspect:
                ui.begin(directory,local_only=True)
                task=app.run.call_args.args[1];self.assertEqual(task(),'plan')
            project.refresh.assert_not_called();inspect.assert_called_once()

    def test_pc_only_dialog_has_no_send_button_and_cancel_does_not_save(self):
        import tkinter as tk
        from tkinter import ttk
        from githug.__main__ import App
        try:root=tk.Tk()
        except tk.TclError:self.skipTest('Tk display unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root._githug_smoke=True;root._githug_smoke_dir=directory
            try:
                app=App(root);app.config.update(author_name='Test',author_email='test@example.invalid')
                from githug.publishing import PushPlan,Change
                folder=Path(directory)/'work';folder.mkdir()
                project=Project(directory,'https://github.com/example/test');project.base.mkdir()
                app.current={'work':[str(folder)],'url':project.url};app.project=project
                plan=PushPlan(folder,'a'*40,[Change('code.py','M','fingerprint')],{},'Test','test@example.invalid')
                popup=app.push_ui.dialog(project,plan,None,local_only=True);popup.geometry('860x740');root.update()
                def descendants(widget):return [child for direct in widget.winfo_children() for child in [direct,*descendants(direct)]]
                widgets=descendants(popup);buttons=[w for w in widgets if isinstance(w,ttk.Button)]
                self.assertNotIn('記録してGitHubへ送る',[str(button.cget('text')) for button in buttons])
                description=next(w for w in widgets if isinstance(w,tk.Text));description.insert('1.0','my local record')
                button=next(w for w in buttons if w.cget('text')=='PCに記録だけ残す')
                self.assertGreater(button.winfo_width(),50)
                self.assertLessEqual(button.winfo_x()+button.winfo_width(),button.master.winfo_width())
                with patch('githug.push_ui.messagebox.askyesno',return_value=False) as ask,patch('githug.push_ui.save_local') as save:
                    button.invoke();save.assert_not_called();self.assertEqual(ask.call_args.kwargs['default'],'no')
                app.terms.set_mode('git');root.update_idletasks()
                self.assertEqual(button.cget('text'),'PCにコミットだけ残す')
                self.assertEqual(description.get('1.0','end-1c'),'my local record')
            finally:
                for timer in root.tk.call('after','info'):root.tk.call('after','cancel',timer)
                root.destroy()
