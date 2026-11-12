"""Validate a World Notes request and stage one atomic data publication."""
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'


def validate(payload):
    if payload.get('schemaVersion') != 1:
        raise ValueError('unsupported schemaVersion')
    report_date = payload.get('reportDate', '')
    date.fromisoformat(report_date)
    if report_date != datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat():
        raise ValueError('reportDate must be today in Shanghai')
    items = payload.get('items')
    if not isinstance(items, list) or len(items) != 5:
        raise ValueError('publish exactly five items')
    ids = set()
    for item in items:
        for field in ('id', 'title', 'body', 'location', 'materialDate', 'evidenceType', 'category'):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f'missing {field}')
        if not re.fullmatch(r'[A-Za-z0-9._-]+', item['id']) or item['id'] in ids:
            raise ValueError('invalid or duplicate item ID')
        ids.add(item['id'])
        if item['category'] not in ('数据', '规则', '报道', '个体'):
            raise ValueError('unknown category')
        if not re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?', item['materialDate']):
            raise ValueError('invalid materialDate')
        date.fromisoformat(item['materialDate'] if len(item['materialDate']) == 10 else item['materialDate'] + '-01')
        if not isinstance(item.get('sources'), list) or not item['sources']:
            raise ValueError('source required')
        for source in item['sources']:
            for field in ('publisher', 'url', 'evidence'):
                if not isinstance(source.get(field), str) or not source[field].strip():
                    raise ValueError(f'source {field} required')
            url = urlsplit(source['url'])
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError('invalid source URL')
    return report_date


def main():
    request = json.loads((DATA / 'world-notes-publish-request.json').read_text())
    request_id = request.get('requestId', '')
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9._-]+', request_id):
        raise ValueError('invalid requestId')
    payload = request['payload']
    report_date = payload.get('reportDate', '')
    date.fromisoformat(report_date)
    archive = DATA / 'world-notes/archive' / f'{report_date}.json'
    if archive.exists():
        existing = json.loads(archive.read_text())
        if existing.get('requestId') == request_id and existing.get('items') == payload['items']:
            print('Already published this request')
            return
        raise ValueError('daily archive already exists')
    validate(payload)
    current_path = DATA / 'world-notes.json'
    if current_path.exists() and json.loads(current_path.read_text())['reportDate'] > report_date:
        raise ValueError('cannot replace newer edition')
    # Catch repeated stories even when a new item ID was assigned.
    for path in (DATA / 'world-notes/archive').glob('*.json'):
        previous = json.loads(path.read_text())
        if (date.fromisoformat(report_date) - date.fromisoformat(previous['reportDate'])).days > 14:
            continue
        for old in previous['items']:
            for item in payload['items']:
                if old['id'] == item['id'] or old['title'] == item['title']:
                    raise ValueError('recent item already published')
    payload['requestId'] = request_id
    payload['publishedAt'] = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    payload.pop('initialEdition', None)
    archive.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
    archive.write_text(text)
    current_path.write_text(text)
    dates = sorted((path.stem for path in archive.parent.glob('*.json')), reverse=True)
    (DATA / 'world-notes/index.json').write_text(json.dumps({'dates': dates}, indent=2) + '\n')
    print(f'Published {report_date} / {request_id}')


if __name__ == '__main__':
    main()
