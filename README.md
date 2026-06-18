# Solana Wallets Tracker

Prototype Python scanner for finding active Solana wallets that may be worth researching for copy trading.

> Research tool only. Crypto trading is risky. Do not connect private keys or automate live trades until you have paper-tested thoroughly.

## What it does

- Discovers candidate wallets from Birdeye top-trader data when an API key is available.
- Scores wallets using recent Helius enhanced transactions.
- Filters out likely bots:
  - 100% win rate
  - 1,000+ trades
- Keeps only wallets that match your thresholds:
  - Win rate > 50%
  - Minimum 10 trades
  - Average buy size >= 0.5 SOL
  - Active today
- Exports ranked wallets to CSV.
- Includes CSV mode so you can filter an uploaded/exported wallet list without API calls.

## Project structure

```text
Solana-wallets-tracker/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── scanner.py
│   ├── metrics.py
│   └── exporter.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Install

```bash
git clone https://github.com/Riseofcoyote/Solana-wallets-tracker.git
cd Solana-wallets-tracker
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
HELIUS_API_KEY=your_helius_api_key_here
BIRDEYE_API_KEY=your_birdeye_api_key_here

LOOKBACK_HOURS=48
MIN_WIN_RATE=0.50
MIN_TRADES=10
MIN_AVG_BUY_SOL=0.5
TOP_WALLETS=100
OUTPUT_FILE=output/top_wallets.csv
```

Optional fallback if wallet discovery fails or you want to test known wallets:

```env
SEED_WALLETS=wallet1,wallet2,wallet3
```

Optional token discovery list:

```env
DISCOVERY_TOKEN_MINTS=So11111111111111111111111111111111111111112
```

## Run API scan

```bash
python -m src.main
```

Output:

```text
output/top_wallets.csv
```

## Run CSV analysis mode

Use this when you already have a wallet CSV.

Expected columns:

```csv
wallet,win_rate,roi,avg_buy_size_sol,trades,last_trade_at
```

Then add this to `.env`:

```env
INPUT_CSV=sniper-wallets.csv
OUTPUT_FILE=output/top_wallets.csv
```

Run:

```bash
python -m src.main
```

## Important prototype notes

This is a working prototype, but true wallet ROI needs deeper token cost-basis tracking. The current API scanner estimates performance from recent swap activity and ranks candidates for research. The CSV mode is better when your input file already includes win rate, ROI, trade count, buy size, and last active time.

## Next upgrades

- Add exact realized PnL per token.
- Store wallet history in SQLite/Postgres.
- Add Telegram alerts.
- Add paper-trading simulation.
- Add copy-trading only after long paper testing.
