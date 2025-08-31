from abc import ABC, abstractmethod
from typing import Iterable
import pandas as pd

class PriceDataSource(ABC):
    """Abstract provider of close prices (one column per ticker, Date index)."""

    @abstractmethod
    def get_close(
        self,
        tickers: Iterable[str],
        start: str,
        end: str,
        force: bool = False,
        save_meta: bool = True,
    ) -> pd.DataFrame:
        ...