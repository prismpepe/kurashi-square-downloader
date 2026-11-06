"""Shared, offline filtering for site and saved document lists."""
from datetime import date
from pathlib import Path
import re
import unicodedata

ALL_CATEGORIES = '全カテゴリー'
ALL_YEARS = '全年度'
UNKNOWN_YEAR = '年度不明'

def fiscal_year(value):
    """Read the displayed 年月 / 期; never substitute a file timestamp."""
    value = unicodedata.normalize('NFKC', str(value or '')).strip()
    explicit = re.search(r'(?<!\d)(\d{4})年度', value)
    if explicit:
        return f'{int(explicit[1])}年度'
    match = re.search(r'(?<!\d)(\d{4})(?:年\s*|[-/]\s*|\s*)(\d{2}|\d)(?:月|(?=\D|$))', value)
    if not match:
        return UNKNOWN_YEAR
    try:
        day = date(int(match[1]), int(match[2]), 1)
    except ValueError:
        return UNKNOWN_YEAR
    return f'{day.year - (day.month < 4)}年度'

def normalize(value):
    return unicodedata.normalize('NFKC', str(value)).casefold()

def matches(row, category, year, query):
    return ((category == ALL_CATEGORIES or row['category'] == category)
            and (year == ALL_YEARS or fiscal_year(row.get('folder')) == year)
            and normalize(query).strip() in normalize(' '.join(str(row.get(key, '')) for key in ('category', 'folder', 'name', 'site_title', 'site_updated'))))

def saved_dates(state):
    dates = {}
    for row in [*state.get('download_history', []), *state.get('downloads', {}).values()]:
        if not row.get('path'):
            continue
        value = row.get('site_updated', '')
        if not value:
            item = state.get('items', {}).get(row.get('id'), {})
            if row.get('fingerprint') and item.get('fingerprint') == row['fingerprint']:
                value = item.get('updated', '')
        if value:
            dates[str(Path(row['path']).resolve())] = value
    return dates
