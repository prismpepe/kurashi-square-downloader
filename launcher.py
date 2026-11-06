"""Standalone Kurashi Square downloader: no chat service or Ollama required."""
import json
import os
import sys
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont
if __package__:
    from .web_panel import WebPanel
    from .version import APP_NAME, VERSION
else:
    from web_panel import WebPanel
    from version import APP_NAME, VERSION

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent

def environment(root=ROOT):
    settings_path = root / 'settings.json'
    if not settings_path.exists():
        settings_path.write_text(json.dumps({'download_folder': str(root / 'documents'), 'rename_from_title': False}, ensure_ascii=False, indent=2), 'utf-8')
    config = json.loads(settings_path.read_text('utf-8-sig'))
    documents = Path(config['download_folder'])
    if not documents.is_absolute():
        raise ValueError('保存先は絶対パスで指定してください')
    documents.mkdir(parents=True, exist_ok=True)
    data = documents / '.kurashi-downloader'
    data.mkdir(exist_ok=True)
    state_path = data / 'web-updates.json'
    if not state_path.exists():
        from web_updates import UpdateState
        state = UpdateState(state_path)
        state.data['schedule'] = 'manual'
        state.save()
    return {'STATE_FILE': str(data / 'manifest-unused.json'),
            'WEB_DOWNLOADS_PATH': str(documents), 'DOCUMENTS_ROOT': str(documents),
            'UNIFIED_DOCUMENTS': 'true', 'AUTH_DIR': str(root / 'data'), 'SETTINGS_PATH': str(root / 'settings.json'),
            'RENAME_FROM_TITLE': str(config.get('rename_from_title', False)).lower()}

def configure_style(window):
    window.configure(background='#f6f8fb')
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont'):
        tkfont.nametofont(name).configure(family='Yu Gothic UI', size=11)
    style = ttk.Style(window)
    style.theme_use('clam')
    style.configure('.', font=('Yu Gothic UI', 11), background='#f6f8fb', foreground='#172b42')
    style.configure('TButton', padding=(10, 6), background='#ffffff', bordercolor='#cbd5e1', focuscolor='#2563eb')
    style.map('TButton', background=[('active', '#e7eef8'), ('disabled', '#edf1f5')], foreground=[('disabled', '#8492a3')])
    style.configure('Primary.TButton', background='#2563eb', foreground='white', bordercolor='#2563eb')
    style.map('Primary.TButton', background=[('active', '#1d4ed8'), ('disabled', '#cbd5e1')], foreground=[('disabled', '#64748b'), ('!disabled', 'white')])
    style.configure('Quiet.TButton', padding=(10, 5))
    style.configure('TEntry', padding=7, fieldbackground='white')
    style.configure('TCombobox', padding=6)
    style.configure('TCheckbutton', padding=(0, 5))
    style.configure('TLabelframe', bordercolor='#d5deea', relief='solid')
    style.configure('TLabelframe.Label', font=('Yu Gothic UI', 11, 'bold'), foreground='#334e70')
    style.configure('Section.TLabel', font=('Yu Gothic UI', 13, 'bold'))
    style.configure('Muted.TLabel', foreground='#536780', font=('Yu Gothic UI', 10))
    style.configure('Status.TFrame', background='#e7edf5')
    style.configure('Status.TLabel', background='#e7edf5')
    style.configure('Treeview', rowheight=34, fieldbackground='white', background='white', bordercolor='#d5deea')
    style.configure('Treeview.Heading', padding=(8, 9), font=('Yu Gothic UI', 11, 'bold'), background='#e7edf5')
    style.map('Treeview', background=[('selected', '#d6e6ff')], foreground=[('selected', '#123b70')])
    style.configure('Horizontal.TProgressbar', background='#2563eb', troughcolor='#d6dfeb', thickness=12)


def main():
    window = tk.Tk()
    window.title(f'{APP_NAME} {VERSION}')
    configure_style(window)
    width = min(1280, window.winfo_screenwidth() - 80)
    height = min(860, window.winfo_screenheight() - 110)
    window.geometry(f'{width}x{height}')
    window.minsize(1040, 640)
    try:
        env = environment()
    except Exception as error:
        messagebox.showerror('設定エラー', str(error), parent=window)
        window.destroy()
        return
    heading = ttk.Frame(window, padding=(20, 14, 20, 10))
    heading.pack(fill='x')
    ttk.Label(heading, text=f'{APP_NAME}  Ver. {VERSION}', font=('Yu Gothic UI', 18, 'bold')).pack(side='left')
    settings = ttk.LabelFrame(window, text='保存先', padding=(14, 8))
    settings.pack(fill='x', padx=20, pady=(0, 12))
    folder = tk.StringVar(value=env['WEB_DOWNLOADS_PATH'])
    bar = ttk.Frame(settings)
    bar.pack(fill='x')
    ttk.Label(bar, text='出力先' ).pack(side='left')
    ttk.Entry(bar, textvariable=folder, state='readonly', width=85).pack(side='left', fill='x', expand=True)
    def change_folder():
        nonlocal panel
        if panel.busy:
            messagebox.showinfo('処理中', '取得・確認処理の終了後に変更してください', parent=window)
            return
        selected = filedialog.askdirectory(initialdir=folder.get(), parent=window)
        if not selected:
            return
        try:
            (Path(selected) / '.kurashi-downloader').mkdir(parents=True, exist_ok=True)
            probe = Path(selected) / '.kurashi-downloader' / '.write-test'
            with probe.open('x') as stream:
                stream.write('')
            probe.unlink()
        except Exception as error:
            messagebox.showerror('保存先を変更できません', str(error), parent=window)
            return
        target = ROOT / 'settings.json'
        temp = target.with_suffix('.tmp')
        config = json.loads(target.read_text('utf-8-sig'))
        temp.write_text(json.dumps({**config, 'download_folder': selected}, ensure_ascii=False, indent=2), 'utf-8')
        temp.replace(target)
        folder.set(selected)
        panel.destroy()
        panel = WebPanel(window, environment(), on_credentials=edit_credentials)
        panel.pack(fill='both', expand=True, padx=20, pady=(0, 14))
    ttk.Button(bar, text='変更', command=change_folder).pack(side='left', padx=5)
    ttk.Button(bar, text='フォルダを開く', command=lambda: os.startfile(folder.get())).pack(side='left')
    panel = WebPanel(window, env, on_credentials=lambda: edit_credentials())
    panel.pack(fill='both', expand=True, padx=20, pady=(0, 14))
    menu = tk.Menu(window)
    options = tk.Menu(menu, tearoff=False)
    def edit_credentials():
        path = ROOT / 'data' / 'login-credentials.json'
        path.parent.mkdir(exist_ok=True)
        if not path.exists():
            path.write_text(json.dumps({'account': '', 'password': ''}, indent=2), 'utf-8')
        subprocess.Popen(['notepad.exe', str(path)])
    options.add_command(label='ログイン情報ファイルを開く', command=edit_credentials)
    options.add_command(label='出力フォルダを変更', command=change_folder)
    menu.add_cascade(label='設定', menu=options)
    window.configure(menu=menu)
    def close():
        panel.cancel(close=True)
    window.protocol('WM_DELETE_WINDOW', close)
    window.mainloop()

if __name__ == '__main__':
    if '--self-test' in sys.argv:
        from frozen_check import run
        run(Path(sys.argv[sys.argv.index('--self-test') + 1]))
    else:
        main()
