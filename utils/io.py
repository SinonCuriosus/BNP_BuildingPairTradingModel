import pandas as pd
import numpy as np
import yfinance as yf

def prep_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans a prices DataFrame for strategies:
      - uses DatetimeIndex (tz-naive), sorted, unique
      - if yfinance MultiIndex, selects 'Close'
      - ensures numeric dtypes
      - drops rows where ALL tickers are NaN
    """
    df = prices.copy()

    # If 'Date' column exists, make it the index
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_localize(None)
        df = df.set_index("Date")

    # If yfinance-like MultiIndex columns, take Close
    if isinstance(df.columns, pd.MultiIndex):
        if ("Close" in df.columns.get_level_values(0)) or ("Adj Close" in df.columns.get_level_values(0)):
            for lvl0 in ("Close", "Adj Close"):
                if lvl0 in df.columns.get_level_values(0):
                    df = df[lvl0]
                    break

    # Ensure datetime index, tz-naive
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
    else:
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)

    # Sort, deduplicate
    df = df[~df.index.duplicated(keep="last")].sort_index()

    # Make sure it’s a DataFrame (even if single ticker)
    if isinstance(df, pd.Series):
        df = df.to_frame()

    # Numeric dtype
    df = df.apply(pd.to_numeric, errors="coerce")

    # Drop rows where all tickers are NaN
    df = df.dropna(how="all")

    return df

def fetch_close_prices(tickers, start="2023-01-01", end=None) -> pd.DataFrame:
    """
    Downloads daily close prices for a list/iterable of tickers and
    returns a cleaned DataFrame ready for strategies.
    """
    df = yf.download(list(tickers), start=start, end=end, auto_adjust=False, progress=False)
    # yfinance returns MultiIndex columns; prep_prices will select Close for us
    return prep_prices(df)