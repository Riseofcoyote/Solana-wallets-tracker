from __future__ import annotations

import os
import time
from pathlib import Path

from .exporter import export_wallets
from .metrics import LAMPORTS_PER_SOL, WalletMetrics, calculate_wallet_metrics

TOKEN_A = "DemoToken1111111111111111111111111111111111111"
TOKEN_B = "DemoToken2222222222222222222222222222222222222"


def _swap(wallet: str, timestamp: int, sol_delta: float, mint: str, token_delta: float) -> dict:
    """Build a small Helius-like SWAP transaction for local smoke tests."""
    if sol_delta < 0:
        native_transfers = [
            {
                "fromUserAccount": wallet,
                "toUserAccount": "demo_pool",
                "amount": int(abs(sol_delta) * LAMPORTS_PER_SOL),
            }
        ]
    else:
        native_transfers = [
            {
                "fromUserAccount": "demo_pool",
                "toUserAccount": wallet,
                "amount": int(sol_delta * LAMPORTS_PER_SOL),
            }
        ]

    if token_delta > 0:
        token_transfers = [
            {
                "fromUserAccount": "demo_pool",
                "toUserAccount": wallet,
                "mint": mint,
                "tokenAmount": token_delta,
            }
        ]
    else:
        token_transfers = [
            {
                "fromUserAccount": wallet,
                "toUserAccount": "demo_pool",
                "mint": mint,
                "tokenAmount": abs(token_delta),
            }
        ]

    return {
        "type": "SWAP",
        "timestamp": timestamp,
        "nativeTransfers": native_transfers,
        "tokenTransfers": token_transfers,
    }


def build_demo_transactions(wallet: str) -> list[dict]:
    """Create 12 demo swaps: 5 wins and 1 loss, active today."""
    now = int(time.time())
    txs: list[dict] = []

    # Five profitable round trips.
    for i in range(5):
        buy_ts = now - 7200 + (i * 900)
        sell_ts = buy_ts + 300
        mint = f"{TOKEN_A}{i}"
        txs.append(_swap(wallet, buy_ts, -1.0, mint, 1000.0))
        txs.append(_swap(wallet, sell_ts, 1.35, mint, -1000.0))

    # One losing round trip so win rate is below 100% and not filtered as a bot.
    txs.append(_swap(wallet, now - 900, -1.0, TOKEN_B, 1000.0))
    txs.append(_swap(wallet, now - 300, 0.70, TOKEN_B, -1000.0))
    return txs


def build_demo_wallets() -> list[WalletMetrics]:
    wallet = "DemoCopyTradeWallet1111111111111111111111111111"
    metrics = calculate_wallet_metrics(wallet, build_demo_transactions(wallet))
    return [metrics]


def run_demo(output_file: str | None = None) -> Path:
    """Run a local no-API demo and export a ranked wallet CSV."""
    output = output_file or os.getenv("OUTPUT_FILE", "output/demo_wallets.csv")
    wallets = [wallet for wallet in build_demo_wallets() if not wallet.is_likely_bot]
    path = export_wallets(wallets, output)
    print(f"Demo complete. Saved {len(wallets)} wallet(s) to {path}")
    for wallet in wallets:
        print(
            f"{wallet.wallet} | ROI={wallet.roi:.2%} | "
            f"WR={wallet.win_rate:.2%} | trades={wallet.trades} | "
            f"closed={wallet.closed_trades}"
        )
    return path


if __name__ == "__main__":
    run_demo()
