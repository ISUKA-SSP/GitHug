"""Canvas lanes aligned to the actual visible Treeview row bounding boxes."""
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

BG = '#0e1824'


class GraphView:
    def __init__(self, parent, tree):
        self.tree = tree
        self.header_font = tkfont.Font(root=parent, font=('Yu Gothic UI', 10))
        self.canvas = tk.Canvas(parent, width=200, background=BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(parent, orient='horizontal', command=self.scroll_x)
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        self.model = None
        self.ids = []
        self.enabled = True
        self.selected = None
        self.scheduled = False
        self.canvas.bind('<Configure>', lambda event: self.schedule())
        tree.bind('<Configure>', lambda event: self.schedule(), add='+')
        self.canvas.bind('<MouseWheel>', self.wheel)
        self.canvas.bind('<Button-4>', lambda event: self.scroll(-1))
        self.canvas.bind('<Button-5>', lambda event: self.scroll(1))

    def scroll_x(self, *args):
        self.canvas.xview(*args)
        self.schedule()

    def scroll(self, amount):
        self.tree.yview_scroll(amount, 'units')
        self.schedule()
        return 'break'

    def wheel(self, event):
        if not event.delta: return 'break'
        return self.scroll(-max(1, abs(event.delta) // 120) if event.delta > 0 else max(1, abs(event.delta) // 120))

    def set_page(self, model, ids, enabled):
        self.model, self.ids, self.enabled = model, list(ids), enabled
        if enabled:
            width = max(self.header_font.measure('分岐・合流') + 20, min(240, model.width * 26 + 28))
            self.canvas.configure(width=width)
            self.canvas.grid()
            self.scrollbar.grid()
        else:
            self.canvas.grid_remove()
            self.scrollbar.grid_remove()
        self.schedule()

    def set_focus(self, sha):
        self.selected = sha
        self.schedule()

    def schedule(self):
        if not self.scheduled and self.canvas.winfo_exists():
            self.scheduled = True
            self.canvas.after_idle(self.draw)

    def draw(self):
        self.scheduled = False
        if not self.canvas.winfo_exists(): return
        canvas = self.canvas
        canvas.delete('all')
        if not self.enabled or not self.model or not self.ids: return
        visible = [(i, sha, self.tree.bbox(sha)) for i, sha in enumerate(self.ids) if self.tree.exists(sha)]
        visible = [(i, sha, box) for i, sha, box in visible if box]
        if not visible: return
        # Derive fixed heading height by locating the first data row in the Treeview.
        heading = 0
        while heading < min(100, self.tree.winfo_height()) and self.tree.identify_region(5, heading) not in ('tree', 'cell'):
            heading += 1
        width = max(canvas.winfo_width(), self.model.width * 26 + 28)
        canvas.configure(scrollregion=(0, 0, width, max(1, canvas.winfo_height())))
        nodes, edges, starts = self.model.focus(self.selected)
        def x(lane): return 18 + lane * 26
        def line(points, color, active):
            canvas.create_line(*points, fill=color if active or not self.selected else '#424e60',
                               width=3 if active else 1.6, smooth=False)
        for local_index, sha, box in visible:
            row = self.model.rows[sha]
            top, bottom = box[1], box[1] + box[3]
            center = (top + bottom) / 2
            after_positions = {value: index for index, (value, _) in enumerate(row.after)}
            for lane, (waiting, color) in enumerate(row.before):
                active = waiting in starts and row.index > starts[waiting]
                if waiting == sha:
                    if row.incoming: line((x(lane), top, x(lane), center), color, active)
                else:
                    destination = after_positions[waiting]
                    line((x(lane), top, x(lane), center, x(destination), bottom), color, active)
            for parent in row.parents:
                destination = after_positions[parent]
                color = row.after[destination][1]
                line((x(row.lane), center, x(destination), bottom), color, (sha, parent) in edges)
            if local_index == 0 and row.index > 0:
                for lane, (waiting, color) in enumerate(row.before):
                    if waiting == sha and not row.incoming: continue
                    canvas.create_polygon(x(lane)-3, top+5, x(lane)+3, top+5, x(lane), top,
                                          fill=color, outline='')
            if local_index == len(self.ids)-1 and row.after:
                for lane, (_, color) in enumerate(row.after):
                    canvas.create_polygon(x(lane)-3, bottom-5, x(lane)+3, bottom-5, x(lane), bottom,
                                          fill=color, outline='')
        # Put nodes over every line, so merge points remain legible.
        for _, sha, box in visible:
            row = self.model.rows[sha]
            center = box[1] + box[3] / 2
            radius = 6 if sha == self.selected else 4.5
            canvas.create_oval(x(row.lane)-radius, center-radius, x(row.lane)+radius, center+radius,
                               fill=row.color if not self.selected or sha in nodes else '#566476',
                               outline='#ffffff' if sha == self.selected else BG, width=2)
            if sha == self.selected:
                canvas.create_oval(x(row.lane)-10, center-10, x(row.lane)+10, center+10, outline=row.color, width=1)
        left = canvas.canvasx(0)
        canvas.create_rectangle(left, 0, left + canvas.winfo_width(), heading, fill='#192a3b', outline='')
        canvas.create_text(left+10, max(10, heading/2), anchor='w', text='分岐・合流', fill='#c7d7e8', font=('Yu Gothic UI', 10))
