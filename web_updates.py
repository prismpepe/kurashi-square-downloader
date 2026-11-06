"""No network operations here: scheduling, change detection and safe file storage."""
import calendar
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from urllib.parse import urljoin, urlsplit

SITE_URL = 'https://www.kurashi-s.jp/GA-M61-031.action?viewFlg=true'
MODES = {'month_start', 'month_end', 'both', 'manual', 'after_download_month'}


def month_after(day):
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def latest_slot(today, mode):
    if mode not in MODES:
        raise ValueError('更新確認の予定が不正です')
    if mode == 'manual':
        return None
    first = today.replace(day=1)
    last = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    candidates = []
    if mode in {'month_start', 'both'}:
        candidates.append(first)
    if mode in {'month_end', 'both'}:
        candidates.append(last if today == last else first - timedelta(days=1))
    return max(candidates).isoformat()


def fingerprint(item):
    return hashlib.sha256(json.dumps([item['title'], item['updated'], item['size']],
                                    ensure_ascii=False).encode()).hexdigest()


def parse_listing(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    root = soup.select_one('#handoutFolders')
    if root is None:
        if soup.select_one('input[type="password"]'):
            raise PermissionError('更新確認にはログインが必要です')
        raise ValueError('組合資料の一覧を読み取れません。サイトの画面変更を確認してください')
    rows = []
    keys = set()
    for link in root.select('a[href]'):
        href = link.get('href', '')
        if not re.search(r'!EV_GA_M61_031_\d+\.action(?:\?|$)', href):
            continue
        url = urljoin(SITE_URL, href)
        if urlsplit(url).scheme != 'https' or urlsplit(url).netloc != 'www.kurashi-s.jp':
            raise ValueError('対象サイト外の文書リンクを拒否しました')
        title = link.get_text(' ', strip=True)
        # Regulations are a direct manageFolder document, without a submenu.
        # Keep the same row boundary for metadata so folder actions cannot
        # inherit timestamps from nested documents.
        item = link.find_parent(class_=re.compile(r'^(?:fl\d+Item|manageFolder)$'))
        if item is None:
            # Navigation links outside document rows are not downloads.
            continue
        # Folder rows may contain many nested file rows. Do not attribute their
        # descendant status elements to the folder's own action link.
        status = next((s for s in item.select('.fileStatus')
                       if s.find_parent(class_=re.compile(r'^(?:fl\d+Item|manageFolder)$')) is item), None)
        if status is None:
            continue
        details = status.get_text(' ', strip=True)
        updated = re.search(r'更新日時[：:]\s*(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})', details)
        size = re.search(r'サイズ[：:]\s*([\d.,]+\s*[KMG]?B)', details, re.I)
        if not updated or not size:
            raise ValueError('更新日時・サイズの書式が変わっています')
        folders = []
        for ancestor in link.parents:
            if ancestor is root:
                break
            heading = ancestor.find('div', class_=re.compile(r'^(currentFolder|l\dFolder)$'), recursive=False)
            if heading:
                folders.append(heading.get_text(' ', strip=True))
        folders.reverse()
        category = folders[0] if folders else title
        subfolders = folders[1:]
        identity = [category, *subfolders, title]
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        if key in keys:
            raise ValueError('同じ名前の文書が同じフォルダに複数あります。識別方法の確認が必要です')
        keys.add(key)
        period = next((x for x in subfolders if re.fullmatch(r'\d{6}', x)), None)
        if period is None:
            match = re.search(r'(\d{4})年(\d{1,2})月', title)
            period = f'{match[1]}{int(match[2]):02d}' if match else updated[1][:7].replace('/', '')
        row = {'id': key, 'title': title, 'category': category, 'folders': subfolders,
               'period': period, 'updated': updated[1], 'size': size[1], 'url': url}
        row['fingerprint'] = fingerprint(row)
        rows.append(row)
    if not rows:
        raise ValueError('文書が0件のため前回結果を維持します。ログイン・権限・画面を確認してください')
    return rows


class UpdateState:
    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {
            'schedule': 'after_download_month', 'last_attempt_slot': None, 'last_checked': None,
            'last_download_date': None, 'last_attempt_date': None,
            'items': {}, 'noticed': {}, 'downloads': {}, 'message': '未確認', 'error': ''}
        self.data.setdefault('last_download_date', None)
        self.data.setdefault('last_attempt_date', None)
        if self.data['schedule'] in {'month_start', 'month_end', 'both'}:
            self.data['schedule'] = 'after_download_month'

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), 'utf-8')
        temporary.replace(self.path)

    def due(self, today):
        if self.data['schedule'] == 'after_download_month':
            anchors = [date.fromisoformat(self.data[key]) for key in ('last_download_date', 'last_attempt_date') if self.data[key]]
            return not anchors or today >= max(month_after(day) for day in anchors)
        slot = latest_slot(today, self.data['schedule'])
        return slot is not None and (not self.data['last_attempt_slot'] or slot > self.data['last_attempt_slot'])

    def attempt(self, today):
        self.data['last_attempt_date'] = today.isoformat()
        if self.data['schedule'] == 'after_download_month':
            self.save()
            return
        slot = latest_slot(today, self.data['schedule'])
        if slot:
            self.data['last_attempt_slot'] = slot
        self.save()

    def downloaded(self, results, today):
        successes = [row for row in results if row['status'] in {'保存', '重複スキップ'}]
        for row in successes:
            row = {**row, 'downloaded_at': datetime.now().isoformat(timespec='seconds')}
            self.data.setdefault('download_history', []).append(row)
            self.data['downloads'][row['id']] = row
        if successes:
            self.data['last_download_date'] = today.isoformat()
        self.save()

    def apply(self, rows):
        initial = self.data['last_checked'] is None
        previous = self.data['items']
        items = {}
        notify = []
        for row in rows:
            old = previous.get(row['id'])
            row = dict(row)
            row['change'] = ('新規' if not old else '更新') if not old or old['fingerprint'] != row['fingerprint'] else old.get('change', '')
            items[row['id']] = row
            if initial:
                self.data['noticed'][row['id']] = row['fingerprint']
            elif self.data['noticed'].get(row['id']) != row['fingerprint']:
                notify.append(row['id'])
        self.data.update(items=items, last_checked=datetime.now().isoformat(timespec='seconds'), error='',
                         message=f'確認完了: {len(rows)}件 / 新しい通知 {len(notify)}件')
        if initial:
            self.data['message'] = f'初回の基準一覧を記録しました: {len(rows)}件。必要な文書を選択して取得できます'
        self.save()
        return notify

    def acknowledge(self, ids):
        for key in ids:
            self.data['noticed'][key] = self.data['items'][key]['fingerprint']
        self.save()

    def failed(self, error):
        self.data['error'] = str(error)
        self.data['message'] = '確認できませんでした。ログイン・接続状態を確認して手動で再試行してください'
        self.save()


def safe_component(value):
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip(' .')[:100]
    if not cleaned or cleaned.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]}:
        cleaned = '_' + (cleaned or '無題')
    return cleaned


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def store_download(source, filename, item, downloads_root, originals_root, *, unified=False):
    root, originals = Path(downloads_root).resolve(), Path(originals_root).resolve()
    if not (unified and root == originals) and (root == originals or root.is_relative_to(originals) or originals.is_relative_to(root)):
        raise ValueError('Web取得先と元本フォルダは別の場所にしてください')
    # This site currently exposes PDFs. Fail closed instead of saving a login HTML as a document.
    with Path(source).open('rb') as stream:
        if stream.read(5) != b'%PDF-':
            raise ValueError('取得内容がPDFではありません。ログイン状態を確認してください')
    digest = sha256(source)
    folder = root / safe_component(item['category']) / safe_component(item['period'])
    if not folder.resolve().is_relative_to(root):
        raise ValueError('保存先がWeb取得フォルダの外にあります')
    folder.mkdir(parents=True, exist_ok=True)
    filename = safe_component(filename)
    if not filename.lower().endswith('.pdf'):
        filename += '.pdf'
    for existing in folder.glob('*.pdf'):
        if existing.is_file() and not existing.is_symlink() and sha256(existing) == digest:
            return {'path': str(existing), 'sha256': digest, 'status': '重複スキップ'}
    target = folder / filename
    if target.exists():
        target = folder / f'{Path(filename).stem}_{digest[:12]}.pdf'
    if target.exists():
        raise FileExistsError('別名の保存先も使用されています')
    temporary = folder / ('.download-' + os.urandom(12).hex())
    try:
        shutil.copyfile(source, temporary)
        # Windows rename is atomic and rejects an existing destination.
        if os.name == 'nt':
            os.rename(temporary, target)
        else:
            os.link(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {'path': str(target), 'sha256': digest, 'status': '保存'}
