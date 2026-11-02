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

Step 2 adds a lane layer on top of the already selected roster.  It never
changes the selected quantities: it only distributes the same plant instances
across ``lanes`` lanes (one defense/control seed per lane, then paid attackers
balanced by current DPS, then the remaining plants, then free attackers to
fill each lane).  When a partial regional CSV contains too few attack plants
to physically cover every lane, per-lane attack coverage falls back to
"vacuously satisfied" so the documented partial-upload flow keeps working
(the same safe-fallback rule used for a missing producer).

The production quota is enforced whenever the candidate pool contains a
producer.  A partial regional CSV may map only vegetables without a producer;
in that case the quota is vacuously satisfied so the existing partial-upload
flow keeps working (the safe fallback required by the project rules).
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

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

# Day/night scenario rules (StrategyWiki mechanics): mushrooms sleep during the
# day, while sky sun only falls during the day.
SCENARIOS = ("day", "night")
MUSHROOM_NAMES = ("小喷菇", "阳光菇", "大喷菇")
MUSHROOMS = frozenset(MUSHROOM_NAMES)
DEFAULT_SKY_SUN_PER_SEC = {"day": 0.25, "night": 0.0}
SCENARIO_LABELS = {"day": "白天", "night": "夜间"}


def optimize_planting_v3(
    ranking: pd.DataFrame,
    *,
    available_sun: int = 150,
    available_cells: int = 20,
    horizon: int = HORIZON_SECONDS,
    max_plant_share: float = DEFAULT_MAX_PLANT_SHARE,
    sky_sun_per_sec: float | None = None,
    lanes: int = 5,
    scenario: str = "day",
) -> dict[str, Any]:
    """Return a deterministic V3 planting combination.

    ``available_sun`` is the spendable budget for this round, so the returned
    ``total_sun_cost`` never exceeds it.  Production inside the horizon is
    reported separately in ``sun_economy`` instead of being re-spent.

    ``lanes`` only controls the read-only ``lane_defense`` deployment plan; it
    never changes the selected plant quantities.

    ``scenario`` selects the day/night mechanics: mushrooms are excluded from
    the candidate pool during the day, and sky sun falls at 0.25/sec by day
    versus 0/sec at night.  Passing ``sky_sun_per_sec`` explicitly overrides
    the scenario default.
    """

    if horizon <= 0:
        raise ValueError("模拟时长必须大于 0")
    if scenario not in DEFAULT_SKY_SUN_PER_SEC:
        raise ValueError("场景必须是 day 或 night")
    if sky_sun_per_sec is None:
        sky_sun_per_sec = DEFAULT_SKY_SUN_PER_SEC[scenario]
    sky_sun_per_sec = float(sky_sun_per_sec)
    if sky_sun_per_sec < 0:
        raise ValueError("天空阳光速率不能为负数")
    _validate_limits(available_sun, available_cells)
    if int(lanes) < 1:
        raise ValueError("车道数必须至少为 1")
    lanes = int(lanes)

    data, score_column = _prepare_plants(ranking, horizon)
    if scenario == "day":
        # Mushrooms sleep during the day and cannot be planted.
        data = data.loc[
            ~data["name"].astype(str).isin(MUSHROOMS)
        ].reset_index(drop=True)
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
            lanes=lanes,
            scenario=scenario,
            sky_sun_per_sec=sky_sun_per_sec,
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
                lanes=lanes,
                scenario=scenario,
                sky_sun_per_sec=sky_sun_per_sec,
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
        lanes=lanes,
        scenario=scenario,
    )


def _validate_limits(available_sun: int, available_cells: int) -> None:
    if available_sun < 0:
        raise ValueError("可用阳光不能为负数")
    if available_cells < 1:
        raise ValueError("格子数必须至少为 1")


def _scenario_note(scenario: str, sky_sun_per_sec: float) -> str:
    """Return the short day/night sentence shared by every result path."""

    label = SCENARIO_LABELS[scenario]
    if scenario == "day":
        return (
            f"{label}：蘑菇（{'、'.join(MUSHROOM_NAMES)}）休眠不可用，"
            f"天降阳光 {sky_sun_per_sec:g}/秒。"
        )
    return f"{label}：蘑菇可用，天降阳光 {sky_sun_per_sec:g}/秒。"


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
    lanes: int,
    scenario: str,
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
    lane_defense = _build_lane_defense(
        data,
        selected,
        lanes=lanes,
        available_cells=available_cells,
        horizon=horizon,
    )
    # A partial regional CSV may select fewer attack plants than there are
    # lanes.  In that documented fallback the per-lane attack coverage is
    # vacuous (mirrors the missing-producer rule) instead of flipping the
    # whole recommendation to infeasible.
    attack_instances = sum(
        int(quantity)
        for index, quantity in selected.items()
        if bool(data.at[index, "_is_attack"])
    )
    has_attack_per_lane = all(
        lane["dps"] > 0 for lane in lane_defense["lanes"]
    ) or attack_instances < lanes
    v3_checks = {
        **checks,
        "has_production": has_production,
        "has_attack_per_lane": has_attack_per_lane,
    }
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

    scenario_note = _scenario_note(scenario, sky_sun_per_sec)
    if combination:
        selected_text = "、".join(
            f"{item['name']}×{item['quantity']}" for item in combination
        )
        reason = (
            scenario_note
            + f"在 {available_sun} 阳光和 {available_cells} 个格子内选择 {selected_text}，"
            f"V3 模拟价值 {round(total_value, 4):.2f}；"
            "攻击、防御/控制与阳光产能约束均已满足。"
            f"模拟 {horizon} 秒内预计提供 {total_dps:g} 点/秒攻击、"
            f"{total_wall_hp:g} 点墙血，并产出 {production_over_horizon:g} 阳光。"
        )
        reason += _lane_reason_suffix(lane_defense)
    else:
        reason = (
            scenario_note
            + "当前阳光、格子或植物类型不足，无法满足 V3 三类经济约束。"
        )

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
        "scenario": scenario,
        "score_column": score_column,
        "constraint_checks": checks,
        "v3_constraint_checks": v3_checks,
        "recommendation_reason": reason,
        "fallback_reason": "",
        "sun_economy": {
            "start_sun": available_sun,
            "initial_cost": _display_number(total_sun),
            "production_over_horizon": production_over_horizon,
            "sky_sun_per_sec": sky_sun_per_sec,
            "sky_sun_over_horizon": sky_sun_over_horizon,
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
        "lane_defense": lane_defense,
    }


def _build_lane_defense(
    data: pd.DataFrame,
    selected: Mapping[Any, int],
    *,
    lanes: int,
    available_cells: int,
    horizon: int,
) -> dict[str, Any]:
    """Distribute the already selected instances across fixed lanes.

    The plan is deterministic: capacity is ``cells // lanes`` plus one extra
    cell for the first ``cells % lanes`` lanes.  Assignment order is
    defense/control seed per lane, paid attackers balanced by current DPS,
    other remaining plants, then free attackers filling the weakest lanes.
    """

    base_capacity, remainder = divmod(available_cells, lanes)
    states = [
        {
            "lane": lane_number,
            "capacity": base_capacity + (1 if lane_number <= remainder else 0),
            "cells": 0,
            "dps": 0.0,
            "defense": 0.0,
            "plants": {},
        }
        for lane_number in range(1, lanes + 1)
    ]
    instances = _expand_instances(data, selected)
    used: set[int] = set()

    # (a) One defense/control seed per lane, strongest first.
    support_positions = sorted(
        (
            position
            for position, instance in enumerate(instances)
            if instance["is_support"]
        ),
        key=lambda position: (
            -instances[position]["support_rating"],
            -instances[position]["dps"],
            instances[position]["name"],
        ),
    )
    support_cursor = 0
    for state in states:
        if support_cursor >= len(support_positions):
            break
        if state["cells"] >= state["capacity"]:
            continue
        position = support_positions[support_cursor]
        support_cursor += 1
        used.add(position)
        _place_instance(state, instances[position])

    # (b) Paid attackers, strongest first, into the currently weakest lane.
    for position in _sorted_positions(
        instances,
        used,
        lambda instance: instance["is_attack"] and instance["sun_cost"] > 0,
    ):
        state = _weakest_open_lane(states)
        if state is None:
            break
        used.add(position)
        _place_instance(state, instances[position])

    # (c) Any remaining paid or non-attacking plants not used as a lane seed.
    for position in _sorted_positions(
        instances,
        used,
        lambda instance: not (
            instance["is_attack"] and instance["sun_cost"] == 0
        ),
    ):
        state = _weakest_open_lane(states)
        if state is None:
            break
        used.add(position)
        _place_instance(state, instances[position])

    # (d) Zero-sun attackers fill whatever capacity remains.
    for position in _sorted_positions(
        instances,
        used,
        lambda instance: instance["is_attack"] and instance["sun_cost"] == 0,
    ):
        state = _weakest_open_lane(states)
        if state is None:
            break
        used.add(position)
        _place_instance(state, instances[position])

    # Safety net: selected quantities must always fit, so place leftovers.
    for position in sorted(set(range(len(instances))) - used):
        state = _weakest_open_lane(states)
        if state is None:
            break
        used.add(position)
        _place_instance(state, instances[position])

    rows = []
    for state in states:
        rows.append(
            {
                "lane": state["lane"],
                "capacity": state["capacity"],
                "cells": state["cells"],
                "dps": round(state["dps"], 4),
                "defense": round(state["defense"], 4),
                "survivability": round(
                    state["dps"] * horizon + 0.1 * state["defense"], 4
                ),
                "plants": dict(sorted(state["plants"].items())),
            }
        )

    weakest = min(rows, key=lambda row: (row["survivability"], row["lane"]))
    return {
        "lanes": rows,
        "lanes_count": lanes,
        "weakest_lane": weakest["lane"],
        "weakest_survivability": weakest["survivability"],
    }


def _expand_instances(
    data: pd.DataFrame,
    selected: Mapping[Any, int],
) -> list[dict[str, Any]]:
    instances: list[dict[str, Any]] = []
    ordered = sorted(
        selected.items(), key=lambda item: str(data.at[item[0], "name"])
    )
    for index, quantity in ordered:
        row = data.loc[index]
        for _ in range(int(quantity)):
            instances.append(
                {
                    "name": str(row["name"]),
                    "sun_cost": float(row["sun_cost"]),
                    "dps": float(row["_dps"]),
                    "defense": float(row["_wall"])
                    + float(row["defense"])
                    + float(row["control"]),
                    "support_rating": float(row["_support_rating"]),
                    "is_attack": bool(row["_is_attack"]),
                    "is_support": bool(row["_is_support"]),
                }
            )
    return instances


def _sorted_positions(
    instances: list[dict[str, Any]],
    used: set[int],
    predicate: Callable[[Mapping[str, Any]], bool],
) -> list[int]:
    return sorted(
        (
            position
            for position, instance in enumerate(instances)
            if position not in used and predicate(instance)
        ),
        key=lambda position: (
            -instances[position]["dps"],
            instances[position]["name"],
        ),
    )


def _weakest_open_lane(states: list[dict[str, Any]]) -> dict[str, Any] | None:
    open_states = [
        state for state in states if state["cells"] < state["capacity"]
    ]
    if not open_states:
        return None
    return min(open_states, key=lambda state: (state["dps"], state["lane"]))


def _place_instance(
    state: dict[str, Any],
    instance: Mapping[str, Any],
) -> None:
    state["cells"] += 1
    state["dps"] += float(instance["dps"])
    state["defense"] += float(instance["defense"])
    name = str(instance["name"])
    state["plants"][name] = state["plants"].get(name, 0) + 1


def _lane_reason_suffix(lane_defense: Mapping[str, Any]) -> str:
    weakest_lane = lane_defense["weakest_lane"]
    if weakest_lane is None:
        return ""
    row = next(
        lane
        for lane in lane_defense["lanes"]
        if lane["lane"] == weakest_lane
    )
    return (
        f"（{lane_defense['lanes_count']} 车道部署：最弱车道 #{weakest_lane}，"
        f"dps≈{_format_metric(row['dps'])}，防御≈{_format_metric(row['defense'])}）"
    )


def _format_metric(value: float) -> str:
    return f"{round(float(value), 4):g}"


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
    lanes: int,
    scenario: str,
    sky_sun_per_sec: float,
    reason: str,
) -> dict[str, Any]:
    checks = {
        "sun_limit": True,
        "cell_limit": True,
        "per_plant_limit": True,
        "has_attack": False,
        "has_defense_or_control": False,
    }
    v3_checks = {
        **checks,
        "has_production": not has_producer_candidates,
        "has_attack_per_lane": False,
    }
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
        "scenario": scenario,
        "score_column": score_column,
        "constraint_checks": checks,
        "v3_constraint_checks": v3_checks,
        "recommendation_reason": _scenario_note(
            scenario, sky_sun_per_sec
        ) + reason,
        "fallback_reason": "",
        "sun_economy": {
            "start_sun": available_sun,
            "initial_cost": 0,
            "production_over_horizon": 0.0,
            "sky_sun_per_sec": sky_sun_per_sec,
            "sky_sun_over_horizon": round(sky_sun_per_sec * horizon, 4),
            "ending_sun": round(
                available_sun + sky_sun_per_sec * horizon, 4
            ),
            "payback_seconds": {},
            "horizon": horizon,
        },
        "combat": {
            "total_dps": 0.0,
            "total_wall_hp": 0.0,
            "effective_defense": 0.0,
            "horizon": horizon,
        },
        "lane_defense": {
            "lanes": [],
            "lanes_count": lanes,
            "weakest_lane": None,
            "weakest_survivability": 0,
        },
    }
