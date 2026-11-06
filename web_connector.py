"""Site adapter for the Windows application; never downloads during check/login."""
from pathlib import Path
import json
import tempfile
import time
import logging
import re
from email.message import Message
from urllib.parse import urlsplit

if __package__:
    from .web_updates import SITE_URL, parse_listing, store_download
else:
    from web_updates import SITE_URL, parse_listing, store_download

if __package__:
    from .operations import Cancelled, check_cancel
    from .credentials import autofill
else:
    from operations import Cancelled, check_cancel
    from credentials import autofill

log = logging.getLogger(__name__)


class LoginRequired(PermissionError):
    pass


def public_error(error):
    # Playwright call logs include Cookie headers. Never persist or display them.
    text = str(error).split('Call log:', 1)[0].strip()
    text = re.sub(r'(?im)^.*(?:cookie|authorization|password|JSESSIONID)\s*[:=].*$', '[認証情報は非表示]', text)
    return text[:800] or '通信処理に失敗しました'


def pause(seconds, cancel=None):
    if cancel is not None:
        if cancel.wait(seconds):
            check_cancel(cancel)
    else:
        time.sleep(seconds)


def request_pdf(context, url, cancel=None):
    for attempt in range(3):
        check_cancel(cancel)
        try:
            response = context.request.get(url, headers={'Referer': SITE_URL}, timeout=60000, max_redirects=0)
        except Exception as error:
            check_cancel(cancel)
            if type(error).__name__ != 'TimeoutError' and not any(word in str(error) for word in ('Timeout', 'ECONNRESET', 'ETIMEDOUT', 'socket hang up')):
                raise RuntimeError(public_error(error)) from None
            if attempt == 2:
                raise TimeoutError('文書取得がタイムアウトしました（待ち時間60秒・最大3回試行）。時間を置いて未取得分を再試行してください') from None
            pause(2 * (attempt + 1), cancel)
            continue
        if response.status in {429, 502, 503, 504} and attempt < 2:
            response.dispose()
            pause(2 * (attempt + 1), cancel)
            continue
        return response


def fetch_pdf(context, row, download_root, original_root, *, unified=False, rename_from_title=False, cancel=None):
    """Use the authenticated session without a browser download/popup lifecycle."""
    check_cancel(cancel)
    url = row['url']
    if urlsplit(url).scheme != 'https' or urlsplit(url).netloc != 'www.kurashi-s.jp':
        raise ValueError('対象サイト外の取得先を拒否しました')
    response = request_pdf(context, url, cancel)
    try:
        if 300 <= response.status < 400:
            raise PermissionError('取得先が別画面へ転送されました。ログイン状態またはサイトの取得方式を確認してください')
        if not response.ok:
            raise RuntimeError(f'文書取得HTTPエラー: {response.status}')
        check_cancel(cancel)
        body = response.body()
        if not body.startswith(b'%PDF-'):
            raise ValueError('取得結果がPDFではありません。ログイン状態またはリンクの種類を確認してください')
        header = Message()
        header['Content-Disposition'] = response.headers.get('content-disposition', '')
        filename = header.get_filename() or (row['title'] + '.pdf')
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'document.pdf'
            source.write_bytes(body)
            naming = {'original_filename': filename, 'extracted_title': '',
                      'title_method': 'disabled', 'title_note': ''}
            saved_name = filename
            check_cancel(cancel)
            result = store_download(source, saved_name, row, download_root, original_root,
                                    unified=unified)
            return {**result, **naming, 'saved_filename': Path(result['path']).name,
                    'category': row['category'], 'site_title': row['title'],
                    'site_updated': row['updated'], 'site_size': row['size']}
    finally:
        response.dispose()


def finish_context(context, cookies_path, authenticated):
    """Cleanup must not replace successful downloads or the original exception."""
    if authenticated:
        try:
            cookies = [cookie for cookie in context.cookies()
                       if cookie['domain'].lstrip('.') in {'www.kurashi-s.jp', 'kurashi-s.jp'}]
            temporary = cookies_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(cookies), 'utf-8')
            temporary.replace(cookies_path)
        except Exception:
            log.warning('Web session save failed; previous saved session retained')
    try:
        context.close()
    except Exception:
        log.warning('Web browser already closed during cleanup')


class KurashiClient:
    def __init__(self, data_dir, download_root, original_root, *, unified=False, management_dir=None, rename_from_title=False):
        self.rename_from_title = rename_from_title
        self.management_dir = Path(management_dir or data_dir)
        self.management_dir.mkdir(parents=True, exist_ok=True)
        self.unified = unified
        self.data_dir = Path(data_dir)
        self.download_root = Path(download_root)
        self.original_root = Path(original_root)

    def run(self, action, selected=(), progress=lambda message: None, cancel=None):
        try:
            return self._run(action, selected, progress, cancel)
        except LoginRequired:
            check_cancel(cancel)
            progress('ログインを確認しています。入力が必要な場合はEdgeが開きます')
            result = self._run('interactive_check', (), progress, cancel)
            if action == 'check':
                return result
            return self._run(action, selected, progress, cancel)

    def _run(self, action, selected=(), progress=lambda message: None, cancel=None):
        check_cancel(cancel)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise RuntimeError('setup.cmdを再実行してWeb取得用ライブラリを導入してください') from error
        if action not in {'login', 'check', 'download', 'interactive_check'}:
            raise ValueError('不明な操作です')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # Separate Edge profile. Do not read the user's normal browser profile or Codex cookies.
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(self.data_dir / 'web-profile'), channel='msedge',
                headless=action not in {'login', 'interactive_check'}, accept_downloads=action == 'download',
                chromium_sandbox=True, timeout=20000)
            authenticated = False
            try:
                cookies_path = self.data_dir / 'web-session.json'
                if cookies_path.exists():
                    context.add_cookies(json.loads(cookies_path.read_text('utf-8')))
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(20000)
                page.goto(SITE_URL, wait_until='domcontentloaded', timeout=20000)
                check_cancel(cancel)
                if action in {'login', 'interactive_check'} and not page.locator('#handoutFolders').count():
                    progress('Edgeでログインしてください。完了すると画面を閉じます。ファイルは取得しません')
                    try:
                        if autofill(page, self.data_dir / 'login-credentials.json', submit=True):
                            progress('保存済みのログイン情報でログインしています')
                    except ValueError:
                        progress('ログイン情報ファイルを読み取れません。Edgeで手動入力してください')
                    deadline = time.monotonic() + 600
                    while time.monotonic() < deadline:
                        check_cancel(cancel)
                        if page.is_closed():
                            raise RuntimeError('ログイン画面が閉じられました')
                        if page.get_by_role('link', name='ログアウト', exact=True).count():
                            # Navigate only after interactive login has completed.
                            page.goto(SITE_URL, wait_until='domcontentloaded')
                            if page.locator('#handoutFolders').count():
                                authenticated = True
                                break
                        page.wait_for_timeout(500)
                    if not authenticated:
                        raise TimeoutError('ログイン待ち時間を超えました。サイト文書一覧を選び直してください')
                if not page.locator('#handoutFolders').count():
                    raise LoginRequired('ログインが必要です')
                authenticated = True
                html = page.content()
                # Keep an inventory even on success: a partial parse must be diagnosable.
                from bs4 import BeautifulSoup
                from urllib.parse import urlsplit
                inventory_root = BeautifulSoup(html, 'html.parser').select_one('#handoutFolders')
                inventory = []
                if inventory_root:
                    for link in inventory_root.select('a[href]'):
                        if '!EV_GA_M61_031_' in link['href']:
                            inventory.append({'action': urlsplit(link['href']).path,
                                              'parents': [{'tag': p.name, 'classes': p.get('class', [])}
                                                          for p in list(link.parents)[:5]]})
                (self.management_dir / 'web-listing-structure.json').write_text(
                    json.dumps(inventory, ensure_ascii=False, indent=2), 'utf-8')
                try:
                    rows = parse_listing(html)
                except ValueError as error:
                    # Structural diagnostics only: no document text, query parameters or cookies.
                    from bs4 import BeautifulSoup
                    from urllib.parse import urlsplit
                    root = BeautifulSoup(html, 'html.parser').select_one('#handoutFolders')
                    details = []
                    if root:
                        for link in root.select('a[href]'):
                            if '!EV_GA_M61_031_' in link['href']:
                                details.append({'action': urlsplit(link['href']).path,
                                                'parents': [{'tag': p.name, 'classes': p.get('class', [])}
                                                            for p in list(link.parents)[:5]]})
                    diagnostic = self.management_dir / 'web-listing-structure.json'
                    diagnostic.write_text(json.dumps(details, ensure_ascii=False, indent=2), 'utf-8')
                    raise ValueError(f'{error}。診断情報: {diagnostic}') from error
                check_cancel(cancel)
                if action in {'check', 'interactive_check', 'login'}:
                    return {'action': 'check', 'rows': rows}
                # Refresh the listing and resolve stable identities. URLs contain mutable indices.
                current = {row['id']: row for row in rows}
                results = []
                for index, chosen in enumerate(selected):
                    if cancel is not None and cancel.is_set():
                        break
                    if page.is_closed():
                        results.extend({'id': remaining['id'], 'status': '失敗',
                                        'error': '取得途中で専用Edgeが終了しました。取得済みの文書は保持しています。再試行してください。'}
                                       for remaining in selected[index:])
                        break
                    row = current.get(chosen['id'])
                    if not row or row['fingerprint'] != chosen['fingerprint']:
                        results.append({'id': chosen['id'], 'status': '失敗',
                                        'error': '選択後に一覧が変更されました。更新確認して選択し直してください'})
                        continue
                    progress({'message': '取得中: ' + row['category'] + ' / ' + row['title'], 'current': index, 'total': len(selected)})
                    try:
                        # Folder expansion only; never click arbitrary external/navigation links.
                        for label in [row['category'], *row['folders']]:
                            for folder in page.locator('#handoutFolders .currentFolder, #handoutFolders .l2Folder').all():
                                if folder.inner_text().strip() == label and 'active' not in (folder.get_attribute('class') or '').split():
                                    if folder.is_visible():
                                        folder.locator('a').click()
                        link = page.locator('#handoutFolders a').filter(has_text=row['title'])
                        matches = [candidate for candidate in link.all()
                                   if candidate.get_attribute('href') == row['url'].replace('https://www.kurashi-s.jp', '')
                                   or candidate.get_attribute('href') == row['url']]
                        if len(matches) != 1:
                            raise ValueError('文書リンクを一意に特定できません')
                        if index:
                            pause(1, cancel)
                        result = fetch_pdf(context, row, self.download_root, self.original_root, unified=self.unified, cancel=cancel)
                        results.append({'id': row['id'], 'fingerprint': row['fingerprint'], **result})
                    except Cancelled:
                        break
                    except Exception as error:
                        if cancel is not None and cancel.is_set():
                            break
                        results.append({'id': row['id'], 'status': '失敗', 'error': public_error(error)})
                    # Preserve incremental results even if later documents fail.
                    progress({'message': '取得結果を保存しています', 'current': index + 1, 'total': len(selected)})
                    checkpoint = self.management_dir / 'web-download-results.json'
                    temporary = checkpoint.with_suffix('.tmp')
                    temporary.write_text(json.dumps(results, ensure_ascii=False, indent=2), 'utf-8')
                    temporary.replace(checkpoint)
                return {'action': 'download', 'results': results, 'cancelled': cancel is not None and cancel.is_set()}
            finally:
                finish_context(context, cookies_path, authenticated)
