"""Discrete event backtester - wave simulation + performance metrics.

Simulates multiple waves of a PvZ level, comparing the optimal strategy
against baselines (pure Peashooter, random) using financial-grade metrics:
Sharpe ratio, max drawdown, and cumulative utility curves.
"""
import sys; sys.path.insert(0, '.')
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Callable, Any
from src.optimizer import solve


def _peashooter_strategy(plants, available_sun, available_cells, budget, zf, dd):
    """Baseline: always plant Peashooters when possible."""
    peashooter = [p for p in plants if p['name'] == '豌豆射手']
    if not peashooter:
        return solve(plants, available_sun, available_cells, budget, zombie_factor=zf, deviation_data=dd)
    ps = peashooter[0]
    max_ct = min(8, available_cells)
    if ps['sun_cost'] > 0:
        max_ct = min(max_ct, int(available_sun / ps['sun_cost']))
    if max_ct <= 0:
        return {'strategy': {}, 'total_utility': 0.0, 'total_cost': 0, 'total_plants': 0, 'status': 'No sun'}
    return {
        'strategy': {ps['name']: max_ct},
        'total_utility': round(ps['utility'] * max_ct, 4),
        'total_cost': ps['sun_cost'] * max_ct,
        'total_plants': max_ct,
        'status': 'Baseline',
    }


def _random_strategy(plants, available_sun, available_cells, budget, zf, dd):
    """Baseline: randomly pick plants."""
    import random
    affordable = [p for p in plants if p['sun_cost'] <= available_sun or p['sun_cost'] == 0]
    if not affordable:
        return {'strategy': {}, 'total_utility': 0.0, 'total_cost': 0, 'total_plants': 0, 'status': 'No sun'}
    picks = {}
    rem_sun, rem_cells = available_sun, available_cells
    total_u = 0
    while rem_cells > 0 and rem_sun > 0:
        p = random.choice(affordable)
        sc = p['sun_cost']
        if sc <= rem_sun:
            picks[p['name']] = picks.get(p['name'], 0) + 1
            total_u += p['utility']
            rem_sun -= sc
            rem_cells -= 1
        else:
            affordable = [x for x in affordable if x['sun_cost'] <= rem_sun or x['sun_cost'] == 0]
            if not affordable:
                break
    return {
        'strategy': picks,
        'total_utility': round(total_u, 4),
        'total_cost': available_sun - rem_sun,
        'total_plants': sum(picks.values()),
        'status': 'Random baseline',
    }


class WaveSimulator:
    """Discrete event wave simulator for PvZ strategy backtesting."""
    
    def __init__(self, plants_list, deviation_dict, total_waves=10, 
                 initial_sun=150, cells=45, sun_per_wave=(50, 150)):
        self.plants = plants_list
        self.dev_dict = deviation_dict
        self.total_waves = total_waves
        self.initial_sun = initial_sun
        self.cells = cells
        self.sun_per_wave = sun_per_wave
        self.seed = 42
    
    def run(self, strategy_fn, label='Strategy', seed=42) -> pd.DataFrame:
        """Run backtest simulation with a given strategy function."""
        np.random.seed(seed)
        records = []
        current_sun = self.initial_sun
        remaining_cells = self.cells
        cumulative_utility = 0.0
        existing_plants = {}
        
        for wave in range(1, self.total_waves + 1):
            # Sun collection phase
            sun_gain = np.random.randint(*self.sun_per_wave)
            current_sun += sun_gain
            
            # Run strategy
            zf = {'swarm': 0.5, 'tank': 0.3, 'air': 0.2}
            result = strategy_fn(self.plants, current_sun, remaining_cells, 
                                 float(current_sun), zf, self.dev_dict)
            
            # Execute strategy
            wave_cost = 0
            wave_plants = 0
            if result['strategy']:
                for plant, count in result['strategy'].items():
                    p = next(p for p in self.plants if p['name'] == plant)
                    cost = p['sun_cost'] * count
                    if cost <= current_sun and count <= remaining_cells:
                        existing_plants[plant] = existing_plants.get(plant, 0) + count
                        current_sun -= cost
                        remaining_cells -= count
                        wave_cost += cost
                        wave_plants += count
            
            # Recalculate total utility from all existing plants
            cumulative_utility = sum(
                next(p['utility'] for p in self.plants if p['name'] == name) * count
                for name, count in existing_plants.items()
            )
            
            records.append({
                'wave': wave,
                'sun_gained': sun_gain,
                'sun_after': current_sun,
                'plants_placed': wave_plants,
                'sun_spent': wave_cost,
                'cells_remaining': remaining_cells,
                'cumulative_utility': round(cumulative_utility, 4),
                'new_utility': round(result['total_utility'], 4)
            })
        
        return pd.DataFrame(records)


def compute_metrics(df: pd.DataFrame, label: str = 'Strategy') -> Dict[str, Any]:
    """Compute performance metrics from simulation results."""
    if df.empty or len(df) < 2:
        return {'label': label, 'sharpe_ratio': 0, 'max_drawdown': 0, 
                'total_utility': 0, 'avg_wave_utility': 0, 'volatility': 0}
    
    # Wave-over-wave returns (change in cumulative utility)
    returns = df['cumulative_utility'].diff().dropna().values
    # Handle negative/zero returns gracefully
    returns = returns[~np.isnan(returns)]
    
    if len(returns) < 2 or np.std(returns) == 0:
        sharpe = 0.0
    else:
        # Sharpe ratio = mean(return) / std(return) * sqrt(periods)
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(len(returns)))
    
    # Max drawdown
    cum = df['cumulative_utility'].values
    peak = np.maximum.accumulate(cum)
    drawdown = (cum - peak) / (peak + 1e-10)
    max_dd = float(np.min(drawdown))
    
    # Total return
    total_return = float(df['cumulative_utility'].iloc[-1]) if len(df) > 0 else 0
    
    return {
        'label': label,
        'sharpe_ratio': round(sharpe, 4),
        'max_drawdown': round(max_dd, 4),
        'total_utility': round(total_return, 4),
        'avg_wave_utility': round(float(df['new_utility'].mean()), 4),
        'volatility': round(float(np.std(returns)), 4) if len(returns) > 0 else 0,
    }


def run_comparison(seed=42) -> Dict[str, Any]:
    """Run full backtest comparing all strategies."""
    df_plants = pd.read_csv('data/plants.csv')
    from src.valuator import calculate_utility, calc_deviation
    du = calculate_utility(df_plants)
    dp = pd.read_csv('data/fallback/vegetable_prices.csv', encoding='utf-8-sig')
    dp['date'] = pd.to_datetime(dp['date'])
    dv = calc_deviation(dp, du)
    dm = df_plants.merge(du[['name', 'utility']], on='name')
    plants_list = dm.to_dict(orient='records')
    dev_dict = dict(zip(dv['plant'].values, dv['deviation'].values))
    
    sim = WaveSimulator(plants_list, dev_dict, total_waves=10, initial_sun=150, cells=20)
    
    results = {}
    
    # Optimal strategy
    def opt_fn(p, s, c, b, z, d):
        return solve(p, s, c, b, z, d)
    results['optimal'] = sim.run(opt_fn, 'Optimal', seed)
    
    # Peashooter baseline
    results['peashooter'] = sim.run(_peashooter_strategy, 'Peashooter', seed)
    
    # Random baseline
    np.random.seed(seed)
    results['random'] = sim.run(_random_strategy, 'Random', seed)
    
    # Metrics
    metrics = {}
    for key, df in results.items():
        metrics[key] = compute_metrics(df, key)
    
    return {'simulations': results, 'metrics': metrics, 'sim': sim}
