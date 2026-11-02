"""Topology-first lane layout and paged/searchable history, independent of Tk."""
from dataclasses import dataclass
from .listing import visible_rows

PALETTE = ('#65b5f6', '#d99dff', '#6bd8b2', '#f5be70', '#f083a5', '#79d8e5', '#aab2ff')


@dataclass(frozen=True)
class GraphRow:
    sha: str
    index: int
    lane: int
    color: str
    incoming: bool
    before: tuple  # (sha, color) pending lanes, including this node
    after: tuple
    parents: tuple


class HistoryGraph:
    def __init__(self, records):
        self.records = {r['sha']: r for r in records}
        self.ids = [r['sha'] for r in records]
        self.positions = {sha: i for i, sha in enumerate(self.ids)}
        self.children = {sha: [] for sha in self.ids}
        for r in records:
            for parent in r['parents'].split():
                self.children.setdefault(parent, []).append(r['sha'])
                if parent in self.positions and self.positions[parent] <= self.positions[r['sha']]:
                    raise ValueError('履歴は子から親の順に取得してください。')
        self.rows = {}
        pending, colors = [], {}
        color_counter = 0
        def new_color():
            nonlocal color_counter
            color = PALETTE[color_counter % len(PALETTE)]
            color_counter += 1
            return color
        self.width = 1
        for index, r in enumerate(records):
            sha = r['sha']
            incoming = sha in pending
            if not incoming:
                pending.append(sha)
                colors[sha] = new_color()
            lane = pending.index(sha)
            color = colors[sha]
            before = tuple((value, colors[value]) for value in pending)
            parents = tuple(dict.fromkeys(r['parents'].split()))
            pending.pop(lane)
            for number, parent in enumerate(parents):
                if parent not in pending:
                    pending.insert(min(lane + number, len(pending)), parent)
                    colors[parent] = color if number == 0 else new_color()
            after = tuple((value, colors[value]) for value in pending)
            self.rows[sha] = GraphRow(sha, index, lane, color, incoming, before, after, parents)
            self.width = max(self.width, len(before), len(after))
        self.focus_cache = None
        self.focused = (set(), set(), {})

    def focus(self, sha):
        if sha == self.focus_cache: return self.focused
        self.focus_cache = sha
        if sha not in self.records:
            self.focused = (set(), set(), {})
            return self.focused
        def walk(start, adjacent):
            found, todo = set(), [start]
            while todo:
                value = todo.pop()
                if value in found: continue
                found.add(value)
                todo.extend(adjacent(value))
            return found
        ancestors = walk(sha, lambda value: self.records.get(value, {}).get('parents', '').split())
        descendants = walk(sha, lambda value: self.children.get(value, ()))
        edges, starts = set(), {}
        for child in ancestors | descendants:
            for parent in self.records.get(child, {}).get('parents', '').split():
                if (child in ancestors and parent in ancestors) or (child in descendants and parent in descendants):
                    edges.add((child, parent))
                    starts[parent] = min(starts.get(parent, float('inf')), self.positions[child])
        self.focused = (ancestors | descendants, edges, starts)
        return self.focused


@dataclass
class HistoryPage:
    rows: list
    page: int
    pages: int
    matches: int
    total: int


def history_page(rows, query='', column='topology', descending=False, page=0, size=100, focus=None):
    if size not in (50, 100, 200): raise ValueError('1ページの件数は50・100・200件から選んでください。')
    ordered = visible_rows(rows, query, column, descending)
    pages = (len(ordered) + size - 1) // size
    if focus:
        index = next((i for i, row in enumerate(ordered) if row['id'] == focus), None)
        if index is not None: page = index // size
    page = max(0, min(page, max(0, pages - 1)))
    return HistoryPage(ordered[page * size:(page + 1) * size], page, pages, len(ordered), len(rows))
