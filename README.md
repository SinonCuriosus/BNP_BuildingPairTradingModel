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
python script.py

### Running on a New Machine (Fresh Setup)
sudo apt install python3-venv python3-full -y
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install yfinance

---

## Data Collection
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
