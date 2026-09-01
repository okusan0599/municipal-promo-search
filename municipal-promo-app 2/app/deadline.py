from __future__ import annotations

import re
from datetime import date

ERA_BASE = {"令和": 2018, "平成": 1988}

_DATE_PATTERN = re.compile(
    r"(?:(?P<era>令和|平成)\s*(?P<ey>\d{1,2})\s*年|(?P<y>20\d{2})\s*[年/.-])"
    r"\s*(?P<m>\d{1,2})\s*[月/.-]\s*(?P<d>\d{1,2})\s*日?"
)

# Prefer the final proposal/application submission deadline over earlier question periods.
DEADLINE_LABELS: tuple[str, ...] = (
    r"企画提案書(?:等|類)?(?:の)?(?:提出)?(?:期限|締切|提出期間|受付期間)",
    r"企画提案(?:書)?(?:等|類)?.{0,15}(?:提出期限|提出締切|提出期間|受付期間)",
    r"提案書(?:等|類)?.{0,15}(?:提出期限|提出締切|提出期間|受付期間)",
    r"応募書類?.{0,15}(?:提出期限|提出締切|提出期間|受付期間)",
    r"申請書類?.{0,15}(?:提出期限|提出締切|提出期間|受付期間)",
    r"参加表明書?.{0,15}(?:提出期限|提出締切|提出期間|受付期限|受付期間)",
    r"参加申込書?.{0,15}(?:提出期限|提出締切|提出期間|受付期限|受付期間|期限)",
    r"参加資格(?:確認)?申請.{0,20}(?:提出期限|提出締切|提出期間|受付期限|受付期間|期限)",
    r"応募受付期間",
    r"申請受付期間",
    r"受付期間",
    r"応募期限",
    r"申込期限",
    r"提出期限",
    r"提出締切",
    r"締切(?:日)?",
)


def _iso(match: re.Match[str]) -> str | None:
    groups = match.groupdict()
    year = int(groups["y"]) if groups.get("y") else ERA_BASE[groups["era"]] + int(groups["ey"])
    try:
        return date(year, int(groups["m"]), int(groups["d"])).isoformat()
    except (TypeError, ValueError):
        return None


def _dates(text: str) -> list[tuple[int, int, str]]:
    normalized = (text or "").replace("元年", "1年")
    rows: list[tuple[int, int, str]] = []
    for match in _DATE_PATTERN.finditer(normalized):
        value = _iso(match)
        if value:
            rows.append((match.start(), match.end(), value))
    return rows


def _date_after_label(text: str, match: re.Match[str]) -> str | None:
    # Keep the window short so a later, unrelated presentation date is not selected.
    window = text[match.start(): match.start() + 320]
    dates = _dates(window)
    if not dates:
        return None

    # If the label introduces a date range, the deadline is the end of the range.
    if len(dates) >= 2:
        between = window[dates[0][1]: dates[1][0]]
        tail = window[dates[1][1]: dates[1][1] + 24]
        if re.search(r"から|～|〜|~|－|—|–|\s[-ー]\s", between) or re.search(r"まで|迄", tail):
            return dates[1][2]
    return dates[0][2]


def extract_deadline(text: str | None) -> str | None:
    normalized = re.sub(r"\s+", " ", text or "")
    for label in DEADLINE_LABELS:
        for match in re.finditer(label, normalized, re.I):
            found = _date_after_label(normalized, match)
            if found:
                return found
    return None
