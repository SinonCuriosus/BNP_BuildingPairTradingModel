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

        # --- guards & prep
        if self.stock1 not in data.columns or self.stock2 not in data.columns:
            raise ValueError(f"Data must contain {self.stock1} and {self.stock2}")

        prices = data[[self.stock1, self.stock2]].copy().dropna()
        prices.index = pd.to_datetime(prices.index)
        rets = prices.pct_change().fillna(0.0)

        # --- hedge ratio & spread z
        beta = float(self._compute_hedge_ratio(prices))
        spread = prices[self.stock1] - beta * prices[self.stock2]
        z = self._compute_z(spread)

        # --- entries from z (no EMA gate)
        raw = pd.Series(0, index=prices.index, dtype=int)
        raw[z >=  self.entry_z] = -1    # short A / long B
        raw[z <= -self.entry_z] =  1    # long  A / short B

        # --- exit by z band
        exits_z = (z.abs() <= self.exit_z)

        # --- carry position until exit
        pos = raw.replace(0, np.nan).ffill()
        pos[exits_z] = 0
        pos = pos.fillna(0).astype(int)

        # --- per-bar pair return & signed pnl (pre-cost)
        pair_ret = rets[self.stock1] - beta * rets[self.stock2]
        signed_pair_ret = pos * pair_ret

        # --- open-trade return since entry (for stops)
        entries = (pos != 0) & (pos.shift(1).fillna(0) == 0)   # 0 -> nonzero
        trade_id = entries.cumsum().where(pos != 0)            # NaN when flat
        cum_since_entry = (1.0 + signed_pair_ret.where(pos != 0)).groupby(trade_id).cumprod() - 1.0
        open_ret = cum_since_entry.where(pos != 0, 0.0).fillna(0.0)

        # --- optional time stop
        if max_bars_in_trade is not None:
            bars_in = pos.where(pos != 0).groupby(trade_id).cumcount() + 1
            time_stop_hit = (bars_in >= int(max_bars_in_trade)) & (pos != 0)
        else:
            time_stop_hit = pd.Series(False, index=pos.index)

        # --- PnL-based stops
        stop_loss_hit = (open_ret <= -float(stop_loss_pct)) & (pos != 0) if stop_loss_pct is not None \
                        else pd.Series(False, index=pos.index)
        take_profit_hit = (open_ret >=  float(take_profit_pct)) & (pos != 0) if take_profit_pct is not None \
                        else pd.Series(False, index=pos.index)

        # --- force exits
        force_exit = exits_z | stop_loss_hit | take_profit_hit | time_stop_hit
        if force_exit.any():
            pos = pos.copy()
            pos[force_exit] = 0
            pos = pos.astype(int)

        # --- trading costs (2 legs per change; flips cost 4 legs)
        position_changes = pos.diff().abs().fillna(pos.abs().iloc[0])
        cost = position_changes * (2 * self.tx_cost_per_leg)

        # --- final daily pnl & equity
        pnl = (pos * pair_ret) - cost
        equity = (1.0 + pnl).cumprod()

        # --- recompute trade blocks after exits (for trade-level stats)
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
        if int(pos.iloc[-1]) != 0 and not trade_returns.empty:
            last_id = int(trade_id2.iloc[-1])
            trade_returns = trade_returns.drop(last_id, errors="ignore")

        # Build trade table (entry, exit, bars, direction, return)
        mask_in_pos = (pos != 0)
        grouped = pnl.where(mask_in_pos).groupby(trade_id2, dropna=True)
        trades_df = grouped.apply(lambda s: pd.Series({
            "return": (1.0 + s).prod() - 1.0,   # net, includes costs
            "entry":  s.index[0],
            "exit":   s.index[-1],
            "bars":   len(s),
        }))
        if not trades_df.empty:
            trades_df["direction"] = trades_df["entry"].apply(lambda ts: int(pos.loc[ts]))
            if int(pos.iloc[-1]) != 0:
                last_id = int(trade_id2.iloc[-1])
                trades_df = trades_df.drop(last_id, errors="ignore")

        # Top 3 wins / losses
        top_wins_df   = trades_df.nlargest(3, "return") if not trades_df.empty else trades_df
        top_losses_df = trades_df.nsmallest(3, "return") if not trades_df.empty else trades_df

        def _to_list(df: pd.DataFrame):
            return [
                {
                    "trade_id": int(idx),
                    "entry": pd.Timestamp(row["entry"]),
                    "exit":  pd.Timestamp(row["exit"]),
                    "bars":  int(row["bars"]),
                    "direction": int(row["direction"]),
                    "return_%": float(row["return"] * 100.0),
                }
                for idx, row in df.iterrows()
            ]

        top_wins   = _to_list(top_wins_df)
        top_losses = _to_list(top_losses_df)

        # --- current open trade snapshot
        current_open_trade = None
        last_pos = int(pos.iloc[-1])
        if last_pos != 0:
            # unrealized return of the ongoing trade (since its entry)
            open_cum = (1.0 + pnl.where(pos != 0)).groupby(trade_id2).cumprod() - 1.0
            last_entry_time = entries2[entries2].index[-1] if entries2.any() else prices.index[-1]
            current_open_trade = {
                "since": pd.Timestamp(last_entry_time),
                "position": last_pos,  # +1 long A/short B; -1 short A/long B
                "unrealized_return_%": float(open_cum.iloc[-1] * 100.0) if not open_cum.empty else 0.0,
                "last_prices": {
                    self.stock1: float(prices[self.stock1].iloc[-1]),
                    self.stock2: float(prices[self.stock2].iloc[-1]),
                },
                "z_last": float(z.iloc[-1]),
            }

        # --- optional “close now” (apply exit cost at last bar)
        equity_close_now = None
        if close_at_end and last_pos != 0:
            pnl_close = pnl.copy()
            pnl_close.iloc[-1] -= (2 * self.tx_cost_per_leg) * abs(last_pos)
            equity_close_now = (1.0 + pnl_close).cumprod()

        # --- daily stats & Sharpe
        avg = float(pnl.mean())
        vol = float(pnl.std(ddof=0))
        sharpe_daily_ratio = float(avg / (vol + 1e-12))
        sharpe_annual = float(sharpe_daily_ratio * np.sqrt(252.0))

        # per-trade metrics (closed trades only)
        n_trades = int(trade_returns.shape[0])
        n_pos_trades = int((trade_returns > 0).sum())
        pos_trade_rate = float(n_pos_trades / n_trades) if n_trades > 0 else 0.0
        avg_trade_ret = float(trade_returns.mean()) if n_trades > 0 else 0.0
        std_trade_ret = float(trade_returns.std(ddof=0)) if n_trades > 0 else 0.0

        stats = {
            "n_days": int(len(pnl)),
            "beta": beta,
            "final_equity": float(equity.iloc[-1]),
            "total_return_%": (float(equity.iloc[-1]) - 1.0) * 100.0,

            "avg_daily_return": avg,
            "vol_daily_return": vol,
            "sharpe_daily": sharpe_daily_ratio,
            "sharpe_annual": sharpe_annual,

            "max_drawdown_%": self._max_drawdown(equity) * 100.0,

            "position_changes": int(position_changes.sum()),  # used for costs

            "n_trades": n_trades,                   # closed trades count
            "positive_trades": n_pos_trades,
            "positive_trade_rate": pos_trade_rate,  # in [0,1]
            "avg_trade_return_%": avg_trade_ret * 100.0,
            "std_trade_return_%": std_trade_ret * 100.0,

            "top_wins": top_wins,
            "top_losses": top_losses,

            "open_position": last_pos,
            "stops": {
                "stop_loss_pct": stop_loss_pct,
                "take_profit_pct": take_profit_pct,
                "max_bars_in_trade": max_bars_in_trade,
            },
        }

        return {
            "signals": raw,                       # +1/-1/0 events (z-only)
            "positions": pos,                     # carried state
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
            "trade_returns": trade_returns,       # closed-trade net returns (decimal)
            "trades_table": trades_df,            # entry/exit/bars/dir/return per closed trade
        }