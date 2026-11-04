import json
from pathlib import Path
import unittest
from githug.mascot import MascotModel, operation_pose

class MascotTests(unittest.TestCase):
    def test_parallel_operations_end_independently(self):
        m=MascotModel(seed=1);m.begin('files','carry');m.begin('gemini','think')
        self.assertEqual(m.activity,'carry')
        m.end('files');self.assertEqual(m.activity,'think')
        self.assertTrue(all(p[1]=='idle' and p[2] in (2,3,6,7) for p in m.advance(.1)))
        m.end('gemini');self.assertEqual(m.activity,'idle')

    def test_error_falls_once_then_recovers_to_pending_activity(self):
        m=MascotModel(seed=1);m.begin('other','think');m.end('failed',True,now=0)
        self.assertEqual(m.advance(.1)[0][1],'fall')
        self.assertEqual(m.advance(1.5)[0][1],'up')
        self.assertEqual(m.advance(1.8)[0][1],'idle')
        self.assertEqual(m.advance(2)[0][2],2)
        self.assertTrue(all(m.advance(n/10)[0][1]!='fall' for n in range(21,100)))
        m.end('second-failure',True,now=10)
        self.assertEqual(m.advance(10.1)[1][1],'fall')

    def test_disabled_never_moves_or_replays_error(self):
        m=MascotModel(seed=1);m.enabled=False;m.begin('files','carry');m.end('bad',True)
        first=m.advance(0)
        self.assertEqual(first,m.advance(100));self.assertTrue(all(a.fall_started is None for a in m.actors))
        m.enabled=True;self.assertEqual(m.activity,'carry')

    def test_walking_bounds_and_valid_frames(self):
        m=MascotModel(seed=10)
        for n in range(1600):
            if n==500:m.begin('copy','carry')
            if n==800:m.end('copy')
            poses=m.advance(n/10)
            for actor,pose in zip(m.actors,poses):
                self.assertGreaterEqual(pose[3],actor.left);self.assertLessEqual(pose[3],actor.right)
                limits={'idle':8,'walk':4,'carry':4,'down':3,'up':2,'fall':6}
                self.assertTrue(0<=pose[2]<limits[pose[1]])
            self.assertGreaterEqual(poses[1][3]-poses[0][3],96)

    def test_only_file_operations_use_boxes(self):
        for text in ('新しいフォルダーへコピーしています…','選んだ版に更新しています…','記録を作ってGitHubへ送っています…','フォルダーをごみ箱へ移動しています…'):
            self.assertEqual(operation_pose(text),'carry')
        for text in ('手元のファイルを比較しています…','GitHubの履歴を確認しています…','内容を再確認して更新の許可を保存しています…'):
            self.assertEqual(operation_pose(text),'think')

    def test_sprite_manifest_complete(self):
        base=Path(__file__).resolve().parent.parent/'githug'/'assets'/'mascots'
        manifest=json.loads((base/'sprites.json').read_text(encoding='utf-8'))
        self.assertEqual(set(manifest['characters']),{'silica','stella'})
        for spec in manifest['characters'].values():
            self.assertTrue((base/spec['file']).is_file())
            indices=[i for values in spec['groups'].values() for i in values]
            self.assertEqual(sorted(indices),list(range(27)))
            self.assertEqual(spec['count'],27)


class ErrorTimingTests(unittest.TestCase):
    def test_error_reaction_is_started_after_modal_dialog(self):
        import queue
        from types import SimpleNamespace
        from unittest.mock import Mock,patch
        from githug.__main__ import App
        order=[];events=queue.Queue();events.put((Mock(),None,'test error'))
        view=Mock();view.end.side_effect=lambda source,error=False:order.append('fall' if error else 'end')
        app=SimpleNamespace(events=events,busy=True,projects=Mock(),operation_state=Mock(),activity_bar=Mock(),status=Mock(),mascot_view=view,window=Mock(),poll=Mock())
        with patch('githug.__main__.messagebox.showinfo',side_effect=lambda *args:order.append('dialog')):
            App.poll(app)
        self.assertEqual(order,['end','dialog','fall'])
