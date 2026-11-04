import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from githug.core import Project
from githug.folder_removal import checked_removal, hide_missing, recycle_registered, identity, RemovalError
from githug.notes import Notes
from githug.recycle import recycle_folder

class FolderRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.project=Project(self.root/'storage','https://github.com/example/test')
        self.project.base.mkdir(parents=True)
        self.records=self.project.base/'records';self.records.mkdir()

    def record(self,folder,name='first',kind='snapshot'):
        data={'folder':str(folder),'sha':'a'*40,'kind':kind,'created':'2026-11-04T12:00:00'}
        path=self.records/(name+'.json');path.write_text(json.dumps(data),encoding='utf-8');return path

    def test_hide_missing_snapshot_keeps_baseline_and_notes(self):
        folder=self.root/'missing';meta=self.record(folder)
        notes=Notes(self.project.base);notes.set('folders',folder,'残すメモ')
        registration={'work':[]};hide_missing(self.project,registration,folder)
        self.assertEqual(self.project.snapshots(),[])
        self.assertTrue(json.loads(meta.read_text())['hidden_from_list'])
        self.assertEqual(self.project.folder_versions()[0]['sha'],'a'*40)
        self.assertEqual(Notes(self.project.base).get('folders',folder),'残すメモ')

    def test_hide_missing_work_removes_registration_only_in_this_project(self):
        folder=self.root/'missing';meta=self.record(folder,kind='work')
        other=self.root/'other';reg={'work':[str(folder),str(other)]}
        hide_missing(self.project,reg,folder)
        self.assertEqual(reg['work'],[str(other)]);self.assertTrue(meta.exists())
        self.assertEqual(self.project.folder_versions()[0]['kind'],'work')

    def test_reappeared_folder_cannot_be_hidden(self):
        folder=self.root/'back';folder.mkdir();meta=self.record(folder);before=meta.read_bytes()
        with self.assertRaises(RemovalError):hide_missing(self.project,{'work':[str(folder)]},folder)
        self.assertEqual(before,meta.read_bytes());self.assertTrue(folder.is_dir())

    def test_same_basename_does_not_hide_another_path(self):
        first=self.root/'one'/'same';second=self.root/'two'/'same'
        self.record(first,'first');self.record(second,'second')
        hide_missing(self.project,{'work':[]},first)
        self.assertEqual([r['folder'] for r in self.project.snapshots()],[str(second)])

    def test_protected_roots_management_installation_and_links(self):
        other=Project(self.root/'storage','https://github.com/example/other');other.base.mkdir()
        for target in (self.project.base,self.project.base.parent,other.base,self.records,Path.home()):
            with self.assertRaises((RemovalError,RuntimeError)):
                checked_removal(self.project,target,[other])
        folder=self.root/'normal';folder.mkdir();self.assertEqual(checked_removal(self.project,folder),folder.resolve())
        try:(self.root/'link').symlink_to(folder,target_is_directory=True)
        except OSError:return
        with self.assertRaises(RemovalError):checked_removal(self.project,self.root/'link')

    def test_replacement_after_confirmation_never_reaches_recycle(self):
        folder=self.root/'normal';folder.mkdir();expected=identity(folder)
        folder.rename(self.root/'original');folder.mkdir()
        with patch('githug.folder_removal.recycle_folder') as trash:
            with self.assertRaises(RemovalError):recycle_registered(self.project,folder,expected)
            trash.assert_not_called()
        self.assertTrue((self.root/'original').exists());self.assertTrue(folder.exists())

    def test_failed_recycle_preserves_record_and_folder(self):
        folder=self.root/'normal';folder.mkdir();meta=self.record(folder);before=meta.read_bytes()
        with patch('githug.folder_removal.recycle_folder',side_effect=OSError('cannot recycle')):
            with self.assertRaises(OSError):recycle_registered(self.project,folder,identity(folder))
        self.assertTrue(folder.is_dir());self.assertEqual(before,meta.read_bytes())

    @unittest.skipUnless(os.name=='nt','Windows Shell recycle-bin integration')
    def test_native_recycle_retains_contents_in_recycle_bin(self):
        folder=self.root/'GitHug-recycle-test';folder.mkdir()
        (folder/'日本語.txt').write_text('recoverable',encoding='utf-8')
        destination=recycle_folder(folder)
        self.assertFalse(folder.exists())
        self.assertIsNotNone(destination,'Shell did not report a recycled item')
        self.assertEqual((Path(destination)/'日本語.txt').read_text(encoding='utf-8'),'recoverable')

class RemovalConfirmationTests(unittest.TestCase):
    def fake_app(self,directory):
        from types import SimpleNamespace
        from unittest.mock import Mock
        project=Project(Path(directory)/'storage','https://github.com/example/test')
        folder=Path(directory)/'work';folder.mkdir()
        tree=Mock();tree.selection.return_value=('work:0',);tree.item.return_value=('作業用（登録）',str(folder))
        return SimpleNamespace(busy=False,project=project,folders=tree,config={'root':str(Path(directory)/'storage'),'projects':[{'url':project.url}]},
                               window=None,console=None,run=Mock()),folder

    def test_cancel_never_schedules_recycling_and_names_work_folder(self):
        from githug.__main__ import App
        with tempfile.TemporaryDirectory() as d:
            app,folder=self.fake_app(d)
            with patch('githug.__main__.messagebox.askyesno',return_value=False) as confirm:
                App.recycle_selected_folder(app)
            app.run.assert_not_called();self.assertTrue(folder.is_dir())
            self.assertIn('作業用',confirm.call_args.args[1]);self.assertIn(str(folder.resolve()),confirm.call_args.args[1])
            self.assertEqual(confirm.call_args.kwargs['default'],'no')

    def test_active_console_prevents_delete(self):
        from githug.__main__ import App
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            app,folder=self.fake_app(d);app.console=SimpleNamespace(active=True,folder=str(folder))
            with patch('githug.__main__.messagebox.showinfo') as info,patch('githug.__main__.messagebox.askyesno') as confirm:
                App.recycle_selected_folder(app)
            info.assert_called_once();confirm.assert_not_called();app.run.assert_not_called()

    def test_cancel_missing_removal_never_changes_metadata(self):
        from githug.__main__ import App
        with tempfile.TemporaryDirectory() as d:
            app,folder=self.fake_app(d);folder.rmdir()
            app.folder_state=App.folder_state
            with patch('githug.__main__.messagebox.askyesno',return_value=False),patch('githug.__main__.hide_missing') as hide:
                App.remove_missing_folder(app)
            hide.assert_not_called()
