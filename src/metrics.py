from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

LAMPORTS_PER_SOL = 1_000_000_000
SOL_MINT = "So11111111111111111111111111111111111111112"
EPSILON = 1e-9


@dataclass
class TokenPosition:
    qty: float = 0.0
    cost_sol: float = 0.0


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
    closed_trades: int = 0
    realized_profit_sol: float = 0.0
    realized_cost_basis_sol: float = 0.0
    sol_spent: float = 0.0
    sol_received: float = 0.0
    unknown_sell_sol: float = 0.0

    @property
    def is_likely_bot(self) -> bool:
        # A perfect win rate over enough closed trades is usually too perfect,
        # and huge trade counts often mean volume bots.
        return (self.win_rate >= 1.0 and self.closed_trades >= 10) or self.trades >= 1000 or bool(self.bot_reason)

    def as_dict(self) -> dict[str, Any]:
        return {
            "wallet": self.wallet,
            "win_rate": round(self.win_rate * 100, 2),
            "roi": round(self.roi * 100, 2),
            "avg_buy_size_sol": round(self.avg_buy_size_sol, 4),
            "trades": self.trades,
            "closed_trades": self.closed_trades,
            "realized_profit_sol": round(self.realized_profit_sol, 6),
            "realized_cost_basis_sol": round(self.realized_cost_basis_sol, 6),
            "sol_spent": round(self.sol_spent, 6),
            "sol_received": round(self.sol_received, 6),
            "unknown_sell_sol": round(self.unknown_sell_sol, 6),
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


def _same_wallet(value: object, wallet: str) -> bool:
    return str(value or "").strip() == wallet


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _raw_token_amount(raw: Any) -> float:
    """Convert Helius rawTokenAmount structures into a decimal token amount."""
    if not isinstance(raw, dict):
        return 0.0

    amount = _float(raw.get("tokenAmount"))
    decimals = int(_float(raw.get("decimals"), 0))
    if decimals <= 0:
        return amount
    return amount / (10**decimals)


def _token_transfer_amount(transfer: dict[str, Any]) -> float:
    if "tokenAmount" in transfer:
        return _float(transfer.get("tokenAmount"))
    return _raw_token_amount(transfer.get("rawTokenAmount"))


def _swap_side_amount(side: dict[str, Any] | None) -> float:
    if not side:
        return 0.0
    return _float(side.get("amount")) / LAMPORTS_PER_SOL


def extract_wallet_native_delta_sol(tx: dict[str, Any], wallet: str) -> float:
    """Return the wallet's SOL flow for one transaction.

    Negative means the wallet spent SOL. Positive means the wallet received SOL.
    """
    delta_lamports = 0.0
    for transfer in tx.get("nativeTransfers") or []:
        amount = _float(transfer.get("amount"))
        if _same_wallet(transfer.get("fromUserAccount"), wallet):
            delta_lamports -= amount
        if _same_wallet(transfer.get("toUserAccount"), wallet):
            delta_lamports += amount

    delta_sol = delta_lamports / LAMPORTS_PER_SOL
    if abs(delta_sol) > EPSILON:
        return delta_sol

    # Some aggregator swaps expose native in/out in events.swap without nativeTransfers.
    swap = (tx.get("events") or {}).get("swap") or {}
    native_input = swap.get("nativeInput") or {}
    native_output = swap.get("nativeOutput") or {}

    if _same_wallet(native_input.get("account"), wallet):
        delta_sol -= _swap_side_amount(native_input)
    if _same_wallet(native_output.get("account"), wallet):
        delta_sol += _swap_side_amount(native_output)

    return delta_sol


def extract_wallet_token_deltas(tx: dict[str, Any], wallet: str) -> dict[str, float]:
    """Return token balance deltas for the wallet keyed by mint address."""
    deltas: dict[str, float] = {}

    for transfer in tx.get("tokenTransfers") or []:
        mint = str(transfer.get("mint") or "").strip()
        if not mint:
            continue

        amount = _token_transfer_amount(transfer)
        if amount <= 0:
            continue

        if _same_wallet(transfer.get("fromUserAccount"), wallet):
            deltas[mint] = deltas.get(mint, 0.0) - amount
        if _same_wallet(transfer.get("toUserAccount"), wallet):
            deltas[mint] = deltas.get(mint, 0.0) + amount

    if deltas:
        return deltas

    # Fallback for enhanced swap payloads when tokenTransfers is not populated.
    swap = (tx.get("events") or {}).get("swap") or {}
    for item in swap.get("tokenInputs") or []:
        mint = str(item.get("mint") or "").strip()
        amount = _raw_token_amount(item.get("rawTokenAmount"))
        user_account = item.get("userAccount")
        if mint and amount > 0 and (not user_account or _same_wallet(user_account, wallet)):
            deltas[mint] = deltas.get(mint, 0.0) - amount

    for item in swap.get("tokenOutputs") or []:
        mint = str(item.get("mint") or "").strip()
        amount = _raw_token_amount(item.get("rawTokenAmount"))
        user_account = item.get("userAccount")
        if mint and amount > 0 and (not user_account or _same_wallet(user_account, wallet)):
            deltas[mint] = deltas.get(mint, 0.0) + amount

    return deltas


def extract_swap_amount_sol(tx: dict[str, Any], wallet: str) -> float:
    """Best-effort SOL size extraction from a Helius enhanced SWAP transaction."""
    return abs(extract_wallet_native_delta_sol(tx, wallet))


def _is_swap(tx: dict[str, Any]) -> bool:
    return str(tx.get("type", "")).upper() == "SWAP" and not tx.get("transactionError")


def calculate_wallet_metrics(wallet: str, transactions: Iterable[dict[str, Any]]) -> WalletMetrics:
    """Estimate wallet quality from recent swap transactions.

    This prototype uses average-cost realized PnL in SOL from swaps where both sides
    can be connected inside the lookback window. Sells for positions bought before
    the lookback window are tracked as unknown sells instead of counted as wins.
    """
    swaps = [tx for tx in transactions if _is_swap(tx)]
    swaps.sort(key=lambda t: t.get("timestamp") or 0)

    positions: dict[str, TokenPosition] = {}
    buy_sizes: list[float] = []

    wins = 0
    closed_trades = 0
    realized_profit_sol = 0.0
    realized_cost_basis_sol = 0.0
    sol_spent = 0.0
    sol_received = 0.0
    unknown_sell_sol = 0.0

    for tx in swaps:
        sol_delta = extract_wallet_native_delta_sol(tx, wallet)
        token_deltas = {
            mint: amount
            for mint, amount in extract_wallet_token_deltas(tx, wallet).items()
            if mint != SOL_MINT and abs(amount) > EPSILON
        }

        positive_tokens = {mint: qty for mint, qty in token_deltas.items() if qty > EPSILON}
        negative_tokens = {mint: abs(qty) for mint, qty in token_deltas.items() if qty < -EPSILON}

        # SOL out + token in = buy.
        if sol_delta < -EPSILON and positive_tokens:
            buy_cost = abs(sol_delta)
            sol_spent += buy_cost
            buy_sizes.append(buy_cost)

            per_token_cost = buy_cost / max(len(positive_tokens), 1)
            for mint, qty in positive_tokens.items():
                position = positions.setdefault(mint, TokenPosition())
                position.qty += qty
                position.cost_sol += per_token_cost

        # Token out + SOL in = sell. Use average cost from tracked buys.
        elif sol_delta > EPSILON and negative_tokens:
            sell_value = sol_delta
            sol_received += sell_value
            per_token_proceeds = sell_value / max(len(negative_tokens), 1)

            for mint, qty_sold in negative_tokens.items():
                position = positions.get(mint)
                if not position or position.qty <= EPSILON or position.cost_sol <= EPSILON:
                    unknown_sell_sol += per_token_proceeds
                    continue

                qty_closed = min(qty_sold, position.qty)
                cost_per_token = position.cost_sol / position.qty
                cost_basis = cost_per_token * qty_closed
                proceeds = per_token_proceeds * (qty_closed / qty_sold)

                profit = proceeds - cost_basis
                realized_profit_sol += profit
                realized_cost_basis_sol += cost_basis
                closed_trades += 1
                if profit > 0:
                    wins += 1

                position.qty -= qty_closed
                position.cost_sol -= cost_basis
                if position.qty <= EPSILON:
                    positions.pop(mint, None)

    trades = len(swaps)
    avg_buy = sum(buy_sizes) / len(buy_sizes) if buy_sizes else 0.0
    last_trade_at = iso_from_unix(swaps[-1].get("timestamp")) if swaps else ""

    win_rate = wins / closed_trades if closed_trades else 0.0
    roi = realized_profit_sol / realized_cost_basis_sol if realized_cost_basis_sol > EPSILON else 0.0

    bot_reason = ""
    if win_rate >= 1.0 and closed_trades >= 10:
        bot_reason = "100_percent_win_rate"
    elif trades >= 1000:
        bot_reason = "too_many_trades"

    return WalletMetrics(
        wallet=wallet,
        win_rate=win_rate,
        roi=roi,
        avg_buy_size_sol=avg_buy,
        trades=trades,
        closed_trades=closed_trades,
        realized_profit_sol=realized_profit_sol,
        realized_cost_basis_sol=realized_cost_basis_sol,
        sol_spent=sol_spent,
        sol_received=sol_received,
        unknown_sell_sol=unknown_sell_sol,
        last_trade_at=last_trade_at,
        active_today=is_today_utc(last_trade_at),
        bot_reason=bot_reason,
    )
