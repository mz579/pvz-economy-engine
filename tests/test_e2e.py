"""End-to-end acceptance test for data -> score -> optimize -> view model."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard import build_dashboard_model
from src.pipeline import run_data_pipeline


class EndToEndWorkflowTests(unittest.TestCase):
    def test_clean_checkout_offline_path_reaches_ui_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            processed = folder / "processed.csv"
            artifacts = run_data_pipeline(
                prefer_network=False,
                raw_path=folder / "raw.csv",
                processed_path=processed,
                metadata_path=folder / "metadata.json",
            )
            model = build_dashboard_model(
                "迷雾夜战",
                200,
                25,
                processed_path=processed,
            )

        self.assertEqual(list(artifacts.data.columns[:4]), ["date", "name", "price", "source"])
        self.assertEqual(artifacts.data["name"].nunique(), 15)
        self.assertEqual(len(model["ranking"]), 15)
        self.assertFalse(model["ranking"]["recommendation_reason"].isna().any())
        self.assertTrue(model["result"]["all_constraints_met"])
        self.assertTrue(model["result"]["combination"])
        self.assertEqual(model["result"]["score_column"], "apocalypse_index")


if __name__ == "__main__":
    unittest.main()
