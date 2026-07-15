"""Batch 2 tests: collection fallback, cleaning, features, and artifacts."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.crawler import CollectionResult, collect_price_data
from src.features import FEATURE_COLUMNS, add_price_features
from src.pipeline import run_data_pipeline
from src.preprocess import NORMALIZED_PRICE_UNIT, STANDARD_COLUMNS, clean_price_data


class DataCleaningTests(unittest.TestCase):
    def test_cleaner_normalizes_fields_aliases_units_and_invalid_rows(self) -> None:
        raw = pd.DataFrame(
            {
                "日期": ["2026-07-01", "2026-07-02", "bad"],
                "品种": ["马铃薯", "黄瓜", "菠菜"],
                "均价": [2.0, "3.5", -1],
                "单位": ["元/斤", "元/kg", "元/kg"],
            }
        )
        cleaned = clean_price_data(raw, source_name="fixture")
        self.assertEqual(list(cleaned.columns), list(STANDARD_COLUMNS))
        self.assertEqual(cleaned["name"].tolist(), ["土豆", "黄瓜"])
        self.assertEqual(cleaned["price"].tolist(), [4.0, 3.5])
        self.assertTrue(cleaned["source"].eq("fixture").all())
        self.assertEqual(cleaned.attrs["price_unit"], NORMALIZED_PRICE_UNIT)

    def test_features_use_coefficient_of_variation(self) -> None:
        cleaned = clean_price_data(
            pd.DataFrame(
                {
                    "date": ["2026-07-01", "2026-07-02"],
                    "name": ["黄瓜", "黄瓜"],
                    "price": [2.0, 4.0],
                    "source": ["fixture", "fixture"],
                }
            )
        )
        featured = add_price_features(cleaned, history_window=30)
        self.assertTrue(set(FEATURE_COLUMNS).issubset(featured.columns))
        self.assertAlmostEqual(featured.iloc[-1]["historical_mean"], 3.0)
        self.assertAlmostEqual(featured.iloc[-1]["volatility"], 1.0 / 3.0)
        self.assertEqual(featured.attrs["price_unit"], NORMALIZED_PRICE_UNIT)


class DataPipelineTests(unittest.TestCase):
    def _fallback_file(self, folder: Path) -> Path:
        path = folder / "fallback.csv"
        pd.DataFrame(
            {
                "date": ["2026-07-01", "2026-07-02"],
                "product": ["豌豆", "豌豆"],
                "price": [5.0, 4.0],
            }
        ).to_csv(path, index=False, encoding="utf-8-sig")
        return path

    def test_network_failure_falls_back_to_local_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            fallback = self._fallback_file(folder)
            with patch(
                "src.crawler.fetch_xinfadi_prices",
                side_effect=requests.ConnectionError("offline"),
            ):
                result = collect_price_data(
                    prefer_network=True,
                    fallback_path=fallback,
                )
        self.assertTrue(result.used_fallback)
        self.assertEqual(result.source, "local_csv_fallback")
        self.assertEqual(list(result.data.columns), ["date", "name", "price", "source", "unit"])

    def test_offline_pipeline_generates_processed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            artifacts = run_data_pipeline(
                prefer_network=False,
                fallback_path=ROOT / "data" / "fallback" / "vegetable_prices.csv",
                raw_path=folder / "raw.csv",
                processed_path=folder / "processed.csv",
                metadata_path=folder / "metadata.json",
            )
            self.assertTrue(artifacts.raw_path.is_file())
            self.assertTrue(artifacts.processed_path.is_file())
            self.assertTrue(artifacts.metadata_path.is_file())
            written = pd.read_csv(artifacts.processed_path)

        self.assertEqual(
            written[["date", "name", "price", "source"]].columns.tolist(),
            list(STANDARD_COLUMNS),
        )
        self.assertEqual(written["source"].unique().tolist(), ["local_csv_fallback"])
        self.assertIn("volatility", written.columns)
        self.assertEqual(artifacts.data.attrs["price_unit"], NORMALIZED_PRICE_UNIT)

    def test_partial_online_sample_falls_back_for_mapping_coverage(self) -> None:
        online = CollectionResult(
            data=pd.DataFrame(
                {
                    "date": ["2026-07-13"],
                    "name": ["豌豆"],
                    "price": [5.0],
                    "source": ["xinfadi_official"],
                    "unit": ["元/kg"],
                }
            ),
            source="xinfadi_official",
            used_fallback=False,
            message="fixture",
            source_url="https://example.invalid",
        )
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with patch("src.pipeline.collect_price_data", return_value=online):
                artifacts = run_data_pipeline(
                    prefer_network=True,
                    raw_path=folder / "raw.csv",
                    processed_path=folder / "processed.csv",
                    metadata_path=folder / "metadata.json",
                )

        self.assertTrue(artifacts.collection.used_fallback)
        self.assertEqual(artifacts.data["name"].nunique(), 15)


if __name__ == "__main__":
    unittest.main()
