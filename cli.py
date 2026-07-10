
"""CLI entry point for PvZ Economy Engine."""
import sys; sys.path.insert(0, ".")
import pandas as pd
from src.valuator import calculate_utility, calc_deviation
from src.optimizer import run_optimization, print_strategy


def main():
    import argparse
    p = argparse.ArgumentParser(description="PvZ Economy Engine")
    p.add_argument("--sun", type=int, default=150, help="Available sun")
    p.add_argument("--cells", type=int, default=20, help="Available cells")
    p.add_argument("--swarm", type=float, default=0.5)
    p.add_argument("--tank", type=float, default=0.3)
    p.add_argument("--air", type=float, default=0.2)
    args = p.parse_args()

    df = pd.read_csv("data/plants.csv")
    du = calculate_utility(df)
    dp = pd.read_csv("data/fallback/vegetable_prices.csv", encoding="utf-8-sig")
    dp["date"] = pd.to_datetime(dp["date"])
    dv = calc_deviation(dp, du)
    dm = df.merge(du[["name", "utility"]], on="name")
    r = run_optimization(dm, dv, args.sun, args.cells,
                         {"swarm": args.swarm, "tank": args.tank, "air": args.air})
    print_strategy(r)


if __name__ == "__main__":
    main()
