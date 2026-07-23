"""Dedicated tests for crawler payload record extraction."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.crawler import _records_from_payload


class PayloadRecordTests(unittest.TestCase):
    def test_list_of_dicts(self) -> None:
        records = [{"name": "黄瓜"}, {"name": "白菜"}]

        self.assertEqual(_records_from_payload(records), records)

    def test_dict_with_list_key(self) -> None:
        records = [{"name": "黄瓜"}]

        self.assertEqual(_records_from_payload({"list": records}), records)

    def test_dict_with_rows_key(self) -> None:
        records = [{"name": "白菜"}]

        self.assertEqual(_records_from_payload({"rows": records}), records)

    def test_dict_with_records_key(self) -> None:
        records = [{"name": "土豆"}]

        self.assertEqual(_records_from_payload({"records": records}), records)

    def test_dict_with_data_key(self) -> None:
        records = [{"name": "豌豆"}]

        self.assertEqual(
            _records_from_payload({"data": {"list": records}}),
            records,
        )

    def test_empty_input(self) -> None:
        for payload in ([], {}, {"list": []}):
            with self.subTest(payload=payload):
                self.assertEqual(_records_from_payload(payload), [])

    def test_non_dict_items_filtered(self) -> None:
        payload = [{"a": 1}, "string", 123]

        self.assertEqual(_records_from_payload(payload), [{"a": 1}])

    def test_none_input(self) -> None:
        self.assertEqual(_records_from_payload(None), [])


if __name__ == "__main__":
    unittest.main()
