from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

DEFAULT_SOLSCAN_ACCOUNT_TRANSFER_URL = "https://pro-api.solscan.io/v2.0/account/transfer"


@dataclass
class SolscanTransferSummary:
    wallet: str
    transfer_count: int
    last_transfer_at: str
    active_in_lookback: bool


def _parse_timestamp(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return 0.0

    # Some APIs return milliseconds instead of seconds.
    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000
    return timestamp


def _iso_from_timestamp(timestamp: float) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


class SolscanClient:
    """Small Solscan Pro client used only for optional wallet enrichment.

    Keep the API key in `.env` as SOLSCAN_API_KEY. Do not hardcode or commit it.
    Endpoint and auth header are configurable because Solscan Pro routes can vary
    by plan/version.
    """

    def __init__(
        self,
        api_key: str,
        account_transfer_url: str = DEFAULT_SOLSCAN_ACCOUNT_TRANSFER_URL,
        auth_header: str = "token",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.account_transfer_url = account_transfer_url.strip() or DEFAULT_SOLSCAN_ACCOUNT_TRANSFER_URL
        self.auth_header = auth_header.strip() or "token"
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({self.auth_header: self.api_key, "Accept": "application/json"})

    def fetch_account_transfers(self, wallet: str, page_size: int = 40) -> list[dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("SOLSCAN_API_KEY is required for Solscan enrichment.")

        params = {
            "address": wallet,
            "page": 1,
            "page_size": page_size,
            "sort_by": "block_time",
            "sort_order": "desc",
        }
        response = self.session.get(self.account_transfer_url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        return self._extract_items(payload)

    def summarize_wallet_activity(self, wallet: str, lookback_hours: int) -> SolscanTransferSummary:
        transfers = self.fetch_account_transfers(wallet)
        cutoff = time.time() - (lookback_hours * 3600)

        last_timestamp = 0.0
        active_count = 0
        for transfer in transfers:
            timestamp = self._transfer_timestamp(transfer)
            if timestamp > last_timestamp:
                last_timestamp = timestamp
            if timestamp >= cutoff:
                active_count += 1

        return SolscanTransferSummary(
            wallet=wallet,
            transfer_count=len(transfers),
            last_transfer_at=_iso_from_timestamp(last_timestamp),
            active_in_lookback=active_count > 0,
        )

    @staticmethod
    def _extract_items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if not isinstance(payload, dict):
            return []

        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("items", "result", "transfers"):
                items = data.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]

        for key in ("items", "result", "transfers"):
            items = payload.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]

        return []

    @staticmethod
    def _transfer_timestamp(transfer: dict[str, Any]) -> float:
        for key in ("block_time", "blockTime", "time", "timestamp", "trans_time", "transTime"):
            timestamp = _parse_timestamp(transfer.get(key))
            if timestamp > 0:
                return timestamp
        return 0.0
