from __future__ import annotations

import re
import unicodedata
from datetime import date

CLOSED_PATTERNS: tuple[str, ...] = (
    r"終了いたしました",
    r"募集終了",
    r"受付終了",
    r"公募終了",
    r"申込終了",
    r"募集を締め切りました",
    r"募集を締め切り",
    r"受付を終了しました",
    r"受付を終了いたしました",
    r"応募を締め切りました",
    r"応募受付を終了",
    r"選定結果",
    r"契約結果",
)


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip()


def has_closed_signal(title: str | None, summary: str | None = None) -> bool:
    title_text = _normalize(title)
    if any(re.search(pattern, title_text, re.I) for pattern in CLOSED_PATTERNS):
        return True
    # Only inspect the leading portion of the body to avoid unrelated navigation,
    # archives, or referenced historical notices triggering a false closure.
    body_head = _normalize(summary)[:500]
    return any(re.search(pattern, body_head, re.I) for pattern in CLOSED_PATTERNS)


def project_status(
    deadline: str | None,
    opening_date: str | None,
    *,
    title: str | None = None,
    summary: str | None = None,
    today: date | None = None,
) -> str:
    if has_closed_signal(title, summary):
        return "closed"

    current = today or date.today()
    relevant = deadline or opening_date
    if not relevant:
        return "unknown"
    try:
        target = date.fromisoformat(relevant)
    except (TypeError, ValueError):
        return "unknown"
    if target < current:
        return "closed"
    if (target - current).days <= 7:
        return "soon"
    return "open"
