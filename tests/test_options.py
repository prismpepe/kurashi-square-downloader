import json
from pathlib import Path
from unittest.mock import MagicMock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from launcher import environment
from pdf_title import choose_title
from web_connector import fetch_pdf
from web_updates import parse_listing, UpdateState
from test_web_updates import direct_listing

def test_output_state_is_independent(tmp_path):
    app = tmp_path / 'app'
    app.mkdir()
    def config(folder):
        (app/'settings.json').write_text(json.dumps({'download_folder':str(folder), 'rename_from_title':True}), 'utf-8')
        return environment(app)
    first=config(tmp_path/'first')
    state=UpdateState(Path(first['STATE_FILE']).parent/'web-updates.json')
    state.apply(parse_listing(direct_listing()))
    second=config(tmp_path/'second')
    assert not UpdateState(Path(second['STATE_FILE']).parent/'web-updates.json').data['items']
    assert first['AUTH_DIR']==second['AUTH_DIR']==str(app/'data')
    assert first['RENAME_FROM_TITLE']=='true'
    assert len(UpdateState(Path(first['STATE_FILE']).parent/'web-updates.json').data['items'])==1

def test_title_ignores_numbers_dates_and_sentences():
    assert choose_title('12345-00\n2026年5月16日\n第20期 通常総会議事録\n議事録について説明します。')=='第20期通常総会議事録'
    assert not choose_title('1234_0987\n内容をご確認ください。')

def test_renaming_records_names_without_changing_identity(tmp_path, monkeypatch):
    import pdf_title
    monkeypatch.setattr(pdf_title, 'extract_title', lambda p: ('管理規約・細則', 'text', ''))
    context=MagicMock()
    response=context.request.get.return_value
    response.status=200; response.ok=True
    response.headers={'content-disposition':'attachment; filename="98765.pdf"'}
    response.body.return_value=b'%PDF-fixture'
    row=parse_listing(direct_listing())[0]
    result=fetch_pdf(context,row,tmp_path/'out',tmp_path/'original',rename_from_title=True)
    assert result['original_filename']=='98765.pdf'
    assert result['saved_filename']=='98765.pdf'
    assert result['title_method']=='disabled'
    state=UpdateState(tmp_path/'out/.kurashi-downloader/web-updates.json')
    from datetime import date
    state.downloaded([{**result,'id':row['id'],'fingerprint':row['fingerprint']}],date.today())
    saved=UpdateState(state.path)
    assert saved.data['downloads'][row['id']]['fingerprint']==row['fingerprint']
    assert saved.data['download_history'][0]['original_filename']=='98765.pdf'

def test_title_failure_preserves_original_name(tmp_path, monkeypatch):
    import pdf_title
    monkeypatch.setattr(pdf_title,'extract_title', lambda p: ('','fallback','unreadable'))
    context=MagicMock(); response=context.request.get.return_value
    response.status=200; response.ok=True
    response.headers={'content-disposition':'attachment; filename="98765.pdf"'}
    response.body.return_value=b'%PDF-fixture'
    result=fetch_pdf(context,parse_listing(direct_listing())[0],tmp_path/'out',tmp_path/'original',rename_from_title=True)
    assert result['saved_filename']=='98765.pdf'
    assert result['title_note']==''
    assert result['title_method']=='disabled'
