import os
import sys
import subprocess
from pathlib import Path
from unittest.mock import patch
import pytest
from list_filters import fiscal_year, matches, saved_dates

@pytest.mark.parametrize('value,expected', [('202603','2025年度'),('202604','2026年度'),('202703','2026年度'),('202704','2027年度'),('202613','年度不明'),('', '年度不明'),('第23期','年度不明'),('2026年3月','2025年度'),('2026/04','2026年度'),('2026年度/第24期','2026年度'),('第24期/202603/資料','2025年度')])
def test_fiscal_year(value, expected):
    assert fiscal_year(value) == expected

def test_filters_are_and_and_normalized():
    row = dict(category='月次報告書', site_updated='2030/04/01', name='ＡＢＣ報告.pdf', site_title='収支報告', folder='202603')
    assert matches(row,'月次報告書','2025年度','abc')
    assert not matches(row,'理事会議事録','2025年度','abc')
    assert not matches(row,'月次報告書','2026年度','abc')
    assert not matches(row,'月次報告書','2025年度','なし')
    assert matches(row,'全カテゴリー','全年度','収支')
    row['folder']='第23期'
    assert matches(row,'全カテゴリー','年度不明','')
    assert not matches(row,'全カテゴリー','2029年度','')

def test_saved_date_uses_site_date_not_download_or_new_version(tmp_path):
    path = str(tmp_path/'renamed.pdf')
    row = dict(id='one',path=path,fingerprint='old',site_updated='2025/03/31',downloaded_at='2026-10-27')
    state = dict(download_history=[row], downloads={'one':row}, items={'one':dict(fingerprint='new',updated='2026/04/01')})
    assert saved_dates(state)[path] == '2025/03/31'
    del row['site_updated']
    assert path not in saved_dates(state)
    state['items']['one']['fingerprint']='old'
    assert saved_dates(state)[path] == '2026/04/01'

def test_gui_combined_filters_and_cached_search(tmp_path):
    if os.environ.get('KURASHI_FILTER_CHILD') != '1':
        result = subprocess.run([sys.executable,'-m','pytest',__file__+'::test_gui_combined_filters_and_cached_search','-q','--basetemp',str(tmp_path/'child')], env=dict(os.environ,KURASHI_FILTER_CHILD='1'), capture_output=True,text=True,timeout=25)
        assert result.returncode == 0, result.stdout + result.stderr
        return
    import tkinter as tk
    from web_panel import WebPanel
    root=tk.Tk(); root.withdraw()
    docs=tmp_path/'docs';docs.mkdir()
    first=docs/'月次報告書'/'202603'/'ABC.pdf';first.parent.mkdir(parents=True);first.write_bytes(b'pdf')
    second=docs/'手動.pdf';second.write_bytes(b'pdf')
    panel=WebPanel(root,dict(STATE_FILE=str(docs/'.kurashi-downloader/state.json'),DOCUMENTS_ROOT=str(docs),WEB_DOWNLOADS_PATH=str(docs),UNIFIED_DOCUMENTS='true'))
    try:
        row=dict(id='one',category='月次報告書',folders=['202603'],period='202603',title='収支報告',updated='2030/04/01 10:00',fingerprint='v1')
        panel.state.data['items']={'one':row,'two':dict(row,id='two',category='理事会議事録',folders=['202604'],period='202604',updated='2026/04/01 10:00')}
        panel.state.data['downloads']={'one':dict(id='one',path=str(first),fingerprint='v1',site_updated=row['updated'])}
        panel.switch_view('site',refresh=False)
        panel.category_filter.set('月次報告書');panel.year_filter.set('2025年度');panel.search_text.set('abc')
        assert panel.tree.get_children()==('one',)
        panel.filter_mode.set('未取得');assert not panel.tree.get_children()
        panel.filter_mode.set('取得済み');assert panel.tree.get_children()==('one',)
        panel.search_text.set('なし');assert not panel.tree.get_children()
        assert '理事会議事録' in panel.category_box.cget('values')
        panel.switch_view('local',refresh=False)
        assert len(panel.tree.get_children())==2
        with patch.object(panel,'saved_rows',side_effect=AssertionError('search must not scan disk')):
            panel.category_filter.set('月次報告書');panel.year_filter.set('2025年度');panel.search_text.set('収支')
            assert len(panel.tree.get_children())==1
            panel.filter_mode.set('手動追加のみ');assert not panel.tree.get_children()
            panel.filter_mode.set('すべて');panel.search_text.set('');panel.category_filter.set('全カテゴリー');panel.year_filter.set('年度不明')
            assert len(panel.tree.get_children())==1
            assert panel.tree.get_children()[0].endswith('手動.pdf')
            panel.year_filter.set('全年度');assert len(panel.tree.get_children())==2
    finally:
        panel.destroy();root.destroy()
