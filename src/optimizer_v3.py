"""V3 step 1: sun-economy-aware planting simulation.

This module is deliberately additive.  It reuses the plant table produced by
the existing scoring pipeline but never mutates ``src/optimizer.py`` or
``src/scoring.py``.  The old V2 optimizer remains the fallback/smoke-tested
entry point; the dashboard switches to this module only for the new
attack/defense/production value model.

Value model (per plant, over ``horizon`` seconds)::

    value = dps * horizon * lanes_cov + 0.1 * hp + 0.4 * prod_rate * horizon

Selection is deterministic: first satisfy one producer, one attacker, and one
defense/control plant; then spend the remaining sun on paid plants by
``value / max(sun_cost, 1)``; finally fill leftover cells with the best free
attacker.  Free plants are reserved for the fill phase so they cannot starve
the paid plants of the whole sun budget.

The production quota is enforced whenever the candidate pool contains a
producer.  A partial regional CSV may map only vegetables without a producer;
in that case the quota is vacuously satisfied so the existing partial-upload
flow keeps working (the safe fallback required by the project rules).
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from src.optimizer import (
    DEFAULT_MAX_PLANT_SHARE,
    _attack_mask,
    _display_number,
    _support_mask,
    calculate_per_plant_limit,
)


HORIZON_SECONDS = 120
PRODUCTION_SCALE = 25 / 24
BURST_TAGS = frozenset({"BOMB", "AOE"})
LANE_COVERAGE_BY_TAG = {"MULTI": 3, "AOE": 2}
SCORE_COLUMN_CANDIDATES = ("apocalypse_index", "score")


def optimize_planting_v3(
    ranking: pd.DataFrame,
    *,
    available_sun: int = 150,
    available_cells: int = 20,
    horizon: int = HORIZON_SECONDS,
    max_plant_share: float = DEFAULT_MAX_PLANT_SHARE,
    sky_sun_per_sec: float = 0.0,
) -> dict[str, Any]:
    """Return a deterministic V3 planting combination.

    ``available_sun`` is the spendable budget for this round, so the returned
    ``total_sun_cost`` never exceeds it.  Production inside the horizon is
    reported separately in ``sun_economy`` instead of being re-spent.
    """

    if horizon <= 0:
        raise ValueError("模拟时长必须大于 0")
    if sky_sun_per_sec < 0:
        raise ValueError("天空阳光速率不能为负数")
    _validate_limits(available_sun, available_cells)

    data, score_column = _prepare_plants(ranking, horizon)
    per_plant_limit = calculate_per_plant_limit(
        available_cells, max_plant_share
    )

    missing = _missing_categories(data)
    if missing:
        return _infeasible_result(
            available_sun=available_sun,
            available_cells=available_cells,
            horizon=horizon,
            max_plant_share=max_plant_share,
            per_plant_limit=per_plant_limit,
            score_column=score_column,
            has_producer_candidates=bool(data["_is_producer"].any()),
            reason="植物表缺少必需的植物类型：" + "、".join(missing)
            + "。请检查菜价映射或 plants.csv。",
        )

    counts: dict[Any, int] = {}
    used_sun = 0.0
    used_cells = 0

    # (a) One seed for each of the three required economies.
    quotas = (
        ("_is_producer", "_prod_rate_per_sun", "产能植物"),
        ("_is_attack", "_dps_per_sun", "攻击植物"),
        ("_is_support", "_support_per_sun", "防御/控制植物"),
    )
    for mask_column, ratio_column, label in quotas:
        if _quota_already_filled(data, counts, mask_column):
            continue
        if mask_column == "_is_producer" and not data["_is_producer"].any():
            # No producer in the uploaded pool: documented vacuous fallback.
            continue
        chosen = _best_quota_candidate(
            data,
            mask_column,
            ratio_column,
            counts,
            used_sun=used_sun,
            used_cells=used_cells,
            available_sun=available_sun,
            available_cells=available_cells,
        )
        if chosen is None:
            return _infeasible_result(
                available_sun=available_sun,
                available_cells=available_cells,
                horizon=horizon,
                max_plant_share=max_plant_share,
                per_plant_limit=per_plant_limit,
                score_column=score_column,
                has_producer_candidates=bool(data["_is_producer"].any()),
                reason=(
                    f"当前阳光 ({available_sun}) 或格子 ({available_cells}) "
                    f"不足以先部署 1 株{label}，无法满足 V3 三类经济约束。"
                ),
            )
        counts[chosen] = counts.get(chosen, 0) + 1
        used_sun += float(data.at[chosen, "sun_cost"])
        used_cells += 1

    # (b) Spend the remaining budget on paid plants, best value/sun first.
    paid_indices = data.index[data["sun_cost"] > 0].tolist()
    for index in _rank_indices(data, paid_indices, "_value_per_sun"):
        cap = per_plant_limit
        while (
            counts.get(index, 0) < cap
            and used_cells < available_cells
            and used_sun + float(data.at[index, "sun_cost"]) <= available_sun
        ):
            counts[index] = counts.get(index, 0) + 1
            used_sun += float(data.at[index, "sun_cost"])
            used_cells += 1

    # (c) Free fill: the best 0-sun attacker may occupy every remaining cell.
    free_attackers = data.index[
        (data["sun_cost"] == 0) & data["_is_attack"]
    ].tolist()
    if free_attackers and used_cells < available_cells:
        filler = _rank_indices(data, free_attackers, "_value")[0]
        while used_cells < available_cells:
            counts[filler] = counts.get(filler, 0) + 1
            used_cells += 1

    return _build_result(
        data,
        counts,
        score_column=score_column,
        available_sun=available_sun,
        available_cells=available_cells,
        horizon=horizon,
        max_plant_share=max_plant_share,
        per_plant_limit=per_plant_limit,
        sky_sun_per_sec=sky_sun_per_sec,
    )


def _validate_limits(available_sun: int, available_cells: int) -> None:
    if available_sun < 0:
        raise ValueError("可用阳光不能为负数")
    if available_cells < 1:
        raise ValueError("格子数必须至少为 1")


def _prepare_plants(
    ranking: pd.DataFrame,
    horizon: int,
) -> tuple[pd.DataFrame, str]:
    data = ranking.copy() if isinstance(ranking, pd.DataFrame) else pd.DataFrame(ranking)
    if data.empty:
        raise ValueError("植物排名数据不能为空")
    for column in ("name", "sun_cost"):
        if column not in data.columns:
            raise ValueError(f"植物排名数据缺少字段: {column}")

    score_column = next(
        (column for column in SCORE_COLUMN_CANDIDATES if column in data.columns),
        None,
    )
    if score_column is None:
        raise ValueError("植物排名数据缺少评分字段，需提供 apocalypse_index 或 score")

    data = data.reset_index(drop=True)
    data["sun_cost"] = _numeric(data, "sun_cost")
    data["attack"] = _numeric(data, "attack")
    data["defense"] = _numeric(data, "defense")
    data["production"] = _numeric(data, "production")
    data["control"] = _numeric(data, "control")
    data["hp"] = _numeric(data, "hp")
    data["_score"] = _numeric(data, score_column)
    if data["sun_cost"].lt(0).any():
        raise ValueError("sun_cost 不能为负数")

    tags = data.get("special_tag", pd.Series("", index=data.index))
    tags = tags.fillna("").astype(str).str.upper()
    data["_prod_rate"] = data["production"] / 10 * PRODUCTION_SCALE

    sustained_dps = data["attack"] / 1.4
    burst_dps = data["attack"] / 30
    data["_dps"] = sustained_dps.where(~tags.isin(BURST_TAGS), burst_dps)
    data.loc[data["attack"] <= 0, "_dps"] = 0.0

    data["_lanes_cov"] = (
        tags.map(LANE_COVERAGE_BY_TAG).fillna(1).astype(float)
    )
    data["_wall"] = data["hp"]
    data["_support_rating"] = data["defense"] + data["control"]
    data["_value"] = (
        data["_dps"] * horizon * data["_lanes_cov"]
        + 0.1 * data["_wall"]
        + 0.4 * data["_prod_rate"] * horizon
    )
    effective_cost = data["sun_cost"].clip(lower=1)
    data["_value_per_sun"] = data["_value"] / effective_cost
    data["_prod_rate_per_sun"] = data["_prod_rate"] / effective_cost
    data["_dps_per_sun"] = data["_dps"] / effective_cost
    data["_support_per_sun"] = data["_support_rating"] / effective_cost

    data["_is_attack"] = _attack_mask(data)
    data["_is_support"] = _support_mask(data)
    data["_is_producer"] = data["production"] > 0
    return data, score_column


def _numeric(data: pd.DataFrame, column: str) -> pd.Series:
    if column not in data.columns:
        return pd.Series(0.0, index=data.index)
    values = pd.to_numeric(data[column], errors="coerce")
    if values.isna().any():
        raise ValueError(f"{column} 必须是有效数字")
    return values.astype(float)


def _missing_categories(data: pd.DataFrame) -> list[str]:
    """Attack and defense/control are mandatory; production falls back safely."""

    missing = []
    if not data["_is_attack"].any():
        missing.append("攻击植物")
    if not data["_is_support"].any():
        missing.append("防御/控制植物")
    return missing


def _quota_already_filled(
    data: pd.DataFrame,
    counts: Mapping[Any, int],
    mask_column: str,
) -> bool:
    return any(
        counts.get(index, 0) > 0
        for index in data.index[data[mask_column]]
    )


def _best_quota_candidate(
    data: pd.DataFrame,
    mask_column: str,
    ratio_column: str,
    counts: Mapping[Any, int],
    *,
    used_sun: float,
    used_cells: int,
    available_sun: int,
    available_cells: int,
) -> Any | None:
    candidates = [
        index
        for index in data.index[data[mask_column]]
        if counts.get(index, 0) == 0
        and used_cells + 1 <= available_cells
        and used_sun + float(data.at[index, "sun_cost"]) <= available_sun
    ]
    if not candidates:
        return None
    return _rank_indices(data, candidates, ratio_column)[0]


def _rank_indices(
    data: pd.DataFrame,
    indices: list[Any],
    ratio_column: str,
) -> list[Any]:
    """Sort deterministically: efficiency desc, value desc, name asc."""

    return sorted(
        indices,
        key=lambda index: (
            -float(data.at[index, ratio_column]),
            -float(data.at[index, "_value"]),
            -float(data.at[index, "sun_cost"]),
            str(data.at[index, "name"]),
        ),
    )


def _build_result(
    data: pd.DataFrame,
    counts: Mapping[Any, int],
    *,
    score_column: str,
    available_sun: int,
    available_cells: int,
    horizon: int,
    max_plant_share: float,
    per_plant_limit: int,
    sky_sun_per_sec: float,
) -> dict[str, Any]:
    selected = {index: int(quantity) for index, quantity in counts.items() if quantity > 0}

    combination = []
    for index, quantity in selected.items():
        row = data.loc[index]
        unit_sun = float(row["sun_cost"])
        unit_score = float(row["_score"])
        combination.append(
            {
                "name": str(row["name"]),
                "quantity": int(quantity),
                "unit_sun_cost": _display_number(unit_sun),
                "unit_score": round(unit_score, 4),
                "subtotal_sun": _display_number(unit_sun * quantity),
                "subtotal_score": round(unit_score * quantity, 4),
                "role": str(row.get("role", row.get("category", ""))),
            }
        )
    combination.sort(
        key=lambda item: (-item["subtotal_score"], item["name"])
    )

    total_sun = sum(
        float(data.at[index, "sun_cost"]) * quantity
        for index, quantity in selected.items()
    )
    total_plants = sum(selected.values())
    total_value = sum(
        float(data.at[index, "_value"]) * quantity
        for index, quantity in selected.items()
    )
    # "相对比较指数" shown in the UI must stay on the apocalypse-index scale
    # (sum of per-plant scores), not the internal v3 objective value.
    relative_score = sum(
        float(data.at[index, "_score"]) * quantity
        for index, quantity in selected.items()
    )

    checks = {
        "sun_limit": total_sun <= available_sun,
        "cell_limit": total_plants <= available_cells,
        "per_plant_limit": all(
            quantity
            <= (
                available_cells
                if float(data.at[index, "sun_cost"]) == 0
                else per_plant_limit
            )
            for index, quantity in selected.items()
        ),
        "has_attack": _has_selected(data, selected, "_is_attack"),
        "has_defense_or_control": _has_selected(data, selected, "_is_support"),
    }
    has_production = _has_selected(data, selected, "_is_producer") or not bool(
        data["_is_producer"].any()
    )
    v3_checks = {**checks, "has_production": has_production}
    all_constraints_met = all(v3_checks.values())

    unused_cells = max(0, available_cells - total_plants)
    free_attackers_available = bool(
        (
            (data["sun_cost"] == 0)
            & data["_is_attack"]
            & (data["_value"] > 0)
        ).any()
    )
    if unused_cells and not free_attackers_available:
        unused_cells_reason = (
            "没有可用的 0 阳光攻击植物填充剩余格子；"
            "付费植物已达到单植物数量上限或剩余阳光不足。"
        )
    else:
        unused_cells_reason = ""

    production_over_horizon = round(
        sum(
            float(data.at[index, "_prod_rate"]) * quantity
            for index, quantity in selected.items()
        )
        * horizon,
        4,
    )
    sky_sun_over_horizon = round(float(sky_sun_per_sec) * horizon, 4)
    ending_sun = round(
        available_sun - total_sun + production_over_horizon + sky_sun_over_horizon,
        4,
    )
    payback_seconds = {
        str(data.at[index, "name"]): round(
            float(data.at[index, "sun_cost"])
            / float(data.at[index, "_prod_rate"]),
            2,
        )
        for index, quantity in selected.items()
        if quantity > 0 and float(data.at[index, "_prod_rate"]) > 0
    }

    total_dps = round(
        sum(
            float(data.at[index, "_dps"]) * quantity
            for index, quantity in selected.items()
        ),
        4,
    )
    total_wall_hp = round(
        sum(
            float(data.at[index, "_wall"]) * quantity
            for index, quantity in selected.items()
        ),
        4,
    )
    effective_defense = round(
        sum(
            (
                float(data.at[index, "_wall"])
                + float(data.at[index, "defense"])
                + float(data.at[index, "control"])
            )
            * quantity
            for index, quantity in selected.items()
        ),
        4,
    )

    if combination:
        selected_text = "、".join(
            f"{item['name']}×{item['quantity']}" for item in combination
        )
        reason = (
            f"在 {available_sun} 阳光和 {available_cells} 个格子内选择 {selected_text}，"
            f"V3 模拟价值 {round(total_value, 4):.2f}；"
            "攻击、防御/控制与阳光产能约束均已满足。"
            f"模拟 {horizon} 秒内预计提供 {total_dps:g} 点/秒攻击、"
            f"{total_wall_hp:g} 点墙血，并产出 {production_over_horizon:g} 阳光。"
        )
    else:
        reason = "当前阳光、格子或植物类型不足，无法满足 V3 三类经济约束。"

    return {
        "strategy": {
            str(data.at[index, "name"]): quantity
            for index, quantity in selected.items()
        },
        "combination": combination,
        "total_sun_cost": _display_number(total_sun),
        "total_plants": total_plants,
        "unused_cells": unused_cells,
        "total_score": round(relative_score, 4),
        "objective_value": round(total_value, 4),
        "max_plant_share": max_plant_share,
        "per_plant_limit": per_plant_limit,
        "all_constraints_met": all_constraints_met,
        "unused_cells_reason": unused_cells_reason,
        "status": (
            "Feasible (v3 simulation)"
            if all_constraints_met
            else "Infeasible (v3 simulation)"
        ),
        "method": "v3-simulation",
        "score_column": score_column,
        "constraint_checks": checks,
        "v3_constraint_checks": v3_checks,
        "recommendation_reason": reason,
        "fallback_reason": "",
        "sun_economy": {
            "start_sun": available_sun,
            "initial_cost": _display_number(total_sun),
            "production_over_horizon": production_over_horizon,
            "ending_sun": ending_sun,
            "payback_seconds": payback_seconds,
            "horizon": horizon,
        },
        "combat": {
            "total_dps": total_dps,
            "total_wall_hp": total_wall_hp,
            "effective_defense": effective_defense,
            "horizon": horizon,
        },
    }


def _has_selected(
    data: pd.DataFrame,
    selected: Mapping[Any, int],
    mask_column: str,
) -> bool:
    return any(
        quantity > 0 and bool(data.at[index, mask_column])
        for index, quantity in selected.items()
    )


def _infeasible_result(
    *,
    available_sun: int,
    available_cells: int,
    horizon: int,
    max_plant_share: float,
    per_plant_limit: int,
    score_column: str,
    has_producer_candidates: bool,
    reason: str,
) -> dict[str, Any]:
    checks = {
        "sun_limit": True,
        "cell_limit": True,
        "per_plant_limit": True,
        "has_attack": False,
        "has_defense_or_control": False,
    }
    v3_checks = {**checks, "has_production": not has_producer_candidates}
    return {
        "strategy": {},
        "combination": [],
        "total_sun_cost": 0,
        "total_plants": 0,
        "unused_cells": available_cells,
        "total_score": 0.0,
        "objective_value": 0.0,
        "max_plant_share": max_plant_share,
        "per_plant_limit": per_plant_limit,
        "all_constraints_met": False,
        "unused_cells_reason": "",
        "status": "Infeasible (v3 simulation)",
        "method": "v3-simulation",
        "score_column": score_column,
        "constraint_checks": checks,
        "v3_constraint_checks": v3_checks,
        "recommendation_reason": reason,
        "fallback_reason": "",
        "sun_economy": {
            "start_sun": available_sun,
            "initial_cost": 0,
            "production_over_horizon": 0.0,
            "ending_sun": available_sun,
            "payback_seconds": {},
            "horizon": horizon,
        },
        "combat": {
            "total_dps": 0.0,
            "total_wall_hp": 0.0,
            "effective_defense": 0.0,
            "horizon": horizon,
        },
    }
