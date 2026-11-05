import tempfile
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
from githug.__main__ import App

class CompareSelectionTests(unittest.TestCase):
    def app(self,selection,folder=''):
        return SimpleNamespace(busy=False,project=object(),history=Mock(selection=Mock(return_value=('a'*40,))),folders=Mock(selection=Mock(return_value=selection),item=Mock(return_value=('kind',folder))),compare_at=Mock())
    def test_selected_folder_is_used_without_picker(self):
        with tempfile.TemporaryDirectory() as folder:
            app=self.app(('one',),folder)
            with patch('githug.__main__.filedialog.askdirectory') as pick:App.compare(app)
            pick.assert_not_called();app.compare_at.assert_called_once_with(app.project,'a'*40,folder)
    def test_no_selection_uses_picker(self):
        with tempfile.TemporaryDirectory() as folder:
            app=self.app(())
            with patch('githug.__main__.filedialog.askdirectory',return_value=folder):App.compare(app)
            app.compare_at.assert_called_once_with(app.project,'a'*40,folder)
    def test_multiple_selection_requests_single_folder(self):
        app=self.app(('one','two'))
        with patch('githug.__main__.messagebox.showinfo') as info,patch('githug.__main__.filedialog.askdirectory') as pick:App.compare(app)
        info.assert_called_once();pick.assert_not_called();app.compare_at.assert_not_called()
    def test_missing_selected_folder_does_not_compare_or_replace(self):
        app=self.app(('one',),'/missing/compare-folder')
        with patch('githug.__main__.messagebox.showinfo') as info,patch('githug.__main__.filedialog.askdirectory') as pick:App.compare(app)
        info.assert_called_once();pick.assert_not_called();app.compare_at.assert_not_called()
