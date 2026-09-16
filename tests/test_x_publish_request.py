import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "read_x_publish_request.py"
SPEC = importlib.util.spec_from_file_location("read_x_publish_request", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class XPublishRequestTests(unittest.TestCase):
    def write_request(self, payload):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "request.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.addCleanup(directory.cleanup)
        return path

    def test_accepts_auditable_backfill_request(self):
        path = self.write_request(
            {
                "schemaVersion": 1,
                "action": "publish_missing_x",
                "asOf": "2026-09-15",
            }
        )
        self.assertEqual(MODULE.requested_as_of(path), "2026-09-15")

    def test_rejects_unknown_action(self):
        path = self.write_request(
            {"schemaVersion": 1, "action": "publish_anything", "asOf": "2026-09-15"}
        )
        with self.assertRaisesRegex(MODULE.RequestError, "action"):
            MODULE.requested_as_of(path)

    def test_rejects_invalid_date(self):
        path = self.write_request(
            {"schemaVersion": 1, "action": "publish_missing_x", "asOf": "2026-09-31"}
        )
        with self.assertRaisesRegex(MODULE.RequestError, "ISO date"):
            MODULE.requested_as_of(path)


if __name__ == "__main__":
    unittest.main()
