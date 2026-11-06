"""Native Windows update-check and explicit-download controls."""
from datetime import date
from pathlib import Path
import os
import queue
import json
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk, simpledialog

if __package__:
    from .web_connector import KurashiClient, public_error
    from .web_updates import UpdateState
    from .list_filters import ALL_CATEGORIES, ALL_YEARS, UNKNOWN_YEAR, fiscal_year, matches, saved_dates
    from .operations import Cancelled
    from .local_documents import scan_local, EXTENSIONS, site_names, manual_title
else:
    from web_connector import KurashiClient, public_error
    from web_updates import UpdateState
    from list_filters import ALL_CATEGORIES, ALL_YEARS, UNKNOWN_YEAR, fiscal_year, matches, saved_dates
    from operations import Cancelled
    from local_documents import scan_local, EXTENSIONS, site_names, manual_title

SCHEDULES = {'取得から1か月': 'after_download_month', '手動のみ': 'manual'}


class WebPanel(ttk.Frame):
    def __init__(self, parent, env, on_credentials=None):
        super().__init__(parent)
        self.env = env
        self.state = UpdateState(Path(env['STATE_FILE']).parent / 'web-updates.json')
        self.client = KurashiClient(Path(env.get('AUTH_DIR', Path(env['STATE_FILE']).parent)),
                                   env['WEB_DOWNLOADS_PATH'], env['DOCUMENTS_ROOT'],
                                   unified=env.get('UNIFIED_DOCUMENTS', '').lower() == 'true',
                                   management_dir=Path(env['STATE_FILE']).parent,
                                   rename_from_title=False)
        self.events = queue.Queue()
        self.busy = False
        self.cancel_event = threading.Event()
        self.close_after_cancel = False
        self.last_results = {}
        self.buttons = []
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        sidebar = ttk.Frame(self, padding=(0, 0, 16, 0))
        sidebar.grid(row=0, column=0, sticky='ns')
        self.view = None
        self.local_rows = {}
        self.resetting_filters = False
        self.nav_buttons = {}
        for key, label in [('site', 'サイト文書一覧'), ('local', '保存文書一覧')]:
            button = ttk.Button(sidebar, text=label, command=lambda key=key: self.switch_view(key), width=17)
            button.pack(fill='x', pady=(0, 8))
            self.nav_buttons[key] = button
            self.buttons.append(button)

        if on_credentials:
            self.login_settings_button = ttk.Button(sidebar, text='ログイン設定', command=on_credentials, width=17)
            self.login_settings_button.pack(fill='x', pady=(14, 0))

        content = self.content = ttk.Frame(self)
        content.grid(row=0, column=1, sticky='nsew')
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)
        selection_bar = ttk.Frame(content)
        selection_bar.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        self.view_title = ttk.Label(selection_bar, text='サイト文書一覧', style='Section.TLabel')
        self.view_title.pack(anchor='w', pady=(0, 6))
        filter_bar = ttk.Frame(selection_bar)
        filter_bar.pack(fill='x')
        self.filter_mode = tk.StringVar(value='すべて')
        self.filter_box = ttk.Combobox(filter_bar, textvariable=self.filter_mode, values=['すべて', '未取得', '更新あり', '取得済み'], state='readonly', width=13)
        self.filter_box.pack(side='left', padx=(0, 8))
        self.category_filter = tk.StringVar(value=ALL_CATEGORIES)
        self.year_filter = tk.StringVar(value=ALL_YEARS)
        self.search_text = tk.StringVar()
        self.category_box = ttk.Combobox(filter_bar, textvariable=self.category_filter, values=[ALL_CATEGORIES], state='readonly', width=17)
        self.category_box.pack(side='left', padx=(0, 8))
        self.year_box = ttk.Combobox(filter_bar, textvariable=self.year_filter, values=[ALL_YEARS], state='readonly', width=12)
        self.year_box.pack(side='left', padx=(0, 8))
        ttk.Label(filter_bar, text='検索').pack(side='left', padx=(0, 4))
        self.search_entry = ttk.Entry(filter_bar, textvariable=self.search_text, width=15)
        self.search_entry.pack(side='left', fill='x', expand=True)
        for variable in (self.filter_mode, self.category_filter, self.year_filter, self.search_text):
            variable.trace_add('write', self.filter_changed)
        self.selection_count = tk.StringVar(value='0件選択')

        self.site_tools = ttk.Frame(content)
        self.site_tools.grid(row=1, column=0, sticky='ew', pady=(0, 6))
        self.command_bar = ttk.Frame(content)
        self.command_bar.grid(row=2, column=0, sticky='ew', pady=(0, 6))
        for label, command in [('全てを選択', lambda: self.tree.selection_set(self.tree.get_children())), ('全てを解除', lambda: self.tree.selection_remove(self.tree.selection()))]:
            button = ttk.Button(self.command_bar, text=label, style='Quiet.TButton', command=command)
            button.pack(side='left', padx=(0, 6)); self.buttons.append(button)
        ttk.Separator(self.command_bar, orient='vertical').pack(side='left', fill='y', padx=(4, 12))
        self.site_actions = ttk.Frame(self.command_bar)
        button = ttk.Button(self.site_actions, text='選択文書を取得', command=self.download, style='Quiet.TButton')
        button.pack(side='left'); self.buttons.append(button)
        self.local_tools = ttk.Frame(self.command_bar)
        for text, command in [('選択文書を登録', self.register_local), ('選択文書を改名', self.review_names), ('手動で改名', self.rename_manually), ('選択文書を開く', self.open_local)]:
            button = ttk.Button(self.local_tools, text=text, command=command, style='Quiet.TButton')
            button.pack(side='left', padx=(0, 6)); self.buttons.append(button)
        area = ttk.Frame(content)
        area.grid(row=3, column=0, sticky='nsew')
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(area, columns=('category', 'period', 'title', 'site_title', 'updated', 'status'), show='headings', selectmode='extended', height=10)
        for key, label, width in [('category', 'カテゴリー', 150), ('period', '年月 / 期', 95),
                                  ('title', '元ファイル名', 250), ('site_title', 'サイト掲載名', 220), ('updated', '更新日時', 150), ('status', '状態', 115)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=75)
        self.tree.tag_configure('stripe', background='#f1f5f9')
        self.tree.tag_configure('updated', background='#fff0c2', foreground='#824400')
        self.tree.tag_configure('new', background='#e0f3e8', foreground='#155b35')
        scrollbar = ttk.Scrollbar(area, orient='vertical', command=self.tree.yview)
        horizontal = ttk.Scrollbar(area, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.bind('<Control-a>', lambda event: self.tree.selection_set(self.tree.get_children()))
        self.tree.bind('<<TreeviewSelect>>', self.show_result)
        self.tree.bind('<Double-1>', lambda event: self.open_local() if self.view == 'local' else None)
        selection_info = ttk.Frame(content)
        selection_info.grid(row=4, column=0, sticky='ew', pady=(6, 4))
        ttk.Label(selection_info, text='Ctrl / Shift キーで複数選択', style='Muted.TLabel').pack(side='left')
        ttk.Label(selection_info, textvariable=self.selection_count, style='Muted.TLabel').pack(side='left', padx=12)
        self.detail = tk.StringVar(value='文書を選ぶと保存先を表示します')
        ttk.Entry(content, textvariable=self.detail, state='readonly').grid(row=5, column=0, sticky='ew')

        # Keep all runtime information in a fixed bottom status area.
        self.statusbar = ttk.Frame(self, style='Status.TFrame', padding=(12, 10))
        self.statusbar.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(14, 0))
        self.statusbar.columnconfigure(1, weight=1)
        self.activity = tk.StringVar(value='待機中')
        ttk.Label(self.statusbar, textvariable=self.activity, style='Status.TLabel', width=33).grid(row=0, column=0, sticky='w', padx=(0, 14))
        self.progressbar = ttk.Progressbar(self.statusbar, mode='indeterminate')
        self.progressbar.grid(row=0, column=1, sticky='ew', padx=(0, 14))
        self.cancel_button = ttk.Button(self.statusbar, text='中止', command=self.cancel, state='disabled', width=8)
        self.cancel_button.grid(row=0, column=2)
        self.started_at = None
        self.completed_count = 0
        self.total_count = None
        self.message = tk.StringVar()
        self.status_summary = tk.StringVar()
        self.message.trace_add('write', lambda *_: self.status_summary.set(self.message.get().replace('\n', '  ')[:150]))
        ttk.Label(self.statusbar, textvariable=self.status_summary, style='Status.TLabel', width=1).grid(row=1, column=0, columnspan=2, sticky='ew', pady=(7, 0))
        ttk.Button(self.statusbar, text='詳細', style='Quiet.TButton', command=lambda: messagebox.showinfo('処理の詳細', self.message.get() + '\n\n' + self.detail.get(), parent=self), width=8).grid(row=1, column=2, pady=(7, 0))
        self.content.grid_remove()
        self.welcome = ttk.Label(self, text='左のメニューから操作を選択してください', style='Muted.TLabel', anchor='center')
        self.welcome.grid(row=0, column=1, sticky='nsew')
        self.poll_job = self.after(200, self.poll)
        self.startup_job = None

    def startup(self):
        self.startup_job = None
        if self.view == 'site' and not self.busy:
            self.begin('check')

    def begin(self, action, selected=(), manual_names=None):
        if self.busy:
            return
        self.state = UpdateState(self.state.path)
        if action == 'check':
            self.state.attempt(date.today())
        self.detail.set('処理中です。完了後に保存先を更新します。')
        self.busy = True
        self.cancel_event.clear()
        self.started_at = time.monotonic()
        self.completed_count = 0
        self.total_count = len(selected) if action == 'download' else None
        self.progressbar.configure(mode='determinate' if self.total_count is not None else 'indeterminate', value=0, maximum=max(self.total_count or 1, 1))
        if self.total_count is None:
            self.progressbar.start(15)
        self.activity.set('実行中 — 経過 00:00')
        self.cancel_button.configure(state='normal')
        for button in self.buttons:
            button.configure(state='disabled')
        for control in (self.filter_box, self.category_box, self.year_box, self.search_entry):
            control.configure(state='disabled')
        self.message.set({'login': 'ログイン画面を開いています', 'check': '文書一覧の更新を確認しています（本体は取得しません）', 'download': '選択した文書を取得しています', 'local': '出力フォルダの手動追加文書を登録しています', 'local_all': '保存済み文書のファイル名を変更しています'}[action])

        def work():
            try:
                progress = lambda msg: self.events.put(('progress', msg))
                if action in {'local', 'local_all'}:
                    result = scan_local(self.client.download_root, action == 'local_all', self.cancel_event, progress, include_downloaded=True, selected_paths=selected, manual_names=manual_names)
                else:
                    result = self.client.run(action, selected, progress, cancel=self.cancel_event)
                self.events.put(('done', result))
            except Exception as error:
                self.events.put(('cancelled' if self.cancel_event.is_set() or isinstance(error, Cancelled) else 'error', public_error(error)))
        threading.Thread(target=work, daemon=True).start()

    def switch_view(self, view, refresh=True):
        if self.busy:
            return
        self.welcome.grid_remove()
        self.content.grid()
        self.view = view
        self.resetting_filters = True
        self.filter_mode.set('すべて')
        self.category_filter.set(ALL_CATEGORIES)
        self.year_filter.set(ALL_YEARS)
        self.search_text.set('')
        self.resetting_filters = False
        self.view_title.configure(text='サイト文書一覧' if view == 'site' else '保存文書一覧')
        self.filter_box.configure(values=['すべて', '未取得', '更新あり', '取得済み'] if view == 'site' else ['すべて', '手動追加のみ'])
        for key, button in self.nav_buttons.items():
            button.configure(style='Primary.TButton' if key == view else 'TButton')
        if view == 'site':
            self.local_tools.pack_forget()
            self.site_tools.grid(); self.site_actions.pack(side='left')
        else:
            self.site_tools.grid_remove(); self.site_actions.pack_forget()
            self.local_tools.pack(side='left')
        self.state = UpdateState(self.state.path) if refresh else self.state
        self.render()
        if refresh:
            job = getattr(self, 'startup_job', None)
            if job:
                self.after_cancel(job)
            self.startup_job = self.after_idle(self.startup) if view == 'site' else None

    def saved_rows(self):
        root = self.client.download_root.resolve()
        inventory = self.client.management_dir / 'manual-documents.json'
        data = json.loads(inventory.read_text('utf-8')) if inventory.exists() else {}
        records = {r['relative_path']: r for r in data.get('documents', {}).values()}
        titles = site_names(self.state.data)
        dates = saved_dates(self.state.data)
        web_paths = {str(Path(r['path']).resolve()) for r in [*self.state.data.get('downloads', {}).values(), *self.state.data.get('download_history', [])] if r.get('path')}
        rows = {}
        for path in sorted(root.rglob('*')):
            rel = path.relative_to(root)
            if any(part.startswith(('.', '~$')) for part in rel.parts) or path.suffix.lower() not in EXTENSIONS or not path.is_file():
                continue
            if not path.resolve().is_relative_to(root) or any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in [path, *path.parents] if p != root):
                continue
            record = records.get(rel.as_posix(), {})
            rows['local:' + rel.as_posix()] = {'path': str(path), 'category': rel.parts[0] if len(rel.parts) > 1 else '未分類', 'folder': '/'.join(rel.parts[1:-1]), 'name': path.name, 'site_updated': dates.get(str(path.resolve()), record.get('site_updated', '')), 'site_title': titles.get(str(path.resolve()), record.get('site_title', '')) or '掲載名なし', 'source': 'Web取得' if str(path.resolve()) in web_paths or record.get('source') == 'web' else '手動追加', 'note': record.get('title_note', ''), 'registered': bool(record) or str(path.resolve()) in web_paths}
        return rows

    def render_local(self, refresh=True):
        if refresh:
            self.local_rows = self.saved_rows()
        self.update_filter_options(self.local_rows.values())
        self.tree.configure(displaycolumns=('category', 'period', 'title', 'site_title', 'updated', 'status'))
        self.tree.heading('title', text='保存ファイル名')
        self.tree.heading('updated', text='登録元')
        for key, row in self.local_rows.items():
            if not self.matches_filters(row):
                continue
            if self.filter_mode.get() == '手動追加のみ' and row['source'] != '手動追加':
                continue
            self.tree.insert('', 'end', iid=key, values=(row['category'], row['folder'], row['name'], row['site_title'], row['source'], '登録済み' if row['registered'] else '未登録'))
        self.show_result()
        self.message.set(f'表示 {len(self.tree.get_children())} / 保存文書 {len(self.local_rows)}件')

    def open_local(self):
        if self.busy or self.view != 'local':
            return
        selected = self.tree.selection()
        if len(selected) != 1:
            self.message.set('開く文書を1件選択してください')
            return
        try:
            os.startfile(self.local_rows[selected[0]]['path'])
        except OSError as error:
            messagebox.showerror('文書を開けません', str(error), parent=self)

    def rename_manually(self):
        if self.busy or self.view != 'local':
            return
        selected = self.tree.selection()
        if len(selected) != 1:
            self.message.set('手動で改名する文書を1件選択してください')
            return
        path = Path(self.local_rows[selected[0]]['path'])
        name = simpledialog.askstring('手動で改名', f'新しい文書名を入力してください（拡張子 {path.suffix} は維持します）', initialvalue=path.stem, parent=self)
        if name is None:
            return
        try:
            title = manual_title(path, name)
        except (ValueError, OSError) as error:
            messagebox.showerror('名前を変更できません', str(error), parent=self)
            return
        if title == path.stem:
            return
        self.begin('local_all', [str(path)], manual_names={str(path): title})

    def review_names(self):
        if self.busy or self.view != 'local':
            return
        rows = self.local_rows
        keys = self.tree.selection()
        paths = [rows[key]['path'] for key in keys]
        if not paths:
            self.message.set('改名する文書を選択してください')
            return
        if messagebox.askyesno('文書名の変更', f'{len(paths)}件の文書を本文・OCRから表題を取得して改名します。取得できない場合は掲載名を補助に使います。実行しますか？', parent=self):
            self.begin('local_all', paths)

    def register_local(self):
        if self.busy or self.view != 'local':
            return
        paths = [self.local_rows[key]['path'] for key in self.tree.selection()]
        if not paths:
            self.message.set('登録する文書を選択してください')
            return
        self.begin('local', paths)

    def cancel(self, close=False):
        if not self.busy:
            if close:
                self.winfo_toplevel().destroy()
            return
        if not self.cancel_event.is_set():
            if not messagebox.askyesno('処理の中止', '処理を中止しますか？完了済みのファイルと管理データは保持します。\n通信・OCR処理中の場合は終了を待ってから中止します。', parent=self):
                return
            self.cancel_event.set()
            self.cancel_button.configure(state='disabled')
            self.message.set('中止待ちです。実行中の通信・OCRが終了すると停止します。')
        if close:
            self.close_after_cancel = True

    def download(self):
        selection = self.tree.selection()
        if not selection:
            self.message.set('取得する文書を一覧から選択してください')
            return
        self.begin('download', [dict(self.state.data['items'][key]) for key in selection])

    def row_status(self, key, row):
        saved = self.state.data['downloads'].get(key, {})
        current = saved.get('fingerprint') == row['fingerprint'] and Path(saved.get('path', '')).is_file()
        if current:
            return '取得済み', ''
        changed = bool(saved.get('fingerprint') and saved['fingerprint'] != row['fingerprint'])
        if changed:
            return '更新あり', 'updated'
        return '未取得', ''

    def original_name(self, key, row):
        saved = self.state.data['downloads'].get(key, {})
        if saved.get('fingerprint') == row['fingerprint']:
            return Path(saved['path']).name if saved.get('path') else saved.get('saved_filename') or saved.get('original_filename') or '未取得'
        return Path(saved['path']).name if saved.get('path') else saved.get('saved_filename') or '未取得'

    def filter_changed(self, *_):
        if not self.resetting_filters and not self.busy:
            self.render(refresh=False)

    def matches_filters(self, row):
        return matches(row, self.category_filter.get(), self.year_filter.get(), self.search_text.get())

    def update_filter_options(self, rows):
        rows = list(rows)
        categories = [ALL_CATEGORIES] + sorted({row['category'] for row in rows})
        years = {fiscal_year(row.get('folder')) for row in rows}
        options = [ALL_YEARS] + sorted(years - {UNKNOWN_YEAR}, reverse=True) + ([UNKNOWN_YEAR] if UNKNOWN_YEAR in years else [])
        self.resetting_filters = True
        try:
            for box, variable, values in ((self.category_box, self.category_filter, categories), (self.year_box, self.year_filter, options)):
                box.configure(values=values)
                if variable.get() not in values:
                    variable.set(values[0])
        finally:
            self.resetting_filters = False

    def site_filter_row(self, key, row):
        return {'category': row['category'], 'folder': '/'.join(row['folders']) or row['period'], 'name': self.original_name(key, row), 'site_title': row['title'], 'site_updated': row['updated']}

    def render(self, refresh=True):
        if self.view is None:
            return
        selected = set(self.tree.selection())
        for key in self.tree.get_children():
            self.tree.delete(key)
        if self.view == 'local':
            self.render_local(refresh=refresh)
            self.tree.selection_set([key for key in self.tree.get_children() if key in selected])
            self.show_result()
            return
        self.tree.configure(displaycolumns=('category', 'period', 'title', 'site_title', 'updated', 'status'))
        self.tree.heading('title', text='保存ファイル名')
        self.tree.heading('updated', text='更新日時')
        filter_rows = {key: self.site_filter_row(key, row) for key, row in self.state.data['items'].items()}
        self.update_filter_options(filter_rows.values())
        displayed = 0
        for key, row in self.state.data['items'].items():
            if not self.matches_filters(filter_rows[key]):
                continue
            state, highlight = self.row_status(key, row)
            if self.filter_mode.get() != 'すべて' and self.filter_mode.get() != state:
                continue
            if self.last_results.get(key, {}).get('status') == '失敗':
                state += '（取得失敗）'
            tags = (highlight,) if highlight else (('stripe',) if displayed % 2 else ())
            self.tree.insert('', 'end', iid=key, values=(row['category'], '/'.join(row['folders']) or row['period'], self.original_name(key, row), row['title'], row['updated'], state), tags=tags)
            displayed += 1
        retained = [key for key in self.tree.get_children() if key in selected]
        self.tree.selection_set(retained)
        self.show_result()
        self.message.set(f"表示 {displayed} / 全{len(self.state.data['items'])}件  |  最終確認: {str(self.state.data['last_checked'] or '未確認')[:16].replace('T', ' ')}  |  最終取得: {self.state.data['last_download_date'] or '未取得'}" +
                         ('\n' + public_error(self.state.data['error']) if self.state.data['error'] else ''))

    def show_result(self, event=None):
        selected = self.tree.selection()
        self.selection_count.set(f'{len(selected)}件選択')
        if not selected:
            self.detail.set('文書を選ぶと保存先を表示します' if self.tree.get_children() else '表示対象の文書はありません')
            return
        key = selected[0]
        if self.view == 'local':
            row = self.local_rows.get(key, {})
            self.detail.set(row.get('path', '') + (' | ' + row['note'] if row.get('note') else ''))
            return
        result = self.last_results.get(key, self.state.data['downloads'].get(key, {}))
        status, _ = self.row_status(key, self.state.data['items'][key])
        if result.get('error'):
            self.detail.set(public_error(result['error']))
        elif result.get('path'):
            self.detail.set(status + ' | ' + result['path'] + (' | ' + result['title_note'] if result.get('title_note') else ''))
        else:
            self.detail.set(status + 'の文書です')

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'progress':
                    if isinstance(value, dict):
                        self.completed_count = value['current']
                        self.total_count = value['total']
                        self.progressbar.stop()
                        self.progressbar.configure(mode='determinate', maximum=max(self.total_count, 1), value=self.completed_count)
                        value = value['message']
                    if not self.cancel_event.is_set():
                        self.message.set(value)
                    continue
                self.busy = False
                self.progressbar.stop()
                outcome = '中止' if kind == 'cancelled' or (isinstance(value, dict) and value.get('cancelled')) else ('失敗' if kind == 'error' else '完了')
                if isinstance(value, dict):
                    if value.get('action') == 'download':
                        self.completed_count = len(value['results'])
                        if any(row['status'] == '失敗' for row in value['results']) and outcome == '完了':
                            outcome = '完了（一部失敗）'
                    elif value.get('action') == 'local':
                        self.total_count = value.get('target_count', self.total_count)
                        if outcome != '中止':
                            self.completed_count = self.total_count or 0
                        if value.get('errors') and outcome == '完了':
                            outcome = '完了（一部失敗）'
                if self.total_count is not None:
                    self.progressbar.configure(mode='determinate', maximum=max(self.total_count, 1), value=self.completed_count)
                self.update_activity(outcome)
                self.cancel_button.configure(state='disabled')
                for button in self.buttons:
                    button.configure(state='normal')
                for control in (self.filter_box, self.category_box, self.year_box):
                    control.configure(state='readonly')
                self.search_entry.configure(state='normal')
                if kind == 'cancelled':
                    self.show_result()
                    self.message.set('処理を中止しました。完了済みのファイルは保持しています。')
                elif kind == 'error':
                    self.state.failed(value)
                    self.render()
                elif value['action'] == 'local':
                    self.state = UpdateState(self.state.path)
                    self.last_results = {}
                    self.render()
                    self.message.set(('中止しました。' if value.get('cancelled') else '処理終了（一部失敗）。' if value['errors'] else '処理完了。') + f'今回登録・更新 {value["count"]}件 / 管理対象 {value["total"]}件 / エラー {len(value["errors"])}件')
                    if value['errors']:
                        failure = value['errors'][0]
                        self.detail.set(failure['path'] + ' | ' + failure['error'])
                        messagebox.showerror('文書の処理に失敗しました', failure['path'] + '\n\n' + failure['error'] + (f'\n\nほか {len(value["errors"]) - 1} 件。詳細は管理データに記録しています。' if len(value['errors']) > 1 else ''), parent=self)
                    else:
                        self.detail.set('管理データ: ' + str(self.client.management_dir / 'manual-documents.json'))
                elif value['action'] == 'check':
                    self.last_results = {}
                    notify = self.state.apply(value['rows'])
                    self.render()
                    if notify:
                        self.message.set(self.message.get() + f' | 一覧の追加・変更 {len(notify)}件')
                        self.state.acknowledge(notify)
                elif value['action'] == 'login':
                    self.message.set(value['message'])
                else:
                    self.last_results = {row['id']: row for row in value['results']}
                    self.state.downloaded(value['results'], date.today())
                    self.render()
                    failures = sum(row['status'] == '失敗' for row in value['results'])
                    self.message.set(('中止しました。' if value.get('cancelled') else '') + f'取得処理終了: {len(value["results"])}件 / 失敗 {failures}件。行を選ぶと保存先・エラーを表示します')
                if self.close_after_cancel:
                    self.winfo_toplevel().destroy()
                    return
        except queue.Empty:
            pass
        if self.busy:
            self.update_activity('中止待ち' if self.cancel_event.is_set() else '実行中')
        self.poll_job = self.after(200, self.poll)

    def update_activity(self, state):
        elapsed = int(time.monotonic() - self.started_at) if self.started_at else 0
        count = f' — {self.completed_count}/{self.total_count}件' if self.total_count is not None else ''
        self.activity.set(f'{state}{count} — 経過 {elapsed // 60:02d}:{elapsed % 60:02d}')

    def destroy(self):
        for name in ('poll_job', 'startup_job'):
            job = getattr(self, name, None)
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        super().destroy()
