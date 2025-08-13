from enum import Enum
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd
import yfinance as yf
from datetime import date
DATA_ROOT = Path("data/market")

class TimePeriod(Enum):
    WEEK = timedelta(weeks=1)
    MONTH = relativedelta(months=1)

    def to_days(self):
        if isinstance(self.value, timedelta):
            return self.value.days
        elif isinstance(self.value, relativedelta):
            # Convert relativedelta to days by applying it to a fixed date
            start = date(2000, 1, 1)
            end = start + self.value
            return (end - start).days
            
# May also be useful:
# today = date.today()
# next_week = today + TimePeriod.WEEK.value
# next_month = today + TimePeriod.MONTH.value



@dataclass
class Enterprise:
    ticker: str
    currency: str | None = None
    meta: dict = field(default_factory=dict)

    @property
    def price_store(self) -> Path:
        return DATA_ROOT / "prices" / f"ticker={self.ticker}"

    @property
    def cache_file(self) -> Path:
        return self.price_store / "close.parquet"

    @property
    def meta_path(self) -> Path:
        return DATA_ROOT / "meta" / f"{self.ticker}.json"

    def fetch_meta(self, force: bool = False) -> dict:
        # If we already have the meta but we want to force for instance for updating the previous frame
        if self.meta and not force:
            return self.meta
        # If the object has no meta yet but we already have that info locally and we don't force the update of that meta
        if self.meta_path.exists() and not force:
            self.meta = pd.read_json(self.meta_path).to_dict(orient="records")[0]
            self.currency = self.meta.get("currency")
            return self.meta

        # If none of the scenarios above happen we want to do an API call
        # yfinance can be flaky/slow; simple retry
        last_err = None
        for _ in range(3):
            try:
                tk = yf.Ticker(self.ticker).info
                break
            except Exception as e:
                last_err = e
                time.sleep(0.6)
        else:
            raise RuntimeError(f"Failed to fetch meta for {self.ticker}: {last_err}")

        self.meta = {
            "ticker": self.ticker,
            "shortName": tk.get("shortName"),
            "sector": tk.get("sector"),
            "industry": tk.get("industry"),
            "currency": tk.get("currency"),
            "sharesOutstanding": tk.get("sharesOutstanding"),
            "exchange": tk.get("exchange"),
        }
        self.currency = self.meta.get("currency")
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([self.meta]).to_json(self.meta_path, orient="records", indent=2)
        return self.meta

    def _download_close(self, start: str, end: str) -> pd.DataFrame:
        AUTO_ADJUST = True # include split/dividendt-adjusted prices
        end_plus = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        # Simple retry for transient failures
        last_err = None
        for _ in range(3):
            try:
                df = yf.download(
                    self.ticker,
                    start=start,
                    end=end_plus,
                    progress=False,
                    auto_adjust=AUTO_ADJUST,
                    threads=True,
                )
                break
            except Exception as e:
                last_err = e
                time.sleep(0.6)
        else:
            raise RuntimeError(f"Download failed for {self.ticker}: {last_err}")

        # Build full calendar-day index for forward-fill logic
        full_idx = pd.date_range(start, end, freq="D")

        if df.empty:
            # Return an empty DataFrame with full index so caller can seed with last close
            return pd.DataFrame(index=full_idx, columns=["Close"])

        df = df[["Close"]].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)  # ensure tz-naive
        df.columns = ["Close"]
        df.index.name = "Date"
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df = df.sort_index()

        # Reindex to all days in range, forward-fill within this segment
        df = df.reindex(full_idx).ffill()

        return df


    def fetch_close_prices(self, start="2020-01-01", end="2025-01-01", force=False) -> pd.Series:
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        self.price_store.mkdir(parents=True, exist_ok=True)

        if self.cache_file.exists() and not force:
            cache = pd.read_parquet(self.cache_file)
            cache.index = pd.to_datetime(cache.index).tz_localize(None)
            cache.index.name = "Date"
            cache = cache.sort_index()
            if "Close" not in cache.columns:
                cache.columns = ["Close"]  # safety if column name lost
        else:
            cache = pd.DataFrame(columns=["Close"])
            cache.index.name = "Date"

        # Determine if download is required
        need_download = force or cache.empty
        if not cache.empty and not force:
            have_start, have_end = cache.index.min(), cache.index.max()
            need_download = not (start_ts >= have_start and end_ts <= have_end)

        if need_download:
            segments = []
            if cache.empty or force:
                segments.append((start_ts, end_ts))
            else:
                have_start, have_end = cache.index.min(), cache.index.max()
                if start_ts < have_start:
                    segments.append((start_ts, min(end_ts, have_start - pd.Timedelta(days=1))))
                if end_ts > have_end:
                    segments.append((max(start_ts, have_end + pd.Timedelta(days=1)), end_ts))

            last_close = None if cache.empty else cache["Close"].iloc[-1]

            for seg_start, seg_end in segments:
                if seg_start <= seg_end:
                    df_new = self._download_close(seg_start.strftime("%Y-%m-%d"), seg_end.strftime("%Y-%m-%d"))

                    # If first row has NaN and we know the last cached close, seed it
                    if pd.isna(df_new["Close"].iloc[0]) and last_close is not None:
                        df_new.iloc[0, 0] = last_close
                        df_new["Close"] = df_new["Close"].ffill()

                    # Update last_close for next segment
                    if not df_new["Close"].dropna().empty:
                        last_close = df_new["Close"].dropna().iloc[-1]

                    cache = pd.concat([cache, df_new])

            cache = cache[~cache.index.duplicated(keep="last")].sort_index()
            cache.to_parquet(self.cache_file)  # requires pyarrow or fastparquet

        out = cache.loc[start_ts:end_ts, "Close"]
        if out.empty:
            raise ValueError(f"No data available for {self.ticker} in requested window {start}..{end}")
        out.name = self.ticker
        return out