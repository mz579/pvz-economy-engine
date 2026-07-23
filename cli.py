"""Command-line entry point for the complete V2 recommendation workflow."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import __version__
from src.dashboard import ZOMBIE_MODES, build_dashboard_model
from src.optimizer import print_strategy
from src.pipeline import DEFAULT_PROCESSED_PATH, run_data_pipeline
from src.user_data import prepare_uploaded_price_data


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"PvZ Economy Engine V{__version__}"
    )
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
    parser.add_argument("--csv", type=Path, help="使用指定地区菜价 CSV")
    parser.add_argument("--region", default="命令行地区", help="CSV 对应地区名称")
    parser.add_argument("--top", type=int, default=15, help="显示前 N 名植物")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="将推荐结果保存为 JSON 文件",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="将推荐结果以 JSON 格式输出到标准输出",
    )
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
    text_output = sys.stderr if args.json else sys.stdout

    if args.csv is not None:
        if args.online:
            raise SystemExit("--csv 与 --online 不能同时使用")
        prices = prepare_uploaded_price_data(
            args.csv.read_bytes(),
            region_name=args.region,
        )
        model = build_dashboard_model(
            args.mode,
            args.sun,
            args.cells,
            price_data=prices,
        )
        data_message = f"已读取 {args.region} CSV：{args.csv}"
    else:
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
        data_message = artifacts.collection.message

    print(f"数据：{data_message}", file=text_output)
    print(f"模式：{args.mode}", file=text_output)
    print(
        "评分权重："
        + "，".join(f"{key}={value:.3f}" for key, value in model["weights"].items()),
        file=text_output,
    )
    print("\n末日性价比排名：", file=text_output)
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
    print(
        model["ranking"].head(args.top)[columns].to_string(index=False),
        file=text_output,
    )
    print(file=text_output)
    result = model["result"]
    print(
        "集中度约束：每种植物最多占草坪容量的 "
        f"{result['max_plant_share']:.0%}，本轮最多 {result['per_plant_limit']} 株。",
        file=text_output,
    )
    with redirect_stdout(text_output):
        print_strategy(model["result"])

    ranking_columns = [
        "rank",
        "name",
        "vegetable_name",
        "current_price",
        "apocalypse_index",
    ]
    output_data = {
        "version": __version__,
        "mode": args.mode,
        "weights": model["weights"],
        "ranking": model["ranking"]
        .head(args.top)[ranking_columns]
        .to_dict(orient="records"),
        "recommendation": result["strategy"],
        "total_score": result["total_score"],
        "total_sun_cost": result["total_sun_cost"],
        "total_plants": result["total_plants"],
        "unused_cells": result["unused_cells"],
        "method": result["method"],
        "status": result["status"],
    }

    if args.output is not None:
        with args.output.open("w", encoding="utf-8") as output_file:
            json.dump(output_data, output_file, ensure_ascii=False, indent=2)
        print(f"结果已保存至：{args.output}", file=text_output)

    if model["reasons"]:
        print("推荐理由：", file=text_output)
        for reason in model["reasons"]:
            print(
                f"- {reason['name']}×{reason['quantity']}：{reason['text']}",
                file=text_output,
            )

    if args.json:
        json.dump(output_data, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0 if model["result"]["all_constraints_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
