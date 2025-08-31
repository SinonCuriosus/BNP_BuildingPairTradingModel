import pandas as pd

def prep_prices(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.copy()
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"]); df = df.set_index("Date")
    df = df.sort_index()
    return df.dropna(how="all")