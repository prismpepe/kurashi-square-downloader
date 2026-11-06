import json
import threading
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from local_documents import scan_local
from operations import Cancelled
from web_connector import fetch_pdf, KurashiClient
from web_updates import parse_listing
from credentials import autofill, load_credentials
from test_web_updates import direct_listing

def test_cancel_before_network(tmp_path):
    cancel=threading.Event(); cancel.set()
    context=MagicMock()
    with pytest.raises(Cancelled):
        fetch_pdf(context,parse_listing(direct_listing())[0],tmp_path/'out',tmp_path/'original',cancel=cancel)
    context.request.get.assert_not_called()
    with pytest.raises(Cancelled):
        KurashiClient(tmp_path/'data',tmp_path/'out',tmp_path/'original').run('check',cancel=cancel)

def test_cancel_after_response_never_saves(tmp_path):
    cancel=threading.Event(); context=MagicMock()
    def response(*args,**kwargs):
        cancel.set()
        return MagicMock(status=200,ok=True)
    context.request.get.side_effect=response
    with pytest.raises(Cancelled):
        fetch_pdf(context,parse_listing(direct_listing())[0],tmp_path/'out',tmp_path/'original',cancel=cancel)
    assert not (tmp_path/'out').exists()

def test_manual_registration_rename_and_repeated_scan(tmp_path,monkeypatch):
    import local_documents
    monkeypatch.setattr(local_documents,'extract_title',lambda p,cancel=None: ('過去の総会議事録','text',''))
    folder=tmp_path/'過去資料'; folder.mkdir()
    source=folder/'000123.pdf'; source.write_bytes(b'%PDF-test')
    assert scan_local(tmp_path)['count']==1
    assert source.exists()
    result=scan_local(tmp_path,rename=True)
    assert result['count']==1
    assert not source.exists()
    assert (folder/'過去の総会議事録.pdf').exists()
    assert scan_local(tmp_path,rename=True)['count']==0
    data=json.loads((tmp_path/'.kurashi-downloader/manual-documents.json').read_text('utf-8'))
    row=next(iter(data['documents'].values()))
    assert row['original_filename']=='000123.pdf'
    assert row['saved_filename']=='過去の総会議事録.pdf'
    assert row['name_history'][0]['before']=='000123.pdf'

def test_manual_scan_excludes_website_and_management_files(tmp_path):
    source=tmp_path/'web.pdf'; source.write_bytes(b'%PDF-web')
    meta=tmp_path/'.kurashi-downloader'; meta.mkdir()
    (meta/'web-updates.json').write_text(json.dumps({'downloads':{'id':{'path':str(source)}}}),'utf-8')
    (meta/'secret.txt').write_text('ignore','utf-8')
    (tmp_path/'manual.md').write_text('manual','utf-8')
    assert scan_local(tmp_path)['total']==1
    source.unlink()
    assert scan_local(tmp_path)['total']==1

def test_manual_cancel_keeps_completed_records(tmp_path):
    for i in range(3): (tmp_path/f'{i}.md').write_text('document','utf-8')
    cancel=threading.Event(); seen=[]
    def progress(msg):
        if isinstance(msg, dict) and msg['message'].startswith('文書を確認中'):
            seen.append(msg)
            if len(seen)==2: cancel.set()
    result=scan_local(tmp_path,cancel=cancel,progress=progress)
    assert result['cancelled']
    assert result['count']==1
    assert result['total']==1
    assert len(list(tmp_path.glob('*.md')))==3

def test_credential_fill_only_trusted_origin_and_no_submit(tmp_path):
    config=tmp_path/'login.json'; config.write_text(json.dumps({'account':'demo','password':'test-only'}),'utf-8')
    page=MagicMock(); page.url='https://www.kurashi-s.jp/login'
    password=MagicMock(); account=MagicMock()
    page.locator.return_value.all.return_value=[password]
    password.locator.return_value.locator.return_value.all.return_value=[account]
    assert autofill(page,config)
    account.fill.assert_called_once_with('demo'); password.fill.assert_called_once_with('test-only')
    page.click.assert_not_called()
    page.url='https://example.com/login'
    assert not autofill(page,config)
    assert account.fill.call_count==1

def test_bad_credentials_dont_expose_contents(tmp_path):
    config=tmp_path/'login.json'; config.write_text('secret-not-json','utf-8')
    with pytest.raises(ValueError) as error: load_credentials(config)
    assert 'secret-not-json' not in str(error.value)


def test_saved_web_pdf_rename_preserves_site_fingerprint(tmp_path,monkeypatch):
    import local_documents
    monkeypatch.setattr(local_documents,'extract_title',lambda p,cancel=None: ('収納状況','text',''))
    source=tmp_path/'1234.pdf'; source.write_bytes(b'%PDF-test')
    meta=tmp_path/'.kurashi-downloader';meta.mkdir()
    web={'items':{'site-id':{'fingerprint':'site-fingerprint'}},'downloads':{'site-id':{'id':'site-id','path':str(source),'fingerprint':'site-fingerprint'}},'download_history':[]}
    (meta/'web-updates.json').write_text(json.dumps(web),'utf-8')
    scan_local(tmp_path,rename=True,include_downloaded=True)
    saved=json.loads((meta/'web-updates.json').read_text('utf-8'))
    assert saved['downloads']['site-id']['fingerprint']=='site-fingerprint'
    assert saved['downloads']['site-id']['original_filename']=='1234.pdf'
    assert Path(saved['downloads']['site-id']['path']).name=='収納状況.pdf'
    assert Path(saved['downloads']['site-id']['path']).exists()
    assert saved['items']==web['items']

def test_monthly_title_spacing_and_trailing_department():
    from pdf_title import choose_title
    assert choose_title('1 頁\n収 納 状 況\n【令和7年6月末】')=='収納状況'
    assert choose_title('第24期 支出明細書(月次) 営業三課')=='第24期支出明細書(月次)'
    assert choose_title('入出金明細書 営業三課')=='入出金明細書'
