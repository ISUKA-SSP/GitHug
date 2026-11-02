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
from .updating import inspect_update, apply_update

class App:
    def __init__(self, window):
        self.window = window
        self.style = apply_dark_theme(window)
        window.title(f'GitHug {__version__} — 履歴から、安心して試す')
        window.geometry('1360x900')
        window.minsize(1050, 760)
        self.config_path = Path(os.environ.get('APPDATA', Path.home() / '.config')) / 'GitHug' / 'settings.json'
        try:
            self.config = json.loads(self.config_path.read_text(encoding='utf-8'))
        except (FileNotFoundError, ValueError):
            self.config = {'root': '', 'projects': []}
        self.project = None
        self.dragging = None
        self.busy = False
        self.records = {}
        self.history_rows = []
        self.folder_rows = []
        self.sort_options = {'history': ('date', True), 'folders': ('created', True)}
        self.events = queue.Queue()
        toolbar = ttk.Frame(window, padding=12)
        toolbar.pack(fill='x')
        ttk.Label(toolbar, text='GitHug', font=('Segoe UI', 22, 'bold')).pack(side='left', padx=(0, 24))
        for title, command in [('保存先を選ぶ', self.choose_root), ('プロジェクトを追加', self.add), ('更新を確認', self.refresh)]:
            ttk.Button(toolbar, text=title, command=command).pack(side='left', padx=4)
        self.status = tk.StringVar(value='プロジェクトを追加して始めましょう。既存の作業フォルダーは書き換えません。')
        ttk.Label(window, textvariable=self.status, padding=10, wraplength=1250).pack(fill='x', side='bottom')
        self.activity_bar = ttk.Progressbar(toolbar, mode='indeterminate', length=100)
        self.activity_bar.pack(side='right', padx=8)
        ttk.Button(toolbar, text='保管した内容', command=self.backups_dialog).pack(side='left', padx=4)
        split = ttk.Panedwindow(window, orient='horizontal')
        split.pack(fill='both', expand=True, padx=12, pady=8)
        left = ttk.Frame(split, padding=8)
        split.add(left, weight=1)
        ttk.Label(left, text='プロジェクト', font=('', 12, 'bold')).pack(anchor='w')
        self.projects = tk.Listbox(left, exportselection=False, width=25)
        self.projects.pack(fill='both', expand=True, pady=8)
        self.projects.bind('<<ListboxSelect>>', self.select_project)
        right = ttk.Frame(split)
        split.add(right, weight=5)
        self.sections = ttk.Panedwindow(right, orient='vertical')
        self.sections.pack(fill='both', expand=True)
        history_tab = ttk.Frame(self.sections, padding=8)
        history_tab.columnconfigure(0, weight=1)
        history_tab.rowconfigure(3, weight=1, minsize=70)
        self.sections.add(history_tab, weight=3)
        ttk.Label(history_tab, text='GitHubの履歴', style='Heading.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(history_tab, text='履歴を下へドラッグ：空白へ新規再現／フォルダーの行へ更新の確認', style='Muted.TLabel').grid(row=1, column=0, sticky='w', pady=4)
        self.history_query, self.history_count = self.search_bar(history_tab, '履歴を検索（説明・枝名・履歴番号・日時）', grid_row=2)
        self.history = self.table(history_tab, ('date', 'refs', 'message'), ('更新日時', '作業の枝・目印', '変更の説明'), tree=True, grid_row=3)
        self.history.bind('<<TreeviewSelect>>', self.detail)
        self.history.bind('<Button-3>', self.menu)
        self.history.bind('<ButtonPress-1>', self.history_press, add='+')
        self.history.bind('<B1-Motion>', self.history_motion, add='+')
        self.history.bind('<ButtonRelease-1>', self.history_release, add='+')
        self.selection = tk.StringVar(value='')
        ttk.Label(history_tab, textvariable=self.selection, wraplength=850, style='Muted.TLabel').grid(row=4, column=0, sticky='ew', pady=4)
        controls = ttk.Frame(history_tab)
        controls.grid(row=5, column=0, sticky='ew')
        ttk.Button(controls, text='この時点を新しいフォルダーに再現', command=self.reproduce).pack(side='left', padx=4)
        ttk.Button(controls, text='作業フォルダーと比較', command=self.compare).pack(side='left', padx=4)
        folders = ttk.Frame(self.sections, padding=8)
        folders.columnconfigure(0, weight=1)
        folders.rowconfigure(3, weight=1, minsize=70)
        self.sections.add(folders, weight=2)
        ttk.Label(folders, text='PCのフォルダー', style='Heading.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(folders, text='再現フォルダーは毎回新規作成。未再現の作業用は履歴・再現日時が空欄です。', style='Muted.TLabel').grid(row=1, column=0, sticky='w', pady=4)
        self.folder_query, self.folder_count = self.search_bar(folders, 'フォルダーを検索（保存場所・再現日時・状態・履歴番号）', grid_row=2)
        self.folders = self.table(folders, ('kind', 'path', 'sha', 'created', 'state'), ('種類', '保存場所', '元の履歴', '再現した日時', '状態'), grid_row=3)
        self.folders.configure(displaycolumns=('sha', 'created', 'state', 'path'))
        self.folders.bind('<Button-3>', self.folder_menu)
        self.window.bind('<FocusIn>', self.on_window_focus, add='+')
        folder_controls = ttk.Frame(folders)
        folder_controls.grid(row=4, column=0, sticky='ew', pady=(6, 0))
        ttk.Button(folder_controls, text='作業フォルダーを登録', command=self.register_folder).pack(side='left', padx=4)
        ttk.Button(folder_controls, text='フォルダーを開く', command=self.open_folder).pack(side='left', padx=4)
        ttk.Button(folder_controls, text='PowerShell／コマンド', command=self.command_dialog).pack(side='left', padx=4)
        ttk.Button(folder_controls, text='一覧を更新', command=self.check_folder_tab).pack(side='left', padx=4)
        self.configure_sort('history', self.history, ('#0', 'date', 'refs', 'message'))
        self.configure_sort('folders', self.folders, ('sha', 'created', 'state', 'path'))
        self.history_query.trace_add('write', lambda *_: self.render_history())
        self.folder_query.trace_add('write', lambda *_: self.render_folders())
        self.populate_projects()
        window.after(150, lambda: self.sections.sashpos(0, int(self.sections.winfo_height() * 0.55)))
        window.after(100, self.poll)

    def search_bar(self, parent, description, grid_row=None):
        frame = ttk.Frame(parent)
        if grid_row is None:
            frame.pack(fill='x', pady=(0, 8))
        else:
            frame.grid(row=grid_row, column=0, sticky='ew', pady=(0, 8))
        ttk.Label(frame, text=description).pack(anchor='w')
        query = tk.StringVar()
        count = tk.StringVar()
        ttk.Entry(frame, textvariable=query).pack(side='left', fill='x', expand=True)
        ttk.Button(frame, text='クリア', command=lambda: query.set('')).pack(side='left', padx=6)
        ttk.Label(frame, textvariable=count).pack(side='right')
        return query, count

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
        shown = visible_rows(rows, query.get(), column, descending)
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

    def render_history(self):
        self.render_rows('history', self.history, self.history_rows, self.history_query, self.history_count)
        self.selection.set('')
        self.detail()

    def render_folders(self):
        self.render_rows('folders', self.folders, self.folder_rows, self.folder_query, self.folder_count)

    def table(self, parent, columns, labels, tree=False, grid_row=None):
        frame = ttk.Frame(parent)
        if grid_row is None:
            frame.pack(fill='both', expand=True)
        else:
            frame.grid(row=grid_row, column=0, sticky='nsew')
        widget = ttk.Treeview(frame, columns=columns, show='tree headings' if tree else 'headings', selectmode='browse', height=3)
        if tree:
            widget.heading('#0', text='履歴・合流')
            widget.column('#0', width=160)
        for col, label in zip(columns, labels):
            widget.heading(col, text=label)
            widget.column(col, width={'path': 550, 'message': 440, 'date': 175, 'created': 175}.get(col, 170), minwidth=100)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=widget.xview)
        horizontal.pack(side='bottom', fill='x')
        widget.configure(xscrollcommand=horizontal.set)
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=widget.yview)
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
        self.current = self.config['projects'][indices[0]]
        self.project = Project(self.config['root'], self.current['url'])
        self.refresh()

    def run(self, description, task, callback):
        if self.busy: return
        self.busy = True
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
        self.records = {r['sha']: r for r in records}
        self.history_rows = []
        for r in records:
            date, timestamp = date_value(r['date'])
            merge = '（合流）' if len(r['parents'].split()) > 1 else ''
            self.history_rows.append({
                'id': r['sha'], 'text': r['sha'][:8] + merge,
                'values': (date, r['refs'], r['message']),
                'search': ' '.join((r['sha'], r['parents'], date, r['date'], r['refs'], r['message'])),
                'sort': {'#0': r['sha'], 'date': timestamp, 'refs': r['refs'].casefold(), 'message': r['message'].casefold()}})
        self.render_history()
        self.load_folders()
        self.status.set('履歴を取得しました（最大400件）。検索は取得済みの履歴が対象です。列見出しで並べ替えできます。')

    def detail(self, event=None):
        items = self.history.selection()
        if items:
            r = self.records[items[0]]
            self.selection.set(r['message'] + '\n元になった履歴: ' + (r['parents'] or '最初の履歴'))

    def menu(self, event):
        item = self.history.identify_row(event.y)
        if not item: return
        self.history.selection_set(item)
        menu = tk.Menu(self.window, tearoff=False)
        menu.add_command(label='この時点を新しいフォルダーに再現', command=self.reproduce)
        menu.add_command(label='作業フォルダーと比較', command=self.compare)
        menu.add_command(label='選んだフォルダーをこの版に更新', command=self.update_selected)
        menu.tk_popup(event.x_root, event.y_root)

    def history_press(self, event):
        self.dragging = None
        if self.busy or not self.project or self.history.identify_region(event.x, event.y) not in ('tree', 'cell'):
            return
        item = self.history.identify_row(event.y)
        if item:
            self.dragging = {'sha': item, 'project': self.project, 'x': event.x_root,
                             'y': event.y_root, 'active': False}

    def history_motion(self, event):
        drag = self.dragging
        if not drag: return
        if abs(event.x_root - drag['x']) + abs(event.y_root - drag['y']) < 8: return
        drag['active'] = True
        self.history.configure(cursor='fleur')
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
            self.status.set('ここで離すと、このフォルダーへの更新を確認します。' if item else 'ここで離すと、新しい再現フォルダーを作ります。')
        else:
            self.status.set('PCのフォルダーの行へドラッグで更新、一覧の空白へドラッグで新規再現。')

    def history_release(self, event):
        drag = self.dragging
        self.dragging = None
        self.history.configure(cursor='')
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
            messagebox.showinfo('再現しました', '新しいフォルダーに保存しました。\n' + folder)
        self.run('新しいフォルダーへ再現しています…', lambda: project.snapshot(sha), done)

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
                    '更新先が削除、または移動されています。\n選んだ履歴から別フォルダーへ新しく再現しますか？\n' + folder):
                self.reproduce_sha(sha)
            return
        project = self.project
        def progress(note): self.operation_note = note
        self.run('手元の変更を確認しています…',
                 lambda: inspect_update(project, folder, sha, progress),
                 lambda plan: self.update_dialog(project, plan))

    def update_dialog(self, project, plan):
        popup = tk.Toplevel(self.window)
        popup.title('このフォルダーを選んだ版に更新')
        popup.geometry('880x660')
        popup.minsize(680, 570)
        popup.transient(self.window)
        popup.columnconfigure(0, weight=1)
        popup.rowconfigure(3, weight=1)
        ttk.Label(popup, text='更新先: ' + str(plan.folder), wraplength=640, padding=12).grid(row=0, column=0, sticky='ew')
        ttk.Label(popup, text='選んだ履歴: ' + plan.sha[:12] + '\n' +
                  ('元の履歴が不明です。現在の内容を保管してからの更新をおすすめします。' if plan.unknown else
                   f'手元の変更・追加など: {len(plan.differences)} 件（元の履歴 {plan.baseline[:8]} との比較）'),
                  padding=(12, 0), wraplength=640).grid(row=1, column=0, sticky='ew')
        ttk.Label(popup, text='同名ファイルだけの上書きではなく、フォルダー全体を選んだ版に入れ替えます。\n'
                  '手元だけの設定・DB・実行環境・Git管理情報も入れ替え対象です。関連アプリを閉じてから実行してください。',
                  wraplength=640, padding=12).grid(row=2, column=0, sticky='ew')
        table = self.table(popup, ('state', 'path'), ('確認内容', 'ファイル／場所'), grid_row=3)
        for row in plan.differences[:1000]: table.insert('', 'end', values=row)
        if len(plan.differences) > 1000: table.insert('', 'end', values=('表示は先頭1000件までです', ''))
        if not plan.differences: table.insert('', 'end', values=('ファイル内容に手元の変更はありません', ''))
        ttk.Label(popup, text='「保管」は更新前のフォルダー全体をZIPにまとめます。\n'
                  '「保管した内容」から確認・削除できます。自分の変更を新しい版へ自動で混ぜる操作ではありません。',
                  padding=12, wraplength=640).grid(row=4, column=0, sticky='ew')
        buttons = ttk.Frame(popup, padding=12)
        buttons.grid(row=5, column=0, sticky='ew')
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        def execute(keep):
            if not keep and not messagebox.askyesno('保管せずに更新しますか？',
                    '現在の内容を保管せずに入れ替えます。\n手元の変更・追加ファイル・Git管理情報は元に戻せません。\n' + str(plan.folder), parent=popup):
                return
            popup.destroy()
            def progress(note): self.operation_note = note
            def done(result):
                self.folder_query.set('')
                self.load_folders()
                detail = '同じ場所を選んだ版に更新しました。\n' + result['folder']
                if result['backup']: detail += '\n\n更新前の内容: ' + result['backup']
                if result['warning']: detail += '\n\n' + result['warning']
                messagebox.showinfo('更新しました', detail)
            self.run('選んだ版に更新しています…', lambda: apply_update(project, plan, keep, progress), done)
        def separate():
            popup.destroy()
            self.reproduce_sha(plan.sha)
        ttk.Button(buttons, text='今の内容を保管して更新', command=lambda: execute(True)).grid(row=0, column=0, sticky='ew', padx=4, pady=4)
        ttk.Button(buttons, text='変更を破棄して更新' if plan.differences else '保管せず更新', command=lambda: execute(False)).grid(row=0, column=1, sticky='ew', padx=4, pady=4)
        ttk.Button(buttons, text='別フォルダーに再現', command=separate).grid(row=1, column=0, sticky='ew', padx=4, pady=4)
        ttk.Button(buttons, text='キャンセル', command=popup.destroy).grid(row=1, column=1, sticky='ew', padx=4, pady=4)
        popup.grab_set()

    def backups_dialog(self):
        if not self.project: return
        project = self.project
        directory = project.base / 'backups'
        popup = tk.Toplevel(self.window)
        popup.title('保管した内容 — ' + project.name)
        popup.geometry('950x550')
        ttk.Label(popup, text='更新前の内容をZIPで保管しています。復元するときはZIPを別の場所へ展開してください。', padding=12).pack(anchor='w')
        controls = ttk.Frame(popup, padding=12)
        controls.pack(side='bottom', fill='x')
        table = self.table(popup, ('created', 'folder', 'size'), ('保管日時', '元のフォルダー', 'サイズ'))
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
            if not messagebox.askyesno('保管した内容を削除', 'このZIPを削除しますか？\n更新前の手元の変更は、このZIPから復元できなくなります。\n' + str(path), parent=popup): return
            try:
                path.unlink()
                path.with_suffix('.json').unlink(missing_ok=True)
            except OSError as exc:
                messagebox.showinfo('削除できませんでした', str(exc), parent=popup)
            reload()
        ttk.Button(controls, text='ZIPを開く', command=open_archive).pack(side='left', padx=4)
        ttk.Button(controls, text='選んだ保管内容を削除', command=delete).pack(side='left', padx=4)
        ttk.Button(controls, text='一覧を更新', command=reload).pack(side='left', padx=4)
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
        self.folder_records = {}
        self.folder_rows = []
        def add(item, kind, folder, sha='', created=''):
            state = self.folder_state(folder)
            date, timestamp = date_value(created)
            self.folder_rows.append({
                'id': item, 'values': (kind, folder, sha[:8], date, state),
                'search': ' '.join((kind, folder, sha, date, created, state)),
                'sort': {'kind': kind.casefold(), 'path': folder.casefold(), 'sha': sha,
                         'created': timestamp, 'state': state}})
        versions = {str(Path(r['folder']).resolve()): r for r in self.project.folder_versions()}
        for index, folder in enumerate(self.current.get('work', [])):
            record = versions.get(str(Path(folder).resolve()), {})
            add('work:' + str(index), '作業用（登録）', folder, record.get('sha', ''), record.get('created', ''))
        for record in self.project.snapshots():
            item = 'snapshot:' + record['folder']
            add(item, '再現したフォルダー', record['folder'], record['sha'], record.get('created', ''))
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
        self.folders.set(item, 'state', state)
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
                                '\n\n登録した作業用フォルダーは自動で再作成しません。移動先を登録するか、上の履歴から新しく再現してください。')
            return
        project, sha = self.project, record['sha']
        if not messagebox.askyesno('再現フォルダーが見つかりません',
                'フォルダーが削除、または移動されています。\n' + folder +
                '\n\n同じ履歴（' + sha[:8] + '）から、新しいフォルダーに再現しますか？' +
                '\n再現後に手元で加えた変更は復元されません。'):
            return
        def done(new_folder):
            self.folder_query.set('')
            self.load_folders()
            for new_item, new_record in self.folder_records.items():
                if new_record['folder'] == new_folder:
                    self.folders.selection_set(new_item)
                    self.folders.see(new_item)
                    break
            self.status.set('同じ履歴から新しく再現しました: ' + new_folder)
            messagebox.showinfo('再現しました', '新しいフォルダーを作成しました。\n' + new_folder)
            action(new_folder)
        self.run('同じ履歴から新しいフォルダーへ再現しています…', lambda: project.snapshot(sha), done)

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
        menu.add_command(label='PowerShellで開く／コマンドを実行', command=self.command_dialog)
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

if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
