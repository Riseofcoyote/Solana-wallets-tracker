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


def build_demo_transactions(wallet: str, win_multiplier: float, loss_multiplier: float) -> list[dict]:
    """Create 12 demo swaps: 5 wins and 1 loss, active today."""
    now = int(time.time())
    txs: list[dict] = []

    for i in range(5):
        buy_ts = now - 7200 + (i * 900)
        sell_ts = buy_ts + 300
        mint = f"{TOKEN_A}{i}"
        txs.append(_swap(wallet, buy_ts, -1.0, mint, 1000.0))
        txs.append(_swap(wallet, sell_ts, win_multiplier, mint, -1000.0))

    txs.append(_swap(wallet, now - 900, -1.0, TOKEN_B, 1000.0))
    txs.append(_swap(wallet, now - 300, loss_multiplier, TOKEN_B, -1000.0))
    return txs


def build_demo_wallets() -> list[WalletMetrics]:
    demo_specs = [
        ("DemoResearchWallet1111111111111111111111111111", 1.35, 0.70),
        ("DemoResearchWallet2222222222222222222222222222", 1.25, 0.80),
        ("DemoResearchWallet3333333333333333333333333333", 1.20, 0.75),
        ("DemoResearchWallet4444444444444444444444444444", 1.15, 0.90),
        ("DemoResearchWallet5555555555555555555555555555", 1.10, 0.85),
        ("DemoResearchWallet6666666666666666666666666666", 1.05, 0.80),
    ]
    return [
        calculate_wallet_metrics(wallet, build_demo_transactions(wallet, win_mult, loss_mult))
        for wallet, win_mult, loss_mult in demo_specs
    ]


def run_demo(output_file: str | None = None) -> tuple[Path, Path]:
    """Run a local no-API demo and export ranked CSV files."""
    output = output_file or os.getenv("OUTPUT_FILE", "output/demo_wallets.csv")
    wallets = [wallet for wallet in build_demo_wallets() if not wallet.is_likely_bot]
    full_path, top_path = export_wallets(wallets, output)
    print(f"Demo complete. Saved {len(wallets)} wallet(s) to {full_path}")
    print(f"Top 5 saved to {top_path}")
    for wallet in wallets[:5]:
        print(
            f"{wallet.wallet} | ROI={wallet.roi:.2%} | "
            f"WR={wallet.win_rate:.2%} | trades={wallet.trades} | "
            f"closed={wallet.closed_trades}"
        )
    return full_path, top_path


if __name__ == "__main__":
    run_demo()
