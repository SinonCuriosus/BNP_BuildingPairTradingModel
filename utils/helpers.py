from __future__ import annotations
from typing import Any, Iterable, Tuple
import pandas as pd

def extract_pair(ranked: Any,ranked_pos=0) -> Tuple[str, str]:
    """
    Returns the top pair (s1, s2) from rank_pairs output.

    Supports:
      - DataFrame with 'pair' column like 'AAPL/MSFT'
      - DataFrame with 'stock1'/'stock2' columns
      - List of pairs or [((s1,s2), score), ...]
    """
    # --- DataFrame cases ---
    if isinstance(ranked, pd.DataFrame):
        if ranked.empty:
            raise ValueError("ranked DataFrame is empty.")

        # Case A: 'stock1'/'stock2'
        if {"stock1", "stock2"}.issubset(ranked.columns):
            r0 = ranked.iloc[ranked_pos]
            return str(r0["stock1"]), str(r0["stock2"])

        # Case B: 'pair' like 'AAA/BBB'
        if "pair" in ranked.columns:
            val = ranked.iloc[ranked_pos]["pair"]
            # val might be "AAA/BBB" or tuple/list ("AAA","BBB")
            if isinstance(val, str) and "/" in val:
                s1, s2 = [x.strip() for x in val.split("/", 1)]
                if not s1 or not s2:
                    raise ValueError(f"Malformed pair string: {val!r}")
                return s1, s2
            if isinstance(val, (list, tuple)) and len(val) == 2:
                return str(val[0]), str(val[1])
            # If pair is something else (e.g., custom object), fail explicitly:
            raise ValueError(f"Unsupported 'pair' cell type: {type(val).__name__}")

        raise ValueError(f"Unsupported DataFrame columns: {ranked.columns.tolist()}")

    # --- List/tuple fallbacks ---
    if isinstance(ranked, (list, tuple)) and ranked:
        top = ranked[0]
        if isinstance(top, dict) and {"stock1", "stock2"}.issubset(top):
            return str(top["stock1"]), str(top["stock2"])
        if isinstance(top, (list, tuple)):
            # ((s1,s2), score)
            if top and isinstance(top[0], (list, tuple)) and len(top[0]) == 2:
                return str(top[0][0]), str(top[0][1])
            # (s1, s2)
            if len(top) == 2 and not isinstance(top[0], (list, tuple)):
                return str(top[0]), str(top[1])

    raise ValueError("Unrecognized rank_pairs output format.")