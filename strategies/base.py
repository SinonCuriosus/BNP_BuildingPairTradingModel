from abc import ABC, abstractmethod
from typing import Dict, Tuple
import numpy as np
import pandas as pd

class Strategy(ABC):
    allow_short: bool = False
    log_trades: bool = True

    def run(self, prices: pd.DataFrame) -> Dict[str, pd.DataFrame | pd.Series]:
        prices = self._prep_prices(prices)
        self.validate_params()
        indicators = self.compute_indicators(prices)
        signals = self.make_signals(prices, indicators)
        pos_raw, pos_exec = self.build_positions(prices, signals)
        ret, strat_ret, ew = self.compute_returns(prices, pos_exec)
        if self.log_trades:
            self.log_trades_fn(prices, signals, pos_exec)
        return {**indicators, **signals, "position_raw": pos_raw, "position_exec": pos_exec,
                "returns": ret, "strategy_returns": strat_ret, "portfolio_ew_returns": ew}

    def validate_params(self) -> None: return

    @abstractmethod
    def compute_indicators(self, prices: pd.DataFrame) -> Dict[str, pd.DataFrame]: ...
    
    @abstractmethod
    def make_signals(self, prices: pd.DataFrame, indicators: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]: ...

    def build_positions(self, prices, signals) -> Tuple[pd.DataFrame, pd.DataFrame]:
        le, lx = signals["long_entry"], signals["long_exit"]
        se, sx = signals["short_entry"], signals["short_exit"]
        pos = pd.DataFrame(0, index=prices.index, columns=prices.columns, dtype=int)
        for i, dt in enumerate(prices.index):
            if i == 0:
                pos.iloc[i] = np.where(le.loc[dt], 1, np.where(self.allow_short & se.loc[dt], -1, 0))
                continue
            prev = pos.iloc[i-1].values
            open_l, close_l = le.loc[dt].values, lx.loc[dt].values
            open_s, close_s = se.loc[dt].values, sx.loc[dt].values
            cur = prev.copy()
            cur = np.where((prev==1)  & (close_l | open_s), 0, cur)
            if self.allow_short:
                cur = np.where((prev==-1) & (close_s | open_l), 0, cur)
            flat = (cur==0)
            cur = np.where(flat & open_l, 1, cur)
            if self.allow_short:
                cur = np.where(flat & open_s, -1, cur)
            pos.iloc[i] = cur
        return pos, pos.shift(1).fillna(0).astype(int)

    def compute_returns(self, prices, pos_exec):
        ret = prices.pct_change().fillna(0.0)
        strat_ret = pos_exec * ret
        return ret, strat_ret, strat_ret.mean(axis=1)

    def log_trades_fn(self, prices, signals, pos_exec): pass

    @staticmethod
    def _prep_prices(prices: pd.DataFrame) -> pd.DataFrame:
        df = prices.copy()
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"]); df = df.set_index("Date")
        if df.iloc[0].isna().any(): df = df.drop(df.index[0])
        df.index = pd.to_datetime(df.index)
        return df.sort_index().dropna(how="all")