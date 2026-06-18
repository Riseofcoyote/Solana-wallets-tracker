from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from .metrics import WalletMetrics

RANK_COLUMNS = ["roi", "win_rate", "avg_buy_size_sol"]


def _top_five_path(output_file: str) -> Path:
    path = Path(output_file)
    return path.with_name("top_5_research_candidates.csv")


def rank_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_values(RANK_COLUMNS, ascending=[False, False, False]).reset_index(drop=True)


def export_wallets(wallets: Iterable[WalletMetrics], output_file: str) -> tuple[Path, Path]:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [wallet.as_dict() for wallet in wallets]
    df = rank_dataframe(pd.DataFrame(rows))
    df.to_csv(path, index=False)

    top_five_path = _top_five_path(output_file)
    df.head(5).to_csv(top_five_path, index=False)
    return path, top_five_path


def export_ranked_dataframe(df: pd.DataFrame, output_file: str) -> tuple[Path, Path]:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    ranked = rank_dataframe(df)
    ranked.to_csv(path, index=False)

    top_five_path = _top_five_path(output_file)
    ranked.head(5).to_csv(top_five_path, index=False)
    return path, top_five_path
