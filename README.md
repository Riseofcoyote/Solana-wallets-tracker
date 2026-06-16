Solana Wallets Tracker

A Python-based Solana wallet scanner designed to identify high-performing wallets from the last 48 hours.

Features

- Scans active Solana wallets
- Filters wallets using custom performance metrics
- Calculates:
  - Win Rate
  - ROI
  - Average Buy Size
  - Trade Count
- Exports ranked wallets to CSV
- Built for future integration with paper trading and copy trading systems

Wallet Selection Criteria

A wallet must meet all of the following:

- Win Rate > 50%
- Minimum 10 completed trades
- Average Buy Size ≥ 0.5 SOL
- Active within the last 48 hours

Wallets are ranked primarily by ROI.

Project Structure

Solana-wallets-tracker/
│
├── src/
│   ├── main.py
│   ├── scanner.py
│   ├── metrics.py
│   └── exporter.py
│
├── output/
│   └── top_wallets.csv
│
├── requirements.txt
├── .env
└── README.md

Installation

git clone https://github.com/Riseofcoyote/Solana-wallets-tracker.git
cd Solana-wallets-tracker

python -m venv .venv

# Linux / Mac
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt

Environment Variables

Create a ".env" file:

HELIUS_API_KEY=YOUR_HELIUS_KEY
BIRDEYE_API_KEY=YOUR_BIRDEYE_KEY

Run

python -m src.main

Output

The scanner will generate:

output/top_wallets.csv

Example:

wallet,win_rate,roi,avg_buy_size,trades
wallet1,68.5,142.7,1.3,34
wallet2,61.2,98.4,0.9,18

Roadmap

Phase 1

- Wallet discovery
- Performance scoring
- CSV exports

Phase 2

- Telegram alerts
- Database storage
- Historical tracking

Phase 3

- Paper trading

Phase 4

- Automated copy trading

Disclaimer

This software is for research and educational purposes only. Cryptocurrency trading is risky and can result in significant financial losses. Always test with paper trading before using real funds.# Solana-wallets-tracker
Bot that scans top solana wallets for last 48 hours and produces list of top wallets to copy trade
requests
pandas
python-dotenv

