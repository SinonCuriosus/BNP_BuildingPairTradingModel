from dataclasses import dataclass
import pandas as pd

@dataclass
class EMA:
    span: int
    def compute(self, prices: pd.DataFrame) -> pd.DataFrame:
        return prices.ewm(span=self.span, adjust=False).mean()

