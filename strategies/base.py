from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any
import pandas as pd

Result = Dict[str, Any]

class Strategy(ABC):
    """Minimal base: every strategy exposes execute(data) -> Result dict."""

    @abstractmethod
    def execute(self, data: pd.DataFrame, **kwargs) -> Result:
        ...