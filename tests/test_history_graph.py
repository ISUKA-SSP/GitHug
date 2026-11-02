import tempfile
from pathlib import Path
import unittest
from githug.core import Project, git
from githug.history_graph import HistoryGraph, history_page


def record(sha, parents='', text=''):
    return {'sha':sha, 'parents':parents, 'message':text, 'date':'2026-11-01T12:00:00+09:00', 'refs':''}


def view_rows(count):
    return [{'id':str(i), 'search':f'change {i} ' + ('#普段使い 詳細メモ' if i == count-1 else ''),
             'sort':{'topology':i,'date':count-i,'message':str(i)}} for i in range(count)]


class GraphModelTests(unittest.TestCase):
    def test_long_linear_history_does_not_grow_horizontally(self):
        records = [record(str(i), str(i+1) if i < 999 else '') for i in range(1000)]
        graph = HistoryGraph(records)
        self.assertEqual(graph.width, 1)
        self.assertTrue(all(row.lane == 0 for row in graph.rows.values()))
        for a,b in zip(records,records[1:]):
            self.assertEqual(graph.rows[a['sha']].after, graph.rows[b['sha']].before)

    def test_merge_has_both_parents_and_reuses_lanes(self):
        records = [record('merge','main feature'),record('feature','base'),record('main','base'),record('base')]
        graph = HistoryGraph(records)
        self.assertEqual(graph.rows['merge'].parents, ('main','feature'))
        self.assertEqual([sha for sha,_ in graph.rows['merge'].after], ['main','feature'])
        self.assertEqual(len(graph.rows['main'].after),1)
        self.assertEqual(graph.rows['base'].after, ())
        nodes,edges,starts = graph.focus('merge')
        self.assertIn(('merge','feature'),edges)
        self.assertIn(('merge','main'),edges)
        self.assertEqual(nodes, {'merge','main','feature','base'})

    def test_focus_does_not_follow_an_unrelated_branch_before_its_join(self):
        graph = HistoryGraph([record('tip-a','a'),record('tip-b','b'),record('a','root'),record('b','root'),record('root')])
        nodes,edges,starts = graph.focus('a')
        self.assertEqual(nodes, {'tip-a','a','root'})
        self.assertNotIn(('b','root'), edges)
        self.assertEqual(starts['root'], graph.positions['a'])

    def test_multiple_roots_and_missing_boundary_are_not_joined(self):
        graph = HistoryGraph([record('a','outside'),record('b')])
        self.assertEqual(graph.rows['b'].lane,1)
        self.assertEqual([sha for sha,_ in graph.rows['b'].after], ['outside'])
        self.assertEqual(graph.rows['b'].parents, ())
        self.assertNotIn(('b','outside'),graph.focus('b')[1])

    def test_invalid_topological_order_is_rejected(self):
        with self.assertRaises(ValueError): HistoryGraph([record('parent'),record('child','parent')])


class PagingTests(unittest.TestCase):
    def test_pages_and_direct_jump_keep_every_row_once(self):
        rows = view_rows(451)
        seen = []
        for page in range(5):
            result = history_page(rows, page=page)
            self.assertEqual(result.pages, 5)
            seen.extend(row['id'] for row in result.rows)
        self.assertEqual(seen, [str(i) for i in range(451)])
        last = history_page(rows, page=999)
        self.assertEqual(last.page,4)
        self.assertEqual(len(last.rows),51)

    def test_search_includes_old_full_notes_not_just_current_page(self):
        rows = view_rows(900)
        result = history_page(rows, query='#普段使い 詳細メモ')
        self.assertEqual([r['id'] for r in result.rows], ['899'])
        self.assertEqual((result.matches,result.total,result.pages),(1,900,1))
        restored = history_page(rows, focus='899')
        self.assertEqual(restored.page,8)
        self.assertIn('899',[r['id'] for r in restored.rows])

    def test_sizes_empty_results_and_non_graph_sorting(self):
        rows = view_rows(451)
        for size,pages in [(50,10),(100,5),(200,3)]:
            self.assertEqual(history_page(rows,size=size).pages,pages)
        empty = history_page(rows,query='not found')
        self.assertEqual((empty.pages,empty.page,empty.rows),(0,0,[]))
        sorted_page = history_page(rows,column='date',descending=False)
        self.assertEqual(sorted_page.rows[0]['id'],'450')
        with self.assertRaises(ValueError): history_page(rows,size=0)


class FullGitHistoryTests(unittest.TestCase):
    def test_git_history_beyond_400_is_returned_topologically(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Project(temporary,'https://github.com/test/history')
            project.base.mkdir()
            git('init','--bare','-b','main',project.cache)
            commands=[]
            for i in range(451):
                message=f'change {i}'
                commands.append(f'commit refs/heads/main\ncommitter Test <test@example.com> {1700000000+i} +0000\ndata {len(message)}\n{message}\nM 100644 inline file.txt\ndata 1\nx\n')
            git('fast-import','--quiet',cwd=project.cache,input_text='\n'.join(commands)+'\n')
            records=project.history()
            self.assertEqual(len(records),451)
            self.assertEqual(records[0]['message'],'change 450')
            self.assertEqual(records[-1]['message'],'change 0')
            self.assertEqual(HistoryGraph(records).width,1)
