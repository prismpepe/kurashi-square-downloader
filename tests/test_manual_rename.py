import json
from pathlib import Path
from unittest.mock import patch
import pytest
from local_documents import scan_local, manual_title
from web_updates import store_download, UpdateState
from datetime import date


def test_manual_rename_then_redownload_skips_duplicate(tmp_path):
    root=tmp_path/'docs'
    incoming=tmp_path/'incoming.pdf';incoming.write_bytes(b'%PDF-original-bytes')
    row={'id':'one','category':'総会議事録','period':'202604','fingerprint':'v1','title':'2026年4月19日'}
    saved=store_download(incoming,'12345.pdf',row,root,root,unified=True)
    state=UpdateState(root/'.kurashi-downloader/web-updates.json')
    state.downloaded([{**saved,'id':'one','fingerprint':'v1','site_title':row['title'],'original_filename':'12345.pdf'}],date(2026,10,26))
    with patch('local_documents.extract_title',side_effect=AssertionError('OCR must not run')):
        result=scan_local(root,True,include_downloaded=True,selected_paths=[saved['path']],manual_names={saved['path']:'第24期総会議事録'})
    assert result['count']==1 and not result['errors']
    target=Path(saved['path']).with_name('第24期総会議事録.pdf')
    assert target.exists() and not Path(saved['path']).exists()
    state=UpdateState(state.path)
    assert state.data['downloads']['one']['path']==str(target)
    assert state.data['downloads']['one']['fingerprint']=='v1'
    assert state.data['download_history'][0]['path']==str(target)
    again=store_download(incoming,'12345.pdf',row,root,root,unified=True)
    assert again['status']=='重複スキップ' and again['path']==str(target)
    assert len(list(target.parent.glob('*.pdf')))==1
    incoming.write_bytes(b'%PDF-new-version')
    updated=store_download(incoming,'12345.pdf',row,root,root,unified=True)
    assert updated['status']=='保存'
    assert target.read_bytes()==b'%PDF-original-bytes'
    assert len(list(target.parent.glob('*.pdf')))==2


def test_manual_office_file_without_ocr(tmp_path):
    source=tmp_path/'manual.docx';source.write_bytes(b'content')
    with patch('local_documents.extract_title',side_effect=AssertionError('OCR must not run')):
        result=scan_local(tmp_path,True,include_downloaded=True,selected_paths=[source],manual_names={source:'会議資料.docx'})
    assert not result['errors']
    assert (tmp_path/'会議資料.docx').read_bytes()==b'content'


@pytest.mark.parametrize('name',['','../outside','a/b','CON','a:bad','trailing.','a'*101])
def test_manual_name_validation(tmp_path,name):
    with pytest.raises(ValueError):manual_title(tmp_path/'source.pdf',name)


def test_manual_collision_preserves_both_files(tmp_path):
    source=tmp_path/'source.pdf';source.write_bytes(b'first')
    target=tmp_path/'exists.pdf';target.write_bytes(b'second')
    result=scan_local(tmp_path,True,include_downloaded=True,selected_paths=[source],manual_names={source:'exists'})
    assert result['errors']
    assert source.read_bytes()==b'first' and target.read_bytes()==b'second'


@pytest.mark.parametrize('registered', [False, True])
def test_locked_manual_rename_does_not_commit_metadata(tmp_path, registered):
    source = tmp_path/'original.pdf'; source.write_bytes(b'%PDF-test')
    if registered:
        scan_local(tmp_path, include_downloaded=True)
    metadata = tmp_path/'.kurashi-downloader/manual-documents.json'
    before = json.loads(metadata.read_text('utf-8'))['documents'] if registered else {}
    error = PermissionError('sharing violation'); error.winerror = 32
    with patch.object(Path, 'rename', side_effect=error):
        result = scan_local(tmp_path, True, include_downloaded=True, selected_paths=[source], manual_names={source:'new'})
    assert result['count'] == 0
    assert 'プレビューを閉じて' in result['errors'][0]['error']
    assert source.exists() and not (tmp_path/'new.pdf').exists()
    assert json.loads(metadata.read_text('utf-8'))['documents'] == before
    retry = scan_local(tmp_path, True, include_downloaded=True, selected_paths=[source], manual_names={source:'new'})
    assert retry['count'] == 1 and not retry['errors']
    assert (tmp_path/'new.pdf').exists()
