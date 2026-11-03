import unittest
from unittest.mock import Mock
from githug.graph_view import GraphView
from githug.history_graph import HistoryGraph

class FakeTree:
    def __init__(self, ids): self.ids=ids
    def exists(self,sha): return sha in self.ids
    def bbox(self,sha): return (0,30+self.ids.index(sha)*27,800,27)
    def identify_row(self,y): return self.ids[0] if y>=30 else ''
    def identify_region(self,x,y): return 'cell' if y>=30 else 'heading'
    def winfo_height(self): return 200

class GraphDrawingTests(unittest.TestCase):
    def test_node_centers_align_with_tree_rows_and_page_continuations(self):
        records=[{'sha':str(i),'parents':str(i+1) if i<5 else ''} for i in range(6)]
        model=HistoryGraph(records)
        view=GraphView.__new__(GraphView)
        view.tree=FakeTree(['2','3'])
        view.canvas=Mock()
        view.canvas.winfo_exists.return_value=True
        view.canvas.winfo_width.return_value=200
        view.canvas.winfo_height.return_value=150
        view.canvas.canvasx.return_value=0
        view.model=model;view.ids=['2','3'];view.enabled=True;view.selected='2';view.scheduled=False
        view.draw()
        self.assertTrue(view.canvas.create_line.called)
        self.assertEqual(view.canvas.create_polygon.call_count,2)  # Continues at both page edges.
        nodes=[c.args for c in view.canvas.create_oval.call_args_list if c.kwargs.get('width')==2]
        self.assertEqual([(args[1]+args[3])/2 for args in nodes],[43.5,70.5])
        self.assertEqual(nodes[0][0],12)  # Selected node's radius is larger.

    def test_no_edges_drawn_in_list_mode(self):
        view=GraphView.__new__(GraphView)
        view.canvas=Mock();view.canvas.winfo_exists.return_value=True
        view.enabled=False;view.model=Mock();view.ids=['id'];view.scheduled=False
        view.draw()
        view.canvas.create_line.assert_not_called()
