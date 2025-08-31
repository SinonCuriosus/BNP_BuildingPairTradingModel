from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
import pandas as pd
import numpy as np
import statsmodels.api as sm
from .base import Strategy

def zscore(series: pd.Series) -> pd.Series:
    return (series - series.mean()) / series.std()

@dataclass
class PairsZScoreOnlyStrategy(Strategy):
    stock1: str
    stock2: str
    entry_z: float = 2.0            # enter when |z| >= entry_z
    exit_z: float = 0.5             # exit when |z| <= exit_z
    tx_cost_per_leg: float = 0.0005 # 5 bps per leg per trade (0.05%)
    use_rolling_z: bool = False
    z_window: int = 60              # used if use_rolling_z=True

    def _compute_hedge_ratio(self, data: pd.DataFrame) -> float:
        y = data[self.stock1]
        X = sm.add_constant(data[self.stock2])
        model = sm.OLS(y, X, missing="drop").fit()
        return float(model.params[self.stock2])

    def _compute_z(self, spread: pd.Series) -> pd.Series:
        if self.use_rolling_z:
            mu = spread.rolling(self.z_window, min_periods=self.z_window//2).mean()
            sd = spread.rolling(self.z_window, min_periods=self.z_window//2).std(ddof=0)
            return (spread - mu) / sd
        return zscore(spread)

    def _max_drawdown(self,eq: pd.Series) -> float:
        if eq.empty: return 0.0
        rm = eq.cummax()
        dd = eq / rm - 1.0
        return float(-dd.min())  # positive fraction

    def execute(
        self,
        data: pd.DataFrame,
        close_at_end: bool = False,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        max_bars_in_trade: int | None = None,
    ) -> Dict[str, Any]:



        if self.stock1 not in data.columns or self.stock2 not in data.columns:
            raise ValueError(f"Data must contain {self.stock1} and {self.stock2}")

        # --- prices & simple returns
        prices = data[[self.stock1, self.stock2]].copy().dropna()
        prices.index = pd.to_datetime(prices.index)
        rets = prices.pct_change().fillna(0.0)

        # --- hedge ratio & z-score on spread
        beta = float(self._compute_hedge_ratio(prices))
        spread = prices[self.stock1] - beta * prices[self.stock2]
        z = self._compute_z(spread)

        # --- raw event signals from z (NO EMA gate)
        raw = pd.Series(0, index=prices.index, dtype=int)
        raw[z >=  self.entry_z] = -1   # short stock1, long stock2
        raw[z <= -self.entry_z] =  1   # long stock1, short stock2

        # --- exit by z
        exits_z = (z.abs() <= self.exit_z)

        # --- build carried position: hold until any exit hits
        pos = raw.replace(0, np.nan).ffill()
        pos[exits_z] = 0
        pos = pos.fillna(0).astype(int)

        # --- per-bar pair return and signed PnL (before costs)
        pair_ret = rets[self.stock1] - beta * rets[self.stock2]
        signed_pair_ret = pos * pair_ret

        # --- open-trade return (since last entry) for stops
        entries = (pos != 0) & (pos.shift(1).fillna(0) == 0)  # 0 -> nonzero
        trade_id = entries.cumsum().where(pos != 0)           # NA when flat
        cum_since_entry = (1.0 + signed_pair_ret.where(pos != 0)).groupby(trade_id).cumprod() - 1.0
        open_ret = cum_since_entry.where(pos != 0, 0.0).fillna(0.0)

        # --- optional time stop
        if max_bars_in_trade is not None:
            bars_in = pos.where(pos != 0).groupby(trade_id).cumcount() + 1
            time_stop_hit = (bars_in >= int(max_bars_in_trade)) & (pos != 0)
        else:
            time_stop_hit = pd.Series(False, index=pos.index)

        # --- PnL-based stops
        stop_loss_hit = (open_ret <= -float(stop_loss_pct)) & (pos != 0) if stop_loss_pct is not None else pd.Series(False, index=pos.index)
        take_profit_hit = (open_ret >=  float(take_profit_pct)) & (pos != 0) if take_profit_pct is not None else pd.Series(False, index=pos.index)

        # --- force exits when any condition hits
        force_exit = exits_z | stop_loss_hit | take_profit_hit | time_stop_hit
        if force_exit.any():
            pos = pos.copy()
            pos[force_exit] = 0
            pos = pos.astype(int)

        # --- trading costs on position changes (2 legs per change; flip costs 4 legs)
        trades = pos.diff().abs().fillna(pos.abs().iloc[0])
        cost = trades * (2 * self.tx_cost_per_leg)

        # --- final pnl/equity (daily series)
        pnl = (pos * pair_ret) - cost
        equity = (1.0 + pnl).cumprod()

        # --- recompute trade blocks AFTER applying forced exits (for trade-level stats)
        entries2 = (pos != 0) & (pos.shift(1).fillna(0) == 0)
        trade_id2 = entries2.cumsum().where(pos != 0)

        # Closed-trade compounded returns (exclude last if still open)
        trade_returns = (
            (1.0 + pnl.where(pos != 0))
            .groupby(trade_id2)
            .prod()
            .dropna()
            .subtract(1.0)
        )
        # Drop the last trade if it's still open
        if int(pos.iloc[-1]) != 0 and not trade_returns.empty:
            last_id = int(trade_id2.iloc[-1])
            if last_id in trade_returns.index:
                trade_returns = trade_returns.drop(last_id, errors="ignore")

        n_trades = int(trade_returns.shape[0])
        n_pos_trades = int((trade_returns > 0).sum())
        pos_trade_rate = float(n_pos_trades / n_trades) if n_trades > 0 else 0.0
        avg_trade_ret = float(trade_returns.mean()) if n_trades > 0 else 0.0
        std_trade_ret = float(trade_returns.std(ddof=0)) if n_trades > 0 else 0.0

        # --- current open trade snapshot (mark-to-market at last prices)
        current_open_trade = None
        last_pos = int(pos.iloc[-1])
        if last_pos != 0:
            last_entry_time = entries2[entries2].index[-1] if entries2.any() else prices.index[-1]
            current_open_trade = {
                "since": pd.Timestamp(last_entry_time),
                "position": last_pos,  # +1: long A/short B; -1: short A/long B
                "unrealized_return_%": float(((1.0 + pnl.where(pos != 0)).groupby(trade_id2).cumprod().iloc[-1] - 1.0) * 100.0),
                "last_prices": {
                    self.stock1: float(prices[self.stock1].iloc[-1]),
                    self.stock2: float(prices[self.stock2].iloc[-1]),
                },
                "z_last": float(z.iloc[-1]),
            }

        # --- optionally “close now” (apply exit cost at last bar)
        equity_close_now = None
        if close_at_end and last_pos != 0:
            pnl_close = pnl.copy()
            pnl_close.iloc[-1] -= (2 * self.tx_cost_per_leg) * abs(last_pos)
            equity_close_now = (1.0 + pnl_close).cumprod()

        # --- daily stats and Sharpe
        avg = float(pnl.mean())                # mean daily pnl (decimal)
        vol = float(pnl.std(ddof=0))           # std daily pnl (decimal)
        sharpe_daily_ratio = float(avg / (vol + 1e-12))
        sharpe_annual = float(sharpe_daily_ratio * np.sqrt(252.0))

        stats = {
            "n_days": int(len(pnl)),
            "beta": beta,
            "final_equity": float(equity.iloc[-1]),
            "total_return_%": (float(equity.iloc[-1]) - 1.0) * 100.0,

            # requested daily stats
            "avg_daily_return": avg,
            "vol_daily_return": vol,
            "sharpe_daily": sharpe_daily_ratio,    # (mean / vol)
            "sharpe_annual": sharpe_annual,        # sharpe_daily * sqrt(252)

            "max_drawdown_%": self._max_drawdown(equity) * 100.0,

            # “trades” here = count of position changes (legacy)
            "trades": int(trades.sum()),

            # trade-level metrics (closed trades only)
            "n_trades": n_trades,
            "positive_trades": n_pos_trades,
            "positive_trade_rate": pos_trade_rate,        # fraction in [0,1]
            "avg_trade_return_%": avg_trade_ret * 100.0,  # percent
            "std_trade_return_%": std_trade_ret * 100.0,  # percent

            "open_position": last_pos,
            "stops": {
                "stop_loss_pct": stop_loss_pct,
                "take_profit_pct": take_profit_pct,
                "max_bars_in_trade": max_bars_in_trade,
            },
        }

        return {
            "signals": raw,                 # +1/-1/0 events (z-only)
            "positions": pos,               # carried state
            "pnl": pnl,
            "equity": equity,
            "stats": stats,
            "hedge_ratio": beta,
            "z": z,
            "open_trade_return": (1.0 + pnl.where(pos != 0)).groupby(trade_id2).cumprod() - 1.0,
            "current_open_trade": current_open_trade,
            "equity_close_now": equity_close_now,
            "stops_triggered": {
                "stop_loss": stop_loss_hit,
                "take_profit": take_profit_hit,
                "time_stop": time_stop_hit,
            },
            "trade_returns": trade_returns,  # closed-trade compounded returns (decimal)
        }

