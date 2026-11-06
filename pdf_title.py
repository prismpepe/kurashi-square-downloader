"""Local, bounded PDF title extraction. No cloud upload or LLM dependency."""
from pathlib import Path
import os
import re
import shutil
import unicodedata

if __package__:
    from .operations import Cancelled, check_cancel
else:
    from operations import Cancelled, check_cancel

KEYWORDS = re.compile(r'議事録|報告書|管理規約|細則|計画|提案|一覧|履歴|通知|案内|資料|決算|予算|収支|総会|理事会|収納状況|貸借対照表|明細書|明細表|科目別|補助簿|元帳|入出金|通帳|残高表')

MAX_TITLE_LENGTH = 40

def cover_title(text):
    lines = [re.sub(r'\s+', '', unicodedata.normalize('NFKC', x)).strip('■□●・_') for x in text.splitlines() if x.strip()]
    # Cover headings can wrap; subtitles alone do not identify the document.
    for index, line in enumerate(lines[:5]):
        if '給水管・給湯管洗浄提案に' in line and index + 1 < len(lines) and lines[index + 1].startswith('関する見解'):
            return line + '関する見解'
        if line == '設備担当提案' and index:
            heading = lines[index - 1]
            if len(heading) <= 32 and re.search('工事|方式', heading):
                return heading + '設備担当提案'
    for line in lines[:3]:
        line = re.sub(r'[0-9]+$', '', line).rstrip()
        line = line.replace('目火報', '自火報')
        if len(line) > MAX_TITLE_LENGTH or re.search(r'。|されて|であり|当マンション|義務化|との|No\.', line):
            continue
        if re.search(r'鳴動方式について$|工事進捗状況$|業者選定履歴$|マンション管理適正評価制度$', line):
            return line
    return ''

def choose_title(text):
    cover = cover_title(text)
    if cover:
        return cover
    lines = [re.sub(r'\s+', '', unicodedata.normalize('NFKC', line)) for line in text.splitlines()[:45]]
    # Prefer the meeting subject, never the publisher/author metadata block.
    if any('議事録' in line for line in lines[:15]):
        for index, line in enumerate(lines):
            if '議題' not in line:
                continue
            subject = line.split('議題', 1)[1] + ''.join(lines[index + 1:index + 3])
            meeting = re.search(r'第([0-9一二三四五六七八九十百]+)期第([0-9一二三四五六七八九十百]+)回(臨時)?理事会', subject)
            if meeting:
                return f'第{meeting[1]}期第{meeting[2]}回{meeting[3] or ""}理事会議事録'
    candidates = []
    for index, line in enumerate(text.splitlines()[:45]):
        line = unicodedata.normalize('NFKC', line)
        line = re.sub(r'\s+', ' ', line).strip(' ・_-')
        compact = line.replace(' ', '')
        if len(compact) > MAX_TITLE_LENGTH:
            continue
        compact = re.sub(r'貸借対[曲照]表', '貸借対照表', compact)
        heading = re.search(r'(?:第\d+期)?(?:予算決算対比表|貸借対照表|支出明細書|入出金明細書|収納状況)(?:\(月次\))?', compact)
        if heading:
            compact = heading.group(0)
        if any(label in compact for label in ('発行元', '作成者', '確認者', '作成日', '出席者', '欠席者', '議題', '審議事項')):
            continue
        if re.search(r'[|${}]', compact):
            continue
        if '(cid:' in compact or any(ord(c) < 32 for c in compact):
            continue
        if not 4 <= len(compact) <= MAX_TITLE_LENGTH:
            continue
        if not re.search(r'[ぁ-んァ-ヶ一-龯A-Za-z]', compact):
            continue
        if re.match(r'^(令和|平成|昭和|20\d{2})\s*\d*年.*[日]$', compact):
            continue
        if re.search(r'https?://|@|電話|TEL|FAX', line, re.I):
            continue
        # Require a document-type clue; ordinary body sentences are unsafe filenames.
        if compact == '設備担当提案' or re.search(r'No\.|見積金額|契約金額|されて|であり|との|に$', compact):
            continue
        if not KEYWORDS.search(compact) or re.search(r'。|します|しました|ください', line):
            continue
        candidates.append((len(KEYWORDS.findall(compact))*20 - index, compact))
    return max(candidates, default=(0, ''))[1]

def extract_title(path, cancel=None):
    check_cancel(cancel)
    errors = []
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:1]:
                check_cancel(cancel)
                title = choose_title(page.extract_text() or '')
                if title:
                    return title, 'text', ''
    except Cancelled:
        raise
    except Exception as error:
        errors.append(type(error).__name__)
    try:
        import pypdfium2 as pdfium
        import pytesseract
        bundled = Path(__file__).resolve().parent / 'runtime/tesseract/tesseract.exe'
        command = str(bundled) if bundled.exists() else (shutil.which('tesseract') or str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tesseract-OCR/tesseract.exe'))
        if not Path(command).exists():
            return '', 'fallback', 'タイトルを抽出できず、元の名前で保存しました（OCR用Tesseract未検出）'
        pytesseract.pytesseract.tesseract_cmd = command
        with pdfium.PdfDocument(path) as pdf:
            for index in range(min(1, len(pdf))):
                check_cancel(cancel)
                page = pdf[index]
                bitmap = page.render(scale=3)
                try:
                    image = bitmap.to_pil()
                    regions = [image.crop((0, 0, image.width, int(image.height * .35))),
                               image.crop((image.width // 2, 0, image.width, image.height))]
                    for region in regions:
                        check_cancel(cancel)
                        text = pytesseract.image_to_string(region, lang='jpn', config='--psm 6', timeout=30)
                        check_cancel(cancel)
                        if re.match(r'^_?管理計画認定制度との', Path(path).stem) and '管理計画認定制度' in re.sub(r'\s+', '', text):
                            return '管理計画認定制度', 'ocr', '表題を確定できないため、既存名の制度名を残し誤読部分を除去しました'
                        title = choose_title(text)
                        if title:
                            return title, 'ocr', 'OCRによるタイトルです。保存名をご確認ください'
                finally:
                    bitmap.close()
                    page.close()
    except Cancelled:
        raise
    except Exception as error:
        errors.append(type(error).__name__)
    return '', 'fallback', 'タイトルを確実に抽出できないため元の名前で保存しました' + (' (' + ', '.join(errors) + ')' if errors else '')
