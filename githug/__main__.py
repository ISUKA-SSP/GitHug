import json
from datetime import datetime
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from .core import Project, ComparisonCancelled
from .terminal import open_powershell
from . import __version__
from .listing import date_value, visible_rows
from .theme import apply_dark_theme
from .updating import (inspect_update, apply_update, record_for_folder, authorize_update,
                       disable_update, UpdateNotAllowed, UpdateConflict)
from .notes import Notes, short_note
from .editors import find_vscode, open_vscode
from .push_ui import PushUI
from .history_graph import HistoryGraph, history_page
from .graph_view import GraphView
from .folder_tree import FolderTree
from .search_header import SearchHeader
from .splitter import SidebarSplitter
from .explanation_panel import ExplanationPanel
from .drag_hint import DragHint
from .branding import attach_logo

class App:
    def __init__(self, window):
        self.window = window
        self.style = apply_dark_theme(window)
        window.title(f'GitHug {__version__} — 履歴から、安心して試す')
        window.geometry('1360x900')
        window.minsize(1100, 800)
        logo = attach_logo(window)
        self.config_path = Path(os.environ.get('APPDATA', Path.home() / '.config')) / 'GitHug' / 'settings.json'
        try:
            self.config = json.loads(self.config_path.read_text(encoding='utf-8'))
        except (FileNotFoundError, ValueError):
            self.config = {'root': '', 'projects': []}
        self.project = None
        self.notes = None
        self.dragging = None
        self.push_ui = PushUI(self)
        self.busy = False
        self.records = {}
        self.history_rows = []
        self.folder_rows = []
        self.sort_options = {'history': ('topology', False), 'folders': ('created', True)}
        self.history_model = HistoryGraph([])
        self.history_page = 0
        self.history_page_size = self.config.get('history_page_size', 100)
        if self.history_page_size not in (50, 100, 200): self.history_page_size = 100
        self.drag_hint = DragHint(window)
        self.events = queue.Queue()
        appbar = ttk.Frame(window, padding=(20,14), style='Appbar.TFrame')
        appbar.pack(fill='x')
        ttk.Label(appbar, image=logo, style='AppbarMuted.TLabel').pack(side='left', padx=(0,12))
        brand = ttk.Frame(appbar, style='Appbar.TFrame')
        brand.pack(side='left')
        ttk.Label(brand, text='GitHug', style='Brand.TLabel').pack(anchor='w')
        ttk.Label(brand, text='履歴から、安心して試す', style='BrandSubtitle.TLabel').pack(anchor='w')
        ttk.Label(appbar, text='v' + __version__, style='Badge.TLabel').pack(side='left', padx=16)
        # Use the supplied illustration unchanged; native Tk scaling needs no imaging dependency.
        self.mascot_image = tk.PhotoImage(master=window, file=str(Path(__file__).parent/'assets'/'living_agent.png')).subsample(4,4)
        self.mascot = tk.Label(appbar, image=self.mascot_image, bg='#202020', borderwidth=0)
        self.mascot.pack(side='right', padx=(16,0))
        self.operation_state = tk.StringVar(value='待機中')
        ttk.Button(appbar, text='使い方・環境', command=self.guide, style='Quiet.TButton').pack(side='right')
        self.activity_bar = ttk.Progressbar(appbar, mode='indeterminate', length=90)
        self.activity_bar.pack(side='right', padx=12)
        ttk.Label(appbar, textvariable=self.operation_state, style='AppbarMuted.TLabel').pack(side='right')
        toolbar = ttk.Frame(window, padding=(14,10), style='Card.TFrame')
        toolbar.pack(fill='x', padx=16, pady=(0,12))
        ttk.Button(toolbar, text='GitHubの履歴を更新', command=self.refresh, style='Primary.TButton').pack(side='left', padx=4)
        ttk.Button(toolbar, text='＋ プロジェクト', command=self.add).pack(side='left', padx=4)
        ttk.Button(toolbar, text='更新前のバックアップ', command=self.backups_dialog).pack(side='left', padx=4)
        ttk.Button(toolbar, text='コピー・履歴の保存先', command=self.choose_root, style='Quiet.TButton').pack(side='right', padx=4)
        self.status = tk.StringVar(value='「＋ プロジェクト」からGitHubのURLを追加して始めましょう。')
        footer=ttk.Frame(window,padding=(12,7),style='Card.TFrame')
        footer.pack(fill='x',side='bottom',padx=16,pady=(8,12))
        status_label=ttk.Label(footer,textvariable=self.status,style='Muted.TLabel',wraplength=1250)
        status_label.pack(fill='x')
        status_label.bind('<Configure>',lambda event:status_label.configure(wraplength=max(100,event.width-4)))
        split = SidebarSplitter(window, orient='horizontal')
        self.main_split = split
        split.pack(fill='both', expand=True, padx=16)
        left = ttk.Frame(split, padding=12, style='Card.TFrame')
        left.configure(width=245)
        left.pack_propagate(False)
        split.add(left, weight=0)
        ttk.Label(left, text='プロジェクト', font=('', 12, 'bold')).pack(anchor='w')
        self.projects = tk.Listbox(left, exportselection=False, width=22, font=('Yu Gothic UI',11), activestyle='none', selectborderwidth=0)
        self.projects.configure(height=6)
        self.projects.pack(fill='x', pady=8)
        self.projects.bind('<<ListboxSelect>>', self.select_project)
        ttk.Label(left,text='上：GitHubの履歴\n下：PCの作業場所\nドラッグで行き来できます',style='Muted.TLabel',wraplength=170).pack(anchor='w',pady=(8,0))
        self.folder_browser = FolderTree(left, self.inspect_file)
        right = ttk.Frame(split, width=800)
        right.pack_propagate(False)
        split.add(right, weight=1)
        self.sections = ttk.Panedwindow(right, orient='vertical')
        self.sections.pack(fill='both', expand=True)
        history_tab = ttk.Frame(self.sections, padding=12, style='Card.TFrame')
        history_tab.columnconfigure(0, weight=1)
        history_tab.rowconfigure(2, weight=1, minsize=70)
        self.sections.add(history_tab, weight=3)
        self.history_header = SearchHeader(history_tab, 'GitHubの履歴')
        self.history_header.grid(row=0,column=0,sticky='ew',pady=(0,6))
        self.history_query,self.history_count = self.history_header.query,self.history_header.count
        self.history = self.table(history_tab, ('date', 'refs', 'message', 'memo'), ('更新日時', '作業の分岐・目印', '変更の説明', '自分用メモ'), tree=True, grid_row=2, graph=True)
        self.history.bind('<<TreeviewSelect>>', self.detail)
        self.history.bind('<Button-3>', self.menu)
        self.history.bind('<ButtonPress-1>', self.history_press, add='+')
        self.history.bind('<B1-Motion>', self.history_motion, add='+')
        self.history.bind('<ButtonRelease-1>', self.history_release, add='+')
        for event, handler in [('<ButtonPress-1>', self.history_press), ('<B1-Motion>', self.history_motion),
                               ('<ButtonRelease-1>', self.history_release), ('<Button-3>', self.menu)]:
            self.history.graph_view.canvas.bind(event, handler)
        self.history_pager(history_tab)
        self.selection = tk.StringVar(value='')
        ttk.Label(history_tab, textvariable=self.selection, wraplength=850, style='Muted.TLabel').grid(row=3, column=0, sticky='ew', pady=4)
        controls = ttk.Frame(history_tab)
        controls.grid(row=4, column=0, sticky='ew')
        ttk.Button(controls, text='この時点のファイルをPCへコピー', command=self.reproduce, style='Primary.TButton').pack(side='left', padx=4)
        ttk.Button(controls, text='作業フォルダーと比較', command=self.compare).pack(side='left', padx=4)
        folders = ttk.Frame(self.sections, padding=12, style='Card.TFrame')
        folders.columnconfigure(0, weight=1)
        folders.rowconfigure(1, weight=1, minsize=70)
        self.sections.add(folders, weight=2)
        self.folder_header = SearchHeader(folders, 'PCのフォルダー')
        self.folder_header.grid(row=0,column=0,sticky='ew',pady=(0,6))
        self.folder_query,self.folder_count = self.folder_header.query,self.folder_header.count
        self.folders = self.table(folders, ('kind', 'path', 'sha', 'created', 'state', 'memo'), ('種類', '保存場所', 'もとにした履歴', 'コピーした日時', '状態', '自分用メモ'), grid_row=1)
        self.folders.configure(displaycolumns=('sha', 'created', 'state', 'path', 'memo'))
        self.folders.bind('<Button-3>', self.folder_menu)
        self.folders.bind('<ButtonPress-1>', self.folder_press, add='+')
        self.folders.bind('<B1-Motion>', self.folder_motion, add='+')
        self.folders.bind('<ButtonRelease-1>', self.folder_release, add='+')
        self.window.bind('<FocusIn>', self.on_window_focus, add='+')
        self.window.bind('<Escape>', self.cancel_drag, add='+')
        folder_controls = ttk.Frame(folders)
        folder_controls.grid(row=2, column=0, sticky='ew', pady=(6, 0))
        ttk.Button(folder_controls, text='作業フォルダーを登録', command=self.register_folder).pack(side='left', padx=4)
        ttk.Button(folder_controls, text='フォルダーを開く', command=self.open_folder).pack(side='left', padx=4)
        ttk.Button(folder_controls, text='PowerShell／コマンド', command=self.command_dialog).pack(side='left', padx=4)
        ttk.Button(folder_controls, text='一覧を再表示', command=self.check_folder_tab).pack(side='left', padx=4)
        self.explanation = ExplanationPanel(split, self)
        self.explanation_visible = False
        ttk.Button(toolbar, text='説明パネル', command=self.toggle_explanation).pack(side='right', padx=4)
        self.folders.bind('<<TreeviewSelect>>', self.browse_selected_folder, add='+')
        self.configure_sort('history', self.history, ('#0', 'date', 'refs', 'message', 'memo'))
        self.configure_sort('folders', self.folders, ('sha', 'created', 'state', 'path', 'memo'))
        self.history_query.trace_add('write', lambda *_: self.render_history())
        self.folder_query.trace_add('write', lambda *_: self.render_folders())
        self.populate_projects()
        window.after(150, lambda: self.sections.sashpos(0, int(self.sections.winfo_height() * 0.60)))
        window.after(150, lambda: self.main_split.sashpos(0, 245))
        window.after(100, self.poll)

    def toggle_explanation(self):
        if self.explanation_visible:
            self.main_split.forget(self.explanation.frame)
        else:
            self.main_split.add(self.explanation.frame, weight=0)
            self.window.update_idletasks()
            self.main_split.sashpos(0, 245)
            self.main_split.sashpos(1, max(650, self.main_split.winfo_width()-350))
        self.explanation_visible = not self.explanation_visible

    def inspect_file(self, path):
        self.explanation.choose({'kind':'file','path':path,'label':'ファイル: '+Path(path).name})

    def browse_selected_folder(self, event=None):
        items=self.folders.selection()
        if not items:return
        folder=self.folders.item(items[0], 'values')[1]
        if self.folder_browser.root!=folder:self.folder_browser.set_folder(folder)

    def guide(self):
        from .platform_support import git_executable
        popup=tk.Toplevel(self.window)
        popup.title('GitHug — 使い方・環境')
        popup.geometry('760x540')
        popup.minsize(600,450)
        ttk.Label(popup,text='GitHug  '+__version__,style='Heading.TLabel',padding=16).pack(anchor='w')
        text=(
            '1  プロジェクトを追加：GitHubのURLを登録します。\n'
            '2  履歴からPCへドラッグ：別フォルダーへのコピーや、確認付きの更新。\n'
            '3  PCから履歴へドラッグ：ファイルを確認してGitHubへ送信。\n\n'
            '検索は全履歴と自分用メモが対象です。選んだ履歴をグラフで見る操作で、その流れへ戻れます。\n'
            '自分用メモ・VS Code・PowerShellは、行の右クリックから開けます。\n'
            '同じ場所への更新は、GitHugのコピーフォルダーか、明示的に有効にした作業用だけです。\n\n'
            '公開プロジェクトの取得にはログイン不要です。送信・非公開プロジェクトにはPC側のGitHub認証が必要です。\n'
            'Geminiは任意。説明を頼むボタンを押すまで呼び出しません。\n\n'
            '使用するGit：'+git_executable()+'\n設定：'+str(self.config_path))
        ttk.Label(popup,text=text,wraplength=700,padding=(16,0),justify='left').pack(fill='both',expand=True)
        ttk.Button(popup,text='閉じる',command=popup.destroy).pack(anchor='e',padx=16,pady=16)

    def configure_sort(self, name, table, columns):
        table.sort_labels = {col: table.heading(col, 'text') for col in columns}
        for col in columns:
            table.heading(col, command=lambda col=col: self.sort_list(name, col))

    def sort_list(self, name, column):
        old_column, descending = self.sort_options[name]
        self.sort_options[name] = (column, not descending if column == old_column else column in ('date', 'created'))
        if name == 'history': self.render_history()
        else: self.render_folders()

    def render_rows(self, name, table, rows, query, count):
        selected = table.selection()
        table.delete(*table.get_children())
        column, descending = self.sort_options[name]
        shown = visible_rows(rows, query.get(), column, descending, pinned_first=(name == 'folders'))
        for row in shown:
            table.insert('', 'end', iid=row['id'], text=row.get('text', ''), values=row['values'])
        for col, label in table.sort_labels.items():
            table.heading(col, text=label + ((' ▼' if descending else ' ▲') if col == column else ''))
        if selected and table.exists(selected[0]):
            table.selection_set(selected[0])
            table.see(selected[0])
        else:
            table.yview_moveto(0)
        count.set(f'{len(shown)} / {len(rows)} 件')

    def history_pager(self, parent):
        bar = ttk.Frame(parent)
        bar.grid(row=1, column=0, sticky='ew', pady=(0, 6))
        self.page_number = tk.StringVar(value='0')
        self.page_total = tk.StringVar(value='/ 0 ページ')
        self.page_size_text = tk.StringVar(value=str(self.history_page_size))
        self.history_mode_text = tk.StringVar(value='グラフ：履歴のつながり順')
        self.newer_button = ttk.Button(bar, text='◁ 新しい方', command=lambda: self.move_history_page(-1), state='disabled')
        self.newer_button.grid(row=0, column=0, padx=(0, 4))
        page_entry = ttk.Entry(bar, textvariable=self.page_number, width=5, justify='center')
        page_entry.grid(row=0, column=1)
        page_entry.bind('<Return>', lambda event: self.go_history_page())
        ttk.Label(bar, textvariable=self.page_total).grid(row=0, column=2, padx=5)
        ttk.Button(bar, text='移動', command=self.go_history_page).grid(row=0, column=3, padx=4)
        self.older_button = ttk.Button(bar, text='古い方 ▷', command=lambda: self.move_history_page(1), state='disabled')
        self.older_button.grid(row=0, column=4, padx=4)
        size = ttk.Combobox(bar, textvariable=self.page_size_text, values=('50', '100', '200'), width=5, state='readonly')
        size.grid(row=0, column=5, padx=(10, 4))
        size.bind('<<ComboboxSelected>>', lambda event: self.resize_history_page())
        ttk.Label(bar, text='件／ページ').grid(row=0, column=6)
        ttk.Button(bar, text='選んだ履歴をグラフで見る', command=self.jump_to_history_graph).grid(row=0, column=7, padx=8)
        ttk.Label(bar, textvariable=self.history_mode_text, style='Muted.TLabel', wraplength=850).grid(row=1, column=0, columnspan=8, sticky='w', pady=(4, 0))

    def move_history_page(self, step):
        self.history_page += step
        self.render_history(reset_page=False)

    def go_history_page(self):
        try:
            value = int(self.page_number.get())
            if value < 1: raise ValueError()
        except ValueError:
            messagebox.showinfo('ページ番号', '1以上のページ番号を入力してください。')
            return
        self.history_page = value - 1
        self.render_history(reset_page=False)

    def resize_history_page(self):
        old_start = self.history_page * self.history_page_size
        self.history_page_size = int(self.page_size_text.get())
        self.history_page = old_start // self.history_page_size
        self.config['history_page_size'] = self.history_page_size
        self.save()
        self.render_history(reset_page=False)

    def jump_to_history_graph(self):
        selected = self.history.selection()
        sha = selected[0] if selected else None
        self.sort_options['history'] = ('topology', False)
        self.history_query.set('')
        self.render_history(focus_sha=sha)

    def render_history(self, reset_page=True, focus_sha=None):
        selected = self.history.selection()
        if reset_page: self.history_page = 0
        column, descending = self.sort_options['history']
        page = history_page(self.history_rows, self.history_query.get(), column, descending,
                            self.history_page, self.history_page_size, focus=focus_sha)
        self.history_page = page.page
        self.history.delete(*self.history.get_children())
        for row in page.rows:
            self.history.insert('', 'end', iid=row['id'], text=row['text'], values=row['values'])
        for col, label in self.history.sort_labels.items():
            self.history.heading(col, text=label + ((' ▼' if descending else ' ▲') if col == column else ''))
        graph_mode = column == 'topology' and not self.history_query.get().strip()
        self.history.graph_view.set_page(self.history_model, [row['id'] for row in page.rows], graph_mode)
        desired = focus_sha or (selected[0] if selected else None)
        if desired and self.history.exists(desired):
            self.history.selection_set(desired)
            self.history.see(desired)
        else:
            self.history.yview_moveto(0)
        self.page_number.set(str(page.page + 1) if page.pages else '0')
        self.page_total.set(f'/ {page.pages} ページ')
        self.newer_button.configure(state='normal' if page.page > 0 else 'disabled')
        self.older_button.configure(state='normal' if page.page + 1 < page.pages else 'disabled')
        self.history_count.set(f'{page.matches} / {page.total} 件')
        self.history_mode_text.set('グラフ：つながり順。上下の矢印は表示範囲外へ続きます。' if graph_mode else
                                   '検索・並べ替え中は線を省略。履歴を選び「選んだ履歴をグラフで見る」で該当位置へ戻れます。')
        self.selection.set('')
        self.detail()

    def render_folders(self):
        self.render_rows('folders', self.folders, self.folder_rows, self.folder_query, self.folder_count)

    def table(self, parent, columns, labels, tree=False, grid_row=None, graph=False):
        frame = ttk.Frame(parent)
        if grid_row is None:
            frame.pack(fill='both', expand=True)
        else:
            frame.grid(row=grid_row, column=0, sticky='nsew')
        widget = ttk.Treeview(frame, columns=columns, show='tree headings' if tree else 'headings', selectmode='browse', height=3)
        if tree:
            widget.heading('#0', text='履歴番号')
            widget.column('#0', width=160)
        for col, label in zip(columns, labels):
            widget.heading(col, text=label)
            widget.column(col, width={'path': 550, 'message': 440, 'date': 175, 'created': 175}.get(col, 170), minwidth=100)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=widget.xview)
        widget.configure(xscrollcommand=horizontal.set)
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=widget.yview)
        if graph:
            frame.columnconfigure(1, weight=1)
            frame.rowconfigure(0, weight=1)
            graph_view = GraphView(frame, widget)
            widget.graph_view = graph_view
            graph_view.canvas.grid(row=0, column=0, sticky='nsew')
            graph_view.scrollbar.grid(row=1, column=0, sticky='ew')
            handle=ttk.Frame(frame,width=7,cursor='sb_h_double_arrow',style='GraphHandle.TFrame')
            handle.grid(row=0,column=1,sticky='ns',padx=(0,2))
            frame.columnconfigure(1,weight=0)
            frame.columnconfigure(2,weight=1)
            def resize_graph(event):
                width=max(90,min(600,event.x_root-graph_view.canvas.winfo_rootx()))
                graph_view.manual_width=width
                graph_view.canvas.configure(width=width)
                self.config['graph_width']=width
                graph_view.schedule()
            handle.bind('<B1-Motion>',resize_graph)
            handle.bind('<ButtonRelease-1>',lambda event:self.save())
            def auto_graph(event):
                graph_view.manual_width=None
                self.config.pop('graph_width',None)
                if graph_view.model:graph_view.set_page(graph_view.model,graph_view.ids,graph_view.enabled)
                self.save()
            handle.bind('<Double-1>',auto_graph)
            if isinstance(self.config.get('graph_width'),int):graph_view.manual_width=max(90,min(600,self.config['graph_width']))
            widget.grid(row=0, column=2, sticky='nsew')
            scrollbar.grid(row=0, column=3, sticky='ns')
            horizontal.grid(row=1, column=2, sticky='ew')
            def scrolled(first, last):
                scrollbar.set(first, last)
                graph_view.schedule()
            widget.configure(yscrollcommand=scrolled)
        else:
            horizontal.pack(side='bottom', fill='x')
            widget.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='right', fill='y')
            widget.pack(fill='both', expand=True)
        return widget

    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.config_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.config_path)

    def choose_root(self):
        if self.busy: return
        if self.config['projects']:
            messagebox.showinfo('保存先', '登録済みプロジェクトの保存先は維持します。\n' + self.config['root'])
            return
        folder = filedialog.askdirectory(title='GitHugの保存先を選択')
        if folder:
            self.config['root'] = folder
            self.save()

    def add(self):
        if self.busy: return
        if not self.config['root']:
            self.choose_root()
        if not self.config['root']: return
        url = simpledialog.askstring('プロジェクトを追加', 'GitHubのプロジェクトURL')
        if not url: return
        try:
            project = Project(self.config['root'], url)
        except ValueError as exc:
            messagebox.showinfo('URLを確認', str(exc)); return
        if not any(p['url'] == project.url for p in self.config['projects']):
            self.config['projects'].append({'url': project.url, 'work': []})
            self.save()
            self.populate_projects()
        index = next(i for i,p in enumerate(self.config['projects']) if p['url'] == project.url)
        self.projects.selection_clear(0, 'end')
        self.projects.selection_set(index)
        self.select_project()

    def populate_projects(self):
        self.projects.delete(0, 'end')
        for p in self.config['projects']:
            self.projects.insert('end', p['url'].removesuffix('.git').split('/')[-1])

    def select_project(self, event=None):
        if self.busy: return
        indices = self.projects.curselection()
        if not indices: return
        self.folder_browser.set_folder(None)
        self.explanation.choose(None)
        self.current = self.config['projects'][indices[0]]
        self.project = Project(self.config['root'], self.current['url'])
        self.records = {}
        self.history_rows = []
        self.history_model = HistoryGraph([])
        self.sort_options['history'] = ('topology', False)
        self.history_page = 0
        self.history_query.set('')
        self.render_history()
        self.notes = None
        try: self.notes = Notes(self.project.base)
        except (OSError, ValueError) as exc: messagebox.showinfo('自分用メモを読み込めませんでした', str(exc))
        self.load_folders()
        self.refresh()

    def run(self, description, task, callback):
        if self.busy: return
        self.busy = True
        self.projects.configure(state='disabled')
        self.operation_state.set('処理中')
        self.operation_label = description
        self.operation_note = ''
        self.operation_started = time.monotonic()
        self.activity_bar.start(40)
        self.status.set(description)
        def worker():
            try: self.events.put((callback, task(), None))
            except Exception as exc: self.events.put((callback, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            callback, result, error = self.events.get_nowait()
            self.busy = False
            self.projects.configure(state='normal')
            self.operation_state.set('待機中')
            self.activity_bar.stop()
            if error:
                self.status.set('操作を完了できませんでした。案内を確認してください。')
                messagebox.showinfo('状況の確認', error)
            else:
                self.status.set('完了しました。')
                callback(result)
        except queue.Empty:
            if self.busy:
                note = self.operation_note[-120:]
                self.status.set(f'{self.operation_label}  {int(time.monotonic() - self.operation_started)} 秒  {note}')
        self.window.after(100, self.poll)

    def refresh(self):
        if self.project and not self.busy:
            self.run('GitHubの履歴を確認しています…', self.project.refresh, self.show_history)

    def show_history(self, records):
        previous = self.history.selection()
        self.history_model = HistoryGraph(records)
        if self.notes: self.notes.reload()
        self.records = {r['sha']: r for r in records}
        self.history_rows = []
        for index, r in enumerate(records):
            memo = self.notes.get('history', r['sha']) if self.notes else ''
            date, timestamp = date_value(r['date'])
            merge = '（合流）' if len(r['parents'].split()) > 1 else ''
            self.history_rows.append({
                'id': r['sha'], 'text': r['sha'][:8] + merge,
                'values': (date, r['refs'], r['message'], short_note(memo)),
                'search': ' '.join((r['sha'], r['parents'], date, r['date'], r['refs'], r['message'], memo)),
                'sort': {'topology': index, '#0': r['sha'], 'date': timestamp, 'refs': r['refs'].casefold(), 'message': r['message'].casefold(), 'memo': memo.casefold()}})
        self.render_history(reset_page=False, focus_sha=previous[0] if previous and previous[0] in self.records else None)
        self.load_folders()
        self.status.set(f'全 {len(records)} 件の履歴を取得しました。検索は自分用メモを含む全履歴が対象です。')

    def detail(self, event=None):
        items = self.history.selection()
        self.history.graph_view.set_focus(items[0] if items else None)
        if items:
            r = self.records[items[0]]
            subject = r['message'][:100] + ('…' if len(r['message']) > 100 else '')
            parents = '・'.join(value[:8] for value in r['parents'].split()) or '最初の履歴'
            self.selection.set(subject + '\n前につながる履歴: ' + parents)
            if hasattr(self, 'explanation'):
                self.explanation.choose({'kind':'history','project':self.project,'sha':items[0], 'label':self.project.name+' / '+items[0][:8]+' '+subject})

    def menu(self, event):
        item = self.history.identify_row(event.y)
        if not item: return
        self.history.selection_set(item)
        menu = tk.Menu(self.window, tearoff=False)
        menu.add_command(label='この時点のファイルをPCへコピー', command=self.reproduce)
        menu.add_command(label='作業フォルダーと比較', command=self.compare)
        menu.add_command(label='自分用メモを編集', command=self.edit_history_note)
        menu.add_command(label='選んだフォルダーをこの版に更新', command=self.update_selected)
        menu.tk_popup(event.x_root, event.y_root)

    def edit_history_note(self):
        items = self.history.selection()
        if items and self.project:
            self.note_dialog('history', items[0], '履歴 ' + items[0][:12])

    def edit_folder_note(self):
        items = self.folders.selection()
        if items and self.project:
            folder = self.folders.item(items[0], 'values')[1]
            self.note_dialog('folders', folder, folder)

    def note_dialog(self, scope, identity, title):
        if self.busy: return
        try: notes = Notes(self.project.base)
        except (OSError, ValueError) as exc:
            messagebox.showinfo('自分用メモを読み込めませんでした', str(exc))
            return
        popup = tk.Toplevel(self.window)
        popup.title('自分用メモ — ' + title)
        popup.geometry('800x480')
        popup.minsize(560, 350)
        popup.transient(self.window)
        popup.columnconfigure(0, weight=1)
        popup.rowconfigure(1, weight=1)
        ttk.Label(popup, text=title + '\nこのPCだけのメモです。GitHubへの送信やAIの説明対象には含めません。',
                  wraplength=530, padding=12).grid(row=0, column=0, sticky='ew')
        frame = ttk.Frame(popup, padding=12)
        frame.grid(row=1, column=0, sticky='nsew')
        editor = tk.Text(frame, width=1, height=1, wrap='word', undo=True)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=editor.yview)
        editor.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        editor.pack(fill='both', expand=True)
        editor.insert('1.0', notes.get(scope, identity))
        buttons = ttk.Frame(popup, padding=12)
        buttons.grid(row=2, column=0, sticky='ew')
        def save():
            try:
                notes.set(scope, identity, editor.get('1.0', 'end-1c'))
                self.notes = notes
                self.show_history(list(self.records.values()))
            except (OSError, ValueError) as exc:
                messagebox.showinfo('メモを保存できませんでした', str(exc), parent=popup)
                return
            popup.destroy()
        ttk.Button(buttons, text='保存', command=save, style='Primary.TButton').pack(side='right', padx=4)
        ttk.Button(buttons, text='キャンセル', command=popup.destroy).pack(side='right', padx=4)
        ttk.Label(buttons, text='空欄にして保存するとメモを削除します。', style='Muted.TLabel').pack(side='left')
        popup.grab_set()
        editor.focus_set()

    def vscode_selected(self):
        self.with_selected_folder(self.vscode_folder)

    def vscode_folder(self, folder):
        executable = self.config.get('vscode_executable')
        if not executable or not Path(executable).is_file():
            executable = find_vscode()
        if not executable:
            if not messagebox.askyesno('VS Codeが見つかりません', 'VS Codeの実行ファイル（Code.exe）を選びますか？\nインストールしていない場合もGitHugは引き続き使えます。'):
                return
            executable = filedialog.askopenfilename(title='VS Codeの実行ファイルを選択',
                         filetypes=[('VS Code', 'Code.exe'), ('実行ファイル', '*.exe')])
            if not executable: return
        try:
            open_vscode(folder, executable)
            self.config['vscode_executable'] = executable
            self.save()
        except (OSError, ValueError) as exc:
            messagebox.showinfo('VS Codeを開けませんでした', str(exc))

    def work_update_permission(self):
        if self.busy: return
        items = self.folders.selection()
        if not items: return
        folder = self.folders.item(items[0], 'values')[1]
        _, record = record_for_folder(self.project, folder)
        if record and record.get('kind') == 'work' and record.get('update_allowed'):
            if messagebox.askyesno('同じ場所への更新を無効にする', folder + '\nこのフォルダーの入れ替えを無効にしますか？比較・送信は引き続き使えます。'):
                disable_update(self.project, folder)
                self.load_folders()
            return
        sha = next(iter(self.records), None)
        if not sha:
            messagebox.showinfo('履歴を取得', '先に「GitHubの履歴を更新」で履歴を取得してください。')
            return
        project = self.project
        def done(plan):
            if not messagebox.askyesno('作業フォルダーの更新を有効にする',
                    '対象: ' + str(plan.folder) + '\n作成元: ' + plan.baseline[:12] +
                    '\n今後、確認画面からこの場所のファイルを入れ替えられるようにしますか？\n有効にするだけではファイルを変更しません。'):
                return
            def saved(_):
                self.load_folders()
                self.status.set('この作業フォルダーの更新を有効にしました: ' + str(plan.folder))
            self.run('内容を再確認して更新の許可を保存しています…', lambda: authorize_update(project, plan), saved)
        self.run('作業フォルダーの作成元を確認しています…',
                 lambda: inspect_update(project, folder, sha, lambda note: setattr(self, 'operation_note', note), for_authorization=True), done)

    def send_selected_folder(self):
        if self.busy or not self.project: return
        items = self.folders.selection()
        if not items:
            messagebox.showinfo('送信元を選択', 'PCのフォルダーを選んでください。')
            return
        self.push_ui.begin(self.folders.item(items[0], 'values')[1])

    def cancel_drag(self, event=None):
        if not self.dragging: return
        self.dragging = None
        self.drag_hint.hide()
        self.history.configure(cursor='')
        self.folders.configure(cursor='')
        self.status.set('ドラッグを取り消しました。')
        return 'break'

    def folder_press(self, event):
        self.dragging = None
        if self.busy or not self.project or self.folders.identify_region(event.x, event.y) != 'cell': return
        item = self.folders.identify_row(event.y)
        if item:
            self.dragging = {'direction': 'push', 'folder': self.folders.item(item, 'values')[1],
                             'project': self.project, 'x': event.x_root, 'y': event.y_root, 'active': False}

    def folder_motion(self, event):
        drag = self.dragging
        if not drag or drag.get('direction') != 'push': return
        if abs(event.x_root - drag['x']) + abs(event.y_root - drag['y']) < 8: return
        drag['active'] = True
        self.folders.configure(cursor='arrow')
        target = self.window.winfo_containing(event.x_root, event.y_root)
        graph_canvas = getattr(getattr(self.history, 'graph_view', None), 'canvas', None)
        if target is self.history or target is graph_canvas:
            y = event.y_root - self.history.winfo_rooty()
            item = self.history.identify_row(y)
            if item: self.history.selection_set(item)
            valid = self.history.identify_region(5, y) not in ('heading', 'separator')
            self.drag_hint.show(event.x_root, event.y_root, 'GitHubへ送る内容を確認' if valid else 'ここには置けません', Path(drag['folder']).name, allowed=valid, action='↑')
            self.status.set('ここで離すと、送信する変更と送信先を確認します。まだGitHubへは送りません。')
        else:
            self.drag_hint.show(event.x_root, event.y_root, 'ここには置けません', Path(drag['folder']).name, allowed=False)
            self.status.set('GitHubの履歴へドラッグすると、送信する変更を確認できます。')

    def folder_release(self, event):
        drag = self.dragging
        self.dragging = None
        self.folders.configure(cursor='')
        if getattr(self, 'drag_hint', None): self.drag_hint.hide()
        if not drag or drag.get('direction') != 'push' or not drag['active'] or self.busy or self.project is not drag['project']: return
        target = self.window.winfo_containing(event.x_root, event.y_root)
        graph_canvas = getattr(getattr(self.history, 'graph_view', None), 'canvas', None)
        if target is not self.history and target is not graph_canvas: return
        x = 5 if target is graph_canvas else event.x_root - self.history.winfo_rootx()
        y = event.y_root - self.history.winfo_rooty()
        if self.history.identify_region(x, y) in ('heading', 'separator'): return
        item = self.history.identify_row(y)
        self.push_ui.begin(drag['folder'], item or None)

    def history_press(self, event):
        self.dragging = None
        canvas = self.history.graph_view.canvas
        x = 5 if getattr(event, 'widget', None) is canvas else event.x
        if self.busy or not self.project or self.history.identify_region(x, event.y) not in ('tree', 'cell'):
            return
        item = self.history.identify_row(event.y)
        if item:
            self.history.selection_set(item)
            self.dragging = {'sha': item, 'project': self.project, 'x': event.x_root,
                             'y': event.y_root, 'active': False}

    def history_motion(self, event):
        drag = self.dragging
        if not drag: return
        if abs(event.x_root - drag['x']) + abs(event.y_root - drag['y']) < 8: return
        drag['active'] = True
        self.history.configure(cursor='arrow')
        target = self.window.winfo_containing(event.x_root, event.y_root)
        if target is self.folders:
            y = event.y_root - self.folders.winfo_rooty()
            item = self.folders.identify_row(y)
            if item: self.folders.selection_set(item)
            now = time.monotonic()
            if now - getattr(self, 'drag_scroll_at', 0) > 0.15:
                if y < 40: self.folders.yview_scroll(-1, 'units')
                elif y > self.folders.winfo_height() - 25: self.folders.yview_scroll(1, 'units')
                self.drag_scroll_at = now
            valid = self.folders.identify_region(event.x_root - self.folders.winfo_rootx(), y) not in ('heading', 'separator')
            self.drag_hint.show(event.x_root, event.y_root, ('このフォルダーを更新' if item else '新しくコピー') if valid else 'ここには置けません',
                                '履歴 ' + drag['sha'][:12], allowed=valid, action='↻' if item else '+')
            self.status.set('ここで離すと、このフォルダーへのGitHubの履歴を更新します。' if item else 'ここで離すと、新しいコピーフォルダーを作ります。')
        else:
            self.drag_hint.show(event.x_root, event.y_root, 'ここには置けません', '履歴 ' + drag['sha'][:12], allowed=False)
            self.status.set('PCのフォルダーの行へドラッグで更新、一覧の空白へドラッグで新規コピー。')

    def history_release(self, event):
        drag = self.dragging
        self.dragging = None
        self.history.configure(cursor='')
        if getattr(self, 'drag_hint', None): self.drag_hint.hide()
        if not drag or not drag['active'] or self.busy or self.project is not drag['project']:
            return
        target = self.window.winfo_containing(event.x_root, event.y_root)
        if target is not self.folders:
            self.status.set('ドラッグを取り消しました。')
            return
        x = event.x_root - self.folders.winfo_rootx()
        y = event.y_root - self.folders.winfo_rooty()
        if self.folders.identify_region(x, y) in ('heading', 'separator'):
            self.status.set('列見出しにはドロップできません。')
            return
        item = self.folders.identify_row(y)
        if item:
            self.folders.selection_set(item)
            self.begin_update(drag['sha'], item)
        else:
            self.reproduce_sha(drag['sha'])

    def reproduce_sha(self, sha):
        if self.busy or not self.project: return
        project = self.project
        def done(folder):
            self.folder_query.set('')
            self.load_folders()
            for item, record in self.folder_records.items():
                if record['folder'] == folder:
                    self.folders.selection_set(item)
                    self.folders.see(item)
                    break
            messagebox.showinfo('コピーしました', '新しいフォルダーに保存しました。\n' + folder)
        self.run('新しいフォルダーへコピーしています…', lambda: project.snapshot(sha), done)

    def update_selected(self):
        history = self.history.selection()
        folders = self.folders.selection()
        if not history or not folders:
            messagebox.showinfo('更新元と更新先を選択', '上で履歴、下で更新先のフォルダーを選んでください。')
            return
        self.begin_update(history[0], folders[0])

    def begin_update(self, sha, item):
        if self.busy or not self.project: return
        folder = self.folders.item(item, 'values')[1]
        if not Path(folder).is_dir():
            if messagebox.askyesno('フォルダーが見つかりません',
                    '更新先が削除、または移動されています。\n選んだ履歴から別フォルダーへ新しくコピーしますか？\n' + folder):
                self.reproduce_sha(sha)
            return
        project = self.project
        def progress(note): self.operation_note = note
        def inspect():
            try: return inspect_update(project, folder, sha, progress)
            except UpdateNotAllowed as exc: return str(exc)
        def done(plan):
            if isinstance(plan, str):
                if messagebox.askyesno('この場所は入れ替えません', plan + '\n\n選んだ版を別の新しいフォルダーへコピーしますか？'):
                    self.reproduce_sha(sha)
                return
            self.update_dialog(project, plan)
        self.run('手元の変更を確認しています…', inspect, done)

    def update_dialog(self, project, plan):
        popup = tk.Toplevel(self.window)
        popup.title('このフォルダーを選んだ版に更新')
        popup.geometry('880x720')
        popup.minsize(680, 650)
        popup.transient(self.window)
        popup.columnconfigure(0, weight=1)
        popup.rowconfigure(3, weight=1)
        ttk.Label(popup, text='更新先: ' + str(plan.folder), wraplength=640, padding=12).grid(row=0, column=0, sticky='ew')
        ttk.Label(popup, text='選んだ履歴: ' + plan.sha[:12] + '\n' +
                  ('もとにした履歴が不明です。現在の内容をバックアップしてからの更新をおすすめします。' if plan.unknown else
                   f'手元の変更・追加など: {len(plan.differences)} 件（もとにした履歴 {plan.baseline[:8]} との比較）'),
                  padding=(12, 0), wraplength=640).grid(row=1, column=0, sticky='ew')
        ttk.Label(popup, text='元の版にあるファイルは選んだ版へ更新し、そのファイルへの手元の編集は引き継ぎません。\n'
                  '手元だけの追加ファイルは下の選択で残せます。Git管理情報は入れ替えます。関連アプリを閉じてください。',
                  wraplength=640, padding=12).grid(row=2, column=0, sticky='ew')
        table = self.table(popup, ('state', 'path'), ('確認内容', 'ファイル／場所'), grid_row=3)
        for row in plan.differences[:1000]: table.insert('', 'end', values=row)
        if len(plan.differences) > 1000: table.insert('', 'end', values=('表示は先頭1000件までです', ''))
        if not plan.differences: table.insert('', 'end', values=('ファイル内容に手元の変更はありません', ''))
        options = ttk.Frame(popup, padding=12)
        options.grid(row=4, column=0, sticky='ew')
        retain = tk.BooleanVar(value=not plan.unknown)
        checkbox = ttk.Checkbutton(options, text=f'手元だけのファイルを残す（{len(plan.local_files)} 件）', variable=retain)
        checkbox.pack(anchor='w')
        if plan.unknown:
            checkbox.configure(state='disabled')
            text = 'もとにした履歴が不明なため、手元だけのファイルを判別できません。別フォルダーへのコピーか、バックアップしての入れ替えを選んでください。'
        elif plan.collisions:
            text = f'選んだ版との衝突が {len(plan.collisions)} 件あります。残す設定のままでは更新せずに案内します。'
        else:
            text = '残す対象には無視対象の設定・DB・実行環境も含みます。元の版で管理されていたファイルは対象外です。'
        ttk.Label(options, text=text, wraplength=640, style='Muted.TLabel').pack(anchor='w', pady=4)
        ttk.Label(options, text='「バックアップ」は更新前の全体をZIPにまとめます。自分の編集を新しいコードへ混ぜる操作ではありません。',
                  wraplength=640, style='Muted.TLabel').pack(anchor='w')
        buttons = ttk.Frame(popup, padding=12)
        buttons.grid(row=5, column=0, sticky='ew')
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        def execute(keep):
            preserve = retain.get()
            if preserve and plan.collisions:
                messagebox.showinfo('手元のファイルと衝突しています',
                    '同じ場所に選んだ版のファイルがあるため、更新を止めています。\n' +
                    '\n'.join(plan.collisions[:20]) +
                    '\n\n別フォルダーにコピーするか、手元のファイルを別の場所に移してから確認し直してください。', parent=popup)
                return
            if not keep:
                detail = ('手元だけのファイルは残しますが、元の版にあるファイルへの編集とGit管理情報は元に戻せません。'
                          if preserve else '手元の変更・追加ファイル・Git管理情報は元に戻せません。')
                if not messagebox.askyesno('バックアップせずに更新しますか？',
                        '更新前の内容をバックアップせずに更新します。\n' + detail + '\n' + str(plan.folder), parent=popup):
                    return
            elif not preserve and not messagebox.askyesno('追加ファイルも入れ替えます',
                    '「手元だけのファイルを残す」がOFFです。\n追加ファイルも更新先から取り除きます（バックアップZIPには残ります）。\n続けますか？', parent=popup):
                return
            popup.destroy()
            def progress(note): self.operation_note = note
            def done(result):
                self.folder_query.set('')
                self.load_folders()
                detail = '同じ場所を選んだ版に更新しました。\n' + result['folder']
                detail += f"\n手元だけのファイルを引き継ぎ: {result['retained']} 件"
                if result['backup']: detail += '\n\n更新前の内容: ' + result['backup']
                if result['warning']: detail += '\n\n' + result['warning']
                messagebox.showinfo('更新しました', detail)
            self.run('選んだ版に更新しています…', lambda: apply_update(project, plan, keep, progress, preserve_local_only=preserve), done)
        def separate():
            popup.destroy()
            self.reproduce_sha(plan.sha)
        ttk.Button(buttons, text='バックアップして更新', command=lambda: execute(True), style='Primary.TButton').grid(row=0, column=0, sticky='ew', padx=4, pady=4)
        ttk.Button(buttons, text='編集内容を取り消して更新（バックアップなし）', command=lambda: execute(False), style='Danger.TButton').grid(row=0, column=1, sticky='ew', padx=4, pady=4)
        ttk.Button(buttons, text='別フォルダーにコピー', command=separate).grid(row=1, column=0, sticky='ew', padx=4, pady=4)
        ttk.Button(buttons, text='キャンセル', command=popup.destroy).grid(row=1, column=1, sticky='ew', padx=4, pady=4)
        popup.grab_set()

    def backups_dialog(self):
        if not self.project: return
        project = self.project
        directory = project.base / 'backups'
        popup = tk.Toplevel(self.window)
        popup.title('更新前のバックアップ — ' + project.name)
        popup.geometry('950x550')
        ttk.Label(popup, text='更新前の内容をZIPでバックアップしています。復元するときはZIPを別の場所へ展開してください。', padding=12).pack(anchor='w')
        controls = ttk.Frame(popup, padding=12)
        controls.pack(side='bottom', fill='x')
        table = self.table(popup, ('created', 'folder', 'size'), ('バックアップ日時', '元のフォルダー', 'サイズ'))
        items = {}
        def reload():
            table.delete(*table.get_children())
            items.clear()
            for archive in sorted(directory.glob('*.zip'), reverse=True):
                meta = archive.with_suffix('.json')
                try:
                    record = json.loads(meta.read_text(encoding='utf-8')) if meta.exists() else {}
                    size = archive.stat().st_size
                except (OSError, ValueError):
                    continue
                item = table.insert('', 'end', values=(date_value(record.get('created'))[0], record.get('folder', archive.name), f'{size / (1024*1024):.1f} MB'))
                items[item] = archive
        def chosen():
            selection = table.selection()
            return items.get(selection[0]) if selection else None
        def open_archive():
            path = chosen()
            if not path: return
            self.open_folder_path(str(path))
        def delete():
            path = chosen()
            if not path: return
            if not messagebox.askyesno('更新前のバックアップを削除', 'このZIPを削除しますか？\n更新前の手元の変更は、このZIPから復元できなくなります。\n' + str(path), parent=popup): return
            try:
                path.unlink()
                path.with_suffix('.json').unlink(missing_ok=True)
            except OSError as exc:
                messagebox.showinfo('削除できませんでした', str(exc), parent=popup)
            reload()
        ttk.Button(controls, text='ZIPを開く', command=open_archive).pack(side='left', padx=4)
        ttk.Button(controls, text='選んだバックアップを削除', command=delete).pack(side='left', padx=4)
        ttk.Button(controls, text='一覧を再表示', command=reload).pack(side='left', padx=4)
        reload()

    def reproduce(self):
        items = self.history.selection()
        if self.busy or not items: return
        self.reproduce_sha(items[0])

    @staticmethod
    def folder_state(folder):
        try:
            path = Path(folder)
            if path.is_dir(): return '利用できます'
            if path.exists(): return 'フォルダーではありません'
            return '削除または移動されています'
        except OSError:
            return 'アクセスできません'

    def on_window_focus(self, event):
        if event.widget is self.window:
            self.check_folder_tab()

    def check_folder_tab(self, event=None):
        if self.project and not self.busy and not self.dragging:
            self.load_folders()

    def load_folders(self):
        if self.notes: self.notes.reload()
        self.folder_records = {}
        self.folder_rows = []
        def add(item, kind, folder, sha='', created=''):
            memo = self.notes.get('folders', folder) if self.notes else ''
            state = self.folder_state(folder)
            if kind == '作業用（登録）' and state == '利用できます':
                _, version = record_for_folder(self.project, folder)
                state += '（上書き更新はON）' if version and version.get('update_allowed') else '（上書き更新はOFF）'
            date, timestamp = date_value(created)
            self.folder_rows.append({
                'id': item, 'pinned': kind == '作業用（登録）', 'values': (kind, folder, sha[:8], date, state, short_note(memo)),
                'search': ' '.join((kind, folder, sha, date, created, state, memo)),
                'sort': {'kind': kind.casefold(), 'path': folder.casefold(), 'sha': sha,
                         'created': timestamp, 'state': state, 'memo': memo.casefold()}})
        versions = {str(Path(r['folder']).resolve()): r for r in self.project.folder_versions()}
        for index, folder in enumerate(self.current.get('work', [])):
            record = versions.get(str(Path(folder).resolve()), {})
            add('work:' + str(index), '作業用（登録）', folder, record.get('sha', ''), record.get('created', ''))
        for record in self.project.snapshots():
            item = 'snapshot:' + record['folder']
            add(item, 'コピーしたフォルダー', record['folder'], record['sha'], record.get('created', ''))
            self.folder_records[item] = record
        self.render_folders()

    def with_selected_folder(self, action):
        if self.busy: return
        items = self.folders.selection()
        if not items:
            messagebox.showinfo('フォルダーを選択', 'PCのフォルダー一覧から、作業場所を選んでください。')
            return
        item = items[0]
        folder = self.folders.item(item, 'values')[1]
        state = self.folder_state(folder)
        display_state = state
        if state == '利用できます' and self.folders.item(item, 'values')[0] == '作業用（登録）':
            _, version = record_for_folder(self.project, folder)
            display_state += '（上書き更新はON）' if version and version.get('update_allowed') else '（上書き更新はOFF）'
        self.folders.set(item, 'state', display_state)
        if state == '利用できます':
            action(folder)
            return
        if state != '削除または移動されています':
            messagebox.showinfo('作業場所を確認', state + '\n' + folder)
            return
        record = self.folder_records.get(item)
        if not record:
            messagebox.showinfo('作業場所が見つかりません',
                                'フォルダーが削除、または移動されています。\n' + folder +
                                '\n\n登録した作業用フォルダーは自動で再作成しません。移動先を登録するか、上の履歴から新しくコピーしてください。')
            return
        project, sha = self.project, record['sha']
        if not messagebox.askyesno('コピーフォルダーが見つかりません',
                'フォルダーが削除、または移動されています。\n' + folder +
                '\n\n同じ履歴（' + sha[:8] + '）から、新しいフォルダーにコピーしますか？' +
                '\nコピー後に手元で加えた変更は復元されません。'):
            return
        def done(new_folder):
            self.folder_query.set('')
            self.load_folders()
            for new_item, new_record in self.folder_records.items():
                if new_record['folder'] == new_folder:
                    self.folders.selection_set(new_item)
                    self.folders.see(new_item)
                    break
            self.status.set('同じ履歴から新しくコピーしました: ' + new_folder)
            messagebox.showinfo('コピーしました', '新しいフォルダーを作成しました。\n' + new_folder)
            action(new_folder)
        self.run('同じ履歴から新しいフォルダーへコピーしています…', lambda: project.snapshot(sha), done)

    def register_folder(self):
        if self.busy or not self.project: return
        folder = filedialog.askdirectory(title='作業フォルダーを登録（移動・変更しません）')
        if folder and folder not in self.current['work']:
            self.current['work'].append(folder)
            self.save()
            self.load_folders()

    def open_folder(self):
        self.with_selected_folder(self.open_folder_path)

    def open_folder_path(self, path):
        try:
            if os.name == 'nt': os.startfile(path)
            else: subprocess.Popen(['xdg-open', path])
        except OSError as exc:
            messagebox.showinfo('フォルダーを開けませんでした', str(exc))

    def folder_menu(self, event):
        item = self.folders.identify_row(event.y)
        if not item: return
        self.folders.selection_set(item)
        menu = tk.Menu(self.window, tearoff=False)
        menu.add_command(label='フォルダーを開く', command=self.open_folder)
        menu.add_command(label='VS Codeで開く', command=self.vscode_selected)
        menu.add_command(label='自分用メモを編集', command=self.edit_folder_note)
        if item.startswith('work:'):
            folder = self.folders.item(item, 'values')[1]
            _, record = record_for_folder(self.project, folder)
            enabled = record and record.get('kind') == 'work' and record.get('update_allowed')
            menu.add_command(label='同じ場所への更新を無効にする' if enabled else 'この作業フォルダーの更新を有効にする', command=self.work_update_permission)
        menu.add_command(label='PowerShellで開く／コマンドを実行', command=self.command_dialog)
        menu.add_command(label='変更を確認してGitHubへ送る', command=self.send_selected_folder)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def command_dialog(self):
        self.with_selected_folder(self.command_dialog_for_folder)

    def command_dialog_for_folder(self, folder):
        popup = tk.Toplevel(self.window)
        popup.title('PowerShellで開く／コマンドを実行')
        popup.geometry('820x520')
        popup.minsize(600, 360)
        popup.columnconfigure(0, weight=1)
        popup.rowconfigure(2, weight=1)
        ttk.Label(popup, text='作業場所: ' + folder, padding=12, wraplength=560).grid(
            row=0, column=0, sticky='ew')
        ttk.Label(popup, text='実行するコマンドを貼り付けてください（複数行可）。空欄ならPowerShellを開くだけです。',
                  padding=(12, 0), wraplength=560).grid(row=1, column=0, sticky='ew')
        editor_frame = ttk.Frame(popup, padding=12)
        editor_frame.grid(row=2, column=0, sticky='nsew')
        editor = tk.Text(editor_frame, width=1, height=1, wrap='none', undo=True, font=('Consolas', 11))
        vertical = ttk.Scrollbar(editor_frame, orient='vertical', command=editor.yview)
        horizontal = ttk.Scrollbar(editor_frame, orient='horizontal', command=editor.xview)
        editor.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom', fill='x')
        vertical.pack(side='right', fill='y')
        editor.pack(fill='both', expand=True)
        ttk.Label(popup, text='実行後もPowerShellは開いたままです。入力したコマンドは保存しません。',
                  padding=(12, 0), wraplength=560).grid(row=3, column=0, sticky='ew')
        buttons = ttk.Frame(popup, padding=12)
        buttons.grid(row=4, column=0, sticky='ew')
        def launch():
            try:
                open_powershell(folder, editor.get('1.0', 'end-1c'))
            except Exception as exc:
                messagebox.showerror('PowerShellを開けませんでした', str(exc), parent=popup)
                return
            self.status.set('PowerShellを開きました: ' + folder)
            popup.destroy()
        ttk.Button(buttons, text='PowerShellを開いて実行', command=launch).pack(side='right')
        ttk.Button(buttons, text='キャンセル', command=popup.destroy).pack(side='right', padx=8)
        editor.focus_set()

    def compare(self):
        items = self.history.selection()
        if self.busy or not items: return
        folder = filedialog.askdirectory(title='選んだ履歴と比較するフォルダー')
        if not folder: return
        project, sha = self.project, items[0]
        cancel = threading.Event()
        lock = threading.Lock()
        state = {'stage': '比較の準備', 'count': 0, 'total': None, 'name': '', 'finished': False}
        started = time.monotonic()
        progress_window = tk.Toplevel(self.window)
        progress_window.title('ファイルを比較しています')
        progress_window.geometry('650x240')
        progress_window.minsize(500, 240)
        progress_window.columnconfigure(0, weight=1)
        progress_window.rowconfigure(2, weight=1)
        label = tk.StringVar()
        ttk.Label(progress_window, textvariable=label, padding=12, wraplength=470).grid(row=0, column=0, sticky='ew')
        bar = ttk.Progressbar(progress_window, mode='indeterminate')
        bar.grid(row=1, column=0, sticky='ew', padx=12, pady=8)
        bar.start(40)
        activity = tk.StringVar()
        ttk.Label(progress_window, textvariable=activity, padding=12, wraplength=470).grid(row=2, column=0, sticky='nsew')
        def stop():
            cancel.set()
            stop_button.configure(state='disabled')
        stop_button = ttk.Button(progress_window, text='中止', command=stop)
        stop_button.grid(row=3, column=0, pady=12)
        progress_window.protocol('WM_DELETE_WINDOW', stop)
        def update_progress():
            if not progress_window.winfo_exists(): return
            with lock:
                current = dict(state)
            if current['finished']:
                bar.stop()
                progress_window.destroy()
                return
            count = str(current['count']) + (('/' + str(current['total'])) if current['total'] is not None else '')
            elapsed = int(time.monotonic() - started)
            title = '中止を待っています（処理中のファイルが終わるまでお待ちください）' if cancel.is_set() else current['stage']
            label.set(f"{title}  {count} 件  ／ 経過 {elapsed} 秒")
            activity.set(current['name'][-160:])
            self.status.set(f"{title}  {count} 件 ／ 経過 {elapsed} 秒")
            progress_window.after(150, update_progress)
        def report(stage, count, total, name):
            with lock:
                state.update(stage=stage, count=count, total=total, name=name)
        def task():
            try:
                return project.compare(sha, folder, progress=report, cancelled=cancel.is_set)
            except ComparisonCancelled:
                return None
            finally:
                with lock:
                    state['finished'] = True
        def done(rows):
            if progress_window.winfo_exists():
                bar.stop()
                progress_window.destroy()
            if rows is None:
                self.status.set('比較を中止しました。ファイルは変更していません。')
                return
            popup = tk.Toplevel(self.window)
            popup.title('ファイルの比較 — 書き換えは行いません')
            popup.geometry('900x600')
            summary = tk.StringVar(value=f'違い {len(rows)} 件。結果を表示しています…')
            ttk.Label(popup, textvariable=summary, padding=10).pack()
            ttk.Label(popup, text='改行形式の違いや、無視対象のファイルも含む比較です。').pack()
            table = self.table(popup, ('state', 'file'), ('状態', 'ファイル'))
            def append_batch(offset=0):
                if not popup.winfo_exists(): return
                for row in rows[offset:offset+200]:
                    table.insert('', 'end', values=row)
                next_offset = offset + 200
                if next_offset < len(rows):
                    summary.set(f'違い {len(rows)} 件。表示済み {next_offset} 件…')
                    popup.after(10, lambda: append_batch(next_offset))
                else:
                    summary.set(f'違い {len(rows)} 件 ／ 比較時間 {int(time.monotonic() - started)} 秒')
                    if not rows: table.insert('', 'end', values=('同じ内容です', ''))
            append_batch()
        self.run('手元のファイルを比較しています…', task, done)
        update_progress()

def main(argv=None):
    from .runtime import launch
    return launch(App, argv)


if __name__ == '__main__':
    raise SystemExit(main())
