from dataclasses import dataclass
import pandas as pd
from indicators.ema import EMA
from indicators.rsi import RSI
from .base import Strategy

@dataclass
class EmaRsiStrategy(Strategy):
    ema_short: int = 7
    ema_long: int = 30
    rsi_window: int = 14
    long_entry_rsi: int = 40
    long_exit_rsi: int = 60
    short_entry_rsi: int = 60
    short_exit_rsi: int = 40
    allow_short: bool = False
    log_trades: bool = True

    def validate_params(self) -> None:
        for v in (self.long_entry_rsi, self.long_exit_rsi, self.short_entry_rsi, self.short_exit_rsi):
            if not (0 <= v <= 100):
                raise ValueError("All RSI thresholds must be in [0, 100].")
        if min(self.ema_short, self.ema_long, self.rsi_window) <= 0:
            raise ValueError("EMA/RSI windows must be positive.")

    def compute_indicators(self, prices: pd.DataFrame):
        ema_s = EMA(self.ema_short).compute(prices)
        ema_l = EMA(self.ema_long).compute(prices)
        rsi_v = RSI(self.rsi_window).compute(prices)
        return {"ema_short": ema_s, "ema_long": ema_l, "rsi": rsi_v}

    def make_signals(self, prices: pd.DataFrame, ind): 
        ema_s, ema_l, rsi = ind["ema_short"], ind["ema_long"], ind["rsi"]
        long_entry = (prices < ema_l) & (prices < ema_s) & (rsi < self.long_entry_rsi)
        long_exit  = (prices > ema_l) & (prices > ema_s) & (rsi > self.long_exit_rsi)
        if self.allow_short:
            short_entry = (prices > ema_l) & (prices > ema_s) & (rsi > self.short_entry_rsi)
            short_exit  = (prices < ema_l) & (prices < ema_s) & (rsi < self.short_exit_rsi)
        else:
            short_entry = pd.DataFrame(False, index=prices.index, columns=prices.columns)
            short_exit  = pd.DataFrame(False, index=prices.index, columns=prices.columns)
        return {"long_entry": long_entry, "long_exit": long_exit,
                "short_entry": short_entry, "short_exit": short_exit}