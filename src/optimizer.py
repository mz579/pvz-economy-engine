"""Planting decision optimizer - greedy heuristic + shadow price estimation."""
from typing import Dict, List, Optional, Any
import pandas as pd


def _core_solve(plants, available_sun, available_cells, budget, zf, dd):
    names = [p['name'] for p in plants]
    sun_c = {p['name']: p['sun_cost'] for p in plants}
    util = {p['name']: p['utility'] for p in plants}
    cat = {p['name']: p.get('category', '') for p in plants}
    spec = {p['name']: p.get('special_tag', '') for p in plants}
    dev = {n: dd.get(n, 0.0) for n in names}
    scores = {}
    for n in names:
        s = sun_c[n] if sun_c[n] > 0 else 0.1
        sc = util[n] / (1 + s * 0.01)
        if dev.get(n, 0) > 0:
            sc -= dev[n] * 0.15
        scores[n] = sc
    sorted_n = sorted(names, key=lambda n: -scores[n])
    strategy = {n: 0 for n in names}
    rem_sun, rem_cells, rem_budget = available_sun, available_cells, budget
    total_util, has_def, has_prod, maxpp = 0.0, False, False, 8

    for n in sorted_n:
        mx = min(maxpp, rem_cells)
        if sun_c[n] > 0:
            mx = min(mx, int(rem_sun / sun_c[n]))
        if mx <= 0:
            continue
        strategy[n] = mx
        total_util += util[n] * mx
        rem_sun -= sun_c[n] * mx
        rem_cells -= mx
        if cat.get(n, '') == '防御':
            has_def = True
        if spec.get(n, '') == 'PRODUCE':
            has_prod = True

    if not has_def:
        defs = [n for n in names if cat.get(n, '') == '防御']
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
    return {'strategy': final, 'total_utility': round(total_util, 4),
            'total_cost': available_sun - rem_sun,
            'total_plants': sum(final.values()), 'status': 'Heuristic (greedy)'}


def solve(plants, available_sun=150, available_cells=45, budget=None,
          zombie_factor=None, deviation_data=None):
    if budget is None: budget = float(available_sun)
    if zombie_factor is None: zombie_factor = {'swarm': 0.5, 'tank': 0.3, 'air': 0.2}
    if deviation_data is None: deviation_data = {}
    result = _core_solve(plants, available_sun, available_cells, budget, zombie_factor, deviation_data)
    base = result['total_utility']
    if base > 0:
        rs = _core_solve(plants, available_sun + 10, available_cells, budget, zombie_factor, deviation_data)
        rc = _core_solve(plants, available_sun, available_cells + 2, budget, zombie_factor, deviation_data)
        result['sun_shadow_price'] = round(max(0, (rs['total_utility'] - base) / 10), 4)
        result['cell_shadow_price'] = round(max(0, (rc['total_utility'] - base) / 2), 4)
    else:
        result['sun_shadow_price'] = result['cell_shadow_price'] = 0.0
    result['cost_shadow_price'] = 0.0
    return result


def run_optimization(df_plants, deviation_df=None, available_sun=150, available_cells=45, zombie_factor=None):
    plants_list = df_plants.to_dict(orient='records')
    dev_dict = {}
    if deviation_df is not None and not deviation_df.empty:
        dev_dict = dict(zip(deviation_df['plant'].values, deviation_df['deviation'].values))
    for p in plants_list:
        p['market_cost'] = p.get('market_cost', p['sun_cost'] * (1 + abs(dev_dict.get(p['name'], 0))))
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
