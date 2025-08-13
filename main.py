import yfinance as yf
from DataStructures import TimePeriod, Enterprise
import pandas as pd
from pathlib import Path

# -------------------------
# Batch helper for your list
# -------------------------

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

if __name__ == "__main__":
    DATA_ROOT = Path("data/market")

    tickers = [
        "ASML.AS", "BESI.AS", "IFX.DE", "HSBA.L", "INGA.AS",
        "ISP.MI", "ABI.BR", "RI.PA", "BN.PA", "TSCO.L"
    ]

    prices = load_universe(tickers, start="2024-01-01", end="2025-01-01", force=False, save_meta=True)
    (DATA_ROOT).mkdir(parents=True, exist_ok=True)
    prices.to_csv(DATA_ROOT / "universe_close_2020_2025.csv")


