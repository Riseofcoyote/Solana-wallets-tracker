from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from .exporter import export_wallets
from .metrics import WalletMetrics, is_today_utc
from .scanner import ScannerConfig, SolanaWalletScanner


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "active"}


def analyze_existing_csv(input_file: str, output_file: str) -> Path:
    """Filter/rank an existing CSV of wallet metrics.

    Expected columns: wallet, win_rate, roi, avg_buy_size_sol or avg_buy_size, trades,
    and optionally last_trade_at/active_today.
    """
    df = pd.read_csv(input_file)
    df.columns = [c.strip().lower() for c in df.columns]

    if "avg_buy_size" in df.columns and "avg_buy_size_sol" not in df.columns:
        df["avg_buy_size_sol"] = df["avg_buy_size"]

    required = {"wallet", "win_rate", "roi", "avg_buy_size_sol", "trades"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")

    # Support win_rate/roi as either decimals or percentages.
    if df["win_rate"].max() > 1:
        df["win_rate"] = df["win_rate"] / 100
    if df["roi"].max() > 2:
        df["roi"] = df["roi"] / 100

    if "active_today" not in df.columns:
        if "last_trade_at" in df.columns:
            df["active_today"] = df["last_trade_at"].fillna("").apply(is_today_utc)
        else:
            df["active_today"] = True
    else:
        df["active_today"] = df["active_today"].apply(_truthy)

    min_win_rate = _env_float("MIN_WIN_RATE", 0.50)
    min_trades = _env_int("MIN_TRADES", 10)
    min_avg_buy = _env_float("MIN_AVG_BUY_SOL", 0.5)
    top_wallets = _env_int("TOP_WALLETS", 100)

    df["bot_reason"] = ""
    df.loc[df["win_rate"] >= 1.0, "bot_reason"] = "100_percent_win_rate"
    df.loc[df["trades"] >= 1000, "bot_reason"] = "too_many_trades"

    filtered = df[
        (df["bot_reason"] == "")
        & (df["active_today"])
        & (df["win_rate"] > min_win_rate)
        & (df["trades"] >= min_trades)
        & (df["avg_buy_size_sol"] >= min_avg_buy)
    ].copy()

    filtered = filtered.sort_values(["roi", "win_rate", "avg_buy_size_sol"], ascending=[False, False, False]).head(top_wallets)

    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(path, index=False)
    return path


def main() -> None:
    load_dotenv()
    output_file = os.getenv("OUTPUT_FILE", "output/top_wallets.csv")
    input_csv = os.getenv("INPUT_CSV", "").strip()

    print("================================")
    print(" Solana Wallet Tracker Started ")
    print("================================")

    if input_csv:
        print(f"Mode: CSV analysis ({input_csv})")
        output = analyze_existing_csv(input_csv, output_file)
        print(f"Saved ranked wallets to {output}")
        return

    print("Mode: API scan")
    config = ScannerConfig.from_env()
    scanner = SolanaWalletScanner(config)
    wallets: list[WalletMetrics] = scanner.scan()
    output = export_wallets(wallets, output_file)
    print(f"Saved {len(wallets)} ranked wallets to {output}")


if __name__ == "__main__":
    main()
