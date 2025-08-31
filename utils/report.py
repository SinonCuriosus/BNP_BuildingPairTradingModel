from __future__ import annotations
import pandas as pd
import numpy as np
import itertools

def build_trade_table(
    positions: pd.Series,        # +1 long s1/short s2, -1 short s1/long s2, 0 flat
    prices: pd.DataFrame,        # columns [s1, s2]
    z: pd.Series,                # z-score of spread
    beta: float,                 # hedge ratio used
    tx_cost_per_leg: float = 0.0005,   # 5 bps per leg
) -> pd.DataFrame:
    """
    Returns a per-trade table with start/end, side, days, gross/net return.
    """
    s1, s2 = prices.columns[:2] 
    rets = prices.pct_change().fillna(0)

    trades = []
    in_trade = False
    trade_side = 0
    start_t = None
    for i, t in enumerate(positions.index):
        pos = int(positions.iloc[i])
        if not in_trade and pos != 0:
            in_trade = True
            trade_side = pos
            start_t = t
        elif in_trade and pos == 0:
            end_t = t
            slice_ = slice(start_t, end_t)
            port_ret = trade_side * (rets[s1].loc[slice_] - beta * rets[s2].loc[slice_])
            gross = float((1 + port_ret).prod() - 1)
            cost = 2 * (2 * tx_cost_per_leg)  # entry + exit, 2 legs each
            net = gross - cost
            trades.append({
                "start": start_t,
                "end": end_t,
                "days": int(len(port_ret)),
                "side": f"LONG {s1} / SHORT {s2}" if trade_side == 1 else f"SHORT {s1} / LONG {s2}",
                "entry_z": float(z.loc[start_t]) if start_t in z.index else None,
                "exit_z": float(z.loc[end_t]) if end_t in z.index else None,
                "gross_return_%": gross * 100.0,
                "est_cost_%": cost * 100.0,
                "net_return_%": net * 100.0,
            })
            in_trade = False
            trade_side = 0
            start_t = None

    return pd.DataFrame(trades)


def print_trade_table(df: pd.DataFrame, max_rows: int = 30) -> None:
    if df.empty:
        print("No trades.")
        return
    show = df.copy()
    # compact formatting
    num_cols = ["gross_return_%", "est_cost_%", "net_return_%"]
    show[num_cols] = show[num_cols].round(2)
    show["start"] = pd.to_datetime(show["start"]).dt.date
    show["end"] = pd.to_datetime(show["end"]).dt.date
    print(show.head(max_rows).to_string(index=False))
    if len(show) > max_rows:
        print(f"... ({len(show) - max_rows} more)")


def summarize_extreme_trades(
    trades: pd.DataFrame,
    k: int = 3,
    out_dir: Optional[str | Path] = None,
) -> Dict[str, pd.DataFrame]:
    """
    From a trade table (as built by build_trade_table), extract the top-k winners
    and top-k losers by net_return_%.

    Returns a dict with:
      - 'top_gains': DataFrame with columns [start, end, days, side, net_return_%]
      - 'top_losses': same columns, lowest net_return_% first

    If out_dir is provided, also saves:
      out_dir/top_gains.csv and out_dir/top_losses.csv
    """
    required = {"start", "end", "days", "side", "net_return_%"}
    missing = required - set(trades.columns)
    if missing:
        raise ValueError(f"trades is missing columns: {sorted(missing)}")

    if trades.empty:
        empty = pd.DataFrame(columns=["start","end","days","side","net_return_%"])
        return {"top_gains": empty, "top_losses": empty}

    k = min(int(k), len(trades))
    cols = ["start", "end", "days", "side", "net_return_%"]

    top_gains = trades.nlargest(k, "net_return_%")[cols].reset_index(drop=True)
    top_losses = trades.nsmallest(k, "net_return_%")[cols].reset_index(drop=True)

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        top_gains.to_csv(out_dir / "top_gains.csv", index=False)
        top_losses.to_csv(out_dir / "top_losses.csv", index=False)

    return {"top_gains": top_gains, "top_losses": top_losses}

def grid_search_pairs_params(
    prices: pd.DataFrame,
    s1: str, s2: str,
    StrategyClass,
    z_window: int = 30,
    use_rolling_z: bool = True,
    tx_cost_per_leg: float = 0.0005,
    entry_grid = (1.5, 2.0, 2.5, 3.0),
    exit_grid  = (0.25, 0.5, 0.75, 1.0),
    sl_grid    = (None, 0.03, 0.05, 0.07),
    tp_grid    = (None, 0.06, 0.10, 0.15),
    max_bars_in_trade = None,
    objective = "sharpe_penalized",   # "sharpe", "return", or "sharpe_penalized"
    dd_limit_pct = 20.0               # penalty kicks in beyond this drawdown
) -> pd.DataFrame:
    rows = []
    for entry_z, exit_z in itertools.product(entry_grid, exit_grid):
        if not (exit_z < entry_z):  # valid hysteresis
            continue
        for sl, tp in itertools.product(sl_grid, tp_grid):
            if sl is not None and tp is not None and sl >= tp:
                continue
            strat = StrategyClass(
                stock1=s1, stock2=s2,
                entry_z=entry_z, exit_z=exit_z,
                tx_cost_per_leg=tx_cost_per_leg,
                use_rolling_z=use_rolling_z, z_window=z_window
            )
            res = strat.execute(
                data=prices,
                stop_loss_pct=sl,
                take_profit_pct=tp,
                max_bars_in_trade=max_bars_in_trade,
            )
            st = res["stats"]
            sharpe = st["sharpe_daily"]
            retpct = st["total_return_%"]
            ddpct  = st["max_drawdown_%"]
            trades = st["number_of_position_changes"]

            if objective == "sharpe":
                score = sharpe
            elif objective == "return":
                score = retpct
            else:  # sharpe_penalized
                # penalty if drawdown exceeds dd_limit_pct
                penalty = max(0.0, (ddpct - dd_limit_pct) / 10.0)
                score = sharpe - penalty

            rows.append({
                "entry_z": entry_z, "exit_z": exit_z,
                "stop_loss_pct": sl, "take_profit_pct": tp,
                "z_window": z_window, "use_rolling_z": use_rolling_z,
                "sharpe": sharpe, "total_return_%": retpct,
                "max_drawdown_%": ddpct, "number_of_position_changes": trades,
                "score": score,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No parameter combinations evaluated (check grids/constraints).")
    df = df.sort_values(by=["score", "sharpe", "total_return_%"], ascending=[False, False, False]).reset_index(drop=True)
    return df