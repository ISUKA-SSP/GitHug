import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from githug.__main__ import App

class MissingFolderTests(unittest.TestCase):
    def fake_app(self, folder, snapshot=True):
        table = Mock()
        table.selection.return_value = ('selected',)
        table.item.return_value = ('再現したフォルダー', str(folder), 'abcdef12', '')
        return SimpleNamespace(busy=False, folders=table, folder_state=App.folder_state,
                               folder_records={'selected': {'sha': 'a' * 40, 'folder': str(folder)}} if snapshot else {},
                               project=Mock(), run=Mock())

    def test_existing_folder_opens_without_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            app = self.fake_app(folder)
            action = Mock()
            with patch('githug.__main__.messagebox.askyesno') as ask:
                App.with_selected_folder(app, action)
                ask.assert_not_called()
            action.assert_called_once_with(folder)
            app.run.assert_not_called()

    def test_missing_snapshot_yes_recreates_original_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            app = self.fake_app(Path(folder) / 'removed')
            action = Mock()
            with patch('githug.__main__.messagebox.askyesno', return_value=True):
                App.with_selected_folder(app, action)
            task = app.run.call_args.args[1]
            task()
            app.project.snapshot.assert_called_once_with('a' * 40)
            action.assert_not_called()  # Must wait until snapshot finishes.

    def test_no_means_no_recreation(self):
        with tempfile.TemporaryDirectory() as folder:
            app = self.fake_app(Path(folder) / 'removed')
            with patch('githug.__main__.messagebox.askyesno', return_value=False):
                App.with_selected_folder(app, Mock())
            app.run.assert_not_called()

    def test_registered_work_folder_not_recreated(self):
        with tempfile.TemporaryDirectory() as folder:
            app = self.fake_app(Path(folder) / 'removed', snapshot=False)
            with patch('githug.__main__.messagebox.askyesno') as ask, patch('githug.__main__.messagebox.showinfo'):
                App.with_selected_folder(app, Mock())
                ask.assert_not_called()
            app.run.assert_not_called()

    def test_folder_state_tracks_move(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / 'original'
            original.mkdir()
            self.assertEqual(App.folder_state(original), '利用できます')
            original.rename(Path(folder) / 'moved')
            self.assertEqual(App.folder_state(original), '削除または移動されています')
