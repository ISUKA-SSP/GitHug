import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
from githug.core import Project
from githug.folder_batch import prepare_batch,execute_batch
from githug.notes import Notes

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.project=Project(self.root/'storage','https://github.com/example/test')
        (self.project.base/'records').mkdir(parents=True)
        self.existing=self.root/'existing';self.existing.mkdir();self.missing=self.root/'missing'
        self.entries=[('作業用（登録）',str(self.existing)),('コピーしたフォルダー',str(self.missing))]

    def record(self,folder,name='missing'):
        record=self.project.base/'records'/(name+'.json')
        record.write_text(json.dumps({'folder':str(folder),'sha':'a'*40,'kind':'snapshot'}),encoding='utf-8')
        return record

    def test_mixed_selection_operations_have_disjoint_targets(self):
        recycle=prepare_batch(self.project,self.entries,'recycle')
        hide=prepare_batch(self.project,self.entries,'hide')
        self.assertEqual([t.folder for t in recycle.targets],[str(self.existing)])
        self.assertEqual([t.folder for t in hide.targets],[str(self.missing)])
        self.assertEqual(len(recycle.untouched),1);self.assertEqual(len(hide.untouched),1)

    def test_missing_reappears_after_confirm_is_not_hidden(self):
        self.record(self.missing);plan=prepare_batch(self.project,self.entries,'hide')
        self.missing.mkdir();result=execute_batch(self.project,plan)
        self.assertEqual(result.succeeded,[]);self.assertEqual(len(result.failed),1)
        self.assertFalse(json.loads((self.project.base/'records/missing.json').read_text()).get('hidden_from_list'))

    def test_replaced_folder_skips_and_next_target_continues(self):
        other=self.root/'other';other.mkdir()
        plan=prepare_batch(self.project,self.entries+[('作業用（登録）',str(other))],'recycle')
        self.existing.rename(self.root/'original');self.existing.mkdir()
        with patch('githug.folder_removal.recycle_folder',return_value='recycled') as recycle:
            result=execute_batch(self.project,plan)
        self.assertEqual(result.succeeded,[str(other)]);self.assertEqual(len(result.failed),1)
        recycle.assert_called_once_with(other)
        self.assertTrue(self.existing.exists());self.assertTrue((self.root/'original').exists())

    def test_partial_failure_preserves_notes_and_continues(self):
        self.record(self.missing)
        second=self.root/'another-missing';self.record(second,'another')
        notes=Notes(self.project.base);notes.set('folders',self.missing,'keep note')
        plan=prepare_batch(self.project,self.entries+[('コピーしたフォルダー',str(second))],'hide')
        from githug.folder_removal import hide_missing
        def operation(project,registration,folder):
            if Path(folder)==self.missing:raise OSError('blocked')
            return hide_missing(project,registration,folder)
        with patch('githug.folder_batch.hide_missing',side_effect=operation):result=execute_batch(self.project,plan)
        self.assertEqual(result.succeeded,[str(second)]);self.assertEqual(len(result.failed),1)
        self.assertEqual(notes.get('folders',self.missing),'keep note')
        self.assertTrue(self.existing.is_dir());self.assertTrue(json.loads((self.project.base/'records/another.json').read_text())['hidden_from_list'])

    def test_parent_child_protected_and_duplicate_folders_are_not_recycled(self):
        child=self.existing/'child';child.mkdir()
        entries=[('work',str(self.existing)),('copy',str(child)),('work',str(self.existing)),('work',str(self.project.base))]
        plan=prepare_batch(self.project,entries,'recycle')
        self.assertEqual(plan.targets,[]);self.assertEqual(len(plan.blocked),3);self.assertEqual(len(plan.untouched),1)

    def test_console_starting_after_confirmation_blocks_only_affected_target(self):
        other=self.root/'other';other.mkdir()
        plan=prepare_batch(self.project,[('work',str(self.existing)),('work',str(other))],'recycle')
        with patch('githug.folder_removal.recycle_folder',return_value='recycled') as recycle:
            result=execute_batch(self.project,plan,console_folder=lambda:str(self.existing))
        self.assertEqual(result.succeeded,[str(other)]);self.assertEqual(len(result.failed),1)
        recycle.assert_called_once_with(other)

    def test_only_successful_missing_items_are_unregistered_in_captured_project(self):
        from githug.folder_batch_ui import remove_selected
        self.record(self.missing)
        second=self.root/'second';self.record(second,'second')
        table=Mock();table.selection.return_value=('one','two','three')
        rows={'one':('work',str(self.existing)),'two':('copy',str(self.missing)),'three':('work',str(second))}
        table.item.side_effect=lambda item,*args:rows[item]
        registration={'work':[str(self.existing),str(self.missing),str(second)]}
        app=SimpleNamespace(busy=False,project=self.project,folders=table,current=registration,console=None,config={'root':str(self.root/'storage'),'projects':[{'url':self.project.url}]},window=None,run=Mock(),save=Mock(),load_folders=Mock(),folder_browser=SimpleNamespace(root=None),status=Mock())
        with patch('githug.folder_batch_ui.review',return_value=True):remove_selected(app,'hide')
        # Reappearance after confirmation is checked, and changing selection cannot change the target set.
        second.mkdir();table.selection.return_value=('one',)
        task,done=app.run.call_args.args[1:];result=task()
        with patch('githug.folder_batch_ui.review'):done(result)
        self.assertEqual(registration['work'],[str(self.existing),str(second)])
        self.assertTrue(self.existing.exists());app.save.assert_called_once()
