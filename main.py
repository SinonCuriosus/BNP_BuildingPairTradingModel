from pathlib import Path
from DataStructures import TimePeriod
from data.market.universe import load_universe
from analysis.pair_analysis import PairAnalyzer
import pandas as pd

from strategies.ema_rsi import EmaRsiStrategy
from strategies.zscore_only import PairsZScoreOnlyStrategy

from utils.io import prep_prices, fetch_close_prices
from utils.helpers import extract_pair
from utils.report import build_trade_table, print_trade_table, grid_search_pairs_params, summarize_extreme_trades
from utils.plotting import plot_positions_with_z

# ----------------- CONFIG -----------------
DATA_ROOT = Path("data/market"); DATA_ROOT.mkdir(parents=True, exist_ok=True)

TICKERS = ["ASML.AS","BESI.AS","IFX.DE","HSBA.L","INGA.AS","ISP.MI","ABI.BR","RI.PA","BN.PA","TSCO.L"]

UNIVERSE_START = "2020-01-01"   # wide enough to cover train + test
TEST_START     = "2023-01-01"   # cutoff (train < TEST_START, test >= TEST_START)
TEST_END       = "2025-01-01"   # optional end bound for test


if __name__ == "__main__":
    # -------- 1) LOAD UNIVERSE (wide window) --------
    raw = load_universe(TICKERS, start=UNIVERSE_START, end=TEST_END, force=False, save_meta=True)
    prices = prep_prices(raw)
    prices.to_csv(DATA_ROOT / f"universe_close_{UNIVERSE_START}_{TEST_END}.csv")

    # -------- 2) TRAIN/TEST SPLIT --------
    cutoff = pd.Timestamp(TEST_START)
    train_prices = prices.loc[prices.index < cutoff]                  # used ONLY to rank pairs
    test_prices  = prices.loc[(prices.index >= cutoff) & (prices.index < TEST_END)]  # used for backtest

    # -------- 3) RANK ON TRAIN --------
    analyzer = PairAnalyzer(use_logs=True, beta_window=30)
    ranked_pairs = analyzer.rank_pairs(train_prices, TICKERS)
    print("Top ranked pairs (train period):")
    print(ranked_pairs.head())
    s1, s2 = extract_pair(ranked_pairs,ranked_pos=0)
    print(f"\nSelected top pair (trained on < {TEST_START}): {s1} / {s2}")
    pair_prices_test = test_prices[[s1,s2]]

    # Hardcode enterprises to skip compute time: comment above, uncomment below.
    # s1, s2 = ("ASML.AS","BESI.AS")
    # pair_prices_test = test_prices[["ASML.AS","BESI.AS"]]

    # -------- 4) BACKTEST ON TEST --------

    # 1st Assessment Delivery (re-structured)
    # strat = EmaRsiStrategy(
    #     ema_short=TimePeriod.WEEK.to_days(),
    #     ema_long=TimePeriod.MONTH.to_days(),
    #     rsi_window=50,
    #     allow_short=True,
    #     long_entry_rsi=40, long_exit_rsi=60,
    #     short_entry_rsi=50, short_exit_rsi=40,
    # )
    # res = strat.run(pair_prices_test)
    # cum = (1 + res["portfolio_ew_returns"]).cumprod()
    # print(cum.tail())

    strat = PairsZScoreOnlyStrategy(
        stock1=s1, stock2=s2,
        entry_z=2.4, exit_z=0.85, # 3.0 and 0.5 not that good in case in the interview we want to compare
        tx_cost_per_leg=0.0005,   # 5 bps per leg
        use_rolling_z=True,
        z_window=30,
    )

    res = strat.execute(
        data=pair_prices_test,
        stop_loss_pct=0.05,         # cut at -5% since entry
        take_profit_pct=0.45,       # take profit at +45%
        max_bars_in_trade=None,       # (optional) time stop
    )

    # Greedy search using 1) sharpe; 2) entry & exit sharpe ;3) stop loss & gain;
    # best = grid_search_pairs_params(
    #     prices=pair_prices_test,   # your test DataFrame with columns [s1, s2]
    #     s1=s1, s2=s2,
    #     StrategyClass=PairsZScoreOnlyStrategy,
    #     z_window=30, use_rolling_z=True,
    #     entry_grid=tuple(i / 20 for i in range(30, 81)), # 1.5-4.0 step 0.05
    #     exit_grid=tuple(i / 20 for i in range(0, 21)), # 0-1 step 0.05
    #     sl_grid=tuple(i / 20 for i in range(0, 11)), # 0-0.5 step 0.05
    #     tp_grid=tuple(i / 20 for i in range(0, 11)), # 0-0.5 step 0.05
    #     max_bars_in_trade=None,
    #     objective="sharpe_penalized",
    #     dd_limit_pct=20.0,
    # )
    # print("\nTop 10 combos:\n")
    # print(best.head(10))

    print(f"\nBacktest summary ({TEST_START}, {TEST_END}):")
    for k, v in res["stats"].items():
        print(f"  {k}: {v}")

    # -------- 5) TRADE TABLE + PLOT --------
    trades = build_trade_table(
        positions=res["positions"],
        prices=pair_prices_test,
        z=res["z"],
        beta=res["hedge_ratio"],
        tx_cost_per_leg=strat.tx_cost_per_leg,
    )

    print(f"\nTrade periods ({TEST_START}, {TEST_END}):")
    print_trade_table(trades)
    extremes = summarize_extreme_trades(trades, k=3, out_dir=None)  # or set a folder path
    print(extremes["top_gains"])
    print(extremes["top_losses"])

    plot_positions_with_z(
        prices=pair_prices_test,
        positions=res["positions"],
        z=res["z"],
        entry_z=strat.entry_z,
        exit_z=strat.exit_z,
        title=f"{s1} /  {s2} - positions & z-score (test ≥ {TEST_START})",
    )