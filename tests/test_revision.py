import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from web_connector import fetch_pdf, request_pdf, public_error, LoginRequired, KurashiClient
from web_updates import parse_listing
from test_web_updates import listing
from local_documents import scan_local
from operations import Cancelled

def response(status=200):
    result=MagicMock();result.status=status;result.ok=status==200
    result.headers={'content-disposition':'attachment; filename="original.pdf"'}
    result.body.return_value=b'%PDF-fixture'
    return result

def test_timeout_retries_and_original_filename(tmp_path):
    context=MagicMock(); pdf=response()
    context.request.get.side_effect=[TimeoutError('Timeout\nCall log:\n cookie: secret'),pdf]
    with patch('web_connector.pause') as pause, patch('pdf_title.extract_title') as title:
        result=fetch_pdf(context,parse_listing(listing())[0],tmp_path/'out',tmp_path/'original',rename_from_title=False)
    assert result['saved_filename']=='original.pdf'
    assert context.request.get.call_count==2
    assert context.request.get.call_args.kwargs['timeout']==60000
    title.assert_not_called(); pdf.dispose.assert_called_once();pause.assert_called_once()

def test_retry_limit_and_safe_error():
    context=MagicMock();context.request.get.side_effect=TimeoutError('Timeout\nCall log:\n cookie: secret')
    with patch('web_connector.pause'),pytest.raises(TimeoutError) as error:
        request_pdf(context,'https://www.kurashi-s.jp/document')
    assert context.request.get.call_count==3
    assert 'secret' not in str(error.value)
    assert 'secret' not in public_error('Timeout\nCall log:\n cookie: secret')
    assert 'secret' not in public_error('cookie: secret')

def test_transient_http_retry_disposes_response():
    context=MagicMock();busy=response(503);pdf=response()
    context.request.get.side_effect=[busy,pdf]
    with patch('web_connector.pause'):assert request_pdf(context,'url') is pdf
    busy.dispose.assert_called_once()

def test_cancel_during_retry_stops():
    event=threading.Event();context=MagicMock()
    def timeout(*args,**kwargs):event.set();raise TimeoutError('Timeout')
    context.request.get.side_effect=timeout
    with pytest.raises(Cancelled):request_pdf(context,'url',event)
    assert context.request.get.call_count==1

def test_expired_login_automatically_continues_check(tmp_path):
    client=KurashiClient(tmp_path/'auth',tmp_path/'docs',tmp_path/'docs')
    with patch.object(client,'_run',side_effect=[LoginRequired(),{'action':'check','rows':[]}]) as run:
        assert client.run('check')=={'action':'check','rows':[]}
    assert [call.args[0] for call in run.call_args_list]==['check','interactive_check']

def test_expired_login_resumes_selected_download(tmp_path):
    client=KurashiClient(tmp_path/'auth',tmp_path/'docs',tmp_path/'docs')
    selected=[{'id':'one'}]
    with patch.object(client,'_run',side_effect=[LoginRequired(),{'action':'check','rows':[]},{'action':'download','results':[]}]) as run:
        client.run('download',selected)
    assert [call.args[0] for call in run.call_args_list]==['download','interactive_check','download']
    assert run.call_args.args[1]==selected

def test_registration_only_selected_includes_office_files(tmp_path):
    a=tmp_path/'a.docx';b=tmp_path/'b.pdf'
    a.write_bytes(b'a');b.write_bytes(b'b')
    result=scan_local(tmp_path,include_downloaded=True,selected_paths=[a])
    data=json.loads((tmp_path/'.kurashi-downloader/manual-documents.json').read_text('utf-8'))
    assert result['count']==1
    assert [r['relative_path'] for r in data['documents'].values()]==['a.docx']
    assert a.read_bytes()==b'a' and b.read_bytes()==b'b'

def test_credential_autosubmit_only_after_valid_fill(tmp_path):
    from credentials import autofill
    path=tmp_path/'credentials.json';path.write_text(json.dumps({'account':'test','password':'test'}),'utf-8')
    page=MagicMock();page.url='https://www.kurashi-s.jp/login'
    password=MagicMock();account=MagicMock()
    page.locator.return_value.all.return_value=[password]
    password.locator.return_value.locator.return_value.all.return_value=[account]
    assert autofill(page,path,submit=True)
    password.press.assert_called_once_with('Enter')
    page.url='https://example.com/login';password.reset_mock()
    assert not autofill(page,path,submit=True)
    password.press.assert_not_called()

def test_auto_login_reads_listing_without_downloading(tmp_path,monkeypatch):
    from test_web_connector import install_fake_browser
    page,context,manager=install_fake_browser(monkeypatch,listing())
    page.locator.return_value.count.side_effect=[0,0,1,1]
    page.get_by_role.return_value.count.return_value=1
    with patch('web_connector.autofill',return_value=True) as fill:
        result=KurashiClient(tmp_path/'auth',tmp_path/'docs',tmp_path/'docs').run('check')
    assert result['action']=='check' and len(result['rows'])==1
    assert fill.call_args.kwargs['submit'] is True
    launches=manager.__enter__.return_value.chromium.launch_persistent_context.call_args_list
    assert [x.kwargs['headless'] for x in launches]==[True,False]
    assert context.close.call_count==2
    context.request.get.assert_not_called()

def test_download_never_extracts_title_even_with_legacy_setting(tmp_path):
    context=MagicMock();context.request.get.return_value=response()
    with patch('pdf_title.extract_title',side_effect=AssertionError('Download must not use OCR')):
        result=fetch_pdf(context,parse_listing(listing())[0],tmp_path/'out',tmp_path/'original',rename_from_title=True)
    assert result['saved_filename']=='original.pdf'
    assert result['title_method']=='disabled'

def test_site_original_filename_is_not_listing_title():
    from types import SimpleNamespace
    from web_panel import WebPanel
    panel=SimpleNamespace(state=SimpleNamespace(data={'downloads':{}}))
    row={'fingerprint':'v1','title':'サイト掲載名'}
    assert WebPanel.original_name(panel,'one',row)=='未取得'
    panel.state.data['downloads']['one']={'fingerprint':'v1','original_filename':'12345.pdf','saved_filename':'改名済み.pdf'}
    assert WebPanel.original_name(panel,'one',row)=='改名済み.pdf'
    row['fingerprint']='v2'
    assert WebPanel.original_name(panel,'one',row)=='改名済み.pdf'

def test_title_priority_and_date_listing_fallback(tmp_path):
    from unittest.mock import patch
    folder=tmp_path/'総会議事録';folder.mkdir()
    path=folder/'123.pdf';path.write_bytes(b'%PDF-test')
    meta=tmp_path/'.kurashi-downloader';meta.mkdir()
    state={'downloads':{'one':{'id':'one','path':str(path),'site_title':'2026年4月19日','fingerprint':'v1'}},'download_history':[]}
    (meta/'web-updates.json').write_text(json.dumps(state),'utf-8')
    with patch('local_documents.extract_title',return_value=('第24期通常総会議事録','text','')):
        scan_local(tmp_path,rename=True,include_downloaded=True)
    renamed=folder/'第24期通常総会議事録.pdf'
    assert renamed.exists()
    with patch('local_documents.extract_title',return_value=('','fallback','')):
        scan_local(tmp_path,rename=True,include_downloaded=True)
    assert (folder/'総会議事録2026年4月19日.pdf').exists()
    current=json.loads((meta/'web-updates.json').read_text('utf-8'))
    assert current['downloads']['one']['site_title']=='2026年4月19日'
    assert current['downloads']['one']['fingerprint']=='v1'

def test_manual_without_title_or_listing_preserves_filename(tmp_path):
    path=tmp_path/'manual.pdf';path.write_bytes(b'%PDF-test')
    with patch('local_documents.extract_title',return_value=('','fallback','読み取り不可')):
        scan_local(tmp_path,rename=True,include_downloaded=True)
    assert path.exists()
