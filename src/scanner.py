from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from .metrics import WalletMetrics, calculate_wallet_metrics

HELIUS_BASE_URL = "https://api.helius.xyz/v0"
BIRDEYE_BASE_URL = "https://public-api.birdeye.so"
SOL_MINT = "So11111111111111111111111111111111111111112"


@dataclass
class ScannerConfig:
    helius_api_key: str
    birdeye_api_key: str = ""
    discovery_token_mints: list[str] | None = None
    lookback_hours: int = 48
    min_win_rate: float = 0.50
    min_trades: int = 10
    min_avg_buy_sol: float = 0.5
    top_wallets: int = 100
    max_wallets_to_score: int = 200
    sleep_seconds: float = 0.15

    @classmethod
    def from_env(cls) -> "ScannerConfig":
        tokens = os.getenv("DISCOVERY_TOKEN_MINTS", "").strip()
        return cls(
            helius_api_key=os.getenv("HELIUS_API_KEY", "").strip(),
            birdeye_api_key=os.getenv("BIRDEYE_API_KEY", "").strip(),
            discovery_token_mints=[t.strip() for t in tokens.split(",") if t.strip()] or [SOL_MINT],
            lookback_hours=int(os.getenv("LOOKBACK_HOURS", "48")),
            min_win_rate=float(os.getenv("MIN_WIN_RATE", "0.50")),
            min_trades=int(os.getenv("MIN_TRADES", "10")),
            min_avg_buy_sol=float(os.getenv("MIN_AVG_BUY_SOL", "0.5")),
            top_wallets=int(os.getenv("TOP_WALLETS", "100")),
            max_wallets_to_score=int(os.getenv("MAX_WALLETS_TO_SCORE", "200")),
        )


class SolanaWalletScanner:
    def __init__(self, config: ScannerConfig):
        self.config = config
        self.session = requests.Session()
        if config.birdeye_api_key:
            self.session.headers.update({"X-API-KEY": config.birdeye_api_key, "x-chain": "solana"})

    def discover_wallets(self) -> list[str]:
        """Discover candidate wallets.

        Uses Birdeye top trader endpoints when available. If that endpoint changes or no
        key is provided, use SEED_WALLETS in .env as a comma-separated fallback.
        """
        seed_wallets = [w.strip() for w in os.getenv("SEED_WALLETS", "").split(",") if w.strip()]
        wallets: set[str] = set(seed_wallets)

        if not self.config.birdeye_api_key:
            return list(wallets)[: self.config.max_wallets_to_score]

        for mint in self.config.discovery_token_mints or [SOL_MINT]:
            try:
                wallets.update(self._birdeye_top_traders(mint))
            except requests.RequestException as exc:
                print(f"Birdeye discovery failed for {mint}: {exc}")
            time.sleep(self.config.sleep_seconds)

        return list(wallets)[: self.config.max_wallets_to_score]

    def _birdeye_top_traders(self, token_mint: str) -> list[str]:
        # Birdeye endpoint names occasionally change. This keeps the prototype isolated
        # so you only edit one method if their route/response shape changes.
        url = f"{BIRDEYE_BASE_URL}/defi/v2/tokens/top_traders"
        params = {
            "address": token_mint,
            "time_frame": "24h",
            "sort_by": "volume",
            "sort_type": "desc",
            "limit": 50,
        }
        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", {}).get("items", []) or payload.get("data", []) or []
        results = []
        for item in items:
            wallet = item.get("owner") or item.get("wallet") or item.get("address")
            if wallet:
                results.append(wallet)
        return results

    def fetch_wallet_transactions(self, wallet: str) -> list[dict[str, Any]]:
        if not self.config.helius_api_key:
            raise RuntimeError("HELIUS_API_KEY is required to score wallets from chain activity.")

        url = f"{HELIUS_BASE_URL}/addresses/{wallet}/transactions"
        params = {"api-key": self.config.helius_api_key}
        body = {"limit": 100, "type": "SWAP"}
        response = requests.post(url, params=params, json=body, timeout=30)
        response.raise_for_status()
        return response.json()

    def score_wallet(self, wallet: str) -> WalletMetrics:
        transactions = self.fetch_wallet_transactions(wallet)
        return calculate_wallet_metrics(wallet, transactions)

    def scan(self) -> list[WalletMetrics]:
        candidates = self.discover_wallets()
        print(f"Discovered {len(candidates)} wallet candidates")

        scored: list[WalletMetrics] = []
        for index, wallet in enumerate(candidates, start=1):
            try:
                metrics = self.score_wallet(wallet)
            except Exception as exc:  # keep scanning if one wallet/API call fails
                print(f"[{index}/{len(candidates)}] Skipped {wallet}: {exc}")
                continue

            if self._passes_filters(metrics):
                scored.append(metrics)
                print(f"[{index}/{len(candidates)}] PASS {wallet} ROI={metrics.roi:.2%} WR={metrics.win_rate:.2%}")
            else:
                print(f"[{index}/{len(candidates)}] fail {wallet}")
            time.sleep(self.config.sleep_seconds)

        scored.sort(key=lambda w: (w.roi, w.win_rate, w.avg_buy_size_sol), reverse=True)
        return scored[: self.config.top_wallets]

    def _passes_filters(self, metrics: WalletMetrics) -> bool:
        if metrics.is_likely_bot:
            return False
        return (
            metrics.active_today
            and metrics.win_rate > self.config.min_win_rate
            and metrics.trades >= self.config.min_trades
            and metrics.avg_buy_size_sol >= self.config.min_avg_buy_sol
        )
