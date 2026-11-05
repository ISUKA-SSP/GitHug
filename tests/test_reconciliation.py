import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from githug.core import Project,git,GitError
from githug.publishing import inspect_push,remote_head,RemoteChanged
from githug.reconciliation import prepare_resolution,initial_choices,preview_result,publish_resolution,cancel_resolution
from githug.local_records import save_local,record_changes
from githug.updating import inventory,UpdateConflict

class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.seed=self.root/'seed'
        git('init','-b','main',self.seed);git('config','user.name','Test',cwd=self.seed);git('config','user.email','test@example.invalid',cwd=self.seed)
        (self.seed/'code.py').write_text('base\n');(self.seed/'remove.txt').write_text('base\n');self.commit('base')
        self.base=git('rev-parse','HEAD',cwd=self.seed).strip()
        self.remote=self.root/'remote.git';git('clone','--bare',self.seed,self.remote)
        self.project=Project(self.root/'managed','https://github.com/example/test');self.project.url=str(self.remote);self.project.base.mkdir(parents=True)
        git('clone','--mirror',self.remote,self.project.cache)
        self.folder=Path(self.project.snapshot(self.base));(self.folder/'code.py').write_text('PC version\n')
        self.source=inspect_push(self.project,self.folder)

    def commit(self,message):
        git('add','.',cwd=self.seed);git('-c','commit.gpgsign=false','commit','-m',message,cwd=self.seed)

    def advance(self,conflict=True):
        if conflict:(self.seed/'code.py').write_text('GitHub version\n')
        (self.seed/'remote-only.txt').write_text('preserve remote data\n');self.commit('remote update');git('push',self.remote,'main',cwd=self.seed)
        return remote_head(self.project,'main')

    def prepare(self):return prepare_resolution(self.project,'main',self.source,['code.py'])
    def send(self,plan,choices):return publish_resolution(self.project,plan,choices,'chosen result','Test','test@example.invalid')

    def test_conflicts_default_to_hold_and_cannot_send(self):
        head=self.advance();before=inventory(self.folder);plan=self.prepare()
        self.assertEqual(initial_choices(plan),{'code.py':'hold'})
        with self.assertRaises(ValueError):self.send(plan,initial_choices(plan))
        self.assertEqual(remote_head(self.project,'main'),head);self.assertEqual(inventory(self.folder),before)

    def test_pc_choice_is_child_of_remote_and_preserves_remote_only_files(self):
        head=self.advance();before=inventory(self.folder);metadata=list((self.project.base/'records').glob('*.json'))[0].read_bytes()
        plan=self.prepare();result=self.send(plan,{'code.py':'pc'})
        self.assertEqual(git('rev-parse',result['sha']+'^',cwd=self.remote).strip(),head)
        self.assertEqual(git('show',result['sha']+':code.py',cwd=self.remote),'PC version\n')
        self.assertEqual(git('show',result['sha']+':remote-only.txt',cwd=self.remote),'preserve remote data\n')
        self.assertEqual(inventory(self.folder),before)
        self.assertEqual(list((self.project.base/'records').glob('*.json'))[0].read_bytes(),metadata)
        # A fresh inspection must not mistake missing remote-only files for PC deletions.
        self.assertNotIn('remote-only.txt',[change.path for change in inspect_push(self.project,self.folder).changes])

    def test_github_choice_is_a_noop_and_pc_file_remains(self):
        head=self.advance();plan=self.prepare();result=self.send(plan,{'code.py':'github'})
        self.assertTrue(result['unchanged']);self.assertEqual(result['sha'],head)
        self.assertEqual(remote_head(self.project,'main'),head);self.assertEqual((self.folder/'code.py').read_text(),'PC version\n')

    def test_disjoint_changes_preserve_both_without_file_conflict(self):
        self.advance(False);plan=self.prepare()
        self.assertEqual(initial_choices(plan),{'code.py':'pc'});self.assertEqual(plan.remote_only,1)
        result=self.send(plan,initial_choices(plan))
        self.assertEqual(git('show',result['sha']+':remote-only.txt',cwd=self.remote),'preserve remote data\n')

    def test_deletion_vs_edit_requires_choice_and_does_not_remove_pc_files(self):
        (self.folder/'remove.txt').unlink();self.source=inspect_push(self.project,self.folder)
        (self.seed/'remove.txt').write_text('remote edited\n');self.commit('edit deleted file');git('push',self.remote,'main',cwd=self.seed)
        plan=prepare_resolution(self.project,'main',self.source,['remove.txt'])
        self.assertEqual(initial_choices(plan),{'remove.txt':'hold'})
        result=self.send(plan,{'remove.txt':'pc'})
        self.assertNotIn('remove.txt',git('ls-tree','--name-only',result['sha'],cwd=self.remote))
        self.assertFalse((self.folder/'remove.txt').exists())

    def test_remote_advance_after_review_is_not_overwritten(self):
        self.advance();plan=self.prepare()
        (self.seed/'remote-only.txt').write_text('newer remote edit\n');self.commit('more remote');git('push',self.remote,'main',cwd=self.seed)
        latest=remote_head(self.project,'main')
        with self.assertRaises(RemoteChanged):self.send(plan,{'code.py':'pc'})
        self.assertEqual(remote_head(self.project,'main'),latest)

    def test_remote_race_during_push_is_not_overwritten(self):
        self.advance();plan=self.prepare();real=git;advanced=[]
        def racing(*args,**kwargs):
            if args[0]=='push' and not advanced:
                (self.seed/'remote-only.txt').write_text('race\n');self.commit('race');real('push',self.remote,'main',cwd=self.seed);advanced.append(remote_head(self.project,'main'))
            return real(*args,**kwargs)
        with patch('githug.reconciliation.git',side_effect=racing):
            with self.assertRaises(GitError):self.send(plan,{'code.py':'pc'})
        self.assertEqual(remote_head(self.project,'main'),advanced[0])
        self.assertEqual(json.loads((plan.directory/'resolution.json').read_text())['state'],'not_confirmed')

    def test_pc_edit_after_comparison_requires_recheck(self):
        head=self.advance();plan=self.prepare();(self.folder/'code.py').write_text('later PC edit\n')
        with self.assertRaises(UpdateConflict):self.send(plan,{'code.py':'pc'})
        self.assertEqual(remote_head(self.project,'main'),head)

    def test_file_directory_overlap_cannot_silently_delete_remote_children(self):
        (self.folder/'newpath').write_text('PC file\n');self.source=inspect_push(self.project,self.folder)
        (self.seed/'newpath').mkdir();(self.seed/'newpath/remote.txt').write_text('remote child\n');self.commit('remote folder');git('push',self.remote,'main',cwd=self.seed)
        plan=prepare_resolution(self.project,'main',self.source,['newpath'])
        self.assertFalse(plan.files[0].pc_allowed)
        with self.assertRaises(ValueError):preview_result(plan,{'newpath':'pc'})
        self.assertTrue(self.send(plan,{'newpath':'github'})['unchanged'])

    def test_saved_record_can_be_resolved_after_original_folder_is_gone(self):
        record=save_local(self.project,self.source,['code.py'],'saved','Test','test@example.invalid')
        original=Path(record['_path']).read_bytes();self.advance();shutil.rmtree(self.folder)
        plan=prepare_resolution(self.project,'main',record=record)
        result=self.send(plan,{'code.py':'pc'})
        self.assertEqual(git('show',result['sha']+':code.py',cwd=self.remote),'PC version\n')
        self.assertEqual(Path(record['_path']).read_bytes(),original);self.assertIn('+PC version',record_changes(record))

    def test_cancel_removes_only_internal_copy(self):
        self.advance();before=inventory(self.folder);plan=self.prepare();cancel_resolution(plan)
        self.assertFalse(plan.repo.exists());self.assertEqual(inventory(self.folder),before)
        self.assertEqual(json.loads((plan.directory/'resolution.json').read_text())['state'],'cancelled')
