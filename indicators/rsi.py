from dataclasses import dataclass
import pandas as pd

@dataclass
class RSI:
    window: int = 14
    def compute(self, prices: pd.DataFrame) -> pd.DataFrame:
        delta = prices.diff()
        up = delta.clip(lower=0.0)
        down = -delta.clip(upper=0.0)
        roll_up = up.ewm(alpha=1/self.window, adjust=False).mean()
        roll_down = down.ewm(alpha=1/self.window, adjust=False).mean()
        rs = roll_up / roll_down
        return 100 - (100 / (1 + rs))