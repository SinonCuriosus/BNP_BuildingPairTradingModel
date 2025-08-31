import yfinance as yf
from DataStructures import TimePeriod, Enterprise
import numpy as np
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint
from statsmodels.regression.linear_model import OLS
from pathlib import Path
import itertools

Estrategias || TA || HELPER

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
    delta = df.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)

    # smoothing (alpha = 1/window)
    roll_up = up.ewm(alpha=1/window, adjust=False).mean()
    roll_down = down.ewm(alpha=1/window, adjust=False).mean()

    rs = roll_up / roll_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

def prep_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Ensure Date index, sort, and (optionally) forward-fill single-day gaps."""
    df = prices.copy()
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
    df = df.sort_index()
    # Remove days where all tickers are NaN
    df = df.dropna(how='all')
    return df

def regress_alpha_beta(y: pd.Series, x: pd.Series):
    """OLS y = alpha + beta * x, returning (alpha, beta, model)."""
    xy = pd.concat([y, x], axis=1).dropna()
    if len(xy) < 30:
        return np.nan, np.nan, None
    X = sm.add_constant(xy.iloc[:, 1])
    model = OLS(xy.iloc[:, 0], X).fit()
    alpha = model.params['const']
    beta = model.params.iloc[1]
    return alpha, beta, model

def build_spread(y: pd.Series, x: pd.Series, alpha: float, beta: float) -> pd.Series:
    """Spread_t = y_t - (alpha + beta * x_t), aligned on common dates."""
    xy = pd.concat([y, x], axis=1).dropna()
    return xy.iloc[:, 0] - (alpha + beta * xy.iloc[:, 1])

def half_life(spread: pd.Series) -> float:
    """
    Half-life of mean reversion (in trading days) using AR(1) on Δspread = θ * spread_{t-1} + ε.
    θ < 0 indicates mean reversion. Half-life = -ln(2) / θ.
    """
    s = spread.dropna()
    if len(s) < 60:
        return np.nan
    s_lag = s.shift(1).dropna()
    delta = (s - s_lag).dropna()
    s_lag = s_lag.loc[delta.index]
    X = sm.add_constant(s_lag)
    model = OLS(delta, X).fit()
    theta = model.params.iloc[1]
    return (-np.log(2) / theta) if theta < 0 else np.inf

def rolling_beta_cv(y: pd.Series, x: pd.Series, window: int = 60) -> float:
    """Coefficient of variation of rolling β (std/mean). Lower is more stable."""
    xy = pd.concat([y, x], axis=1).dropna()
    if len(xy) < window + 10:
        return np.nan
    betas = []
    for i in range(window, len(xy)):
        X = sm.add_constant(xy.iloc[i-window:i, 1])
        model = OLS(xy.iloc[i-window:i, 0], X).fit()
        betas.append(model.params.iloc[1])
    betas = np.array(betas)
    mean_beta = np.mean(betas)
    if len(betas) == 0 or mean_beta == 0:
        return np.nan
    return float(np.std(betas, ddof=1) / abs(mean_beta))

def pair_stats(prices: pd.DataFrame, a: str, b: str, use_logs: bool = True) -> dict:
    """
    Compute metrics for pair (a,b):
      - Engle–Granger p-value
      - alpha, beta
      - rolling beta CV (stability)
      - half-life (days)
    """
    # Align, optionally log-transform (still on levels for cointegration)
    A = prices[a].copy()
    B = prices[b].copy()
    if use_logs:
        A = np.log(A)
        B = np.log(B)
    df_pair = pd.concat([A, B], axis=1).dropna()
    if len(df_pair) < 90:
        return {"pair": f"{a}/{b}", "n_obs": len(df_pair), "p_value": np.nan,
                "alpha": np.nan, "beta": np.nan, "beta_cv": np.nan,
                "half_life": np.nan, "score": 0}

    # Cointegration test on (log) price levels
    _, p_value, _ = coint(df_pair.iloc[:, 0], df_pair.iloc[:, 1])

    # Hedge ratio and spread
    alpha, beta, _ = regress_alpha_beta(df_pair.iloc[:, 0], df_pair.iloc[:, 1])
    if np.isnan(beta):
        return {"pair": f"{a}/{b}", "n_obs": len(df_pair), "p_value": p_value,
                "alpha": np.nan, "beta": np.nan, "beta_cv": np.nan,
                "half_life": np.nan, "score": 0}

    spread = build_spread(df_pair.iloc[:, 0], df_pair.iloc[:, 1], alpha, beta)

    # Rolling beta stability (use original (log) prices to avoid look-ahead)
    beta_cv = rolling_beta_cv(df_pair.iloc[:, 0], df_pair.iloc[:, 1], window=60)

    # Half-life from spread
    hl = half_life(spread)

    # Binary score on three gates tuned to your 1w–1m horizon
    cointegration_ok = (p_value < 0.05)
    beta_stable = (beta_cv < 0.2) if pd.notna(beta_cv) else False
    hl_ok = (3 <= hl <= 20) if np.isfinite(hl) else False

    score = int(cointegration_ok) + int(beta_stable) + int(hl_ok)

    return {
        "pair": f"{a}/{b}",
        "n_obs": int(len(df_pair)),
        "p_value": float(p_value),
        "alpha": float(alpha),
        "beta": float(beta),
        "beta_cv": float(beta_cv) if pd.notna(beta_cv) else np.nan,
        "half_life": float(hl) if np.isfinite(hl) else np.inf,
        "cointegration_ok": cointegration_ok,
        "beta_stable": beta_stable,
        "hl_ok": hl_ok,
        "score": int(score),
    }

def rank_all_pairs(prices: pd.DataFrame, tickers: list[str], use_logs: bool = True) -> pd.DataFrame:
    prices = prep_prices(prices)
    results = []
    for a, b in itertools.combinations(tickers, 2):
        stats = pair_stats(prices, a, b, use_logs=use_logs)
        results.append(stats)
    df = pd.DataFrame(results)
    # Sort: best score desc, then lowest p-value, then shortest half-life
    df = df.sort_values(by=["score", "p_value", "half_life"], ascending=[False, True, True]).reset_index(drop=True)
    return df

def build_strategy(
    prices: pd.DataFrame,
    ema_short=7,
    ema_long=30,
    rsi_window=14,
    # Long thresholds
    long_entry_rsi=40,
    long_exit_rsi=60,
    # Short thresholds (independent from long)
    short_entry_rsi=60,
    short_exit_rsi=40,
    allow_short=False
):
    """
    Long entry when:  price < EMA_long & price < EMA_short & RSI < long_entry_rsi
    Long exit  when:  price > EMA_long & price > EMA_short & RSI > long_exit_rsi

    Short entry when: price > EMA_long & price > EMA_short & RSI > short_entry_rsi
    Short exit  when: price < EMA_long & price < EMA_short & RSI < short_exit_rsi
    """


    # --- validation ---
    for v in (long_entry_rsi, long_exit_rsi, short_entry_rsi, short_exit_rsi):
        if not (0 <= v <= 100):
            raise ValueError("All RSI thresholds must be in [0, 100].")

    prices = prices.copy()
    if prices.iloc[0].isna().any():
        prices = prices.drop(prices.index[0])
    prices.index = pd.to_datetime(prices.index)

    ema_s = ema(prices, ema_short)
    ema_l = ema(prices, ema_long)
    rsi14 = rsi(prices, rsi_window)

    # --- Signals ---
    long_entry = (prices < ema_l) & (prices < ema_s) & (rsi14 < long_entry_rsi)
    long_exit  = (prices > ema_l) & (prices > ema_s) & (rsi14 > long_exit_rsi)

    if allow_short:
        short_entry = (prices > ema_l) & (prices > ema_s) & (rsi14 > short_entry_rsi)
        short_exit  = (prices < ema_l) & (prices < ema_s) & (rsi14 < short_exit_rsi)
    else:
        short_entry = pd.DataFrame(False, index=prices.index, columns=prices.columns)
        short_exit  = pd.DataFrame(False, index=prices.index, columns=prices.columns)

    # --- Position state in {-1,0,+1} ---
    pos = pd.DataFrame(0, index=prices.index, columns=prices.columns, dtype=int)
    for i, dt in enumerate(prices.index):
        if i == 0:
            new = np.where(long_entry.loc[dt], 1,
                  np.where(allow_short & short_entry.loc[dt], -1, 0))
            pos.iloc[i] = new
            continue

        prev = pos.iloc[i-1].values
        open_long  = long_entry.loc[dt].values
        close_long = long_exit.loc[dt].values
        open_short = short_entry.loc[dt].values
        close_short= short_exit.loc[dt].values

        cur = prev.copy()

        # exits first; also allow flip on opposite entry
        cur = np.where((prev ==  1) & (close_long | open_short), 0, cur)
        if allow_short:
            cur = np.where((prev == -1) & (close_short | open_long), 0, cur)

        # entries if flat
        flat = cur == 0
        cur = np.where(flat & open_long,  1, cur)
        if allow_short:
            cur = np.where(flat & open_short, -1, cur)

        pos.iloc[i] = cur

    # execute next bar to avoid lookahead
    pos_exec = pos.shift(1).fillna(0).astype(int)

    # --- Logging trades ---
    for ticker in prices.columns:
        prev_pos = 0
        for dt in prices.index:
            p = pos_exec.at[dt, ticker]
            if prev_pos == 0 and p == 1 and long_entry.at[dt, ticker]:
                print(f"{dt.date()} | BUY           {ticker} at {prices.at[dt, ticker]:.2f}")
            elif prev_pos == 1 and p == 0 and long_exit.at[dt, ticker]:
                print(f"{dt.date()} | SELL          {ticker} at {prices.at[dt, ticker]:.2f}")
            elif allow_short and prev_pos == 0 and p == -1 and short_entry.at[dt, ticker]:
                print(f"{dt.date()} | SELL SHORT    {ticker} at {prices.at[dt, ticker]:.2f}")
            elif allow_short and prev_pos == -1 and p == 0 and short_exit.at[dt, ticker]:
                print(f"{dt.date()} | BUY TO COVER  {ticker} at {prices.at[dt, ticker]:.2f}")
            prev_pos = p

    # --- Returns ---
    ret = prices.pct_change().fillna(0.0)
    strat_ret = pos_exec * ret               # -1 flips return sign on shorts
    ew_port_ret = strat_ret.mean(axis=1)

    return {
        "ema_short": ema_s,
        "ema_long": ema_l,
        "rsi": rsi14,
        "long_entry": long_entry,
        "long_exit": long_exit,
        "short_entry": short_entry,
        "short_exit": short_exit,
        "position_raw": pos,
        "position_exec": pos_exec,
        "returns": ret,
        "strategy_returns": strat_ret,
        "portfolio_ew_returns": ew_port_ret,
    }

if __name__ == "__main__":
    DATA_ROOT = Path("data/market")

    tickers = ["ASML.AS", "BESI.AS", "IFX.DE", "HSBA.L", "INGA.AS", "ISP.MI", "ABI.BR", "RI.PA", "BN.PA", "TSCO.L"]
    prices = load_universe(tickers, start="2024-01-01", end="2025-01-01", force=False, save_meta=True)

    (DATA_ROOT).mkdir(parents=True, exist_ok=True)
    prices.to_csv(DATA_ROOT / "universe_close_2020_2025.csv")

    
    # 2/3. Data Collection: Method to check this phase, shows individual prices
    # prices_data_collec_phase(prices) # prices[["ASML.AS", "BESI.AS"]])

    # 4. Statistical Analysis: Determine what is the best method for medium to long term pair trading
    pairs_df = rank_all_pairs(prices, tickers, use_logs=True)
    #df_filtered = pairs_df[pairs_df['cointegration_ok'] == True]
    print(pairs_df.head(5))
    
    # 5/6. Trading Strategy/Backtesting (explored and discussed in README.md https://github.com/SinonCuriosus/BNP_BuildingPairTradingModel)
    res = build_strategy(
    prices[["ASML.AS","BN.PA"]],
    ema_short=TimePeriod.WEEK.to_days(), 
    ema_long=TimePeriod.MONTH.to_days(), 
    rsi_window=50,
    allow_short=True,
    long_entry_rsi=40, 
    long_exit_rsi=60,
    short_entry_rsi=50,
    short_exit_rsi=40
    )
    
    # Alternative pair used using the Fundamental Analysis written in readme.md ["ASML.AS","BESI.AS"]

    # 6. Backtesting (explored and discussed in README.md https://github.com/SinonCuriosus/BNP_BuildingPairTradingModel)
    # (equal-weighted)
    cum = (1 + res["portfolio_ew_returns"]).cumprod()
    print(cum.tail())



