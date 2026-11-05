from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from githug.core import Project,git
from githug.restoration import prepare_backup,prepare_local,execute_restore,prepare_again,RestoreError
from githug.updating import archive_folder,inventory,record_for_folder,require_update_permission,UpdateNotAllowed
from githug.local_records import save_local,latest_for_folder
from githug.publishing import inspect_push
from githug.notes import Notes

class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.project=Project(self.root/'managed','https://github.com/example/test')
        self.source=self.root/'work';self.source.mkdir();(self.source/'empty').mkdir()
        (self.source/'日本語.txt').write_bytes('設定とメモ'.encode('utf-8'))
        (self.source/'.env').write_bytes(b'local configuration\n');(self.source/'data.db').write_bytes(bytes(range(256)))
        (self.source/'.git').mkdir();(self.source/'.git/config').write_bytes(b'old git settings')
        (self.project.base/'backups').mkdir(parents=True)
        self.archive=self.project.base/'backups'/'test.zip';archive_folder(self.source,self.archive)
        self.archive.with_suffix('.json').write_text(json.dumps({'folder':str(self.source),'sha':'a'*40,'created':'2026-11-05T12:00:00+09:00'}),encoding='utf-8')

    def test_complete_backup_restores_to_unique_folder_without_touching_original(self):
        before=inventory(self.source);original=hashlib.sha256(self.archive.read_bytes()).hexdigest()
        notes=Notes(self.project.base);notes.set('folders',self.source,'keep personal memo')
        first=execute_restore(self.project,prepare_backup(self.project,self.archive))
        second=execute_restore(self.project,prepare_backup(self.project,self.archive))
        self.assertNotEqual(first['folder'],second['folder']);dest=Path(first['folder'])
        for name in ('日本語.txt','.env','data.db','.git/config'):self.assertEqual((dest/name).read_bytes(),(self.source/name).read_bytes())
        self.assertTrue((dest/'empty').is_dir());self.assertEqual(inventory(self.source),before)
        self.assertEqual(hashlib.sha256(self.archive.read_bytes()).hexdigest(),original)
        self.assertEqual(Notes(self.project.base).get('folders',dest),'keep personal memo')
        self.assertEqual(Notes(self.project.base).get('folders',self.source),'keep personal memo')
        _,meta=record_for_folder(self.project,dest);self.assertEqual(meta['kind'],'restored');self.assertFalse(meta['update_allowed'])
        with self.assertRaises(UpdateNotAllowed):require_update_permission(self.project,dest,'a'*40)

    def test_existing_destination_even_empty_is_not_reused(self):
        plan=prepare_backup(self.project,self.archive);plan.destination.mkdir(parents=True)
        (plan.destination/'keep.txt').write_bytes(b'keep')
        with self.assertRaises(RestoreError):execute_restore(self.project,plan)
        self.assertEqual((plan.destination/'keep.txt').read_bytes(),b'keep')
        self.assertEqual(list(plan.destination.iterdir()),[plan.destination/'keep.txt'])

    def test_backup_replacement_after_confirmation_is_refused(self):
        plan=prepare_backup(self.project,self.archive)
        self.archive.write_bytes(b'changed zip')
        with self.assertRaises(RestoreError):execute_restore(self.project,plan)
        self.assertFalse(plan.destination.exists());self.assertEqual(self.project.snapshots(),[])

    def test_traversal_devices_case_collisions_links_and_file_parent_are_rejected(self):
        cases=[['../outside.txt'],['/absolute.txt'],['C:/outside.txt'],['a\\b.txt'],['A.txt','a.txt'],['CON.txt'],['name.'],['file','file/child.txt']]
        for index,names in enumerate(cases):
            archive=self.archive.parent/(str(index)+'.zip')
            with zipfile.ZipFile(archive,'w') as z:
                for name in names:z.writestr(name,b'data')
            with self.subTest(names=names),self.assertRaises(RestoreError):prepare_backup(self.project,archive)
        linked=self.archive.parent/'link.zip'
        with zipfile.ZipFile(linked,'w') as z:
            info=zipfile.ZipInfo('link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'../outside')
        with self.assertRaises(RestoreError):prepare_backup(self.project,linked)
        self.assertFalse((self.root/'outside.txt').exists())

    def test_extraction_failure_does_not_register_or_leave_partial_success(self):
        plan=prepare_backup(self.project,self.archive);before=self.archive.read_bytes()
        with patch('githug.restoration.write_backup',side_effect=OSError('cannot write')):
            with self.assertRaises(RestoreError):execute_restore(self.project,plan)
        self.assertFalse(plan.destination.exists());self.assertEqual(self.project.snapshots(),[]);self.assertEqual(self.archive.read_bytes(),before)

    def test_recreating_missing_restored_folder_uses_original_backup_and_keeps_latest_note(self):
        result=execute_restore(self.project,prepare_backup(self.project,self.archive));folder=Path(result['folder'])
        (folder/'日本語.txt').write_bytes(b'not in backup')
        Notes(self.project.base).set('folders',folder,'updated note')
        shutil.rmtree(folder)
        second=execute_restore(self.project,prepare_again(self.project,result['record']))
        self.assertNotEqual(result['folder'],second['folder'])
        self.assertEqual((Path(second['folder'])/'日本語.txt').read_bytes(),(self.source/'日本語.txt').read_bytes())
        self.assertEqual(Notes(self.project.base).get('folders',second['folder']),'updated note')

    def test_corrupt_optional_description_does_not_block_file_recovery(self):
        self.archive.with_suffix('.json').write_text('{broken',encoding='utf-8')
        result=execute_restore(self.project,prepare_backup(self.project,self.archive))
        self.assertIn('説明データ',result['warning']);self.assertEqual(result['record']['sha'],'')
        self.assertEqual((Path(result['folder'])/'data.db').read_bytes(),bytes(range(256)))

class LocalRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);seed=self.root/'seed'
        git('init','-b','main',seed);git('config','user.name','Test',cwd=seed);git('config','user.email','test@example.invalid',cwd=seed)
        (seed/'code.py').write_bytes(b'base\n');(seed/'other.txt').write_bytes(b'unchanged\n')
        (seed/'.gitattributes').write_bytes(b'*.bin export-ignore\ncode.py export-subst\n')
        git('add','.',cwd=seed);git('-c','commit.gpgsign=false','commit','-m','base',cwd=seed)
        base=git('rev-parse','HEAD',cwd=seed).strip()
        self.project=Project(self.root/'managed','https://github.com/example/test');self.project.base.mkdir(parents=True)
        git('clone','--mirror',seed,self.project.cache)
        self.folder=Path(self.project.snapshot(base));(self.folder/'code.py').write_bytes(b'saved $Format:%H$\n')
        (self.folder/'binary.bin').write_bytes(bytes(range(256)));(self.folder/'private.db').write_bytes(b'not selected')
        plan=inspect_push(self.project,self.folder)
        self.record=save_local(self.project,plan,['code.py','binary.bin'],'saved','Test','test@example.invalid')
        self.identifier=Path(self.record['_path']).parent.name

    def test_exact_record_bytes_ignore_archive_attributes_and_do_not_need_original(self):
        archive=Path(self.record['_path']).read_bytes();(self.folder/'code.py').write_bytes(b'later edit')
        shutil.rmtree(self.folder)
        plan=prepare_local(self.project,self.identifier)
        with patch.object(self.project,'refresh',side_effect=AssertionError('unexpected network')):result=execute_restore(self.project,plan)
        folder=Path(result['folder'])
        self.assertEqual((folder/'code.py').read_bytes(),b'saved $Format:%H$\n')
        self.assertEqual((folder/'binary.bin').read_bytes(),bytes(range(256)))
        self.assertTrue((folder/'other.txt').exists());self.assertFalse((folder/'private.db').exists());self.assertFalse((folder/'.git').exists())
        self.assertEqual(Path(self.record['_path']).read_bytes(),archive)
        self.assertEqual(result['record']['restore_commit'],self.record['commit'])

    def test_restored_copy_can_continue_local_record_chain_after_cache_prune(self):
        result=execute_restore(self.project,prepare_local(self.project,self.identifier));folder=Path(result['folder'])
        git('gc','--prune=now',cwd=self.project.cache)
        self.assertEqual(latest_for_folder(self.project,folder)['commit'],self.record['commit'])
        (folder/'code.py').write_bytes(b'continued\n')
        plan=inspect_push(self.project,folder);self.assertEqual(plan.base,self.record['commit'])
        next_record=save_local(self.project,plan,['code.py'],'next','Test','test@example.invalid')
        self.assertEqual(git('rev-parse',next_record['commit']+'^',cwd=next_record['_repo']).strip(),self.record['commit'])
        self.assertEqual(latest_for_folder(self.project,folder)['commit'],next_record['commit'])

    def test_reused_path_does_not_adopt_restored_origin(self):
        result=execute_restore(self.project,prepare_local(self.project,self.identifier));folder=Path(result['folder'])
        folder.rename(folder.with_name(folder.name+'-old'));folder.mkdir();(folder/'new.txt').write_bytes(b'new')
        self.assertIsNone(latest_for_folder(self.project,folder))

class RestoreDialogTests(unittest.TestCase):
    def test_cancel_does_not_execute_and_confirmation_defaults_to_no(self):
        from types import SimpleNamespace
        from githug.restoration_ui import start_restore
        parent=SimpleNamespace(winfo_exists=lambda:True)
        app=SimpleNamespace(busy=False,window=parent)
        calls=[]
        def run(label,task,done):calls.append(label);done(task())
        app.run=run
        plan=SimpleNamespace(kind='backup',source=Path('test.zip'),destination=Path('new-folder'),count=3,size=10)
        with patch('githug.restoration_ui.messagebox.askyesno',return_value=False) as ask,patch('githug.restoration_ui.execute_restore') as execute:
            start_restore(app,None,lambda:plan)
        self.assertEqual(len(calls),1);execute.assert_not_called()
        self.assertEqual(ask.call_args.kwargs['default'],'no')

    def test_confirm_registers_and_selects_new_folder(self):
        from types import SimpleNamespace
        from githug.restoration_ui import start_restore
        parent=SimpleNamespace(winfo_exists=lambda:True);project=object();selected=[]
        tree=SimpleNamespace(get_children=lambda:['item'],item=lambda *args:('restored','new-folder'),selection_set=selected.append,focus=lambda item:None,see=lambda item:None)
        app=SimpleNamespace(busy=False,window=parent,project=project,folders=tree,folder_query=SimpleNamespace(set=lambda text:None),load_folders=lambda:None,status=SimpleNamespace(set=lambda text:None))
        app.run=lambda label,task,done:done(task())
        plan=SimpleNamespace(kind='backup',source=Path('test.zip'),destination=Path('new-folder'),count=3,size=10)
        with patch('githug.restoration_ui.messagebox.askyesno',return_value=True),patch('githug.restoration_ui.messagebox.showinfo'),patch('githug.restoration_ui.execute_restore',return_value={'folder':'new-folder','registered':True,'warning':''}) as execute:
            start_restore(app,project,lambda:plan)
        execute.assert_called_once();self.assertEqual(selected,['item'])
