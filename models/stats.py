import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.linear_model import OLS

def half_life(spread: pd.Series) -> float:
    s = spread.dropna()
    if len(s) < 60:
        return np.nan
    s_lag = s.shift(1).dropna()
    delta = (s - s_lag).dropna()
    s_lag = s_lag.loc[delta.index]
    X = sm.add_constant(s_lag)
    model = OLS(delta, X).fit()
    theta = float(model.params.iloc[1])
    return (-np.log(2) / theta) if theta < 0 else np.inf

def rolling_beta_cv(y: pd.Series, x: pd.Series, window: int = 60) -> float:
    xy = pd.concat([y, x], axis=1).dropna()
    if len(xy) < window + 10:
        return np.nan
    betas = []
    for i in range(window, len(xy)):
        X = sm.add_constant(xy.iloc[i-window:i, 1])
        model = OLS(xy.iloc[i-window:i, 0], X).fit()
        betas.append(model.params.iloc[1])
    betas = np.asarray(betas, dtype=float)
    if betas.size == 0: return np.nan
    mean_b = float(np.mean(betas))
    if mean_b == 0: return np.nan
    return float(np.std(betas, ddof=1) / abs(mean_b))