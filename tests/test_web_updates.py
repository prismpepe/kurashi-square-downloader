from datetime import date
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from web_updates import UpdateState, month_after, parse_listing, store_download


def listing(idx=1, updated='2026/09/25 03:33'):
    # Reproduces the observed fl2Item/l2Folder/fileStatus structure, without account details.
    return f'''<div id="handoutFolders"><div class="fixFolder fl1Item open">
    <div class="currentFolder active"><p><a>月次報告書</a></p></div>
    <div class="folderLevel2"><div class="fl2Item open">
    <div class="l2Folder active"><p><a>202608</a></p></div>
    <div class="folderLevel3"><div class="fl2Item close">
    <a href="/GA-M61-031!EV_GA_M61_031_009.action?funcId=func036&amp;idx={idx}">収納状況</a>
    <div class="fileStatus"><p>更新日時：{updated} サイズ：104KB</p></div>
    </div></div></div></div></div></div>'''


@pytest.mark.parametrize('before,after', [
    (date(2026,1,31), date(2026,2,28)), (date(2024,1,31),date(2024,2,29)),
    (date(2026,12,31),date(2027,1,31)), (date(2026,9,25),date(2026,10,25))])
def test_calendar_month(before, after):
    assert month_after(before) == after


def test_schedule_tracks_download_not_just_startup(tmp_path):
    state = UpdateState(tmp_path / 'state.json')
    state.data['last_download_date'] = '2026-09-25'
    assert not state.due(date(2026,10,24))
    assert state.due(date(2026,10,25))
    state.attempt(date(2026,10,25))
    assert state.data['last_download_date'] == '2026-09-25'
    assert not state.due(date(2026,10,26))
    assert state.due(date(2026,11,25))
    assert not UpdateState(state.path).due(date(2026,11,24))


def test_first_start_and_manual_only(tmp_path):
    state = UpdateState(tmp_path / 's.json')
    assert state.due(date(2026,9,25))
    state.data['schedule'] = 'manual'
    assert not state.due(date(2026,9,25))


def test_failed_download_does_not_change_date(tmp_path):
    state = UpdateState(tmp_path / 's.json')
    state.downloaded([{'id':'x','status':'失敗'}], date(2026,9,25))
    assert state.data['last_download_date'] is None
    state.downloaded([{'id':'x','status':'保存','path':'file.pdf'}], date(2026,9,25))
    assert state.data['last_download_date'] == '2026-09-25'


def test_parser_stable_identity_ignores_mutable_index():
    first, changed = parse_listing(listing()), parse_listing(listing(idx=99))
    assert first[0]['id'] == changed[0]['id']
    assert first[0]['fingerprint'] == changed[0]['fingerprint']
    assert first[0]['category'] == '月次報告書'
    assert first[0]['period'] == '202608'
    assert first[0]['folders'] == ['202608']


def test_folder_actions_are_not_parsed_as_documents():
    html = listing().replace('<div id="handoutFolders">', '<div id="handoutFolders"><a href="/GA-M61-031!EV_GA_M61_031_001.action?idx=0">フォルダ操作</a>')
    assert len(parse_listing(html)) == 1


def test_document_actions_are_not_limited_to_monthly_reports():
    html = listing().replace('031_009.action', '031_010.action')
    assert len(parse_listing(html)) == 1
    assert parse_listing(html)[0]['title'] == '収納状況'


def test_folder_link_does_not_inherit_nested_document_status():
    html = listing().replace('<a>月次報告書</a>', '<a href="/GA-M61-031!EV_GA_M61_031_001.action">月次報告書</a>')
    rows = parse_listing(html)
    assert len(rows) == 1
    assert rows[0]['title'] == '収納状況'


def test_changes_notify_once_and_survive_restart(tmp_path):
    state = UpdateState(tmp_path / 's.json')
    assert state.apply(parse_listing(listing())) == []  # Initial baseline.
    rows = parse_listing(listing(updated='2026/10/25 03:33'))
    notice = state.apply(rows)
    assert len(notice) == 1
    state.acknowledge(notice)
    state = UpdateState(state.path)
    assert state.apply(rows) == []
    assert state.data['items'][rows[0]['id']]['change'] == '更新'


def test_failure_keeps_last_known_listing(tmp_path):
    state = UpdateState(tmp_path / 's.json')
    state.apply(parse_listing(listing()))
    state.failed('ログインが必要です')
    assert len(state.data['items']) == 1
    assert state.data['error'] == 'ログインが必要です'


@pytest.mark.parametrize('html,error', [('<input type="password">',PermissionError),
    ('<div>Maintenance</div>',ValueError), ('<div id="handoutFolders"></div>',ValueError)])
def test_invalid_listing_does_not_look_like_no_changes(html,error):
    with pytest.raises(error):
        parse_listing(html)


def test_store_separate_non_overwriting_and_duplicate(tmp_path):
    originals = tmp_path / 'originals'
    originals.mkdir()
    (originals / 'a.pdf').write_bytes(b'%PDF-original')
    source = tmp_path / 'tmp.pdf'
    source.write_bytes(b'%PDF-one')
    row = {'category':'月次報告書','period':'202608'}
    target = tmp_path / 'web'
    first = store_download(source,'a.pdf',row,target,originals)
    assert first['status'] == '保存'
    assert store_download(source,'a.pdf',row,target,originals)['status'] == '重複スキップ'
    source.write_bytes(b'%PDF-two')
    second = store_download(source,'a.pdf',row,target,originals)
    assert second['path'] != first['path']
    assert Path(first['path']).read_bytes() == b'%PDF-one'
    assert (originals / 'a.pdf').read_bytes() == b'%PDF-original'


def test_reject_originals_as_download_destination(tmp_path):
    source = tmp_path / 'a.pdf'
    source.write_bytes(b'%PDF-one')
    with pytest.raises(ValueError):
        store_download(source,'a.pdf',{'category':'test','period':'202609'},tmp_path / 'originals/web',tmp_path / 'originals')


def test_reject_login_page_as_pdf(tmp_path):
    source = tmp_path / 'a.pdf'
    source.write_bytes(b'<html>login</html>')
    with pytest.raises(ValueError):
        store_download(source,'a.pdf',{'category':'test','period':'202609'},tmp_path / 'web',tmp_path / 'originals')


def direct_listing(updated='2026/09/25 03:33'):
    return '<div id="handoutFolders"><div class="manageFolder"><p class="folderIcon01">' +         '<a href="/GA-M61-031!EV_GA_M61_031_011.action?idx=1">管理規約・細則</a></p>' +         '<div class="fileStatus">更新日時：' + updated + ' サイズ：104KB</div></div></div>'


def test_direct_document_and_annual_timestamp_change(tmp_path):
    first = parse_listing(direct_listing())[0]
    updated = parse_listing(direct_listing('2027/09/25 03:33'))[0]
    assert first['category'] == '管理規約・細則'
    assert first['folders'] == []
    assert first['id'] == updated['id']
    assert first['fingerprint'] != updated['fingerprint']
    assert first['period'] == '202609'
    assert updated['period'] == '202709'
    state = UpdateState(tmp_path / 'state.json')
    state.apply([first])
    state.downloaded([{'id': first['id'], 'fingerprint':first['fingerprint'], 'status':'保存'}], date(2026,9,25))
    state = UpdateState(state.path)
    assert state.apply([updated]) == [first['id']]
    assert state.data['items'][first['id']]['change'] == '更新'
    assert state.data['downloads'][first['id']]['fingerprint'] != updated['fingerprint']


def test_direct_document_coexists_with_nested_documents():
    html = listing().replace('<div id="handoutFolders">', direct_listing().removesuffix('</div>'), 1)
    assert {r['category'] for r in parse_listing(html)} == {'管理規約・細則', '月次報告書'}
