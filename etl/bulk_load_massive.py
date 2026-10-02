"""
etl/bulk_load_massive.py
Stub for the 32 validation tickers (Mag 7 + semis).
Full list was in IBKR_workbench; only the constant is needed by extract_yfinance.
"""

TICKERS = [
    # Mag 7
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    # Semis
    "AMD", "INTC", "QCOM", "AVGO", "MU", "MRVL", "TXN", "ADI",
    "LRCX", "KLAC", "AMAT", "ASML", "TSM", "ON", "NXPI", "MCHP",
    "SWKS", "QRVO", "CRUS", "MPWR", "OLED", "ENTG", "COHR", "IIVI",
    "ACLS",
]