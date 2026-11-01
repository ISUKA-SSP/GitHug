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

class App:
    def __init__(self, window):
        self.window = window
        window.title(f'GitHug {__version__} — 履歴から、安心して試す')
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
        ttk.Label(history_tab, text='履歴を選択 → 右クリックで、この時点を新しいフォルダーに再現できます。').pack(anchor='w', pady=8)
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
        self.folders = self.table(folders, ('kind', 'path', 'sha', 'state'), ('種類', '保存場所', '元の履歴', '状態'))
        self.folders.bind('<Button-3>', self.folder_menu)
        self.tabs.bind('<<NotebookTabChanged>>', self.check_folder_tab)
        ttk.Button(folders, text='既存の作業フォルダーを登録', command=self.register_folder).pack(side='left', padx=4)
        ttk.Button(folders, text='選んだフォルダーを開く', command=self.open_folder).pack(side='left', padx=4)
        ttk.Button(folders, text='PowerShellで開く／コマンドを実行', command=self.command_dialog).pack(side='left', padx=4)
        ttk.Button(folders, text='一覧を更新', command=self.check_folder_tab).pack(side='left', padx=4)
        self.populate_projects()
        window.after(100, self.poll)

    def table(self, parent, columns, labels, tree=False):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        widget = ttk.Treeview(frame, columns=columns, show='tree headings' if tree else 'headings', selectmode='browse')
        if tree:
            widget.heading('#0', text='履歴・合流')
            widget.column('#0', width=160)
        for col, label in zip(columns, labels):
            widget.heading(col, text=label)
            widget.column(col, width={'path': 550, 'message': 440, 'date': 165}.get(col, 170), minwidth=100)
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
        # Dates must be compared as instants: repositories can contain mixed time zones.
        ordered = sorted(records, key=lambda r: datetime.fromisoformat(r['date']).timestamp(), reverse=True)
        for r in ordered:
            parents = r['parents'].split()
            merge = '（合流）' if len(parents) > 1 else ''
            date = datetime.fromisoformat(r['date']).astimezone().strftime('%Y/%m/%d %H:%M')
            self.history.insert('', 'end', iid=r['sha'], text=r['sha'][:8] + merge,
                                values=(date, r['refs'], r['message']))
        self.selection.set('')
        self.history.yview_moveto(0)
        self.history.xview_moveto(0)
        self.load_folders()
        self.status.set(f'{len(records)}件の履歴を新しい順に表示（最大400件）。枝の目印と、選択時の元の履歴でつながりを確認できます。')

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
        menu.tk_popup(event.x_root, event.y_root)

    def reproduce(self):
        items = self.history.selection()
        if self.busy or not items: return
        def done(folder):
            self.load_folders()
            messagebox.showinfo('再現しました', '新しいフォルダーに保存しました。\n' + folder)
        self.run('新しいフォルダーへ再現しています…', lambda: self.project.snapshot(items[0]), done)

    @staticmethod
    def folder_state(folder):
        try:
            path = Path(folder)
            if path.is_dir(): return '利用できます'
            if path.exists(): return 'フォルダーではありません'
            return '削除または移動されています'
        except OSError:
            return 'アクセスできません'

    def check_folder_tab(self, event=None):
        if self.project and not self.busy:
            self.load_folders()

    def load_folders(self):
        self.folders.delete(*self.folders.get_children())
        self.folder_records = {}
        for folder in self.current.get('work', []):
            self.folders.insert('', 'end', values=('作業用（登録）', folder, '', self.folder_state(folder)))
        for record in self.project.snapshots():
            item = self.folders.insert('', 'end', values=('再現したフォルダー', record['folder'], record['sha'][:8],
                                                        self.folder_state(record['folder'])))
            self.folder_records[item] = record

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
                                '\n\n作業用フォルダーは元の履歴が不明なため自動で再現できません。移動先を登録してください。')
            return
        project, sha = self.project, record['sha']
        if not messagebox.askyesno('再現フォルダーが見つかりません',
                'フォルダーが削除、または移動されています。\n' + folder +
                '\n\n同じ履歴（' + sha[:8] + '）から、新しいフォルダーに再現しますか？' +
                '\n再現後に手元で加えた変更は復元されません。'):
            return
        def done(new_folder):
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
