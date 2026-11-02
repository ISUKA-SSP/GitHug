from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from githug.__main__ import App

class DragTests(unittest.TestCase):
    def make(self, item='', active=True):
        project = object()
        tree = Mock()
        tree.winfo_rootx.return_value = 0
        tree.winfo_rooty.return_value = 0
        tree.identify_region.return_value = 'cell' if item else 'nothing'
        tree.identify_row.return_value = item
        window = Mock()
        window.winfo_containing.return_value = tree
        app = SimpleNamespace(dragging={'sha':'a'*40, 'project':project, 'active':active},
                              busy=False, project=project, history=Mock(), folders=tree,
                              window=window, status=Mock(), begin_update=Mock(), reproduce_sha=Mock())
        return app, SimpleNamespace(x_root=100, y_root=200)

    def test_row_drop_opens_update_flow(self):
        app, event = self.make('folder')
        App.history_release(app, event)
        app.begin_update.assert_called_once_with('a'*40, 'folder')
        app.reproduce_sha.assert_not_called()

    def test_blank_drop_creates_new_snapshot(self):
        app, event = self.make()
        App.history_release(app, event)
        app.reproduce_sha.assert_called_once_with('a'*40)
        app.begin_update.assert_not_called()

    def test_simple_click_and_outside_drop_do_nothing(self):
        app, event = self.make(active=False)
        App.history_release(app, event)
        app.begin_update.assert_not_called()
        app.reproduce_sha.assert_not_called()
        app, event = self.make()
        app.window.winfo_containing.return_value = app.window
        App.history_release(app, event)
        app.reproduce_sha.assert_not_called()

    def test_header_and_changed_project_do_not_update(self):
        app, event = self.make('folder')
        app.folders.identify_region.return_value = 'heading'
        App.history_release(app, event)
        app.begin_update.assert_not_called()
        app, event = self.make('folder')
        app.project = object()
        App.history_release(app, event)
        app.begin_update.assert_not_called()
