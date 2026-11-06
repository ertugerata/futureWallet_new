#!/usr/bin/env python3
r"""
FutureWallet – sembol temizleme aracı (Prompt 2.4).

Mevcut veritabanındaki kayıtları tarar; asset_symbol regex
^[A-Z0-9.=^\-/]{1,20}$ uymayanları listeler.

Kullanım:
    python scripts/sanitize_symbols.py          # sadece listele
    python scripts/sanitize_symbols.py --fix    # uymayan kayıtları sil
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Proje kökünü sys.path'e ekle
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent),
)

from sqlalchemy import select

from db import Decision, ShadowPortfolio, Transaction, get_session

ASSET_SYMBOL_PAT = re.compile(r"^[A-Z0-9.=^\-/]{1,20}$")


def _check_symbol(sym: str | None) -> bool:
    if not sym:
        return True  # None → uyumlu sayılmaz ama boş olmayan kayıtlar için
    return bool(ASSET_SYMBOL_PAT.match(sym))


def scan(session) -> list[dict]:
    """Tüm tablolardaki kötü sembolleri tar."""
    problems: list[dict] = []

    for model, label, sym_col in [
        (Transaction, "transactions", "asset_symbol"),
        (Decision, "decisions", "asset_symbol"),
        (ShadowPortfolio, "shadow_portfolios", "asset_symbol"),
    ]:
        rows = (
            session.execute(
                select(getattr(model, sym_col)).where(getattr(model, sym_col).isnot(None))
            )
            .scalars()
            .all()
        )
        for row in rows:
            sym = row[0] if isinstance(row, tuple) else row
            if sym and not _check_symbol(str(sym)):
                problems.append(
                    {
                        "table": label,
                        "symbol": str(sym),
                    }
                )

    return problems


def fix(session, problems: list[dict]) -> int:
    """Kayıtları sil (passed --fix ile). Dikkat: Transaction CASCADE ile
    bağlı Decision ve ShadowPortfolio'ları da silebilir.
    Önce ShadowPortfolio, sonra Decision, sonra Transaction."""
    deleted = 0
    for p in problems:
        if p["table"] == "shadow_portfolios":
            session.execute(
                ShadowPortfolio.__table__.delete().where(
                    ShadowPortfolio.asset_symbol == p["symbol"]
                )
            )
            deleted += 1
        elif p["table"] == "decisions":
            session.execute(Decision.__table__.delete().where(Decision.asset_symbol == p["symbol"]))
            deleted += 1
        elif p["table"] == "transactions":
            session.execute(
                Transaction.__table__.delete().where(Transaction.asset_symbol == p["symbol"])
            )
            deleted += 1
    session.commit()
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="FutureWallet sembol temizleme aracı")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Uymayan kayıtları sil (dikkat: veri kaybı!)",
    )
    args = parser.parse_args()

    session = get_session()
    try:
        problems = scan(session)
    finally:
        session.close()

    if not problems:
        print("✓ Uygun olmayan sembol bulunamadı.")
        return 0

    print(f"⚠ {len(problems)} kayıt uyumsuz sembol içeriyor:")
    for p in problems:
        print(f"  - {p['table']}: {p['symbol']!r}")

    if not args.fix:
        print("\nÇözüm: --fix ile silin veya sembolleri düzenleyin.")
        return 1

    print("\n--fix ile siliniyor...")
    session = get_session()
    try:
        deleted = fix(session, problems)
        print(f"✓ {deleted} kayıt silindi.")
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
