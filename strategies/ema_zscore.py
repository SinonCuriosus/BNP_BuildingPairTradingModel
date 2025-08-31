from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
import pandas as pd
import statsmodels.api as sm
from indicators.ema import EMA
from .base import Strategy

@dataclass
class EmaZScorePair(Strategy):
    stock1: str
    stock2: str
    entry_z: float = 2.0
    exit_z: float = 0.5
    z_lookback: int = 60
    tx_cost_per_leg: float = 0.0005
    ema_span: int = 7
    slope_window: int = 7
    symmetric_gate: bool = True
    allow_short: bool = True

    _beta: float = 0.0
    _z: pd.Series | None = None
    _pair_ret: pd.Series | None = None
    _ema_df: pd.DataFrame | None = None
    _slope_df: pd.DataFrame | None = None

    def validate_params(self) -> None:
        if self.entry_z <= 0 or self.exit_z < 0 or self.entry_z <= self.exit_z:
            raise ValueError("Require entry_z > exit_z >= 0.")
        if self.z_lookback < 20:
            raise ValueError("z_lookback should be reasonably large (e.g., 60).")
        if self.slope_window < 2:
            raise ValueError("slope_window must be >= 2.")

    def compute_indicators(self, prices: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        a, b = self.stock1, self.stock2
        X = sm.add_constant(prices[b])
        beta = sm.OLS(prices[a], X, missing="drop").fit().params[b]
        self._beta = float(beta)

        spread = prices[a] - self._beta * prices[b]
        mu = spread.rolling(self.z_lookback).mean()
        sd = spread.rolling(self.z_lookback).std(ddof=0)
        z = (spread - mu) / sd.replace(0, pd.NA)
        self._z = z

        rets = prices.pct_change().fillna(0.0)
        self._pair_ret = rets[a] - self._beta * rets[b]

        self._ema_df = EMA(self.ema_span).compute(prices)
        self._slope_df = self._ema_df.diff(self.slope_window - 1)

        return {
            "z": z.to_frame("z"),
            "pair_ret": self._pair_ret.to_frame("pair_ret"),
            "ema": self._ema_df,
            "ema_slope": self._slope_df,
        }

    def make_signals(self, prices: pd.DataFrame, indicators: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        a, b = self.stock1, self.stock2
        idx = prices.index
        cols = [a, b]
        le = pd.DataFrame(False, index=idx, columns=cols)
        lx = pd.DataFrame(False, index=idx, columns=cols)
        se = pd.DataFrame(False, index=idx, columns=cols)
        sx = pd.DataFrame(False, index=idx, columns=cols)

        z = indicators["z"]["z"]
        slope = indicators["ema_slope"]
        slope_a = slope[a]; slope_b = slope[b]

        # Pair-long gate: A EMA slope > 0 AND B EMA slope < 0
        allow_plus1 = (slope_a > 0) & (slope_b < 0)
        # Pair-short gate: symmetric or unrestricted
        if self.symmetric_gate:
            allow_minus1 = (slope_a < 0) & (slope_b > 0)
        else:
            allow_minus1 = pd.Series(True, index=idx)

        # Raw z events
        long_pair  = (z <= -self.entry_z) & allow_plus1
        short_pair = (z >=  self.entry_z) & allow_minus1

        # Encode into per-ticker signals
        le.loc[long_pair, a] = True
        se.loc[long_pair, b] = True

        se.loc[short_pair, a] = True
        le.loc[short_pair, b] = True

        exit_pair = (z.abs() <= self.exit_z)
        lx.loc[exit_pair, cols] = True
        sx.loc[exit_pair, cols] = True

        return {"long_entry": le, "long_exit": lx, "short_entry": se, "short_exit": sx}

    def compute_returns(self, prices: pd.DataFrame, pos_exec: pd.DataFrame):
        a, b = self.stock1, self.stock2
        if self._pair_ret is None:
            rets = prices.pct_change().fillna(0.0)
            self._pair_ret = rets[a] - self._beta * rets[b]

        pos_pair = pos_exec[a].astype(int)
        trades = pos_pair.diff().abs().fillna(pos_pair.abs().iloc[0])
        cost = trades * (2 * self.tx_cost_per_leg)

        strat = pos_pair * self._pair_ret - cost
        ret_df = pd.DataFrame({"PAIR": self._pair_ret})
        strat_df = pd.DataFrame({"PAIR": strat})
        ew_series = strat_df["PAIR"]

        return ret_df, strat_df, ew_series