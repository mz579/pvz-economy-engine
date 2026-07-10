"""Price forecast module."""
import numpy as np
import pandas as pd
from typing import Dict, Tuple

def decompose(series, period=7):
    values = series.values.astype(float)
    trend = pd.Series(values).rolling(window=period,center=True,min_periods=1).mean().values
    detrended = values - trend
    seasonal = np.zeros(len(values))
    for i in range(period):
        idxs = list(range(i, len(values), period))
        seasonal[idxs] = np.nanmean(detrended[idxs])
    if len(seasonal) >= period:
        seasonal -= np.mean(seasonal[:period])
    return {"trend":trend,"seasonal":seasonal,"residual":values-trend-seasonal}

def forecast_series(series, steps=7, period=7, alpha=0.3):
    values = series.values.astype(float)
    comp = decompose(series, period)
    resid = comp["residual"]; resid = resid[~np.isnan(resid)]
    pat = comp["seasonal"][-period:] if len(comp["seasonal"])>=period else np.zeros(period)
    level = np.mean(values[-period:]) if len(values)>=period else values[-1]
    fc = np.zeros(steps)
    for i in range(steps):
        fc[i] = level + pat[i%period]
        level = alpha*values[-1] + (1-alpha)*level
    rs = np.nanstd(resid) if len(resid)>0 else np.nanstd(values)*0.1
    f = 1.96*(1+np.arange(steps)*0.1)
    return fc, fc-f*rs, fc+f*rs

def predict(df, product, steps=7):
    sub = df[df["product"]==product].sort_values("date")
    if len(sub)<14: return {"product":product,"error":"need more data"}
    s = sub.set_index("date")["price"]
    fc,lo,up = forecast_series(s, steps=steps)
    lp = float(s.values[-1])
    pct = (fc[-1]-lp)/lp*100 if lp>0 else 0
    return {"product":product,"forecast":fc,"lower":lo,"upper":up,"last_price":round(lp,3),"pct_change_7d":round(pct,2)}

def forecast_all(df):
    rows = []
    for p in df["product"].unique():
        r = predict(df, p)
        if "error" not in r:
            rows.append({"product":p,"last_price":r["last_price"],"forecast_7d":round(float(r["forecast"][-1]),3),"lower_7d":round(float(r["lower"][-1]),3),"upper_7d":round(float(r["upper"][-1]),3),"pct_change_7d":r["pct_change_7d"]})
    return pd.DataFrame(rows).sort_values("pct_change_7d",ascending=False)
