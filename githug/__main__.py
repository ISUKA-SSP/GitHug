import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from .core import Project

class App:
    def __init__(self, window):
        self.window = window
        window.title('GitHug — 履歴から、安心して試す')
        window.geometry('1360x850')
        window.minsize(950, 620)
        self.config_path = Path(os.environ.get('APPDATA', Path.home() / '.config')) / 'GitHug' / 'settings.json'
        try:
            self.config = json.loads(self.config_path.read_text(encoding='utf-8'))
        except (FileNotFoundError, ValueError):
            self.config = {'root': '', 'projects': []}
        self.project = None
        self.busy = False
        self.events = queue.Queue()
        toolbar = ttk.Frame(window, padding=12)
        toolbar.pack(fill='x')
        ttk.Label(toolbar, text='GitHug', font=('Segoe UI', 22, 'bold')).pack(side='left', padx=(0, 24))
        for title, command in [('保存先を選ぶ', self.choose_root), ('プロジェクトを追加', self.add), ('更新を確認', self.refresh)]:
            ttk.Button(toolbar, text=title, command=command).pack(side='left', padx=4)
        self.status = tk.StringVar(value='プロジェクトを追加して始めましょう。既存の作業フォルダーは書き換えません。')
        ttk.Label(window, textvariable=self.status, padding=10).pack(fill='x', side='bottom')
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
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill='both', expand=True)
        history_tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(history_tab, text='GitHubの履歴')
        ttk.Label(history_tab, text='履歴を選択 → 右クリックで、この時点を別フォルダーに再現できます。').pack(anchor='w', pady=8)
        self.history = self.table(history_tab, ('date', 'refs', 'message'), ('更新日時', '作業の枝・目印', '変更の説明'), tree=True)
        self.history.bind('<<TreeviewSelect>>', self.detail)
        self.history.bind('<Button-3>', self.menu)
        self.selection = tk.StringVar(value='')
        ttk.Label(history_tab, textvariable=self.selection, wraplength=850).pack(fill='x', pady=8)
        controls = ttk.Frame(history_tab)
        controls.pack(fill='x')
        ttk.Button(controls, text='この時点を新しいフォルダーに再現', command=self.reproduce).pack(side='left', padx=4)
        ttk.Button(controls, text='作業フォルダーと比較', command=self.compare).pack(side='left', padx=4)
        folders = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(folders, text='PCのフォルダー')
        ttk.Label(folders, text='作業フォルダーは登録だけ。再現フォルダーは毎回新しく作ります。').pack(anchor='w', pady=8)
        self.folders = self.table(folders, ('kind', 'path', 'sha'), ('種類', '保存場所', '元の履歴'))
        ttk.Button(folders, text='既存の作業フォルダーを登録', command=self.register_folder).pack(side='left', padx=4)
        ttk.Button(folders, text='選んだフォルダーを開く', command=self.open_folder).pack(side='left', padx=4)
        self.populate_projects()
        window.after(100, self.poll)

    def table(self, parent, columns, labels, tree=False):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        widget = ttk.Treeview(frame, columns=columns, show='tree headings' if tree else 'headings', selectmode='browse')
        if tree:
            widget.heading('#0', text='履歴の分岐')
            widget.column('#0', width=160)
        for col, label in zip(columns, labels):
            widget.heading(col, text=label)
            widget.column(col, width=170 if col != 'path' else 550)
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
        self.status.set(description)
        def worker():
            try: self.events.put((callback, task(), None))
            except Exception as exc: self.events.put((callback, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            callback, result, error = self.events.get_nowait()
            self.busy = False
            if error:
                self.status.set('操作を完了できませんでした。フォルダーはそのまま残しています。')
                messagebox.showinfo('状況の確認', error)
            else:
                self.status.set('完了しました。')
                callback(result)
        except queue.Empty: pass
        self.window.after(100, self.poll)

    def refresh(self):
        if self.project and not self.busy:
            self.run('GitHubの履歴を確認しています…', self.project.refresh, self.show_history)

    def show_history(self, records):
        self.history.delete(*self.history.get_children())
        self.records = {r['sha']: r for r in records}
        for r in reversed(records):
            parents = r['parents'].split()
            parent = parents[0] if parents and self.history.exists(parents[0]) else ''
            merge = '（合流）' if len(parents) > 1 else ''
            self.history.insert(parent, 0, iid=r['sha'], text=r['sha'][:8] + merge,
                                values=(r['date'], r['refs'], r['message']), open=True)
        self.load_folders()
        self.status.set(f'{len(records)}件の履歴を表示。最大400件／分岐は最初の親で表示します。')

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
        menu.add_command(label='この時点を別フォルダーに再現', command=self.reproduce)
        menu.add_command(label='作業フォルダーと比較', command=self.compare)
        menu.tk_popup(event.x_root, event.y_root)

    def reproduce(self):
        items = self.history.selection()
        if self.busy or not items: return
        def done(folder):
            self.load_folders()
            messagebox.showinfo('再現しました', '新しいフォルダーに保存しました。\n' + folder)
        self.run('新しいフォルダーへ再現しています…', lambda: self.project.snapshot(items[0]), done)

    def load_folders(self):
        self.folders.delete(*self.folders.get_children())
        for folder in self.current.get('work', []):
            self.folders.insert('', 'end', values=('作業用（登録）', folder, ''))
        for record in self.project.snapshots():
            self.folders.insert('', 'end', values=('再現したフォルダー', record['folder'], record['sha'][:8]))

    def register_folder(self):
        if self.busy or not self.project: return
        folder = filedialog.askdirectory(title='作業フォルダーを登録（移動・変更しません）')
        if folder and folder not in self.current['work']:
            self.current['work'].append(folder)
            self.save()
            self.load_folders()

    def open_folder(self):
        items = self.folders.selection()
        if not items: return
        path = self.folders.item(items[0], 'values')[1]
        if os.name == 'nt': os.startfile(path)
        else: subprocess.Popen(['xdg-open', path])

    def compare(self):
        items = self.history.selection()
        if self.busy or not items: return
        folder = filedialog.askdirectory(title='選んだ履歴と比較するフォルダー')
        if not folder: return
        def done(rows):
            popup = tk.Toplevel(self.window)
            popup.title('ファイルの比較 — 書き換えは行いません')
            popup.geometry('900x600')
            ttk.Label(popup, text='改行形式の違いや、無視対象のファイルも含む比較です。', padding=10).pack()
            table = self.table(popup, ('state', 'file'), ('状態', 'ファイル'))
            for row in rows: table.insert('', 'end', values=row)
            if not rows: table.insert('', 'end', values=('同じ内容です', ''))
        self.run('手元のファイルを比較しています…', lambda: self.project.compare(items[0], folder), done)

if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
