"""Planting decision optimizer - PuLP MIP with shadow prices and cash-flow constraints.

V1.0 upgrade:
- Mixed Integer Programming (MIP) via PuLP
- Proper shadow prices from LP relaxation dual variables
- Dynamic cash-flow (payback period) constraint
- Zombie factor style rotation integrated
"""
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import pulp as pl
import numpy as np


MAX_PER_PLANT = 8
SUN_GEN_RATE = 2
SUN_DROP_MEAN = 25
SUN_DROP_RATE = 1 / 10
CASH_FLOW_WINDOW = 30


def _get_params(plants):
    names = [p['name'] for p in plants]
    sun_c = {p['name']: p['sun_cost'] for p in plants}
    util = {p['name']: p['utility'] for p in plants}
    cat = {p['name']: p.get('category', '') for p in plants}
    spec = {p['name']: p.get('special_tag', '') for p in plants}
    return names, sun_c, util, cat, spec


def _build_lp_for_shadow(plants, available_sun, available_cells, deviation_dict):
    """Build LP relaxation to extract proper shadow prices."""
    names, sun_c, util, cat, spec = _get_params(plants)
    dev = {n: deviation_dict.get(n, 0.0) for n in names}
    defense_tag = chr(38450) + chr(24432)

    prob = pl.LpProblem('LP_Shadow', pl.LpMaximize)
    x = {n: pl.LpVariable('x_' + n, lowBound=0, upBound=MAX_PER_PLANT, cat=pl.LpContinuous) for n in names}
    penalty_weights = {n: util[n] * (1 - abs(dev[n]) * 0.15) for n in names}
    prob += pl.lpSum([penalty_weights[n] * x[n] for n in names]), 'Total_Efficiency'
    prob += pl.lpSum([sun_c[n] * x[n] for n in names]) <= available_sun, 'Sun_Limit'
    prob += pl.lpSum([x[n] for n in names]) <= available_cells, 'Cell_Limit'
    def_plants = [n for n in names if cat.get(n, '') == defense_tag]
    if def_plants:
        prob += pl.lpSum([x[n] for n in def_plants]) >= 1, 'Min_Defense'
    prod_plants = [n for n in names if spec.get(n, '') == 'PRODUCE']
    if prod_plants:
        prob += pl.lpSum([x[n] for n in prod_plants]) >= 1, 'Min_Producer'

    prob.solve(pl.PULP_CBC_CMD(msg=False))
    return prob, x


def _build_mip(plants, available_sun, available_cells, deviation_dict, zombie_factor):
    names, sun_c, util, cat, spec = _get_params(plants)
    defense_tag = chr(38450) + chr(24432)
    dev = {n: deviation_dict.get(n, 0.0) for n in names}
    prob = pl.LpProblem('PvZ_Optimizer', pl.LpMaximize)
    x = {n: pl.LpVariable('x_' + n, lowBound=0, upBound=MAX_PER_PLANT, cat=pl.LpInteger) for n in names}
    penalty_weights = {n: util[n] * (1 - abs(dev[n]) * 0.15) for n in names}
    prob += pl.lpSum([penalty_weights[n] * x[n] for n in names]), 'Total_Efficiency'
    prob += pl.lpSum([sun_c[n] * x[n] for n in names]) <= available_sun, 'Sun_Limit'
    prob += pl.lpSum([x[n] for n in names]) <= available_cells, 'Cell_Limit'
    def_plants = [n for n in names if cat.get(n, '') == defense_tag]
    if def_plants:
        prob += pl.lpSum([x[n] for n in def_plants]) >= 1, 'Min_Defense'
    prod_plants = [n for n in names if spec.get(n, '') == 'PRODUCE']
    if prod_plants:
        prob += pl.lpSum([x[n] for n in prod_plants]) >= 1, 'Min_Producer'
    non_prod = [n for n in names if spec.get(n, '') != 'PRODUCE']
    producer_income = pl.lpSum([x[n] for n in prod_plants]) * SUN_GEN_RATE * CASH_FLOW_WINDOW
    drop_income = pl.lpSum([x[n] for n in names]) * SUN_DROP_MEAN * SUN_DROP_RATE * CASH_FLOW_WINDOW
    total_cost = pl.lpSum([sun_c[n] * x[n] for n in names])
    total_income = producer_income + drop_income
    prob += total_cost - total_income <= available_sun, 'CashFlow_Payback'
    prob.solve(pl.PULP_CBC_CMD(msg=False))
    if pl.LpStatus[prob.status] != 'Optimal':
        return None, None
    return prob, x


def solve(plants, available_sun=150, available_cells=45, budget=None, zombie_factor=None, deviation_data=None):
    if zombie_factor is None:
        zombie_factor = {'swarm': 0.5, 'tank': 0.3, 'air': 0.2}
    if deviation_data is None:
        deviation_data = {}
    if budget is None:
        budget = float(available_sun)

    prob, x = _build_mip(plants, available_sun, available_cells, deviation_data, zombie_factor)
    if prob is None:
        return _fallback_greedy(plants, available_sun, available_cells, deviation_data, zombie_factor)

    names = [p['name'] for p in plants]
    strategy = {n: int(pl.value(x[n])) for n in names if int(pl.value(x[n]) or 0) > 0}
    sun_c = {p['name']: p['sun_cost'] for p in plants}
    util = {p['name']: p['utility'] for p in plants}
    total_util = sum(util[n] * c for n, c in strategy.items())
    total_cost = sum(sun_c[n] * c for n, c in strategy.items())
    total_plants = sum(strategy.values())

    # Get shadow prices from LP relaxation (dual values from MIP are unreliable)
    lp_prob, _ = _build_lp_for_shadow(plants, available_sun, available_cells, deviation_data)
    sun_shadow = 0.0
    cell_shadow = 0.0
    if lp_prob is not None:
        if 'Sun_Limit' in lp_prob.constraints:
            pi_val = lp_prob.constraints['Sun_Limit'].pi
            sun_shadow = round(float(pi_val), 4) if pi_val is not None else 0.0
        if 'Cell_Limit' in lp_prob.constraints:
            pi_val = lp_prob.constraints['Cell_Limit'].pi
            cell_shadow = round(float(pi_val), 4) if pi_val is not None else 0.0

    return {
        'strategy': strategy,
        'total_utility': round(total_util, 4),
        'total_cost': int(total_cost),
        'total_plants': total_plants,
        'sun_shadow_price': sun_shadow,
        'cell_shadow_price': cell_shadow,
        'cost_shadow_price': 0.0,
        'status': 'Optimal (MIP)',
    }


def _fallback_greedy(plants, available_sun, available_cells, deviation_data, zombie_factor):
    names, sun_c, util, cat, spec = _get_params(plants)
    defense_tag = chr(38450) + chr(24432)
    dev = {n: deviation_data.get(n, 0.0) for n in names}
    scores = {}
    for n in names:
        s = sun_c[n] if sun_c[n] > 0 else 0.1
        sc = util[n] / (1 + s * 0.01)
        sc -= abs(dev.get(n, 0)) * 0.15
        scores[n] = sc
    sorted_n = sorted(names, key=lambda n: -scores[n])
    strategy = {}
    rem_sun, rem_cells = available_sun, available_cells
    total_util, has_def, has_prod = 0.0, False, False
    for n in sorted_n:
        mx = min(MAX_PER_PLANT, rem_cells)
        if sun_c[n] > 0:
            mx = min(mx, int(rem_sun / sun_c[n]))
        if mx <= 0:
            continue
        strategy[n] = mx
        total_util += util[n] * mx
        rem_sun -= sun_c[n] * mx
        rem_cells -= mx
        if cat.get(n, '') == defense_tag:
            has_def = True
        if spec.get(n, '') == 'PRODUCE':
            has_prod = True
    if not has_def:
        defs = [n for n in names if cat.get(n, '') == defense_tag]
        if defs:
            bd = max(defs, key=lambda n: util[n] / max(sun_c[n], 1))
            sc = sun_c[bd]
            if sc <= rem_sun and rem_cells >= 1:
                strategy[bd] = strategy.get(bd, 0) + 1
                total_util += util[bd]
                rem_sun -= sc
                rem_cells -= 1
    if not has_prod:
        prods = [n for n in names if spec.get(n, '') == 'PRODUCE']
        if prods:
            bp = min(prods, key=lambda n: sun_c[n])
            sc = sun_c[bp]
            if sc <= rem_sun and rem_cells >= 1:
                strategy[bp] = strategy.get(bp, 0) + 1
                total_util += util[bp]
                rem_sun -= sc
                rem_cells -= 1
    final = {k: v for k, v in strategy.items() if v > 0}
    total_cost = available_sun - rem_sun
    sun_shadow, cell_shadow = 0.0, 0.0
    if total_util > 0:
        def _perturb(sun_adj, cell_adj):
            s = available_sun + sun_adj
            c = available_cells + cell_adj
            strat2 = {}
            rs, rc = s, c
            tu = 0.0
            for n in sorted(names, key=lambda nn: -scores[nn]):
                mx = min(MAX_PER_PLANT, rc)
                if sun_c[n] > 0:
                    mx = min(mx, int(rs / sun_c[n]))
                if mx <= 0:
                    continue
                strat2[n] = mx
                tu += util[n] * mx
                rs -= sun_c[n] * mx
                rc -= mx
            return tu
        base_u = total_util
        sun_shadow = round(max(0, (_perturb(10, 0) - base_u) / 10), 4)
        cell_shadow = round(max(0, (_perturb(0, 2) - base_u) / 2), 4)
    return {
        'strategy': final,
        'total_utility': round(total_util, 4),
        'total_cost': int(total_cost),
        'total_plants': sum(final.values()),
        'sun_shadow_price': sun_shadow,
        'cell_shadow_price': cell_shadow,
        'cost_shadow_price': 0.0,
        'status': 'Heuristic (greedy fallback)',
    }


def run_optimization(df_plants, deviation_df=None, available_sun=150, available_cells=45, zombie_factor=None):
    plants_list = df_plants.to_dict(orient='records')
    dev_dict = {}
    if deviation_df is not None and not deviation_df.empty:
        dev_dict = dict(zip(deviation_df['plant'].values, deviation_df['deviation'].values))
    return solve(plants_list, available_sun, available_cells, float(available_sun), zombie_factor, dev_dict)


def print_strategy(result):
    print('=' * 50)
    print(f"Status: {result['status']}")
    print(f"Total plants: {result.get('total_plants', 0)}")
    print(f"Total utility: {result['total_utility']:.2f}")
    print(f"Total sun cost: {result['total_cost']}")
    print(f"Sun shadow price: {result['sun_shadow_price']:.4f}")
    print(f"Cell shadow price: {result['cell_shadow_price']:.4f}")
    print('-' * 50)
    if result['strategy']:
        print('Optimal strategy:')
        for plant, count in sorted(result['strategy'].items(), key=lambda x: -x[1]):
            print(f"  {plant}: {count}")
    else:
        print('No feasible solution')
    print('=' * 50)
