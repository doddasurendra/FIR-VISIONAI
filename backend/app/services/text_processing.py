"""
Text cleanup and structure-aware chunking for ingested documents.

Chunks never cross a physical page boundary, so every citation can name an exact page. For legal
texts, numbered headings ("303. ...", "21A. ...") are tracked so each chunk also carries the
Section/Article/Rule it belongs to.
"""
import html
import re
from dataclasses import dataclass, field
from typing import List, Optional

# Common English function words; official English legal text contains several per line.
_ENGLISH_MARKERS = {
    "the", "of", "and", "to", "in", "or", "a", "an", "be", "by", "any", "shall", "is", "for",
    "with", "as", "on", "such", "under", "that", "which", "may", "not", "this", "from", "at",
    "who", "whoever", "person", "section", "act", "article", "it", "his", "he", "has", "been",
}
# Legacy (non-Unicode) Hindi fonts such as Kruti Dev map Devanagari to ASCII: letters glued to
# punctuation ("fnYyh]", "vlk/kkj.k"), tokens opening with "[" ("[k.M"), and short words with
# repeated "k", which stands for the vowel sign aa ("Hkkx", "izkf/kdkj").
_LEGACY_TOKEN = re.compile(r"[A-Za-z][\]\[/;|][A-Za-z]|[A-Za-z]\]$|^\[[A-Za-z]|^[A-Za-z]{0,3}k[a-jl-z]{0,2}k")
# Tokens with digits ("DB/RC9-ACB-GNT/", "13(1)/2020") and relation abbreviations ("S/o", "r/w")
# are FIR form text, not legacy-font garbage
_FORM_TOKEN = re.compile(r"\d|^\(?[A-Za-z]{1,2}/[A-Za-z]{1,2}[.,;:)]*$")
_FIRST_SECTION = re.compile(r"(short title|this (act|sanhita|adhiniyam|code|constitution) may be called|name and territory)", re.I)
# Structural headings printed above runs of sections, e.g. "CHAPTER XVII" / "OF OFFENCES AGAINST PROPERTY" / "Of theft"
_CHAPTER = re.compile(r"^\s*CHAPTER\s+([IVXLC]+[A-Z]?)\s*$", re.I)
_GROUP = re.compile(r"^\s*(Of [a-z][^.]{2,60})\s*$")
# Amendment footnotes and schedule entries that look like numbered headings ("1. Subs. by Act ...")
_FOOTNOTE = re.compile(r"^(subs?\.|ins\.|omitted|added|rep\.|renumbered|the words|certain words|entr(y|ies)\b|paragraph\b|w\.e\.f)", re.I)
# Optional amendment marker before inserted provisions, e.g. "2[21A. Right to education.—"
_HEADING = re.compile(r"^\s*(?:\d{1,2}\[)?(\d{1,3})([A-Z]{0,3})\.\s+(.{2,})$")
_TOC_HEADINGS_PER_PAGE = 15


def _is_garbled_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.count("�") / max(len(stripped), 1) > 0.05:
        return True
    latin1 = sum(1 for ch in stripped if " " <= ch <= "ÿ")
    if latin1 / max(len(stripped), 1) > 0.15:
        return True
    tokens = re.findall(r"\S+", stripped)
    legacy_hits = sum(1 for t in tokens if _LEGACY_TOKEN.search(t) and not _FORM_TOKEN.search(t))
    words = [t.lower().strip(".,;:()[]\"'") for t in tokens]
    markers = sum(1 for w in words if w in _ENGLISH_MARKERS)
    # English sentences with a bracketed note ("[Attach separate sheet if necessary]") are kept
    if legacy_hits >= 2 and not (markers >= 2 and legacy_hits < 3):
        return True
    alpha = [w for w in words if w.isalpha() and len(w) > 1]
    if len(alpha) >= 6 and not any(w in _ENGLISH_MARKERS for w in alpha) and legacy_hits >= 1:
        return True
    return False


_CELL_BREAK = re.compile(r"</t[dh]>\s*<t[dh][^>]*>", re.I)
_ROW_BREAK = re.compile(r"</tr>|<br\s*/?>|</p>|</li>|</h[1-6]>|</div>", re.I)
_MARKUP_TAG = re.compile(r"</?(?:table|thead|tbody|tfoot|tr|td|th|caption|br|p|div|span|b|i|u|strong|em|sup|sub|"
                         r"ul|ol|li|h[1-6]|img|font|center|col|colgroup)\b[^>]*>", re.I)


def strip_markup(text: str) -> str:
    """
    OCR services return tables as HTML ("<table><tr><td>1. District</td><td>Guntur</td>...") and may
    escape characters ("&amp;"). Keep every cell's text: cells become " | "-separated, rows become lines.
    Only known HTML tags are removed, so text such as "< 5 kg" is left alone.
    """
    if "<" not in text and "&" not in text:
        return text
    out = _CELL_BREAK.sub(" | ", text)
    out = _ROW_BREAK.sub("\n", out)
    out = _MARKUP_TAG.sub(" ", out)
    return html.unescape(out)


# Vision models asked to "read" a page sometimes describe a logo, seal or photograph instead
# ("The image depicts the emblem of ..."). Such paragraphs are not text printed on the page.
_DESCRIBE_OPENER = re.compile(
    r"^\s*(?:\d+\.\s*)?(?:the|this|in summary,? the|overall,? the|the overall design of the)\s+"
    r"(?:image|picture|photo|photograph|emblem|logo|seal|insignia|crest|badge|design|scan|document image)\b", re.I)
_DESCRIBE_WORDS = re.compile(
    r"\b(image|picture|photograph|depicts?|depicted|emblem|logo|seal|insignia|crest|symboli[sz]es?|symbol|"
    r"circular in shape|spokes|ribbon|banner|encircled|reminiscent|motto|design|background|appears to be|"
    r"visible|features?:|encapsulates|underscores|translates to)\b", re.I)
# Form text: numbered FIR fields ("6. Complainant / Informant :"), labels with colons, dates, crime numbers
_FORM_MARKER = re.compile(r"^\s*\(?[0-9ivx]{1,4}[.)]\s*\(?[a-z]?\)?\s*[A-Z][^:]{1,60}:|\b\d{1,4}/\d{2,4}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|"
                          r"\b(Cr\.?P\.?C|IPC|BNS|BNSS|Sections?|u/s|FIR No|Crime No)\b", re.I)


def strip_image_descriptions(text: str) -> str:
    """
    Remove paragraphs that describe pictures (logos, emblems, photographs) rather than transcribe
    text, e.g. the "The image depicts the emblem of the Maharashtra Police ..." block an OCR model
    put above FIR 178/2024. Paragraphs carrying FIR form text are always kept.
    """
    if not text or not _DESCRIBE_WORDS.search(text):
        return text
    paragraphs = re.split(r"\n\s*\n", text)
    kept, describing = [], False
    for para in paragraphs:
        words = len(re.findall(r"\w+", para)) or 1
        hits = len(_DESCRIBE_WORDS.findall(para))
        opener = bool(_DESCRIBE_OPENER.match(para))
        is_form = bool(_FORM_MARKER.search(para))
        # Paragraphs right after a description that still talk about the picture ("Below the central
        # wheel ... ribbon", "1. A central wheel with 24 spokes") continue it
        continued = describing and hits >= 1
        if not is_form and (opener or continued or (hits >= 3 and hits / words > 0.04)):
            describing = True
            continue
        describing = False
        kept.append(para)
    return "\n\n".join(kept)


# Text older pipeline versions (and failed OCR calls) stored instead of what is printed on the page
_PLACEHOLDER = re.compile(
    r"^\s*(GOVERNMENT OF ANDHRA PRADESH - LAW ENFORCEMENT EVIDENCE RECORD\s+EVIDENCE PHOTOGRAPH:|"
    r"\[Physical Page \d+ Official Evidence Record\]|No visible text (was )?found|"
    r"(The )?image (appears to be|is) (a )?(solid|blank|plain))", re.I)


def is_placeholder_text(text: str) -> bool:
    """True when stored page text is a placeholder or 'no text' notice rather than OCR of the page."""
    t = (text or "").strip()
    if not t:
        return True
    if _PLACEHOLDER.match(t):
        return True
    return "Visual evidence document authenticated via cryptographic SHA-256 hash" in t and len(t) < 600


def clean_extracted_text(text: str) -> str:
    """Remove OCR markup, drop legacy-font garbage lines and normalise whitespace. Unicode Telugu/Hindi text is kept."""
    if not text:
        return ""
    text = strip_image_descriptions(strip_markup(text))
    kept = [ln.rstrip() for ln in text.replace("\r", "\n").split("\n") if not _is_garbled_line(ln)]
    cleaned = "\n".join(kept)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def section_label_for(title: Optional[str], category: Optional[str]) -> Optional[str]:
    """Which heading word a document uses, or None for non-legal documents such as FIRs."""
    t = (title or "").lower()
    if "constitution" in t:
        return "Article"
    if re.search(r"\brules?\b", t):
        return "Rule"
    if (category or "").upper() == "LEGAL_ACT" or re.search(r"\b(act|sanhita|adhiniyam|code)\b", t):
        return "Section"
    return None


@dataclass
class PageText:
    page_number: int
    text: str
    ocr_applied: bool = False
    unreadable: bool = False


@dataclass
class Segment:
    """Contiguous text on one page belonging to one section (or to no section)."""
    page_number: int
    text: str
    section_ref: Optional[str] = None
    section_title: Optional[str] = None


@dataclass
class Provision:
    """A full section/article spanning one or more pages, used to build legal_corpus rows."""
    section_ref: str
    section_number: str
    section_title: str
    page_start: int
    parts: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.parts).strip()


def _heading_title(rest: str, context: Optional[str] = None) -> str:
    """Title from 'Title.—body' headings; otherwise the enclosing group/chapter heading, else the opening words."""
    rest = rest.strip()
    for sep in (".—", ".—", "—", ".–", ".-"):
        idx = rest.find(sep)
        if 0 < idx <= 140:
            return rest[:idx].strip(" .")
    if context:
        return context
    return (rest[:100] + ("…" if len(rest) > 100 else "")).strip()


def _accept_heading(num: int, prev: int, rest: str) -> bool:
    # Numbers rise monotonically through an Act. Footnote-style lines are never headings, and a
    # (re)start at 1 must read like a first provision ("Short title", "This Act may be called",
    # "Name and territory"), which skips tables of contents, footnotes and schedule entries.
    if _FOOTNOTE.match(rest.strip()):
        return False
    if num == 1:
        return bool(_FIRST_SECTION.search(rest[:80]))
    return prev >= 1 and prev <= num <= prev + 6


def segment_pages(pages: List[PageText], section_label: Optional[str]):
    """
    Split pages into per-page segments tagged with the current section, and collect provisions.
    Returns (segments, provisions). Without a section_label, each page is one untagged segment.
    """
    segments: List[Segment] = []
    provisions: List[Provision] = []
    if not section_label:
        for p in pages:
            if p.text.strip():
                segments.append(Segment(p.page_number, p.text.strip()))
        return segments, provisions

    prev_num = 0
    label = section_label
    chapter: Optional[str] = None
    group: Optional[str] = None
    current: Optional[Provision] = None
    for p in pages:
        lines = p.text.split("\n")
        heading_lines = [i for i, ln in enumerate(lines) if _HEADING.match(ln)]
        # Contents pages: many headings, or several headings with almost no text under each
        is_toc_page = len(heading_lines) > _TOC_HEADINGS_PER_PAGE or (
            len(heading_lines) >= 6 and len(p.text) / len(heading_lines) < 160
        )
        if is_toc_page:
            # Arrangement-of-sections pages: searchable, but not attributed to any one section
            segments.append(Segment(p.page_number, p.text.strip(), None, "Arrangement of contents"))
            current = None
            prev_num = 0
            continue

        buf: List[str] = []
        pending_chapter_title = False
        for ln in lines:
            stripped = ln.strip()
            cm = _CHAPTER.match(ln)
            if cm:
                chapter, group, pending_chapter_title = f"Chapter {cm.group(1).upper()}", None, True
            elif pending_chapter_title and stripped:
                if stripped.isupper() and len(stripped) < 120:
                    chapter = f"{chapter}: {stripped.capitalize()}"
                pending_chapter_title = False
            gm = _GROUP.match(ln)
            if gm:
                group = gm.group(1).strip()
            m = _HEADING.match(ln)
            if m:
                num = int(m.group(1))
                if _accept_heading(num, prev_num, m.group(3)):
                    if num == 1 and prev_num > 1 and label == "Article" and re.search(r"act may be called", m.group(3), re.I):
                        # An amending Act printed as an appendix to the Constitution has sections, not articles
                        label = "Appendix section"
                    if buf and "".join(buf).strip():
                        segments.append(Segment(
                            p.page_number, "\n".join(buf).strip(),
                            current.section_ref if current else None,
                            current.section_title if current else None,
                        ))
                        if current:
                            current.parts.append("\n".join(buf).strip())
                    buf = []
                    number = f"{m.group(1)}{m.group(2)}"
                    current = Provision(
                        section_ref=f"{label} {number}",
                        section_number=number,
                        section_title=_heading_title(m.group(3), group or chapter),
                        page_start=p.page_number,
                    )
                    provisions.append(current)
                    prev_num = num
            buf.append(ln)
        if buf and "".join(buf).strip():
            segments.append(Segment(
                p.page_number, "\n".join(buf).strip(),
                current.section_ref if current else None,
                current.section_title if current else None,
            ))
            if current:
                current.parts.append("\n".join(buf).strip())
    return segments, provisions


def split_text(text: str, max_chars: int = 1100, overlap: int = 150) -> List[str]:
    """Split on paragraph/sentence/word boundaries into chunks of at most max_chars."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
            if cut < max_chars * 0.5:
                cut = window.rfind(" ")
            if cut > 0:
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_chunks(segments: List[Segment], max_chars: int = 1100, overlap: int = 150) -> List[dict]:
    """Turn segments into chunk dicts; each chunk inherits its segment's page and section."""
    out: List[dict] = []
    for seg in segments:
        for piece in split_text(seg.text, max_chars, overlap):
            out.append({
                "chunk_index": len(out),
                "physical_page_number": seg.page_number,
                "chunk_text": piece,
                "section_ref": seg.section_ref,
                "section_title": seg.section_title,
            })
    return out
