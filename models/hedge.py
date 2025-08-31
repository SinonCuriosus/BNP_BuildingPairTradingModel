import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.regression.linear_model import OLS

class OLSHedge:
    # fits y = alpha + beta * x
    def fit(self, y: pd.Series, x: pd.Series):
        xy = pd.concat([y, x], axis=1).dropna()
        if len(xy) < 30:
            return np.nan, np.nan, None
        X = sm.add_constant(xy.iloc[:, 1])
        model = OLS(xy.iloc[:, 0], X).fit()
        alpha = float(model.params["const"])
        beta = float(model.params.iloc[1])
        return alpha, beta, model

    @staticmethod
    def spread(y: pd.Series, x: pd.Series, alpha: float, beta: float) -> pd.Series:
        xy = pd.concat([y, x], axis=1).dropna()
        return xy.iloc[:, 0] - (alpha + beta * xy.iloc[:, 1])