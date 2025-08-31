import pandas as pd
from DataStructures import Enterprise

def load_universe(tickers, start="2020-01-01", end="2025-01-01", force=False, save_meta=True):
    series = []
    for t in tickers:
        e = Enterprise(t)
        if save_meta:
            try: e.fetch_meta(force=False)
            except Exception as ex: print(f"[meta warn] {t}: {ex}")
        try:
            s = e.fetch_close_prices(start=start, end=end, force=force)
            series.append(s)
        except Exception as ex:
            print(f"[price warn] {t}: {ex}")
    if not series:
        raise RuntimeError("No ticker data loaded.")
    return pd.concat(series, axis=1).sort_index()