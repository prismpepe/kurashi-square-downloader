import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_connector import KurashiClient
from test_web_updates import listing
import pytest


def install_fake_browser(monkeypatch, html):
    page = MagicMock()
    page.content.return_value = html
    page.is_closed.return_value = False
    page.locator.return_value.count.return_value = 1
    context = MagicMock()
    context.pages = [page]
    context.cookies.return_value = []
    manager = MagicMock()
    manager.__enter__.return_value.chromium.launch_persistent_context.return_value = context
    module = SimpleNamespace(sync_playwright=lambda: manager)
    monkeypatch.setitem(sys.modules, 'playwright', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', module)
    return page, context, manager


def test_check_never_downloads(monkeypatch, tmp_path):
    page, context, manager = install_fake_browser(monkeypatch, listing())
    result = KurashiClient(tmp_path / 'state', tmp_path / 'web', tmp_path / 'originals').run('check')
    assert len(result['rows']) == 1
    page.expect_download.assert_not_called()
    page.locator.return_value.click.assert_not_called()
    assert not (tmp_path / 'web').exists()
    options = manager.__enter__.return_value.chromium.launch_persistent_context.call_args.kwargs
    assert options['accept_downloads'] is False
    context.close.assert_called_once()


def test_stale_selection_never_downloads(monkeypatch, tmp_path):
    from web_updates import parse_listing
    page, context, _ = install_fake_browser(monkeypatch, listing(updated='2026/10/25 03:33'))
    selected = parse_listing(listing())
    result = KurashiClient(tmp_path / 'state', tmp_path / 'web', tmp_path / 'originals').run('download', selected)
    assert result['results'][0]['status'] == '失敗'
    page.expect_download.assert_not_called()
    assert not (tmp_path / 'web').exists()


def test_cleanup_failure_preserves_check_result(monkeypatch, tmp_path):
    page, context, _ = install_fake_browser(monkeypatch, listing())
    context.cookies.side_effect = RuntimeError('Target closed')
    context.close.side_effect = RuntimeError('Target closed')
    result = KurashiClient(tmp_path/'state',tmp_path/'web',tmp_path/'originals').run('check')
    assert len(result['rows']) == 1


def test_browser_closed_reports_all_unprocessed_documents(monkeypatch, tmp_path):
    from web_updates import parse_listing
    page, context, _ = install_fake_browser(monkeypatch, listing())
    page.is_closed.return_value = True
    context.cookies.side_effect = RuntimeError('Target closed')
    result = KurashiClient(tmp_path/'state',tmp_path/'web',tmp_path/'originals').run('download',parse_listing(listing()))
    assert len(result['results']) == 1
    assert result['results'][0]['status'] == '失敗'
    page.expect_download.assert_not_called()


def test_session_request_saves_pdf_without_browser_download(tmp_path):
    from web_connector import fetch_pdf
    from web_updates import parse_listing
    context = MagicMock()
    response = context.request.get.return_value
    response.status = 200
    response.ok = True
    response.headers = {'content-disposition': 'attachment; filename="minutes.pdf"'}
    response.body.return_value = b'%PDF-1.7\nfixture'
    row = parse_listing(listing())[0]
    result = fetch_pdf(context, row, tmp_path/'web', tmp_path/'originals')
    assert Path(result['path']).read_bytes() == b'%PDF-1.7\nfixture'
    assert context.request.get.call_args.kwargs['max_redirects'] == 0
    response.dispose.assert_called_once()


@pytest.mark.parametrize('status,body', [(302,b''),(200,b'<html>login</html>'),(403,b'forbidden')])
def test_session_request_rejects_non_pdf(tmp_path,status,body):
    from web_connector import fetch_pdf
    from web_updates import parse_listing
    context=MagicMock(); response=context.request.get.return_value
    response.status=status;response.ok=status==200;response.body.return_value=body
    with pytest.raises((ValueError,PermissionError,RuntimeError)):
        fetch_pdf(context,parse_listing(listing())[0],tmp_path/'web',tmp_path/'originals')
    assert not (tmp_path/'web').exists()
    response.dispose.assert_called_once()
