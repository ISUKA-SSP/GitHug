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

class PushDragTests(unittest.TestCase):
    def make(self, row=''):
        project = object()
        history = Mock()
        history.winfo_rootx.return_value = 0
        history.winfo_rooty.return_value = 0
        history.identify_region.return_value = 'cell' if row else 'nothing'
        history.identify_row.return_value = row
        window = Mock()
        window.winfo_containing.return_value = history
        app = SimpleNamespace(dragging={'direction':'push','folder':'folder','project':project,'active':True},
                              project=project,busy=False,folders=Mock(),history=history,window=window,push_ui=Mock(),status=Mock())
        app.folders.selection.return_value=("selected",)
        return app, SimpleNamespace(x_root=100,y_root=200)

    def test_drop_on_history_row_passes_branch_hint(self):
        app,event = self.make('sha')
        App.folder_release(app,event)
        app.push_ui.begin.assert_called_once_with('folder','sha')

    def test_drop_on_blank_requests_new_branch(self):
        app,event = self.make()
        App.folder_release(app,event)
        app.push_ui.begin.assert_called_once_with('folder',None)

    def test_multi_selection_never_sends_first_folder(self):
        app,event=self.make('sha');app.folders.selection.return_value=('one','two')
        self.assertEqual(App.folder_release(app,event),'break')
        app.push_ui.begin.assert_not_called();app.folders.selection_set.assert_not_called()
        app.status.set.assert_called_once()

class DragCancelTests(unittest.TestCase):
    def test_escape_cancels_without_any_transfer(self):
        app=SimpleNamespace(dragging={'active':True},drag_hint=Mock(),history=Mock(),folders=Mock(),status=Mock())
        self.assertEqual(App.cancel_drag(app),'break')
        self.assertIsNone(app.dragging)
        app.drag_hint.hide.assert_called_once()
