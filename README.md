# BNP_BuildingPairTradingModel

## 📌 Business Case  
**Objective:** Build a Pair Trading Model to identify and exploit pricing dislocations between two correlated stocks.  

**Strategy:**  
- Long one stock and short the other based on **daily close prices**.  
- **Time horizon:** Medium to long term (1 week to 1 month).  

---

## ⚙️ Setup  

### Running on my Local Machine (Existing Virtual Environment)  
source .venv/bin/activate

python main.py

### Running on a New Machine (Fresh Setup)
sudo apt install python3-venv python3-full -y
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip

pip install yfinance

pip install matplotlib

---

## 2/3. Data Collection and preprocessing
- **Source:** yfinance lib
- **Stocks to consider:**
    [
        "ASML.AS", "BESI.AS", "IFX.DE", "HSBA.L", 
        "INGA.AS", "ISP.MI", "ABI.BR", "RI.PA", 
        "BN.PA", "TSCO.L"
    ]

### ⚠️ Challenges & Solutions  

- **Challenges found in this phase:**  
  Missing daily close prices for some tickers → prevents normalized comparisons.  

- **Solution implemented:**  
  Forward-fill missing dates with the most recent available close price, creating a **continuous daily price series**.

### Features added (thinking used)
- **RSI**

    RSI > 60 => a bullish momentum is ongoing

    RSI > 40 => a bearish momentum is ongoing
- **EMA**

    Price > EMA Long && Price > EMA Short => Price might be good for selling

    Price < EMA Long && Price < EMA Short => Price might be good for buying

    **EMA was choosen agains't SMA** because it reacts faster to current changes.

### Fundamentals brief summary 2021-2024 
(taken from finance.yahoo website Financials Tab)
- **ASML.AS (2021–2024):**
  - **Net Income CAGR:**

    Approximately +6.5 % per annum
  - **Share Repurchases:**

    AVG of 35.295% and STD of 33.87%, of gross profit invested in NET repurchased programs (3.45, 7.08, 43.38, 87.27)
  - **Long-Term Debt:**

    2021: 0.77, 0.75.,  0.59, 2024: 0.61 (total debt/net income), pays off all its long term debt in a single operating year

- **BESI.AS (2021–2024):**
  - **Net Income CAGR:**

    Approximately -14.1 % per annum
  - **Share Repurchases:**

    AVG of 30.32% and STD of 17.65%, of gross profit invested in NET repurchased programs (20.17, 56.77, 33.13, 11.21)
  - **Long-Term Debt:**
  
    2021: 1.11, 2022: 1.42, 2023: 1.80, 2024: 3.00 (total debt/net income), pays off all its long term debt in approximately 3.08 operating years in the worst scenario

- **IFX.DE (2021–2024):**
  - **Net Income CAGR:**

    Approximately +3.63 % per annum
  - **Share Repurchases:**

    AVG of 0.96% and STD of 1.66%, of gross profit invested in NET repurchased programs (3.84, 0.00, 0.00, 0.00)
  - **Long-Term Debt:**

    2021: 6.05, 2022: 2.81, 2023: 1.65, 2024: 4.06 (total debt/net income), pays off all its long term debt in approximately 6.05 operating years in the worst scenario

**Why did I use these 3 indicators and not other ones?**
    1. Net Income growth analysis and Share Repurchases influence highly the potencial price of share, respectively, because:
        - If the net income increases, naturally the price of the shares also increase if the they are not overvalued
        - If a company repurchases stocks it reduces their supply to the market. Therefore if the demand remains steady or increases the stock naturally will increase on price

    2. Long-Term debt, the first, second, and third rule in investing is to never lose money.
    
    We must remain mindful of macroeconomic scenarios that could push businesses toward bankruptcy. 
    
    Bankruptcy often stems from a company’s inability to service its debt. If a company can repay its debt using its net earnings within 2-4 years (there's no fixed number here, but it should be a small number ofc), that is generally a reasonable timeframe, as it allows them to better navigate periods of macroeconomic uncertainty.

  **Note:**
  We could do the same for the rest but I guess **this already shows up some analytical skills given Fundamental Analysis** which is not asked in the assessment but if I could choose I'd partially integrate it in the work.


