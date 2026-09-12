"""Split a 10-K / 10-Q into its regulatory Items.

The Item is the single most useful filter an analyst has, so sections are
first-class: a Risk Factors chunk must never bleed into MD&A.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "Item 1A." / "ITEM 7 —" / "Item 7A:" at the start of a line, followed by a title.
_ITEM_RE = re.compile(
    r"^\s*item\s+(?P<item>\d{1,2}[a-c]?)\s*[.:\-—–]?\s*(?P<title>[^\n]{0,120})$",
    re.IGNORECASE | re.MULTILINE,
)

KNOWN_10K_ITEMS = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity",
    "6": "Reserved",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits and Financial Statement Schedules",
}

# Minimum body size for a heading to count as the real section rather than a
# table-of-contents entry.
_MIN_SECTION_CHARS = 400


@dataclass(frozen=True)
class Section:
    item: str
    title: str
    text: str
    char_start: int
    char_end: int


def split_sections(text: str) -> list[Section]:
    """Return sections in document order.

    Headings that appear in a table of contents produce tiny bodies; when the
    same item appears more than once we keep the longest occurrence.
    """
    matches = list(_ITEM_RE.finditer(text))
    if not matches:
        return [
            Section(item="FULL", title="Full document", text=text, char_start=0, char_end=len(text))
        ]

    candidates: list[Section] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        item = m.group("item").upper()
        title = m.group("title").strip(" .:-—–") or KNOWN_10K_ITEMS.get(item, "")
        # Trim whitespace while keeping offsets exact, so citations resolve.
        raw = text[start:end]
        lead = len(raw) - len(raw.lstrip())
        trail = len(raw) - len(raw.rstrip())
        candidates.append(
            Section(
                item=item,
                title=title,
                text=raw.strip(),
                char_start=start + lead,
                char_end=end - trail,
            )
        )

    best: dict[str, Section] = {}
    for sec in candidates:
        if len(sec.text) < _MIN_SECTION_CHARS and sec.item in best:
            continue
        if sec.item not in best or len(sec.text) > len(best[sec.item].text):
            best[sec.item] = sec
    return sorted(best.values(), key=lambda s: s.char_start)
