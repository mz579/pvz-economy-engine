"""Data-quality rules for cleaned vegetable-price frames.

Every rule receives a cleaned frame with at least ``date``, ``name`` and
``price`` columns (``source`` and an optional ``unit`` column may also be
present). Rules never mutate the frame and never fill missing rows: problems
are reported for a human/ETL decision instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd


REQUIRED_COLUMNS = ("date", "name", "price")

# R3: cleaned prices are yuan/kg and must sit in (0, 200].
PRICE_MIN_EXCLUSIVE = 0.0
PRICE_MAX_INCLUSIVE = 200.0

# R6: adjacent-day price moves above this fraction are flagged.
MAX_DAY_CHANGE = 0.5

# R7: batch row counts moving more than this fraction are flagged.
MAX_ROW_COUNT_CHANGE = 0.3

# Keep detail strings readable without dumping thousands of rows.
SAMPLE_LIMIT = 5

# Unit labels accepted after cleaning. The contract is kg, so fully-qualified
# kg labels are accepted as well as the bare ``kg`` token.
ALLOWED_UNITS = frozenset({"kg", "千克", "元/kg", "元/千克"})

# RULES is the stable public registry: id -> metadata used in result records.
RULES: dict[str, dict[str, str]] = {
    "R1": {"title": "非空", "severity": "blocking"},
    "R2": {"title": "唯一", "severity": "blocking"},
    "R3": {"title": "范围", "severity": "blocking"},
    "R4": {"title": "连续性", "severity": "warning"},
    "R5": {"title": "单位一致", "severity": "blocking"},
    "R6": {"title": "分布异常", "severity": "warning"},
    "R7": {"title": "行数波动", "severity": "warning"},
}


@dataclass
class DQResult:
    """Outcome of one ``validate`` call.

    ``passed`` is True only when no blocking rule failed. ``errors`` and
    ``warnings`` are human-readable messages; ``records`` holds exactly one
    row per rule for persistence into ``dq_result``.
    """

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    records: list[dict[str, str]] = field(default_factory=list)


class DQError(ValueError):
    """Raised by the pipeline when blocking data-quality rules fail."""

    def __init__(self, result: DQResult) -> None:
        self.result = result
        summary = "；".join(result.errors) or "数据质量校验未通过"
        super().__init__(f"数据质量校验未通过: {summary}")


def _as_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def _format_samples(samples: list[str]) -> str:
    shown = samples[:SAMPLE_LIMIT]
    suffix = "" if len(samples) <= SAMPLE_LIMIT else f" 等 {len(samples)} 项"
    return "，".join(shown) + suffix


# --- Rules -----------------------------------------------------------------


def _rule_r1(frame: pd.DataFrame) -> tuple[str, str]:
    """R1: date/name/price must be present and non-empty."""

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        return "fail", f"缺少必需列: {', '.join(missing)}"

    problems: list[str] = []

    blank_dates = int(_as_date(frame["date"]).isna().sum())
    if blank_dates:
        problems.append(f"date 为空或不可解析 {blank_dates} 行")

    names = frame["name"]
    blank_names = int((names.isna() | names.astype(str).str.strip().eq("")).sum())
    if blank_names:
        problems.append(f"name 为空 {blank_names} 行")

    blank_prices = int(pd.to_numeric(frame["price"], errors="coerce").isna().sum())
    if blank_prices:
        problems.append(f"price 为空或非数值 {blank_prices} 行")

    if problems:
        return "fail", "；".join(problems)
    return "pass", "date/name/price 均非空且可解析"


def _rule_r2(frame: pd.DataFrame) -> tuple[str, str]:
    """R2: (date, name) must be unique."""

    if not {"date", "name"}.issubset(frame.columns):
        return "pass", "缺少 date/name 列，跳过唯一性检查"

    keys = pd.DataFrame(
        {
            "date": _as_date(frame["date"]).dt.strftime("%Y-%m-%d"),
            "name": frame["name"].astype(str).str.strip(),
        }
    ).dropna(subset=["date"])
    duplicated = keys.duplicated(keep=False)
    if not duplicated.any():
        return "pass", "date+name 无重复"

    groups = keys.loc[duplicated].drop_duplicates()
    samples = [f"{row.date}/{row.name}" for row in groups.itertuples()]
    return (
        "fail",
        f"date+name 重复 {len(groups)} 组，涉及 {int(duplicated.sum())} 行；"
        f"示例: {_format_samples(samples)}",
    )


def _rule_r3(frame: pd.DataFrame) -> tuple[str, str]:
    """R3: price must be in (0, 200] yuan/kg."""

    if "price" not in frame.columns:
        return "pass", "缺少 price 列，跳过范围检查"

    price = pd.to_numeric(frame["price"], errors="coerce")
    present = price.notna()
    invalid = present & ((price <= PRICE_MIN_EXCLUSIVE) | (price > PRICE_MAX_INCLUSIVE))
    if not invalid.any():
        if not present.any():
            return "pass", "price 为空，由 R1 负责阻断"
        return (
            "pass",
            f"price 均在 (0, 200] 内（min={price[present].min():g}，"
            f"max={price[present].max():g}）",
        )

    samples = [
        f"{index}:{value:g}" for index, value in price[invalid].items()
    ]
    return (
        "fail",
        f"price 超出 (0, 200] 区间 {int(invalid.sum())} 行；"
        f"示例: {_format_samples(samples)}",
    )


def _rule_r4(frame: pd.DataFrame) -> tuple[str, str]:
    """R4: each commodity's daily date sequence must have no missing days."""

    if not {"date", "name"}.issubset(frame.columns):
        return "pass", "缺少 date/name 列，跳过连续性检查"

    work = pd.DataFrame(
        {"date": _as_date(frame["date"]), "name": frame["name"].astype(str)}
    ).dropna(subset=["date"])
    if work.empty:
        return "pass", "没有可校验的日期，跳过连续性检查"

    missing_by_name: list[tuple[str, pd.DatetimeIndex]] = []
    for name, group in work.groupby("name", sort=True):
        dates = pd.DatetimeIndex(sorted(group["date"].dt.normalize().unique()))
        if len(dates) < 2:
            continue
        expected = pd.date_range(dates.min(), dates.max(), freq="D")
        missing = expected.difference(dates)
        if len(missing):
            missing_by_name.append((name, missing))

    if not missing_by_name:
        return "pass", f"{work['name'].nunique()} 个品种日期序列连续"

    total = sum(len(missing) for _, missing in missing_by_name)
    samples = [
        f"{name}:{missing[0].strftime('%Y-%m-%d')}"
        for name, missing in missing_by_name
    ]
    return (
        "warn",
        f"{len(missing_by_name)} 个品种共缺失 {total} 个日期（未静默补全）；"
        f"示例: {_format_samples(samples)}",
    )


def _rule_r5(frame: pd.DataFrame) -> tuple[str, str]:
    """R5: a surviving ``unit`` column must express kg consistently."""

    if "unit" not in frame.columns:
        return "pass", "无 unit 列，视为已归一为 kg"

    units = frame["unit"].fillna("").astype(str).str.strip().str.lower()
    invalid = ~units.isin(ALLOWED_UNITS)
    if not invalid.any():
        return "pass", "unit 列全部为 kg 口径"

    samples = [f"{index}:{value!r}" for index, value in units[invalid].items()]
    return (
        "fail",
        f"unit 存在非 kg 口径 {int(invalid.sum())} 行；"
        f"示例: {_format_samples(samples)}",
    )


def _rule_r6(frame: pd.DataFrame) -> tuple[str, str]:
    """R6: flag adjacent-day price moves greater than 50%."""

    if not {"date", "name", "price"}.issubset(frame.columns):
        return "pass", "缺少 date/name/price 列，跳过分布检查"

    work = pd.DataFrame(
        {
            "date": _as_date(frame["date"]),
            "name": frame["name"].astype(str),
            "price": pd.to_numeric(frame["price"], errors="coerce"),
        }
    ).dropna(subset=["date", "price"])
    if work.empty:
        return "pass", "没有可校验的价格，跳过分布检查"

    anomalies: list[str] = []
    for name, group in work.groupby("name", sort=True):
        group = (
            group.sort_values("date")
            .drop_duplicates("date", keep="last")
            .reset_index(drop=True)
        )
        if len(group) < 2:
            continue
        previous = group["price"].shift(1)
        change = group["price"].pct_change()
        day_gap = group["date"].diff().dt.days
        flagged = (day_gap == 1) & previous.gt(0) & change.abs().gt(MAX_DAY_CHANGE)
        for position in group.index[flagged]:
            date_value = group.iloc[position]["date"].strftime("%Y-%m-%d")
            change_value = change.iloc[position]
            anomalies.append(f"{name}@{date_value}:{change_value:+.1%}")

    if not anomalies:
        return "pass", "未发现相邻日涨跌超过 50% 的记录"

    return (
        "warn",
        f"{len(anomalies)} 条相邻日涨跌超过 50%；"
        f"示例: {_format_samples(anomalies)}",
    )


def _rule_r7(frame: pd.DataFrame, prev_row_count: int | None) -> tuple[str, str]:
    """R7: flag batch row-count swings over 30% versus the previous batch."""

    current = int(len(frame))
    if prev_row_count is None:
        return "pass", "无上一批次行数，跳过行数波动检查"

    previous = int(prev_row_count)
    if previous <= 0:
        return "pass", "上一批次行数为 0，跳过行数波动检查"

    change = abs(current - previous) / previous
    if change > MAX_ROW_COUNT_CHANGE:
        return (
            "warn",
            f"行数由 {previous} 变为 {current}，波动 {change:.1%} 超过 30%",
        )
    return "pass", f"行数 {previous} -> {current}，波动 {change:.1%} 未超过 30%"


# --- Entry point -----------------------------------------------------------


def validate(
    df: pd.DataFrame,
    *,
    prev_row_count: int | None = None,
) -> DQResult:
    """Run R1-R7 over ``df`` and return a structured :class:`DQResult`.

    ``prev_row_count`` is the previous successful batch row count (usually read
    from ``pipeline_run``). When omitted, R7 is not triggered.
    """

    if df is None:
        raise ValueError("dq 校验输入不能为空")
    frame = pd.DataFrame(df)

    checks: list[tuple[str, Callable[[], tuple[str, str]]]] = [
        ("R1", lambda: _rule_r1(frame)),
        ("R2", lambda: _rule_r2(frame)),
        ("R3", lambda: _rule_r3(frame)),
        ("R4", lambda: _rule_r4(frame)),
        ("R5", lambda: _rule_r5(frame)),
        ("R6", lambda: _rule_r6(frame)),
        ("R7", lambda: _rule_r7(frame, prev_row_count)),
    ]

    errors: list[str] = []
    warnings: list[str] = []
    records: list[dict[str, str]] = []

    for rule_id, check in checks:
        status, detail = check()
        severity = RULES[rule_id]["severity"]
        records.append(
            {
                "rule": rule_id,
                "status": status,
                "severity": severity,
                "detail": detail,
            }
        )
        if status == "fail":
            errors.append(f"[{rule_id}] {detail}")
        elif status == "warn":
            warnings.append(f"[{rule_id}] {detail}")

    return DQResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
        records=records,
    )
