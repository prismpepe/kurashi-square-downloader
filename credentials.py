"""Fill only the known site's login form; never submit or log credentials."""
import json
from pathlib import Path
from urllib.parse import urlsplit

def load_credentials(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text('utf-8-sig'))
        account, password = value.get('account'), value.get('password')
        if not isinstance(account, str) or not isinstance(password, str):
            raise ValueError()
        if not account or not password:
            return None
        return account, password
    except Exception:
        raise ValueError('ログイン情報ファイルの形式が不正です。account と password を確認してください') from None

def autofill(page, path, submit=False):
    parts = urlsplit(page.url)
    if parts.scheme != 'https' or parts.netloc != 'www.kurashi-s.jp':
        return False
    credentials = load_credentials(path)
    if not credentials:
        return False
    passwords = [field for field in page.locator('input[type="password"]').all() if field.is_visible()]
    if len(passwords) != 1:
        return False
    password = passwords[0]
    form = password.locator('xpath=ancestor::form[1]')
    accounts = [field for field in form.locator('input[type="text"], input[type="email"], input:not([type])').all()
                if field.is_visible() and field.is_enabled()]
    if len(accounts) != 1:
        return False
    try:
        accounts[0].fill(credentials[0])
        password.fill(credentials[1])
        if submit:
            password.press('Enter')
    except Exception:
        # Playwright exceptions can include the fill value: never expose them.
        return False
    return True
