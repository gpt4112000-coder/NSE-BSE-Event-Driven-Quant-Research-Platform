"""Event-type classification for NSE corporate announcements.

Keyword-rule classifier over announcement headlines/descriptions.
V1 taxonomy covers the highest-frequency, most-studyable types; anything
unmatched falls into OTHER so no event is silently dropped.
"""

from __future__ import annotations

import re

EVENT_TYPES = (
    "RESULTS",
    "BOARD_MEETING",
    "DIVIDEND",
    "AGM_EGM",
    "CAPITAL_RAISE",
    "M_A",
    "BUYBACK",
    "SPLIT_BONUS",
    "CREDIT_RATING",
    "INVESTOR_MEET",
    "INSIDER_TRADE",
    "OTHER",
)

_RULES: list[tuple[str, list[tuple[str, str]]]] = [
    ("RESULTS", [(r"\b(result|results|financial result|q[1-4]\b|quarter)", "i")]),
    ("BOARD_MEETING", [(r"board meeting", "i")]),
    ("DIVIDEND", [(r"\bdividend\b", "i")]),
    ("AGM_EGM", [(r"\b(agm|egm|annual general meeting|extra.?ordinary general)\b", "i")]),
    ("CAPITAL_RAISE", [
        (r"\b(prefe?rential|qip|qualified institutional|rights issue|fund raising|"
         r"funds raising|capital raise)\b", "i")]),
    ("M_A", [(r"\b(acquisition|acquire|merger|amalgamation|stake in|divest\w*)\b", "i")]),
    ("BUYBACK", [(r"\bbuy ?back\b", "i")]),
    ("SPLIT_BONUS", [(r"\b(stock split|sub-?division|bonus issue|bonus equity)\b", "i")]),
    ("CREDIT_RATING", [(r"\b(credit rating|rating assigned|rating reaffirmed)\b", "i")]),
    ("INVESTOR_MEET", [(r"\b(investor meet|investor meeting|conference call|"
                        r"institutional investors)\b", "i")]),
    ("INSIDER_TRADE", [(r"\b(insider trading|sast|pledge|acquisition under)\b", "i")]),
]


def classify(text: str | None) -> str:
    """Return the first matching event type; OTHER when nothing matches."""
    low = str(text or "").lower()
    if not low.strip():
        return "OTHER"
    for event_type, patterns in _RULES:
        for pattern, flags in patterns:
            if re.search(pattern, low, getattr(re, flags.upper(), 0)):
                return event_type
    return "OTHER"


def classify_frame(frame, text_column: str = "headline"):
    """Attach an 'event_type' column to a DataFrame of announcements."""
    out = frame.copy()
    out["event_type"] = out[text_column].map(classify)
    return out


__all__ = ["EVENT_TYPES", "classify", "classify_frame"]
