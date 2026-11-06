"""Persistent inventory of manually placed files, separate from the live listing."""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
if __package__:
    from .web_updates import sha256, safe_component
    from .pdf_title import extract_title
    from .operations import Cancelled, check_cancel
else:
    from web_updates import sha256, safe_component
    from pdf_title import extract_title
    from operations import Cancelled, check_cancel

EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.md', '.txt'}

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    temp.replace(path)

def site_names(state):
    """Use stored download identities, never guess a match from a filename."""
    candidates = {}
    for row in [*state.get('download_history', []), *state.get('downloads', {}).values()]:
        if not row.get('path'):
            continue
        title = row.get('site_title', '')
        if not title:
            item = state.get('items', {}).get(row.get('id'), {})
            if item.get('fingerprint') == row.get('fingerprint'):
                title = item.get('title', '')
        if title:
            candidates.setdefault(str(Path(row['path']).resolve()), set()).add(title)
    return {path: next(iter(names)) for path, names in candidates.items() if len(names) == 1}


def manual_title(source, value):
    """Validate a user-entered basename; directory and extension stay unchanged."""
    value = value.strip()
    suffix = Path(source).suffix
    if value.lower().endswith(suffix.lower()):
        value = value[:-len(suffix)]
    if not value or len(value) > 100 or safe_component(value) != value:
        raise ValueError('名前は1～100文字で入力してください。末尾の空白・ピリオド、予約名、\\ / : * ? " < > | は使用できません')
    target = Path(source).with_name(value + suffix)
    if target != Path(source) and target.exists():
        raise FileExistsError('同名ファイルが存在します。別の名前を指定してください')
    return value


def scan_local(root, rename=False, cancel=None, progress=lambda message: None, include_downloaded=False, selected_paths=None, manual_names=None):
    root = Path(root).resolve()
    manual_names = {str(Path(p).resolve()): name for p, name in (manual_names or {}).items()}
    selected_set = {str(Path(p).resolve()) for p in selected_paths} if selected_paths is not None else None
    meta = root / '.kurashi-downloader'
    path = meta / 'manual-documents.json'
    data = json.loads(path.read_text('utf-8')) if path.exists() else {'documents': {}}
    records = data['documents']
    # Recover a rename whose disk operation completed before the final journal save.
    for record in records.values():
        pending = record.get('pending_path')
        if pending:
            target = root / pending
            source = root / record['relative_path']
            if target.is_file() and not source.exists() and sha256(target) == record['sha256']:
                record['relative_path'] = pending
                record['saved_filename'] = target.name
            record.pop('pending_path', None)
    state_path = meta / 'web-updates.json'
    state = json.loads(state_path.read_text('utf-8')) if state_path.exists() else {}
    titles = site_names(state)
    web_paths = {str(Path(row['path']).resolve()) for row in state.get('downloads', {}).values() if row.get('path')}
    web_paths.update(str(Path(row['path']).resolve()) for row in state.get('download_history', []) if row.get('path'))
    def sync_web_paths(changed_record=None):
        changed = False
        for record in ([changed_record] if changed_record else records.values()):
            if record.get('source') != 'web' or not record.get('previous_relative_path'):
                continue
            old = str((root / record['previous_relative_path']).resolve())
            target = root / record['relative_path']
            if not target.is_file() or sha256(target) != record['sha256']:
                continue
            for row in [*state.get('downloads', {}).values(), *state.get('download_history', [])]:
                if row.get('path') and str(Path(row['path']).resolve()) == old:
                    row.setdefault('original_filename', Path(row['path']).name)
                    row.update(path=str(target), saved_filename=target.name, extracted_title=record['extracted_title'], title_method=record['title_method'])
                    changed = True
        if changed:
            save(state_path, state)
    sync_web_paths()
    processed = 0
    errors = []
    cancelled = False
    try:
        progress('対象ファイルを数えています')
        files = []
        for candidate in root.rglob('*'):
            check_cancel(cancel)
            if selected_set is not None and str(candidate.resolve()) not in selected_set:
                continue
            if candidate.is_file() and candidate.suffix.lower() in EXTENSIONS and (manual_names or not rename or not include_downloaded or candidate.suffix.lower() == '.pdf') and not any(part.startswith(('.', '~$')) for part in candidate.relative_to(root).parts):
                if include_downloaded or str(candidate.resolve()) not in web_paths:
                    files.append(candidate)
        for index, source in enumerate(files):
            check_cancel(cancel)
            relative = source.relative_to(root)
            if any(part.startswith(('.', '~$')) for part in relative.parts):
                continue
            if source.suffix.lower() not in EXTENSIONS or not source.is_file():
                continue
            if any(parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)() for parent in [source, *source.parents] if parent != root):
                continue
            if not source.resolve().is_relative_to(root) or (not include_downloaded and str(source.resolve()) in web_paths):
                continue
            record_id = next((key for key, value in records.items() if value['relative_path'] == relative.as_posix()), uuid.uuid4().hex)
            previous = records.get(record_id, {})
            progress({'message': '文書を確認中: ' + relative.as_posix(), 'current': index, 'total': len(files)})
            disk_renamed = False
            try:
                digest = sha256(source)
                if not include_downloaded and previous.get('sha256') == digest and (not rename or previous.get('title_method') in {'text', 'ocr'}):
                    previous['missing'] = False
                    continue
                site_title = titles.get(str(source.resolve()), previous.get('site_title', ''))
                title, method, note = '', 'disabled', ''
                if str(source.resolve()) in manual_names:
                    title = manual_title(source, manual_names[str(source.resolve())])
                    method = 'manual'
                    note = '手動で変更したファイル名です'
                elif rename and source.suffix.lower() == '.pdf':
                    title, method, note = extract_title(source, cancel=cancel)
                if rename and not title and site_title:
                    import re
                    title = site_title
                    if not re.search(r'[ぁ-んァ-ヶ一-龯]', title.replace('年', '').replace('月', '').replace('日', '')):
                        category = relative.parts[0] if len(relative.parts) > 1 else ''
                        title = category + title if category else ''
                    method = 'site' if title else 'fallback'
                    note = '本文の表題を取得できないため、掲載名を使用しました' if title else '表題を確定できないため元の名前を維持しました'
                elif rename and not title and source.suffix.lower() != '.pdf':
                    note = '本文タイトルによる改名はPDFのみ対応しています'
                check_cancel(cancel)
                if sha256(source) != digest:
                    raise ValueError('処理中にファイルが変更されました。再登録してください')
                record = {**previous, 'source': 'web' if str(source.resolve()) in web_paths else previous.get('source', 'manual'), 'relative_path': relative.as_posix(),
                          'original_filename': previous.get('original_filename', source.name),
                          'saved_filename': source.name, 'sha256': digest, 'missing': False,
                          'category': relative.parts[0] if len(relative.parts) > 1 else '未分類',
                          'site_title': site_title, 'extracted_title': title, 'title_method': method, 'title_note': note,
                          'registered_at': datetime.now().isoformat(timespec='seconds')}
                records[record_id] = record
                if title:
                    stem = title[:-len(source.suffix)] if title.lower().endswith(source.suffix.lower()) else title
                    target = source.with_name(safe_component(stem) + source.suffix)
                    if target != source:
                        if target.exists() and method == 'manual':
                            raise FileExistsError('同名ファイルが存在します。別の名前を指定してください')
                        if target.exists():
                            target = source.with_name(safe_component(stem) + '_' + digest[:12] + source.suffix)
                        if target != source:
                            if target.exists():
                                record['title_note'] = '同名ファイルが存在するため改名せず登録しました'
                            else:
                                record['previous_relative_path'] = relative.as_posix()
                                record['pending_path'] = target.relative_to(root).as_posix()
                                save(path, data)
                                # Windows rename refuses to overwrite existing files.
                                if os.name == 'nt':
                                    source.rename(target)
                                else:
                                    os.link(source, target)
                                    source.unlink()
                                disk_renamed = True
                                record['name_history'] = list(record.get('name_history', []))
                                record.setdefault('name_history', []).append({'before':source.name, 'after':target.name})
                                record['relative_path'] = record.pop('pending_path')
                                record['saved_filename'] = target.name
                save(path, data)
                sync_web_paths(record)
                progress({'message': '管理データを保存しました', 'current': index + 1, 'total': len(files)})
                processed += 1
            except Cancelled:
                raise
            except Exception as error:
                # A failed disk rename must not commit the proposed name or success note.
                # After a successful disk rename keep the journal for metadata recovery.
                if not disk_renamed:
                    if previous:
                        records[record_id] = previous
                    else:
                        records.pop(record_id, None)
                message = str(error)
                if getattr(error, 'winerror', None) in {32, 33}:
                    message = '文書が別のアプリで使用中のため変更できません。PDFビューアーやエクスプローラーのプレビューを閉じて、再実行してください。'
                errors.append({'path': relative.as_posix(), 'error': message})
    except Cancelled:
        cancelled = True
    for record in records.values():
        record['missing'] = not (root / record['relative_path']).is_file()
    data['errors'] = errors
    data['last_scanned'] = datetime.now().isoformat(timespec='seconds')
    save(path, data)
    return {'action': 'local', 'visited': index + 1 if 'index' in locals() else 0, 'target_count': len(files) if 'files' in locals() else 0, 'count': processed, 'total':len(records), 'errors':errors, 'cancelled':cancelled}
