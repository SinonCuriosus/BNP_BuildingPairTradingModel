from pathlib import Path
from DataStructures import TimePeriod
from data.market.universe import load_universe
from utils.io import prep_prices
from analysis.pair_analysis import PairAnalyzer
from strategies.ema_rsi import EmaRsiStrategy

if __name__ == "__main__":
    DATA_ROOT = Path("data/market"); DATA_ROOT.mkdir(parents=True, exist_ok=True)

    tickers = ["ASML.AS","BESI.AS","IFX.DE","HSBA.L","INGA.AS","ISP.MI","ABI.BR","RI.PA","BN.PA","TSCO.L"]
    prices = prep_prices(load_universe(tickers, start="2024-01-01", end="2025-01-01", force=False, save_meta=True))
    prices.to_csv(DATA_ROOT / "universe_close_2024_2025.csv")

    analyzer = PairAnalyzer(use_logs=True, beta_window=60)
    pairs_df = analyzer.rank_pairs(prices, tickers)
    print(pairs_df.head())

    strat = EmaRsiStrategy(
        ema_short=TimePeriod.WEEK.to_days(),
        ema_long=TimePeriod.MONTH.to_days(),
        rsi_window=50,
        allow_short=True,
        long_entry_rsi=40, long_exit_rsi=60,
        short_entry_rsi=50, short_exit_rsi=40,
    )
    res = strat.run(prices[["ASML.AS","BN.PA"]])
    cum = (1 + res["portfolio_ew_returns"]).cumprod()
    print(cum.tail())