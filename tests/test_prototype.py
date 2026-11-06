from pathlib import Path
import json
import tkinter as tk
from unittest.mock import patch
from pdf_title import choose_title
from local_documents import scan_local
from web_panel import WebPanel
from launcher import configure_style

def test_cover_headings():
    cases = [
        ('サンプルマンションの非常ベル鳴動方式について １\n１、今回の工事で判明したこと', 'サンプルマンションの非常ベル鳴動方式について'),
        ('管理会社様紹介\n提案会社様給水管・給湯管洗浄提案に\n関する見解\n2025/1/19', '提案会社様給水管・給湯管洗浄提案に関する見解'),
        ('自動火災報知設備・非常用放送設備 更新工事\n設備担当 提案', '自動火災報知設備・非常用放送設備更新工事設備担当提案'),
        ('次回大規模修繕工事の発注方式\n設備担当 提案', '次回大規模修繕工事の発注方式設備担当提案'),
        ('給水ポンプ工事\n設備担当 提案', '給水ポンプ工事設備担当提案'),
        ('■共用部設備工事 業者選定履歴\nNo. 期数 年 案件 管理会社紹介提案業者 見積金額 理事会契約業者 契約金額 理事会対応', '共用部設備工事業者選定履歴'),
        ('241117 目火報・非常放送設備更新工事 進捗状況 １', '241117自火報・非常放送設備更新工事進捗状況'),
    ]
    for text, expected in cases:
        assert choose_title(text) == expected
    assert not choose_title('区分鳴動の義務化は1997年に通知されており、当マンションの竣工以前の時期')

def test_selected_rename_preserves_other_files(tmp_path):
    a=tmp_path/'a.pdf'; b=tmp_path/'b.pdf'
    a.write_bytes(b'a'); b.write_bytes(b'b')
    with patch('local_documents.extract_title', return_value=('給水ポンプ工事設備担当提案','text','')):
        result=scan_local(tmp_path,True,include_downloaded=True,selected_paths=[str(a)])
    assert result['count']==1 and not a.exists() and b.read_bytes()==b'b'
    assert (tmp_path/'給水ポンプ工事設備担当提案.pdf').read_bytes()==b'a'

def test_two_views_filter_open_and_layout(tmp_path,monkeypatch):
    import os, sys, subprocess
    if os.environ.get('KURASHI_GUI_CASE') != 'test_two_views_filter_open_and_layout':
        result = subprocess.run([sys.executable, '-m', 'pytest', __file__ + '::test_two_views_filter_open_and_layout', '-q', '--basetemp', str(tmp_path/'child')], env=dict(os.environ, KURASHI_GUI_CASE='test_two_views_filter_open_and_layout'), capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stdout + result.stderr
        return

    monkeypatch.setattr(WebPanel,'startup',lambda self:None)
    root=tk.Tk(); root.geometry('1040x640'); configure_style(root)
    docs=tmp_path/'docs'; docs.mkdir(); (docs/'手動.pdf').write_bytes(b'manual')
    web=docs/'web.pdf'; web.write_bytes(b'web')
    login_calls=[]
    panel=WebPanel(root,{'STATE_FILE':str(docs/'.kurashi-downloader/state.json'),'DOCUMENTS_ROOT':str(docs),'WEB_DOWNLOADS_PATH':str(docs),'UNIFIED_DOCUMENTS':'true'},on_credentials=lambda:login_calls.append(True))
    assert panel.view is None and panel.startup_job is None
    panel.login_settings_button.invoke()
    assert login_calls==[True]
    assert panel.view is None and panel.startup_job is None
    panel.pack(fill='both',expand=True)
    try:
        panel.state.data['downloads']={'web':{'path':str(web)}}
        panel.state.save()
        panel.switch_view('local'); root.update()
        assert len(panel.tree.get_children())==2
        panel.filter_mode.set('手動追加のみ'); panel.render()
        keys=panel.tree.get_children(); assert len(keys)==1
        panel.tree.selection_set(keys[0])
        with patch('web_panel.os.startfile') as launch:
            panel.open_local(); launch.assert_called_once_with(str(docs/'手動.pdf'))
        for button in [*panel.nav_buttons.values(),*panel.local_tools.winfo_children()]:
            assert button.winfo_ismapped()
            assert button.winfo_rooty()+button.winfo_height() <= root.winfo_rooty()+root.winfo_height()
        assert panel.nav_buttons['local'].cget('style')=='Primary.TButton'
        panel.switch_view('site');root.update()
        assert not panel.local_tools.winfo_ismapped()
        assert panel.site_tools.winfo_ismapped()
        assert panel.nav_buttons['site'].cget('style')=='Primary.TButton'
    finally:
        panel.destroy();root.destroy()

def test_full_launcher_controls_fit_small_window(tmp_path):
    import subprocess, sys, os
    script = Path(__file__).with_name('layout_probe.py')
    env = dict(os.environ, PYTHONPATH=str(script.parent.parent))
    result = subprocess.run([sys.executable, str(script), str(tmp_path)], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr

def test_selected_registration_and_automatic_view_check(tmp_path,monkeypatch):
    import os, sys, subprocess
    if os.environ.get('KURASHI_GUI_TEST_CHILD') != '1':
        result = subprocess.run([sys.executable, '-m', 'pytest', __file__ + '::test_selected_registration_and_automatic_view_check', '-q', '--basetemp', str(tmp_path/'child')], env=dict(os.environ, KURASHI_GUI_TEST_CHILD='1'), capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stdout + result.stderr
        return
    monkeypatch.setattr(WebPanel,'startup',lambda self: self.begin('check') if self.view=='site' else None)
    root=tk.Tk();root.withdraw()
    docs=tmp_path/'docs';docs.mkdir();(docs/'a.pdf').write_bytes(b'a');(docs/'b.pdf').write_bytes(b'b')
    panel=WebPanel(root,{'STATE_FILE':str(tmp_path/'meta/state.json'),'DOCUMENTS_ROOT':str(docs),'WEB_DOWNLOADS_PATH':str(docs),'UNIFIED_DOCUMENTS':'true'})
    calls=[]
    panel.begin=lambda action, selected=():calls.append((action,selected))
    try:
        panel.switch_view('local');root.update()
        assert not calls
        key=next(k for k in panel.local_rows if k.endswith('a.pdf'))
        panel.tree.selection_set(key);panel.register_local()
        assert calls==[('local',[str(docs/'a.pdf')])]
        with patch('web_panel.simpledialog.askstring', return_value='任意の文書名'), patch.object(panel, 'begin') as begin:
            panel.rename_manually()
            begin.assert_called_once_with('local_all', [str(docs/'a.pdf')], manual_names={str(docs/'a.pdf'):'任意の文書名'})
        with patch('web_panel.simpledialog.askstring', return_value=None), patch.object(panel, 'begin') as begin:
            panel.rename_manually()
            begin.assert_not_called()
        panel.switch_view('site');root.update()
        assert calls[-1]==('check',())
        assert [b.cget('text') for b in panel.local_tools.winfo_children()]==['選択文書を登録','選択文書を改名','手動で改名','選択文書を開く']
        assert [b.cget('text') for b in panel.site_actions.winfo_children()]==['選択文書を取得']
        row={'fingerprint':'current','change':'新規'}
        assert panel.row_status('id',row)[0]=='未取得'
        panel.state.data['downloads']['id']={'fingerprint':'old','path':str(docs/'a.pdf')}
        assert panel.row_status('id',row)[0]=='更新あり'
        panel.state.data['downloads']['id']['fingerprint']='current'
        assert panel.row_status('id',row)[0]=='取得済み'
    finally:
        panel.destroy();root.destroy()
