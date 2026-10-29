"""
Display cleanup for statutory text imported from the Gazette PDFs.

The official BNS / BNSS / BSA text was read page by page, so a provision that crosses a page break
carries the page furniture with it: the running header ("THE GAZETTE OF INDIA EXTRAORDINARY",
"[Part II—", "Sec. 1]"), page numbers, rules of underscores, and the margin side-notes of every
section on that page ("Negligent act likely to spread infection ...", "Theft."), which the PDF emits
as a run of short lines just before the page number. This module removes that furniture and rejoins
the wrapped lines; the stored text is not changed.
"""
import re
from typing import List, Optional

_HEADER = re.compile(r"^(?:THE GAZETTE OF INDIA(?: EXTRAORDINARY)?|\[Part [IVX]+\s*[—–-]?.*|Sec\.\s*\d+\]?|PART [IVX]+\s*[—–-].*)$", re.I)
_PAGE_NUMBER = re.compile(r"^\d{1,4}$")
_RULE = re.compile(r"^[_\-—–=.\s]{3,}$")
# Side-notes are margin headings set in a narrow column: every line of the run is short
SIDE_NOTE_MAX = 26
# A line that starts a new paragraph rather than continuing the previous one
_NEW_PARAGRAPH = re.compile(r"^(?:\(\w{1,4}\)|\d{1,3}[A-Z]?\.\s|Explanation|Illustrations?|Provided|Exception)")


def _is_furniture(line: str) -> bool:
    return bool(_HEADER.match(line) or _PAGE_NUMBER.match(line) or _RULE.match(line))


def clean_statutory_text(text: Optional[str]) -> Optional[str]:
    """Statutory text without Gazette headers, page numbers, underscore rules or stray side-notes."""
    if not text:
        return text
    lines = [l.strip() for l in text.replace("\r", "").split("\n")]
    drop = [False] * len(lines)
    i = 0
    while i < len(lines):
        if lines[i] and _is_furniture(lines[i]):
            start = i
            while i < len(lines) and (not lines[i] or _is_furniture(lines[i])):
                drop[i] = True
                i += 1
            # The side-notes of the page sit directly above its page number / header
            j = start - 1
            while j >= 0 and lines[j] and len(lines[j]) <= SIDE_NOTE_MAX and not _NEW_PARAGRAPH.match(lines[j]):
                drop[j] = True
                j -= 1
            continue
        i += 1
    kept = [l for l, d in zip(lines, drop) if not d]

    paragraphs: List[str] = []
    for line in kept:
        if not line:
            continue
        if not paragraphs or _NEW_PARAGRAPH.match(line):
            paragraphs.append(line)
        else:
            joiner = "" if paragraphs[-1].endswith("-") else " "
            paragraphs[-1] = (paragraphs[-1][:-1] if joiner == "" else paragraphs[-1]) + joiner + line
    text = "\n".join(paragraphs)
    text = re.sub(r"_{3,}", "", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def subsection_text(text: Optional[str], number: str) -> Optional[str]:
    """
    The paragraph of one sub-section ('Section 318(4)' -> the '(4) Whoever cheats ...' paragraph) from
    a cleaned section text, or None when it cannot be found. Only a leading numeric sub-section is used.
    """
    m = re.search(r"\((\d+)\)", number or "")
    if not text or not m:
        return None
    n = int(m.group(1))
    paras = text.split("\n")
    start = next((k for k, p in enumerate(paras)
                  if re.match(rf"^(?:\d{{1,3}}[A-Z]?\.\s*)?\({n}\)\s", p)), None)
    if start is None:
        return None
    out = [re.sub(r"^\d{1,3}[A-Z]?\.\s*", "", paras[start])]
    for p in paras[start + 1:]:
        if re.match(rf"^\({n + 1}\)\s", p):
            break
        if re.match(r"^\(\d+\)\s", p):
            break
        out.append(p)
    return "\n".join(out)
