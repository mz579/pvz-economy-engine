"""V2.0 planting combination optimizer.

The optimizer consumes a score that is calculated elsewhere. It maximizes the
total score under sun, cell, attack, and defense/control constraints. PuLP is
optional at runtime: when it or its solver is unavailable, a deterministic
greedy fallback still returns a constraint-checked result.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence
import warnings

import pandas as pd

try:  # The fallback must remain importable when PuLP is not installed.
    import pulp as pl
except ImportError:  # pragma: no cover - covered through use_pulp=False tests
    pl = None


SCORE_COLUMN_CANDIDATES = ("apocalypse_index", "score", "utility")
SUPPORT_SCORE_THRESHOLD = 5


def optimize_planting(
    plants: pd.DataFrame | Sequence[Mapping[str, Any]],
    *,
    available_sun: int = 150,
    available_cells: int = 45,
    score_column: str | None = None,
    use_pulp: bool = True,
) -> dict[str, Any]:
    """Return the highest-scoring feasible planting combination.

    A plant is considered an attacker when it is explicitly categorized as
    ``攻击`` or, when no category is available, has a positive attack value.
    Defense/control candidates are recognized from their category, role, or a
    defense/control rating of at least five on the V2 0-10 scale.
    """

    data, resolved_score = _prepare_plants(plants, score_column)
    _validate_limits(available_sun, available_cells)

    if not data["_is_attack"].any() or not data["_is_support"].any():
        return _build_result(
            data,
            {},
            available_sun,
            available_cells,
            resolved_score,
            status="Infeasible",
            method="none",
            fallback_reason="植物表缺少攻击或防御/控制候选植物",
        )

    fallback_reason = ""
    if use_pulp and pl is not None:
        try:
            strategy, solver_status = _solve_with_pulp(
                data, available_sun, available_cells
            )
        except Exception as exc:  # Solver availability varies by environment.
            fallback_reason = f"PuLP 求解不可用: {exc}"
        else:
            if solver_status == "Optimal":
                return _build_result(
                    data,
                    strategy,
                    available_sun,
                    available_cells,
                    resolved_score,
                    status="Optimal (PuLP)",
                    method="pulp",
                )
            return _build_result(
                data,
                {},
                available_sun,
                available_cells,
                resolved_score,
                status=f"Infeasible (PuLP: {solver_status})",
                method="pulp",
            )
    elif use_pulp:
        fallback_reason = "未安装 PuLP"
    else:
        fallback_reason = "已指定使用贪心 fallback"

    strategy = _solve_greedy(data, available_sun, available_cells)
    if strategy is None:
        return _build_result(
            data,
            {},
            available_sun,
            available_cells,
            resolved_score,
            status="Infeasible (greedy fallback)",
            method="greedy",
            fallback_reason=fallback_reason,
        )

    return _build_result(
        data,
        strategy,
        available_sun,
        available_cells,
        resolved_score,
        status="Feasible (greedy fallback)",
        method="greedy",
        fallback_reason=fallback_reason,
    )


def _prepare_plants(
    plants: pd.DataFrame | Sequence[Mapping[str, Any]],
    score_column: str | None,
) -> tuple[pd.DataFrame, str]:
    data = plants.copy() if isinstance(plants, pd.DataFrame) else pd.DataFrame(plants)
    if data.empty:
        raise ValueError("植物数据不能为空")

    for column in ("name", "sun_cost"):
        if column not in data.columns:
            raise ValueError(f"植物数据缺少字段: {column}")

    resolved_score = _resolve_score_column(data, score_column)
    if data["name"].fillna("").astype(str).str.strip().eq("").any():
        raise ValueError("植物名不能为空")
    if data["name"].duplicated().any():
        raise ValueError("植物名不能重复")

    data["sun_cost"] = pd.to_numeric(data["sun_cost"], errors="coerce")
    data["_score"] = pd.to_numeric(data[resolved_score], errors="coerce")
    if data[["sun_cost", "_score"]].isna().any().any():
        raise ValueError("sun_cost 和评分必须是有效数字")
    if data["sun_cost"].lt(0).any():
        raise ValueError("sun_cost 不能为负数")

    data["_is_attack"] = _attack_mask(data)
    data["_is_support"] = _support_mask(data)
    return data.reset_index(drop=True), resolved_score


def _resolve_score_column(data: pd.DataFrame, requested: str | None) -> str:
    if requested is not None:
        if requested not in data.columns:
            raise ValueError(f"植物数据缺少评分字段: {requested}")
        return requested
    for candidate in SCORE_COLUMN_CANDIDATES:
        if candidate in data.columns:
            return candidate
    raise ValueError(
        "植物数据缺少评分字段，需提供 apocalypse_index、score 或 utility"
    )


def _attack_mask(data: pd.DataFrame) -> pd.Series:
    if "is_attack" in data.columns:
        return data["is_attack"].fillna(False).astype(bool)

    category = data.get("category", pd.Series("", index=data.index)).fillna("")
    mask = category.astype(str).str.strip().eq("攻击")
    if not mask.any() and "attack" in data.columns:
        mask = pd.to_numeric(data["attack"], errors="coerce").fillna(0).gt(0)
    return mask


def _support_mask(data: pd.DataFrame) -> pd.Series:
    if "is_defense_or_control" in data.columns:
        return data["is_defense_or_control"].fillna(False).astype(bool)

    category = data.get("category", pd.Series("", index=data.index)).fillna("")
    role = data.get("role", pd.Series("", index=data.index)).fillna("")
    defense = pd.to_numeric(
        data.get("defense", pd.Series(0, index=data.index)), errors="coerce"
    ).fillna(0)
    control = pd.to_numeric(
        data.get("control", pd.Series(0, index=data.index)), errors="coerce"
    ).fillna(0)

    return (
        category.astype(str).str.strip().eq("防御")
        | role.astype(str).str.contains("防御|控制", regex=True)
        | defense.ge(SUPPORT_SCORE_THRESHOLD)
        | control.ge(SUPPORT_SCORE_THRESHOLD)
    )


def _validate_limits(available_sun: int, available_cells: int) -> None:
    if available_sun < 0:
        raise ValueError("可用阳光不能为负数")
    if available_cells < 1:
        raise ValueError("格子数必须至少为 1")


def _solve_with_pulp(
    data: pd.DataFrame, available_sun: int, available_cells: int
) -> tuple[dict[str, int], str]:
    if pl is None:
        raise RuntimeError("PuLP 未安装")

    problem = pl.LpProblem("PvZ_V2_Planting", pl.LpMaximize)
    indices = data.index.tolist()
    if hasattr(problem, "add_variable_dicts"):
        quantities = problem.add_variable_dicts(
            "quantity",
            indices,
            lowBound=0,
            upBound=available_cells,
            cat=pl.LpInteger,
        )
    else:  # PuLP 2.x compatibility.
        quantities = pl.LpVariable.dicts(
            "quantity",
            indices,
            lowBound=0,
            upBound=available_cells,
            cat=pl.LpInteger,
        )

    problem += pl.lpSum(data.at[i, "_score"] * quantities[i] for i in indices)
    problem += (
        pl.lpSum(data.at[i, "sun_cost"] * quantities[i] for i in indices)
        <= available_sun,
        "sun_limit",
    )
    problem += (
        pl.lpSum(quantities[i] for i in indices) <= available_cells,
        "cell_limit",
    )
    problem += (
        pl.lpSum(quantities[i] for i in indices if data.at[i, "_is_attack"]) >= 1,
        "minimum_attack",
    )
    problem += (
        pl.lpSum(quantities[i] for i in indices if data.at[i, "_is_support"]) >= 1,
        "minimum_defense_or_control",
    )

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="PULP_CBC_CMD is deprecated.*", category=DeprecationWarning
        )
        solver = pl.PULP_CBC_CMD(msg=False)
        problem.solve(solver)

    solver_status = pl.LpStatus.get(problem.status, str(problem.status))
    if solver_status != "Optimal":
        return {}, solver_status

    strategy = {
        data.at[i, "name"]: int(round(pl.value(quantities[i]) or 0))
        for i in indices
        if int(round(pl.value(quantities[i]) or 0)) > 0
    }
    return strategy, solver_status


def _solve_greedy(
    data: pd.DataFrame, available_sun: int, available_cells: int
) -> dict[str, int] | None:
    attack_indices = data.index[data["_is_attack"]].tolist()
    support_indices = data.index[data["_is_support"]].tolist()
    seeds: list[tuple[tuple[float, float], dict[int, int]]] = []

    for attack_index in attack_indices:
        for support_index in support_indices:
            seed = {attack_index: 1}
            seed[support_index] = seed.get(support_index, 0) + (
                0 if support_index == attack_index else 1
            )
            cells = sum(seed.values())
            sun = sum(data.at[i, "sun_cost"] * count for i, count in seed.items())
            score = sum(data.at[i, "_score"] * count for i, count in seed.items())
            if cells <= available_cells and sun <= available_sun:
                seeds.append(((score, -sun), seed))

    if not seeds:
        return None

    _, selected = max(seeds, key=lambda item: item[0])
    used_cells = sum(selected.values())
    used_sun = sum(data.at[i, "sun_cost"] * count for i, count in selected.items())

    ranked = sorted(data.index, key=lambda i: _greedy_rank(data.loc[i]), reverse=True)
    while used_cells < available_cells:
        choice = next(
            (
                i
                for i in ranked
                if data.at[i, "_score"] > 0
                and used_sun + data.at[i, "sun_cost"] <= available_sun
            ),
            None,
        )
        if choice is None:
            break
        selected[choice] = selected.get(choice, 0) + 1
        used_sun += data.at[choice, "sun_cost"]
        used_cells += 1

    return {data.at[i, "name"]: count for i, count in selected.items() if count > 0}


def _greedy_rank(row: pd.Series) -> tuple[float, float, float]:
    score = float(row["_score"])
    cost = float(row["sun_cost"])
    efficiency = float("inf") if cost == 0 and score > 0 else score / max(cost, 1)
    return efficiency, score, -cost


def _build_result(
    data: pd.DataFrame,
    strategy: Mapping[str, int],
    available_sun: int,
    available_cells: int,
    score_column: str,
    *,
    status: str,
    method: str,
    fallback_reason: str = "",
) -> dict[str, Any]:
    indexed = data.set_index("name", drop=False)
    combination = []
    for name, quantity in strategy.items():
        row = indexed.loc[name]
        unit_sun = float(row["sun_cost"])
        unit_score = float(row["_score"])
        combination.append(
            {
                "name": name,
                "quantity": int(quantity),
                "unit_sun_cost": _display_number(unit_sun),
                "unit_score": round(unit_score, 4),
                "subtotal_sun": _display_number(unit_sun * quantity),
                "subtotal_score": round(unit_score * quantity, 4),
                "role": str(row.get("role", row.get("category", ""))),
            }
        )

    combination.sort(key=lambda item: item["subtotal_score"], reverse=True)
    total_sun = sum(float(item["subtotal_sun"]) for item in combination)
    total_score = sum(float(item["subtotal_score"]) for item in combination)
    total_plants = sum(int(item["quantity"]) for item in combination)
    selected_names = {name for name, quantity in strategy.items() if quantity > 0}
    has_attack = any(
        name in selected_names and bool(row["_is_attack"])
        for name, row in indexed.iterrows()
    )
    has_support = any(
        name in selected_names and bool(row["_is_support"])
        for name, row in indexed.iterrows()
    )

    checks = {
        "sun_limit": total_sun <= available_sun,
        "cell_limit": total_plants <= available_cells,
        "has_attack": has_attack,
        "has_defense_or_control": has_support,
    }
    all_constraints_met = all(checks.values())

    if combination:
        selected_text = "、".join(
            f"{item['name']}×{item['quantity']}" for item in combination
        )
        reason = (
            f"在 {available_sun} 阳光和 {available_cells} 个格子内选择 {selected_text}，"
            f"总评分 {total_score:.2f}；攻击与防御/控制约束均已满足。"
        )
    else:
        reason = "当前阳光、格子或植物类型不足，无法同时满足全部组合约束。"

    displayed_sun = _display_number(total_sun)
    rounded_score = round(total_score, 4)
    return {
        "strategy": dict(strategy),
        "combination": combination,
        "total_sun_cost": displayed_sun,
        "total_cost": displayed_sun,
        "total_score": rounded_score,
        "total_utility": rounded_score,
        "total_plants": total_plants,
        "score_column": score_column,
        "constraint_checks": checks,
        "all_constraints_met": all_constraints_met,
        "recommendation_reason": reason,
        "status": status,
        "method": method,
        "fallback_reason": fallback_reason,
        # Temporary V1 UI compatibility; V2 no longer computes shadow prices.
        "sun_shadow_price": 0.0,
        "cell_shadow_price": 0.0,
        "cost_shadow_price": 0.0,
    }


def _display_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(float(value), 4)


def solve(
    plants: Sequence[Mapping[str, Any]],
    available_sun: int = 150,
    available_cells: int = 45,
    budget: float | None = None,
    zombie_factor: Mapping[str, float] | None = None,
    deviation_data: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper used by the legacy backtester."""

    del budget, zombie_factor, deviation_data
    return optimize_planting(
        plants,
        available_sun=available_sun,
        available_cells=available_cells,
    )


def run_optimization(
    df_plants: pd.DataFrame,
    deviation_df: pd.DataFrame | None = None,
    available_sun: int = 150,
    available_cells: int = 45,
    zombie_factor: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper used by the current CLI and Streamlit page."""

    del deviation_df, zombie_factor
    return optimize_planting(
        df_plants,
        available_sun=available_sun,
        available_cells=available_cells,
    )


def print_strategy(result: Mapping[str, Any]) -> None:
    """Print a compact command-line recommendation summary."""

    print("=" * 50)
    print(f"Status: {result['status']}")
    print(f"Method: {result['method']}")
    print(f"Total plants: {result['total_plants']}")
    print(f"Total score: {result['total_score']:.2f}")
    print(f"Total sun cost: {result['total_sun_cost']}")
    print("-" * 50)
    if result["strategy"]:
        print("Recommended combination:")
        for plant, count in result["strategy"].items():
            print(f"  {plant}: {count}")
        print(result["recommendation_reason"])
    else:
        print("No feasible solution")
    print("=" * 50)
