import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from githug.operation_guide import GOALS,required_step,begin,finish

class GuideRulesTests(unittest.TestCase):
    def test_prerequisites_and_existing_selections_skip_finished_steps(self):
        self.assertEqual(required_step('compare',False,0,0),'project')
        self.assertEqual(required_step('compare',True,0,0),'history')
        self.assertEqual(required_step('compare',True,1,0),'folder')
        self.assertEqual(required_step('compare',True,1,2),'folder')
        self.assertEqual(required_step('compare',True,1,1,False),'missing')
        self.assertEqual(required_step('compare',True,1,1),'act')
        self.assertEqual(required_step('copy',True,1,0),'act')
    def test_restore_does_not_require_original_folder_or_history_selection(self):
        for goal in ('restore-local','restore-backup','routes'):
            self.assertEqual(required_step(goal,True,0,0,False),'act')
    def fixture(self,goal='copy'):
        project=object();app=SimpleNamespace(project=project)
        guide=SimpleNamespace(goal=goal,completed=False,project=project,step='act',generation=4,app=app,alive=lambda:True,complete=Mock())
        # SimpleNamespace cannot be weakly referenced.
        class RefGuide:pass
        obj=RefGuide();obj.__dict__.update(guide.__dict__);app.operation_guide=obj
        return app,obj
    def test_only_matching_goal_succeeds(self):
        app,guide=self.fixture();self.assertIsNone(begin(app,'send',app.project))
        ticket=begin(app,'copy',app.project);finish(ticket,'actual success')
        guide.complete.assert_called_once_with('actual success')
    def test_close_back_new_goal_and_project_switch_invalidate_old_completion(self):
        for change in ('generation','project','closed'):
            app,guide=self.fixture();ticket=begin(app,'copy',app.project)
            if change=='generation':guide.generation+=1
            elif change=='project':app.project=object()
            else:guide.alive=lambda:False
            finish(ticket,'old success');guide.complete.assert_not_called()
    def test_opening_guide_midway_does_not_adopt_old_operation(self):
        app=SimpleNamespace(project=object());ticket=begin(app,'copy',app.project)
        app,guide=self.fixture();finish(ticket,'old success');guide.complete.assert_not_called()
    def test_every_goal_has_explanations_and_defined_completion(self):
        for title,needs,kind,button,hint in GOALS.values():
            self.assertTrue(title and kind and button and hint)
            self.assertTrue(set(needs)<= {'folder','history'})
