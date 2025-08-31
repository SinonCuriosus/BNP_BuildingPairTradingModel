import numpy as np
import pandas as pd
import itertools
from statsmodels.tsa.stattools import coint
from models.hedge import OLSHedge
from models.stats import half_life, rolling_beta_cv

class PairAnalyzer:
    def __init__(self, use_logs: bool = True, beta_window: int = 60):
        self.use_logs = use_logs
        self.beta_window = beta_window
        self.hedge = OLSHedge()

    def analyze_pair(self, prices: pd.DataFrame, a: str, b: str) -> dict:
        A, B = prices[a].copy(), prices[b].copy()
        if self.use_logs:
            A, B = np.log(A), np.log(B)
        df = pd.concat([A, B], axis=1).dropna()
        if len(df) < 90:
            return {"pair": f"{a}/{b}", "n_obs": len(df), "p_value": np.nan,
                    "alpha": np.nan, "beta": np.nan, "beta_cv": np.nan,
                    "half_life": np.nan, "score": 0}

        _, pval, _ = coint(df.iloc[:,0], df.iloc[:,1])
        alpha, beta, _ = self.hedge.fit(df.iloc[:,0], df.iloc[:,1])
        if np.isnan(beta):
            return {"pair": f"{a}/{b}", "n_obs": len(df), "p_value": float(pval),
                    "alpha": np.nan, "beta": np.nan, "beta_cv": np.nan,
                    "half_life": np.nan, "score": 0}

        spread = self.hedge.spread(df.iloc[:,0], df.iloc[:,1], alpha, beta)
        beta_cv = rolling_beta_cv(df.iloc[:,0], df.iloc[:,1], window=self.beta_window)
        hl = half_life(spread)

        cointegration_ok = (pval < 0.05)
        beta_stable = (beta_cv < 0.2) if pd.notna(beta_cv) else False
        hl_ok = (3 <= hl <= 20) if np.isfinite(hl) else False
        score = int(cointegration_ok) + int(beta_stable) + int(hl_ok)

        return {"pair": f"{a}/{b}", "n_obs": int(len(df)), "p_value": float(pval),
                "alpha": float(alpha), "beta": float(beta),
                "beta_cv": float(beta_cv) if pd.notna(beta_cv) else np.nan,
                "half_life": float(hl) if np.isfinite(hl) else np.inf,
                "cointegration_ok": cointegration_ok, "beta_stable": beta_stable,
                "hl_ok": hl_ok, "score": int(score)}

    def rank_pairs(self, prices: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
        rows = [self.analyze_pair(prices, a, b) for a,b in itertools.combinations(tickers, 2)]
        df = pd.DataFrame(rows)
        return df.sort_values(by=["score","p_value","half_life"], ascending=[False, True, True]).reset_index(drop=True)