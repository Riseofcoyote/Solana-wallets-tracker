from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from .metrics import WalletMetrics, calculate_wallet_metrics, utc_now
from .solscan import DEFAULT_SOLSCAN_ACCOUNT_TRANSFER_URL, SolscanClient

HELIUS_BASE_URL = "https://api.helius.xyz/v0"
BIRDEYE_BASE_URL = "https://public-api.birdeye.so"
DEXSCREENER_BASE_URL = "https://api.dexscreener.com"
DEXSCREENER_TOKEN_PROFILES_URL = f"{DEXSCREENER_BASE_URL}/token-profiles/latest/v1"
SOL_MINT = "So11111111111111111111111111111111111111112"


@dataclass
class ScannerConfig:
    helius_api_key: str
    birdeye_api_key: str = ""
    discovery_token_mints: list[str] | None = None
    lookback_hours: int = 24
    min_win_rate: float = 0.50
    min_trades: int = 10
    min_avg_buy_sol: float = 0.5
    top_wallets: int = 100
    max_wallets_to_score: int = 200
    sleep_seconds: float = 0.15
    dexscreener_discovery: bool = False
    dexscreener_token_profile_url: str = DEXSCREENER_TOKEN_PROFILES_URL
    dexscreener_max_tokens: int = 25
    solscan_api_key: str = ""
    solscan_enrichment: bool = False
    solscan_account_transfer_url: str = DEFAULT_SOLSCAN_ACCOUNT_TRANSFER_URL
    solscan_auth_header: str = "token"

    @classmethod
    def from_env(cls) -> "ScannerConfig":
        tokens = os.getenv("DISCOVERY_TOKEN_MINTS", "").strip()
        return cls(
            helius_api_key=os.getenv("HELIUS_API_KEY", "").strip(),
            birdeye_api_key=os.getenv("BIRDEYE_API_KEY", "").strip(),
            discovery_token_mints=[t.strip() for t in tokens.split(",") if t.strip()] or [SOL_MINT],
            lookback_hours=int(os.getenv("LOOKBACK_HOURS", "24")),
            min_win_rate=float(os.getenv("MIN_WIN_RATE", "0.50")),
            min_trades=int(os.getenv("MIN_TRADES", "10")),
            min_avg_buy_sol=float(os.getenv("MIN_AVG_BUY_SOL", "0.5")),
            top_wallets=int(os.getenv("TOP_WALLETS", "100")),
            max_wallets_to_score=int(os.getenv("MAX_WALLETS_TO_SCORE", "200")),
            sleep_seconds=float(os.getenv("SLEEP_SECONDS", "0.15")),
            dexscreener_discovery=_env_bool("DEXSCREENER_DISCOVERY", False),
            dexscreener_token_profile_url=os.getenv("DEXSCREENER_TOKEN_PROFILE_URL", DEXSCREENER_TOKEN_PROFILES_URL).strip()
            or DEXSCREENER_TOKEN_PROFILES_URL,
            dexscreener_max_tokens=int(os.getenv("DEXSCREENER_MAX_TOKENS", "25")),
            solscan_api_key=os.getenv("SOLSCAN_API_KEY", "").strip(),
            solscan_enrichment=_env_bool("SOLSCAN_ENRICHMENT", False),
            solscan_account_transfer_url=os.getenv(
                "SOLSCAN_ACCOUNT_TRANSFER_URL", DEFAULT_SOLSCAN_ACCOUNT_TRANSFER_URL
            ).strip()
            or DEFAULT_SOLSCAN_ACCOUNT_TRANSFER_URL,
            solscan_auth_header=os.getenv("SOLSCAN_AUTH_HEADER", "token").strip() or "token",
        )


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        value = value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        results.append(value)
    return results


def _full_url(url_or_path: str) -> str:
    value = url_or_path.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if not value.startswith("/"):
        value = f"/{value}"
    return f"{DEXSCREENER_BASE_URL}{value}"


class SolanaWalletScanner:
    def __init__(self, config: ScannerConfig):
        self.config = config
        self.helius_session = requests.Session()
        self.birdeye_session = requests.Session()
        self.dexscreener_session = requests.Session()
        self.solscan_client: SolscanClient | None = None

        if config.birdeye_api_key:
            self.birdeye_session.headers.update({"X-API-KEY": config.birdeye_api_key, "x-chain": "solana"})

        if config.solscan_enrichment:
            if config.solscan_api_key:
                self.solscan_client = SolscanClient(
                    api_key=config.solscan_api_key,
                    account_transfer_url=config.solscan_account_transfer_url,
                    auth_header=config.solscan_auth_header,
                )
            else:
                print("SOLSCAN_ENRICHMENT=true but SOLSCAN_API_KEY is not set; skipping Solscan verification.")

    def discover_wallets(self) -> list[str]:
        """Discover candidate wallets.

        DEX Screener can discover fresh Solana token mints. Birdeye is then used
        to convert those token mints into top-trader wallet candidates. If no
        API discovery is available, SEED_WALLETS can still be used as fallback.
        """
        seed_wallets = [w.strip() for w in os.getenv("SEED_WALLETS", "").split(",") if w.strip()]
        wallets: list[str] = list(seed_wallets)
        token_mints = self.discover_token_mints()

        if not self.config.birdeye_api_key:
            if token_mints:
                print(
                    "DEX Screener discovered token mints, but BIRDEYE_API_KEY is needed "
                    "to convert tokens into top-trader wallets."
                )
            if not wallets:
                print("No BIRDEYE_API_KEY or SEED_WALLETS found, so there are no wallets to score.")
            return _dedupe_keep_order(wallets)[: self.config.max_wallets_to_score]

        for mint in token_mints:
            try:
                wallets.extend(self._birdeye_top_traders(mint))
            except requests.RequestException as exc:
                print(f"Birdeye discovery failed for {mint}: {self._format_http_error(exc)}")
            time.sleep(self.config.sleep_seconds)

        return _dedupe_keep_order(wallets)[: self.config.max_wallets_to_score]

    def discover_token_mints(self) -> list[str]:
        mints = list(self.config.discovery_token_mints or [SOL_MINT])
        if self.config.dexscreener_discovery:
            try:
                mints.extend(self._dexscreener_recent_solana_token_mints())
            except requests.RequestException as exc:
                print(f"DEX Screener discovery failed: {self._format_http_error(exc)}")
        return _dedupe_keep_order(mints)

    def _dexscreener_recent_solana_token_mints(self) -> list[str]:
        """Fetch recent Solana token profile mints from DEX Screener.

        The default endpoint is the documented HTTP latest profile endpoint.
        DEXSCREENER_TOKEN_PROFILE_URL can override it if you want to test a newer
        path such as /token-profiles/recent-updates/v1.
        """
        url = _full_url(self.config.dexscreener_token_profile_url)
        response = self.dexscreener_session.get(url, headers={"Accept": "*/*"}, timeout=30)
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, dict):
            items = payload.get("items") or payload.get("data") or payload.get("profiles") or []
        elif isinstance(payload, list):
            items = payload
        else:
            items = []

        mints: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            chain_id = str(item.get("chainId") or "").strip().lower()
            token_address = str(item.get("tokenAddress") or item.get("address") or "").strip()
            if chain_id == "solana" and token_address:
                mints.append(token_address)
            if len(mints) >= self.config.dexscreener_max_tokens:
                break

        print(f"DEX Screener discovered {len(mints)} recent Solana token mint(s)")
        return mints

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
        response = self.birdeye_session.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", {}).get("items", []) or payload.get("data", []) or []
        results: list[str] = []
        for item in items:
            wallet = item.get("owner") or item.get("wallet") or item.get("address")
            if wallet:
                results.append(wallet)
        return results

    def fetch_wallet_transactions(self, wallet: str) -> list[dict[str, Any]]:
        if not self.config.helius_api_key:
            raise RuntimeError("HELIUS_API_KEY is required to score wallets from chain activity.")

        url = f"{HELIUS_BASE_URL}/addresses/{wallet}/transactions"
        params = {"api-key": self.config.helius_api_key, "limit": 100, "type": "SWAP"}
        response = self.helius_session.get(url, params=params, timeout=30)
        response.raise_for_status()
        transactions = response.json()
        if not isinstance(transactions, list):
            raise RuntimeError(f"Unexpected Helius response shape for {wallet}: {type(transactions).__name__}")
        return self._filter_lookback(transactions)

    def _filter_lookback(self, transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cutoff = utc_now().timestamp() - (self.config.lookback_hours * 3600)
        filtered: list[dict[str, Any]] = []
        for tx in transactions:
            try:
                timestamp = float(tx.get("timestamp") or 0)
            except (TypeError, ValueError):
                continue
            if timestamp >= cutoff:
                filtered.append(tx)
        return filtered

    def score_wallet(self, wallet: str) -> WalletMetrics:
        transactions = self.fetch_wallet_transactions(wallet)
        return calculate_wallet_metrics(wallet, transactions)

    def scan(self) -> list[WalletMetrics]:
        candidates = self.discover_wallets()
        print(f"Discovered {len(candidates)} wallet candidates")

        if candidates and not self.config.helius_api_key:
            print("Set HELIUS_API_KEY in .env before running API scan mode.")
            return []

        scored: list[WalletMetrics] = []
        for index, wallet in enumerate(candidates, start=1):
            try:
                metrics = self.score_wallet(wallet)
            except Exception as exc:  # keep scanning if one wallet/API call fails
                print(f"[{index}/{len(candidates)}] Skipped {wallet}: {self._format_http_error(exc)}")
                continue

            if self._passes_filters(metrics) and self._passes_solscan_verification(metrics.wallet):
                scored.append(metrics)
                print(
                    f"[{index}/{len(candidates)}] PASS {wallet} "
                    f"ROI={metrics.roi:.2%} WR={metrics.win_rate:.2%} "
                    f"trades={metrics.trades} closed={metrics.closed_trades}"
                )
            else:
                reasons = ", ".join(self._failure_reasons(metrics)) or "below threshold"
                print(f"[{index}/{len(candidates)}] fail {wallet} ({reasons})")
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

    def _passes_solscan_verification(self, wallet: str) -> bool:
        if not self.solscan_client:
            return True

        try:
            summary = self.solscan_client.summarize_wallet_activity(wallet, self.config.lookback_hours)
        except Exception as exc:
            # Do not block a wallet just because optional enrichment is temporarily unavailable.
            print(f"Solscan verification skipped for {wallet}: {self._format_http_error(exc)}")
            return True

        if not summary.active_in_lookback:
            print(f"Solscan verification failed for {wallet}: no transfers in the lookback window")
            return False

        print(f"Solscan verified {wallet}: last_transfer_at={summary.last_transfer_at}")
        return True

    def _failure_reasons(self, metrics: WalletMetrics) -> list[str]:
        reasons: list[str] = []
        if metrics.bot_reason:
            reasons.append(metrics.bot_reason)
        elif metrics.is_likely_bot:
            reasons.append("likely_bot")
        if not metrics.active_today:
            reasons.append("not_active_today")
        if metrics.win_rate <= self.config.min_win_rate:
            reasons.append(f"win_rate<={self.config.min_win_rate:.0%}")
        if metrics.trades < self.config.min_trades:
            reasons.append(f"trades<{self.config.min_trades}")
        if metrics.avg_buy_size_sol < self.config.min_avg_buy_sol:
            reasons.append(f"avg_buy<{self.config.min_avg_buy_sol:g}_SOL")
        return reasons

    @staticmethod
    def _format_http_error(exc: BaseException) -> str:
        response = getattr(exc, "response", None)
        if response is None:
            return str(exc)
        body = getattr(response, "text", "") or ""
        body = body[:250].replace("\n", " ")
        return f"{exc} | response={body}"
