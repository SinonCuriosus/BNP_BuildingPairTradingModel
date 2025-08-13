import yfinance as yf
from DataStructures import TimePeriod, Enterprise
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

def load_universe(tickers, start="2020-01-01", end="2025-01-01", force=False, save_meta=True):
    series = []
    for t in tickers:
        e = Enterprise(t)
        if save_meta:
            try:
                e.fetch_meta(force=False)
            except Exception as ex:
                print(f"[meta warn] {t}: {ex}")
        try:
            s = e.fetch_close_prices(start=start, end=end, force=force)
            series.append(s)
        except Exception as ex:
            print(f"[price warn] {t}: {ex}")
    if not series:
        raise RuntimeError("No ticker data loaded.")
    return pd.concat(series, axis=1).sort_index()

def prices_data_collec_phase(prices):
    weekly = prices.resample("W-FRI").last().ffill()

    plt.figure(figsize=(12, 6))
    weekly.plot(ax=plt.gca())
    plt.title("Weekly Close (last trading day each week)")
    plt.xlabel("Week")
    plt.ylabel("Close Price")
    plt.legend(title="Ticker")
    plt.tight_layout()
    plt.show()
    

def ema(df: pd.DataFrame, span: int) -> pd.DataFrame:
    return df.ewm(span=span, adjust=False).mean()

def rsi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    # Wilder's RSI (uses exponential smoothing)
    delta = df.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)

    # Wilder smoothing (alpha = 1/window)
    roll_up = up.ewm(alpha=1/window, adjust=False).mean()
    roll_down = down.ewm(alpha=1/window, adjust=False).mean()

    rs = roll_up / roll_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

def build_strategy(prices: pd.DataFrame, ema_short=7, ema_long=30, rsi_window=14, entry_rsi=40, exit_rsi=60):
    prices = prices.copy()
    prices.index = pd.to_datetime(prices.index)

    ema_s = ema(prices, ema_short)
    ema_l = ema(prices, ema_long)
    rsi14 = rsi(prices, rsi_window)

    # --- Entry/Exit rules (your spec) ---
    entry = (prices < ema_l) & (prices < ema_s) & (rsi14 < entry_rsi)
    exit_  = (prices > ema_l) & (prices > ema_s) & (rsi14 > exit_rsi)

    # --- Build long-only position state (0/1) ---
    # +1 when entry, -1 when exit, then cumulative sum, clipped to [0,1]
    toggles = entry.astype(int) - exit_.astype(int)
    position = toggles.cumsum().clip(lower=0, upper=1)

    # Prevent accidental starting in position if first row toggles negative
    position.iloc[0] = np.where(entry.iloc[0], 1, 0)

    # Optional: only enter **after** the signal day (avoid lookahead)
    # You buy at next bar open/close; simplest is to apply a 1-day delay:
    position_exec = position.shift(1).fillna(0)

    # --- Returns ---
    ret = prices.pct_change().fillna(0.0)
    strat_ret = position_exec * ret  # per ticker daily strategy returns
    # If you want an equal-weighted portfolio of all signals:
    ew_port_ret = strat_ret.mean(axis=1)

    out = {
        "ema_short": ema_s,
        "ema_long": ema_l,
        "rsi": rsi14,
        "entry": entry,
        "exit": exit_,
        "position_raw": position,
        "position_exec": position_exec,  # shifted by 1 bar for execution
        "returns": ret,
        "strategy_returns": strat_ret,
        "portfolio_ew_returns": ew_port_ret,
    }
    return out

if __name__ == "__main__":
    DATA_ROOT = Path("data/market")

    tickers = [
        "ASML.AS", "BESI.AS", "IFX.DE", "HSBA.L", "INGA.AS",
        "ISP.MI", "ABI.BR", "RI.PA", "BN.PA", "TSCO.L"
    ]
    prices = load_universe(tickers, start="2024-01-01", end="2025-01-01", force=False, save_meta=True)

    (DATA_ROOT).mkdir(parents=True, exist_ok=True)
    prices.to_csv(DATA_ROOT / "universe_close_2020_2025.csv")

    # 2/3. Data Collection: Method to check this phase
    # prices_data_collec_phase(prices)

    res = build_strategy(prices,ema_short=7, ema_long=30, rsi_window=30,entry_rsi=30, exit_rsi=60)

    # Inspect signals for one ticker, e.g., "TSCO.L"
    ticker = prices.columns[0]  # or choose explicitly
    print("Entries:\n", res["entry"][ticker].loc[res["entry"][ticker]].head())
    print("Exits:\n",   res["exit"][ticker].loc[res["exit"][ticker]].head())

    print("check performance")
    # Quick performance check (equal-weighted)
    cum = (1 + res["portfolio_ew_returns"]).cumprod()
    print(cum.tail())



