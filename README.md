# Solana Wallets Tracker

Prototype Python scanner for finding active Solana wallets that may be worth researching for copy trading.

> Research tool only. Crypto trading is risky. This repo does **not** connect private keys, place live trades, or custody funds.

## What it does

- Runs a no-API demo so you can confirm the project works locally.
- Discovers fresh Solana token mints from DEX Screener when enabled.
- Discovers candidate wallets from Birdeye top-trader data when an API key is available.
- Scores wallets using recent Helius enhanced SWAP transactions.
- Estimates realized PnL in SOL from recent buy/sell flows using average-cost token positions.
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
│   ├── demo.py
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

## Quick test without API keys

Use demo mode first. It creates a fake active wallet with 12 demo swaps and exports a CSV so you can confirm the code path works.

```bash
cp .env.example .env
```

Edit `.env` and add:

```env
DEMO_MODE=true
OUTPUT_FILE=output/top_wallets.csv
```

Run:

```bash
python -m src.main
```

Expected output file:

```text
output/top_wallets.csv
```

You can also run the demo directly:

```bash
python -m src.demo
```

## Configure API scan

After the demo works, edit `.env`:

```env
DEMO_MODE=false
HELIUS_API_KEY=your_helius_api_key_here
BIRDEYE_API_KEY=your_birdeye_api_key_here

LOOKBACK_HOURS=48
MIN_WIN_RATE=0.50
MIN_TRADES=10
MIN_AVG_BUY_SOL=0.5
TOP_WALLETS=100
MAX_WALLETS_TO_SCORE=200
SLEEP_SECONDS=0.15
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

Optional DEX Screener discovery:

```env
DEXSCREENER_DISCOVERY=true
DEXSCREENER_MAX_TOKENS=25
DEXSCREENER_TOKEN_PROFILE_URL=https://api.dexscreener.com/token-profiles/latest/v1
```

If you want to try the route you sent, override the URL/path:

```env
DEXSCREENER_TOKEN_PROFILE_URL=/token-profiles/recent-updates/v1
```

Run API scan:

```bash
python -m src.main
```

## How DEX Screener is used

DEX Screener is used to discover fresh Solana token mints. It does not directly provide copy-trading wallet PnL. The scanner flow is:

```text
DEX Screener recent token profiles
        ↓
Fresh Solana token mint list
        ↓
Birdeye top traders for each token mint
        ↓
Helius wallet SWAP transactions
        ↓
Local realized-PnL estimate + filters
        ↓
output/top_wallets.csv
```

You still need `BIRDEYE_API_KEY` to turn token mints into candidate wallets, and `HELIUS_API_KEY` to score each wallet's recent activity.

## Run CSV analysis mode

Use this when you already have a wallet CSV.

Expected columns:

```csv
wallet,win_rate,roi,avg_buy_size_sol,trades,last_trade_at
```

Then add this to `.env`:

```env
DEMO_MODE=false
INPUT_CSV=sniper-wallets.csv
OUTPUT_FILE=output/top_wallets.csv
```

Run:

```bash
python -m src.main
```

## Output columns

The API/demo output includes:

```csv
wallet,win_rate,roi,avg_buy_size_sol,trades,closed_trades,realized_profit_sol,realized_cost_basis_sol,sol_spent,sol_received,unknown_sell_sol,last_trade_at,active_today,bot_reason
```

## Important prototype notes

This is a working research prototype, not a live trading bot. The API scanner estimates realized PnL from recent Helius enhanced transaction payloads. It is better than the old placeholder scoring, but exact wallet PnL still needs deeper cost-basis tracking across longer history, token decimals, fees, partial fills, wrapped SOL routes, and aggregator edge cases.

Use the output as a shortlist for research, not an automatic copy-trading signal.

## Next upgrades

- Add exact realized PnL per token across longer history.
- Add DEX Screener pair filtering by liquidity, volume, and recent buy/sell activity.
- Add Solscan wallet enrichment as an optional verification source.
- Store wallet history in SQLite/Postgres.
- Add Telegram alerts.
- Add paper-trading simulation.
- Add copy-trading only after long paper testing.
