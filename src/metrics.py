from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

LAMPORTS_PER_SOL = 1_000_000_000


@dataclass
class WalletMetrics:
    wallet: str
    win_rate: float
    roi: float
    avg_buy_size_sol: float
    trades: int
    last_trade_at: str
    active_today: bool
    bot_reason: str = ""

    @property
    def is_likely_bot(self) -> bool:
        # 100% win rate is usually too perfect, and huge trade counts often mean volume bots.
        return self.win_rate >= 1.0 or self.trades >= 1000 or bool(self.bot_reason)

    def as_dict(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "win_rate": round(self.win_rate * 100, 2),
            "roi": round(self.roi * 100, 2),
            "avg_buy_size_sol": round(self.avg_buy_size_sol, 4),
            "trades": self.trades,
            "last_trade_at": self.last_trade_at,
            "active_today": self.active_today,
            "bot_reason": self.bot_reason,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_from_unix(ts: int | float | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


def is_today_utc(iso_date: str) -> bool:
    if not iso_date:
        return False
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt.date() == utc_now().date()


def extract_swap_amount_sol(tx: dict[str, Any], wallet: str) -> float:
    """Best-effort SOL size extraction from a Helius enhanced SWAP transaction."""
    native_transfers = tx.get("nativeTransfers") or []
    amounts = []
    for transfer in native_transfers:
        amount = abs(float(transfer.get("amount", 0))) / LAMPORTS_PER_SOL
        if amount > 0:
            amounts.append(amount)
    return max(amounts) if amounts else 0.0


def calculate_wallet_metrics(wallet: str, transactions: Iterable[dict[str, Any]]) -> WalletMetrics:
    swaps: list[dict[str, Any]] = []
    buy_sizes: list[float] = []

    for tx in transactions:
        if str(tx.get("type", "")).upper() != "SWAP":
            continue
        swaps.append(tx)
        size = extract_swap_amount_sol(tx, wallet)
        if size > 0:
            buy_sizes.append(size)

    swaps.sort(key=lambda t: t.get("timestamp") or 0)
    trades = len(swaps)
    avg_buy = sum(buy_sizes) / len(buy_sizes) if buy_sizes else 0.0
    last_trade_at = iso_from_unix(swaps[-1].get("timestamp")) if swaps else ""

    # Prototype scoring: use a conservative placeholder until full cost-basis PnL is added.
    # The scanner still filters by real activity, trade count, and buy size.
    estimated_wins = 0
    estimated_losses = 0
    for tx in swaps:
        events = tx.get("events") or {}
        swap = events.get("swap") or {}
        token_inputs = swap.get("tokenInputs") or []
        token_outputs = swap.get("tokenOutputs") or []
        if token_inputs and token_outputs:
            estimated_wins += 1
        else:
            estimated_losses += 1

    win_rate = estimated_wins / trades if trades else 0.0
    roi = (win_rate - 0.5) * 2 if trades else 0.0

    bot_reason = ""
    if win_rate >= 1.0 and trades >= 10:
        bot_reason = "100_percent_win_rate"
    elif trades >= 1000:
        bot_reason = "too_many_trades"

    return WalletMetrics(
        wallet=wallet,
        win_rate=win_rate,
        roi=roi,
        avg_buy_size_sol=avg_buy,
        trades=trades,
        last_trade_at=last_trade_at,
        active_today=is_today_utc(last_trade_at),
        bot_reason=bot_reason,
    )
