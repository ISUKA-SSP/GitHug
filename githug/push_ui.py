"""UI for reviewed GitHub sends and opt-in AI explanations."""
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from .publishing import inspect_push, local_base, preview_changes, publish
from .explaining import explainable, explanation_input, explain, cache_key


class PushUI:
    def __init__(self, app):
        self.app = app
        self.responses = {}

    def begin(self, folder, dropped_sha=None):
        app = self.app
        if app.busy or not app.project: return
        project = app.project
        folder = Path(folder)
        if not folder.is_dir():
            messagebox.showinfo('送信元が見つかりません', 'フォルダーが削除または移動されています。')
            return
        # Unknown folders require an explicit comparison base, not a guess at deletions.
        fallback = None
        if not local_base(project, folder):
            selection = app.history.selection()
            fallback = dropped_sha or (selection[0] if selection else None)
            if not fallback:
                messagebox.showinfo('元の履歴を選択', '送信元の基準が分かりません。上で比較元の履歴を選び、もう一度送信してください。')
                return
            if not messagebox.askyesno('比較する基準を確認', '元の履歴が不明です。選択した履歴 ' + fallback[:8] +
                                       ' を基準に、変更・追加・削除を調べますか？\n送信前に対象ファイルを選べます。'):
                return
        def task():
            project.refresh()
            return inspect_push(project, folder, fallback, lambda note: setattr(app, 'operation_note', note))
        app.run('送信する変更を確認しています…', task, lambda plan: self.dialog(project, plan, dropped_sha))

    def dialog(self, project, plan, dropped_sha):
        app = self.app
        if not plan.changes:
            messagebox.showinfo('送信する変更はありません', '基準の履歴と比べて、送信対象になる変更がありません。')
            return
        popup = tk.Toplevel(app.window)
        popup.title('変更を確認してGitHubへ送る')
        popup.geometry('1040x820')
        popup.minsize(860, 740)
        popup.transient(app.window)
        popup.columnconfigure(0, weight=1)
        popup.rowconfigure(2, weight=1)
        ttk.Label(popup, text='送信元: ' + str(plan.folder) + '\n送信先: ' + project.url.removesuffix('.git') +
                  ' ／ 比較元 ' + plan.base[:8], wraplength=820, padding=12).grid(row=0, column=0, sticky='ew')
        target = ttk.Frame(popup, padding=(12, 0))
        target.grid(row=1, column=0, sticky='ew')
        target.columnconfigure(1, weight=1)
        tips = [name for name, sha in plan.branches.items() if sha == dropped_sha]
        if dropped_sha and not tips and dropped_sha != plan.base:
            if not messagebox.askyesno('新しい枝の基準を確認',
                    '指定した過去の履歴へ変更を合わせる機能は未対応です。\n送信元の基準 ' + plan.base[:8] +
                    ' から新しい枝を作る確認を続けますか？', parent=popup):
                popup.destroy()
                return
        mode = tk.StringVar(value='既存の枝へ送る' if tips else '新しい枝として送る')
        branch = tk.StringVar(value=tips[0] if tips else 'work/' + datetime.now().strftime('%Y%m%d-%H%M%S'))
        ttk.Combobox(target, textvariable=mode, values=('新しい枝として送る', '既存の枝へ送る'), state='readonly', width=22).grid(row=0, column=0, padx=(0, 8), pady=4)
        branch_box = ttk.Combobox(target, textvariable=branch, values=sorted(plan.branches))
        branch_box.grid(row=0, column=1, sticky='ew', pady=4)
        ttk.Label(target, text='新しい枝は送信元の比較基準から作ります。GitHub側や過去の版へ変更を合わせる機能は未実装です。',
                  style='Muted.TLabel', wraplength=820).grid(row=1, column=0, columnspan=2, sticky='w', pady=4)
        table = app.table(popup, ('send', 'kind', 'path'), ('送信', '変更', 'ファイル'), grid_row=2)
        table.column('send', width=80, stretch=False)
        table.column('kind', width=100, stretch=False)
        table.column('path', width=700)
        selected = {change.path for change in plan.changes if change.initially_selected}
        by_item = {}
        for index, change in enumerate(plan.changes):
            item = str(index)
            by_item[item] = change
            table.insert('', 'end', iid=item, values=('✓ 送る' if change.path in selected else '—',
                         {'M':'変更', 'A':'追加', 'D':'削除'}[change.kind], change.path))
        def toggle(event=None):
            item = table.identify_row(event.y) if event is not None and hasattr(event, 'y') else (table.selection()[0] if table.selection() else '')
            if not item or item not in by_item: return
            path = by_item[item].path
            if path in selected: selected.remove(path)
            else: selected.add(path)
            table.set(item, 'send', '✓ 送る' if path in selected else '—')
        table.bind('<Double-1>', toggle)
        table.bind('<space>', lambda event: toggle())
        selection_controls = ttk.Frame(popup, padding=(12, 4))
        selection_controls.grid(row=3, column=0, sticky='ew')
        ttk.Button(selection_controls, text='選んだ行を送る／外す', command=toggle).pack(side='left')
        ttk.Label(selection_controls, text='追加・削除は未選択。設定やDBも自動追加しません。ダブルクリックでも切り替えできます。',
                  wraplength=650, style='Muted.TLabel').pack(side='left', padx=8)
        details = ttk.Frame(popup, padding=(12, 4))
        details.grid(row=4, column=0, sticky='ew')
        details.columnconfigure(1, weight=1)
        ttk.Label(details, text='変更の説明').grid(row=0, column=0, sticky='w')
        description = tk.Text(details, height=3, width=1, wrap='word', undo=True)
        description.grid(row=0, column=1, columnspan=3, sticky='ew', pady=4)
        name = tk.StringVar(value=app.config.get('author_name') or plan.author_name)
        email = tk.StringVar(value=app.config.get('author_email') or plan.author_email)
        ttk.Label(details, text='記録する名前').grid(row=1, column=0, sticky='w')
        ttk.Entry(details, textvariable=name).grid(row=1, column=1, sticky='ew', padx=4)
        ttk.Label(details, text='メール').grid(row=1, column=2)
        ttk.Entry(details, textvariable=email, width=30).grid(row=1, column=3, sticky='ew', padx=4)
        ttk.Label(details, text='名前とメールはGitHubの履歴に記録されます。手元のコードとGitの履歴は書き換えません。',
                  style='Muted.TLabel', wraplength=820).grid(row=2, column=0, columnspan=4, sticky='w', pady=4)
        commands = ttk.Frame(popup, padding=12)
        commands.grid(row=5, column=0, sticky='ew')
        def preview():
            if app.busy: return
            paths = list(selected)
            app.run('選んだ差分を準備しています…', lambda: preview_changes(project, plan, paths),
                    lambda data: self.text_view('送信する差分（GitHubへはまだ送りません）', data['summary'] + '\n' + data['patch']))
        def ask_ai():
            if app.busy: return
            paths = [path for path in selected if explainable(path)]
            excluded = len(selected) - len(paths)
            if not paths:
                messagebox.showinfo('説明するファイルを選択', '送信対象のコードなどを選んでください。設定・DB・鍵などは説明対象外です。', parent=popup)
                return
            def show(data): self.ai_dialog(data, description, popup, excluded)
            app.run('説明対象の差分を準備しています…', lambda: preview_changes(project, plan, paths), show)
        def send():
            if app.busy: return
            paths = list(selected)
            if not paths or not description.get('1.0','end-1c').strip() or not branch.get().strip() or not name.get().strip() or not email.get().strip():
                messagebox.showinfo('入力を確認', 'ファイル・枝の名前・変更の説明・記録する名前とメールを確認してください。', parent=popup)
                return
            new = mode.get() == '新しい枝として送る'
            destination = branch.get().strip()
            if not new and plan.branches.get(destination) != plan.base:
                messagebox.showinfo('新しい枝をおすすめします', 'この枝には元の版と異なる更新があります。「新しい枝として送る」を選んでください。', parent=popup)
                return
            if not messagebox.askyesno('GitHubへ送信', f'{project.name}\n枝: {destination}\n対象: {len(paths)} 件\n選んだ内容を記録してGitHubへ送りますか？', parent=popup):
                return
            message = description.get('1.0','end-1c')
            name_value, email_value = name.get(), email.get()
            def done(result):
                popup.destroy()
                app.config['author_name'], app.config['author_email'] = name_value, email_value
                app.save()
                messagebox.showinfo('GitHubへ送りました', '枝: ' + result['branch'] + '\n履歴: ' + result['sha'][:12] + '\n' + result['warning'])
                app.refresh()
            app.run('記録を作ってGitHubへ送っています…',
                    lambda: publish(project, plan, paths, destination, new, message, name_value, email_value,
                                    lambda note: setattr(app, 'operation_note', note)), done)
        def cancel():
            if app.busy:
                messagebox.showinfo('処理中です', '処理が終わってから閉じてください。', parent=popup)
                return
            popup.destroy()
        popup.protocol('WM_DELETE_WINDOW', cancel)
        ttk.Button(commands, text='選んだ差分を見る', command=preview).pack(side='left', padx=4)
        ttk.Button(commands, text='AIに説明を頼む（任意）', command=ask_ai).pack(side='left', padx=4)
        ttk.Button(commands, text='キャンセル', command=cancel).pack(side='right', padx=4)
        ttk.Button(commands, text='記録してGitHubへ送る', command=send).pack(side='right', padx=4)
        popup.grab_set()

    def text_view(self, title, text):
        app = self.app
        view = tk.Toplevel(app.window)
        view.title(title)
        view.geometry('940x650')
        editor = tk.Text(view, wrap='none', font=('Consolas', 10))
        vertical = ttk.Scrollbar(view, orient='vertical', command=editor.yview)
        horizontal = ttk.Scrollbar(view, orient='horizontal', command=editor.xview)
        editor.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom', fill='x')
        vertical.pack(side='right', fill='y')
        editor.pack(fill='both', expand=True)
        editor.insert('1.0', text)
        editor.configure(state='disabled')
        # Allow inspection while the send-review window has a grab.
        previous = app.window.grab_current()
        view.grab_set()
        def close():
            view.destroy()
            if previous and previous.winfo_exists(): previous.grab_set()
        view.protocol('WM_DELETE_WINDOW', close)

    def ai_dialog(self, data, description, parent, excluded):
        app = self.app
        try:
            initial = explanation_input(data, False)
        except ValueError as exc:
            messagebox.showinfo('説明するファイルを減らしてください', str(exc), parent=parent)
            return
        popup = tk.Toplevel(parent)
        popup.title('Geminiへ送る内容を確認')
        popup.geometry('960x780')
        popup.minsize(800, 680)
        popup.columnconfigure(0, weight=1)
        popup.rowconfigure(3, weight=1)
        settings = ttk.Frame(popup, padding=12)
        settings.grid(row=0, column=0, sticky='ew')
        settings.columnconfigure(1, weight=1)
        key = tk.StringVar()
        model = tk.StringVar(value=app.config.get('gemini_model', ''))
        detail = tk.BooleanVar(value=False)
        ttk.Label(settings, text='Gemini APIキー（保存しません）').grid(row=0, column=0, sticky='w')
        ttk.Entry(settings, textvariable=key, show='●').grid(row=0, column=1, sticky='ew', padx=8, pady=4)
        ttk.Label(settings, text='モデル名（AI Studioで確認）').grid(row=1, column=0, sticky='w')
        ttk.Entry(settings, textvariable=model).grid(row=1, column=1, sticky='ew', padx=8, pady=4)
        ttk.Label(popup, text=f'次の欄だけをGoogleへ送ります。内容は編集できます。対象外の設定・DB・鍵など: {excluded} 件。\n'
                  '利用量はGoogle側の契約によります。自動送信・自動再試行はしません。',
                  padding=(12, 0), wraplength=820).grid(row=1, column=0, sticky='ew')
        editor_frame = ttk.Frame(popup, padding=12)
        editor_frame.grid(row=3, column=0, sticky='nsew')
        editor = tk.Text(editor_frame, width=1, height=1, wrap='none', undo=True)
        scroll = ttk.Scrollbar(editor_frame, orient='vertical', command=editor.yview)
        editor.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        editor.pack(fill='both', expand=True)
        def populate():
            try: text = explanation_input(data, detail.get())
            except ValueError as exc:
                detail.set(False)
                text = initial
                messagebox.showinfo('概要のみ表示します', str(exc), parent=popup)
            editor.delete('1.0', 'end')
            editor.insert('1.0', text)
        ttk.Checkbutton(popup, text='コードの差分も含める（OFFならファイル名と行数のみ）', variable=detail,
                        command=populate).grid(row=2, column=0, sticky='w', padx=12, pady=4)
        populate()
        output = tk.Text(popup, height=6, wrap='word')
        output.grid(row=4, column=0, sticky='ew', padx=12)
        buttons = ttk.Frame(popup, padding=12)
        buttons.grid(row=5, column=0, sticky='ew')
        def request():
            if app.busy: return
            text, selected_model, api_key = editor.get('1.0','end-1c'), model.get(), key.get()
            if not selected_model.strip() or not api_key.strip():
                messagebox.showinfo('入力を確認', 'APIキーとモデル名を入力してください。', parent=popup); return
            token = cache_key(selected_model, text)
            def done(answer):
                self.responses[token] = answer
                if not popup.winfo_exists(): return
                output.delete('1.0','end'); output.insert('1.0',answer)
                app.config['gemini_model'] = selected_model.strip()
                app.save()
            if token in self.responses:
                done(self.responses[token]); return
            app.run('Geminiへ説明を依頼しています…', lambda: explain(api_key, selected_model, text), done)
        def use():
            if not output.get('1.0','end-1c').strip(): return
            if description.winfo_exists():
                description.delete('1.0','end')
                description.insert('1.0',output.get('1.0','end-1c'))
        def close():
            key.set('')
            popup.destroy()
            if parent.winfo_exists(): parent.grab_set()
        ttk.Button(buttons, text='この内容をGeminiへ送って説明', command=request).pack(side='left', padx=4)
        ttk.Button(buttons, text='説明を変更の説明欄へコピー', command=use).pack(side='left', padx=4)
        ttk.Button(buttons, text='閉じる', command=close).pack(side='right', padx=4)
        popup.protocol('WM_DELETE_WINDOW', close)
        popup.grab_set()
