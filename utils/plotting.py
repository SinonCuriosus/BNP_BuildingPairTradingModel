import pandas as pd
import matplotlib.pyplot as plt

def plot_positions_with_z(
    prices: pd.DataFrame,       # columns [s1, s2]
    positions: pd.Series,       # +1/-1/0
    z: pd.Series,               # z-score
    entry_z: float,
    exit_z: float,
    title: str = "Pairs Trading — Positions & Z-score",
):
    s1, s2 = prices.columns[:2]

    # Normalize prices for visual comparison
    norm = prices / prices.iloc[0]

    fig, ax1 = plt.subplots(figsize=(11, 6))
    norm[s1].plot(ax=ax1, label=s1)
    norm[s2].plot(ax=ax1, label=s2)
    ax1.set_ylabel("Normalized Price")
    ax1.legend(loc="upper left")

    # Shade position regions
    # Long periods (+1)
    long_mask = positions == 1
    short_mask = positions == -1
    for mask, alpha in [(long_mask, 0.12), (short_mask, 0.12)]:
        # draw contiguous spans
        in_span = False
        span_start = None
        for t, flag in mask.items():
            if flag and not in_span:
                in_span = True
                span_start = t
            elif not flag and in_span:
                ax1.axvspan(span_start, t, color=("green" if mask is long_mask else "red"), alpha=alpha)
                in_span = False
        if in_span:
            ax1.axvspan(span_start, positions.index[-1], color=("green" if mask is long_mask else "red"), alpha=alpha)

    # Twin axis for z-score
    ax2 = ax1.twinx()
    z.plot(ax=ax2, linewidth=1.0, alpha=0.6, label="z-score")
    ax2.axhline(entry_z, linestyle="--")
    ax2.axhline(-entry_z, linestyle="--")
    ax2.axhline(exit_z, linestyle=":")
    ax2.axhline(-exit_z, linestyle=":")
    ax2.set_ylabel("Z-score")

    fig.suptitle(title)
    fig.tight_layout()
    plt.show()