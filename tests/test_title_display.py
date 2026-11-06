import json
from pathlib import Path
import tkinter as tk
from datetime import date
from pdf_title import choose_title
from web_panel import WebPanel

def test_agenda_heading_wins_over_publisher_metadata():
    text = "議事録\n発行元 サンプルマンション管理組合 議事録作成日2025/3/16 作成者 担当A 確認者 担当B\n議題 サンプルマンション 第23期 第10回 理事会"
    assert choose_title(text) == '第23期第10回理事会議事録'

def test_wrapped_agenda_and_fullwidth_numbers():
    assert choose_title('議 事 録\n議 題\nサンプルマンション 第２３期 第１０回 理事会') == '第23期第10回理事会議事録'

def test_long_body_and_metadata_are_rejected():
    assert not choose_title('議事録発行元サンプルマンション管理組合議事録作成日2025/3/16作成者担当A確認者担当B')
    assert not choose_title('この予算決算対比表についての説明' * 8)
    assert choose_title('非常に長い議事録の本文' * 9 + '\n管理規約・細則') == '管理規約・細則'

def test_filter_and_detail_refresh_after_download(tmp_path, monkeypatch):
    import os, sys, subprocess
    if os.environ.get('KURASHI_GUI_CASE') != 'test_filter_and_detail_refresh_after_download':
        result = subprocess.run([sys.executable, '-m', 'pytest', __file__ + '::test_filter_and_detail_refresh_after_download', '-q', '--basetemp', str(tmp_path/'child')], env=dict(os.environ, KURASHI_GUI_CASE='test_filter_and_detail_refresh_after_download'), capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stdout + result.stderr
        return

    monkeypatch.setattr(WebPanel, 'startup', lambda self: None)
    window = tk.Tk()
    window.withdraw()
    panel = WebPanel(window, {'STATE_FILE':str(tmp_path/'meta/state.json'), 'DOCUMENTS_ROOT':str(tmp_path/'docs'), 'WEB_DOWNLOADS_PATH':str(tmp_path/'docs'), 'UNIFIED_DOCUMENTS':'true'})
    try:
        panel.switch_view('site', refresh=False)
        row={'title':'文書','category':'理事会議事録','period':'202503','folders':[], 'updated':'2025/03/16 08:00','fingerprint':'new','change':'更新'}
        panel.state.data['items']={'one':row}
        old=tmp_path/'old.pdf'; old.write_bytes(b'old')
        panel.state.data['downloads']={'one':{'fingerprint':'old','path':str(old)}}
        panel.render()
        panel.tree.selection_set('one');panel.show_result()
        assert '更新あり' in panel.detail.get()
        assert 'updated' in panel.tree.item('one','tags')
        panel.filter_mode.set('更新あり');panel.render()
        assert panel.tree.get_children()==('one',)
        path=tmp_path/'saved.pdf';path.write_bytes(b'%PDF-test')
        panel.events.put(('done',{'action':'download','results':[{'id':'one','fingerprint':'new','path':str(path),'status':'保存'}]}))
        panel.poll()
        assert panel.tree.get_children()==()
        assert '未取得' not in panel.detail.get()
        panel.filter_mode.set('すべて');panel.render()
        panel.tree.selection_set('one');panel.show_result()
        assert '取得済み' in panel.detail.get()
        assert str(path) in panel.detail.get()
        panel.render()
        assert panel.tree.selection()==('one',)
        assert '取得済み' in panel.detail.get()
        panel.tree.selection_remove('one');panel.show_result()
        assert panel.detail.get()=='文書を選ぶと保存先を表示します'
    finally:
        panel.destroy()
        window.destroy()
