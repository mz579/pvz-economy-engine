"""Command-line entry point for the complete V2 recommendation workflow."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard import ZOMBIE_MODES, build_dashboard_model
from src.optimizer import print_strategy
from src.pipeline import DEFAULT_PROCESSED_PATH, run_data_pipeline


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PvZ Economy Engine V2.0")
    parser.add_argument("--sun", type=int, default=150, help="可用阳光")
    parser.add_argument("--cells", type=int, default=20, help="可用草坪格子")
    parser.add_argument(
        "--mode",
        choices=list(ZOMBIE_MODES),
        default="均衡巡逻",
        help="僵尸场景",
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="优先尝试北京新发地；失败时仍自动回退本地 CSV",
    )
    parser.add_argument("--top", type=int, default=15, help="显示前 N 名植物")
    parser.add_argument(
        "--processed-output",
        type=Path,
        default=DEFAULT_PROCESSED_PATH,
        help="清洗特征文件输出路径",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.top < 1:
        raise SystemExit("--top 必须大于 0")

    artifacts = run_data_pipeline(
        prefer_network=args.online,
        processed_path=args.processed_output,
    )
    model = build_dashboard_model(
        args.mode,
        args.sun,
        args.cells,
        processed_path=args.processed_output,
    )

    print(f"数据：{artifacts.collection.message}")
    print(f"模式：{args.mode}")
    print("评分权重：" + "，".join(f"{key}={value:.3f}" for key, value in model["weights"].items()))
    print("\n末日性价比排名：")
    columns = [
        "rank",
        "name",
        "vegetable_name",
        "current_price",
        "battle_value",
        "price_undervaluation",
        "stability_coefficient",
        "apocalypse_index",
    ]
    print(model["ranking"].head(args.top)[columns].to_string(index=False))
    print()
    print_strategy(model["result"])

    if model["reasons"]:
        print("推荐理由：")
        for reason in model["reasons"]:
            print(f"- {reason['name']}×{reason['quantity']}：{reason['text']}")
    return 0 if model["result"]["all_constraints_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
