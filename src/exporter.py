from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from .metrics import WalletMetrics


def export_wallets(wallets: Iterable[WalletMetrics], output_file: str) -> Path:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [wallet.as_dict() for wallet in wallets]
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["roi", "win_rate", "avg_buy_size_sol"], ascending=[False, False, False])
    df.to_csv(path, index=False)
    return path
