"""World Notes editions must publish five verified items atomically."""
import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('world_notes', ROOT / 'scripts/publish_world_notes.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class WorldNotesPublicationTests(unittest.TestCase):
    def setUp(self):
        today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
        self.payload = {
            'schemaVersion': 1, 'reportDate': today,
            'items': [dict(id=f'item-{i}', title=f'Title {i}', body='Body', location='Place',
                           materialDate=today, evidenceType='Interview', category='报道',
                           image=dict(url='https://example.com/photo.jpg', sourceUrl='https://example.com/article',
                                      alt='Photo description', credit='Photographer', caption='Photo caption'),
                           sources=[dict(publisher='Publisher', url='https://example.com/article',
                                         evidence='Verified paragraph')]) for i in range(5)],
        }

    def test_accepts_five_and_rejects_partial_or_oversized_editions(self):
        self.assertEqual(publisher.validate(self.payload), self.payload['reportDate'])
        for count in (0, 1, 2, 3, 4, 6):
            payload = copy.deepcopy(self.payload)
            payload['items'] = (payload['items'] * 2)[:count]
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, 'exactly five'):
                publisher.validate(payload)

    def test_partial_request_preserves_current_archive_and_index(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / 'world-notes/archive').mkdir(parents=True)
            files = {
                'world-notes.json': '{"reportDate":"2026-01-01","items":[]}',
                'world-notes/index.json': '{"dates":["2026-01-01"]}',
                'world-notes/archive/2026-01-01.json': '{"reportDate":"2026-01-01","items":[]}',
            }
            for name, content in files.items():
                (data / name).write_text(content)
            self.payload['items'] = self.payload['items'][:2]
            (data / 'world-notes-publish-request.json').write_text(json.dumps({
                'requestId': 'partial-request', 'payload': self.payload}))
            with patch.object(publisher, 'DATA', data), self.assertRaisesRegex(ValueError, 'exactly five'):
                publisher.main()
            for name, content in files.items():
                self.assertEqual((data / name).read_text(), content)
            self.assertEqual(len(list((data / 'world-notes/archive').glob('*.json'))), 1)

    def test_rejects_missing_images_and_unsafe_image_links(self):
        for field in ('url', 'sourceUrl', 'alt', 'credit', 'caption'):
            payload = copy.deepcopy(self.payload)
            del payload['items'][0]['image'][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                publisher.validate(payload)
        for field in ('url', 'sourceUrl'):
            for url in ('javascript:alert(1)', 'http://example.com/p.jpg', 'https://user:pass@example.com/p.jpg'):
                payload = copy.deepcopy(self.payload)
                payload['items'][0]['image'][field] = url
                with self.subTest(field=field, url=url), self.assertRaises(ValueError):
                    publisher.validate(payload)
        del self.payload['items'][0]['image']
        with self.assertRaisesRegex(ValueError, 'image required'):
            publisher.validate(self.payload)

    def test_full_edition_is_atomic_and_repeat_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / 'world-notes/archive').mkdir(parents=True)
            (data / 'world-notes-publish-request.json').write_text(json.dumps({
                'requestId': 'five-items-request', 'payload': self.payload}))
            with patch.object(publisher, 'DATA', data):
                publisher.main()
                current = (data / 'world-notes.json').read_text()
                archive = data / 'world-notes/archive' / f'{self.payload["reportDate"]}.json'
                self.assertEqual(current, archive.read_text())
                self.assertEqual(len(json.loads(current)['items']), 5)
                publisher.main()
                self.assertEqual(current, (data / 'world-notes.json').read_text())
                self.assertEqual(json.loads((data / 'world-notes/index.json').read_text())['dates'],
                                 [self.payload['reportDate']])


if __name__ == '__main__':
    unittest.main()
