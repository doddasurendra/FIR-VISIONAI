"""
Evidence-based case classification engine.
Classifies cases into FIR folder categories based on extracted text.
Never defaults to a liquor/excise category — must be evidence-driven.
"""
from __future__ import annotations
import re
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class ClassificationResult:
    folder_slug: str
    folder_name: str
    confidence: float
    evidence_snippets: list[str] = field(default_factory=list)
    source: str = "AUTO"


# ─── Keyword rules per folder slug ──────────────────────────────────────────
# Each rule: (slug, folder_name, group_label, keywords[])
# Matching is case-insensitive substring search against combined extracted text.
FOLDER_RULES: list[tuple[str, str, str, list[str]]] = [
    ("illicit-distillation", "Illicit Distillation", "FIR Types",
     ["illicit distill", "arrack", "country liquor", "spirit wash", "hooch", "chakki",
      "distillation", "illicit brew", "fermented wash", "jaggery wash"]),

    ("ndps-transport", "NDPS / Drug Transport", "FIR Types",
     ["ndps", "narcotic", "ganja", "cannabis", "heroin", "opium", "cocaine",
      "drug transport", "psychotropic", "contraband drug", "smack", "marijuana",
      "methamphetamine", "brown sugar", "synthetic drug"]),

    ("non-duty-paid-liquor", "Non-Duty-Paid Liquor", "FIR Types",
     ["non duty paid", "non-duty-paid", "foreign liquor", "smuggled liquor",
      "iml", "indian made foreign", "beer without label", "unlicensed liquor",
      "duty evaded", "bootlegging"]),

    ("vehicle-seizure", "Vehicle Seizure Cases", "FIR Types",
     ["vehicle seiz", "seized vehicle", "transport vehicle", "lorry seized",
      "auto seized", "bike seized", "truck seized", "tempo seized",
      "vehicle confiscat", "automobile seized"]),

    ("unlawful-possession", "Unlawful Possession", "FIR Types",
     ["unlawful possession", "illegal possession", "unauthorised possession",
      "possessed without permit", "found in possession"]),

    ("theft", "Theft / Property Crime", "FIR Types",
     ["theft", "stolen", "burglary", "dacoity", "robbery", "house breaking",
      "pickpocket", "snatching", "motor vehicle theft", "chain snatching",
      "break-in", "shoplifting"]),

    ("assault", "Assault / Bodily Harm", "FIR Types",
     ["assault", "bodily harm", "grievous hurt", "simple hurt", "attack",
      "beaten", "stabbing", "physical altercation", "rioting", "brawl",
      "grievous injury"]),

    ("road-accident", "Road / Traffic Accidents", "FIR Types",
     ["road accident", "vehicle collision", "hit and run",
      "rash driving", "negligent driving", "fatal accident", "motor accident",
      "traffic accident", "mva", "hit-and-run"]),

    ("cheating-fraud", "Cheating / Fraud", "FIR Types",
     ["fraud", "cheating", "forgery", "impersonation", "misappropriation",
      "embezzlement", "deceive", "fake document", "counterfeit",
      "financial fraud", "banking fraud"]),

    ("public-nuisance", "Public Nuisance / Disorder", "FIR Types",
     ["public nuisance", "disorder", "disturbance", "unlawful assembly",
      "breach of peace", "affray", "public intoxication", "nuisance"]),

    ("missing-person", "Missing Person Reports", "FIR Types",
     ["missing person", "missing child", "kidnap", "abduction", "runaway",
      "missing since", "untraceable", "person missing"]),

    ("sexual-offence", "Sexual Offence Cases", "FIR Types",
     ["rape", "sexual assault", "molestation", "pocso", "indecent",
      "sexual harassment", "outraging modesty", "obscenity"]),

    ("domestic-violence", "Domestic Violence", "FIR Types",
     ["domestic violence", "cruelty by husband", "matrimonial", "dowry",
      "498a", "498-a", "marital dispute", "spousal abuse"]),

    ("land-property", "Land / Property Dispute", "FIR Types",
     ["land dispute", "property dispute", "encroachment", "trespass",
      "boundary dispute", "illegal occupation", "patta", "revenue land",
      "land grab"]),

    ("cyber-crime", "Cyber Crime", "FIR Types",
     ["cyber", "online fraud", "phishing", "hacking", "identity theft online",
      "social media", "upi fraud", "otp fraud", "e-mail fraud",
      "internet fraud", "digital fraud"]),

    ("death-investigation", "Death / Unnatural Death", "FIR Types",
     ["unnatural death", "suspected murder", "homicide",
      "suicide", "postmortem", "body found", "deceased", "death case",
      "unexplained death"]),

    ("arms-explosives", "Arms & Explosives", "FIR Types",
     ["arms act", "illegal weapon", "pistol", "firearm", "bomb", "explosive",
      "ammunition", "illegal arms", "knife attack", "weapons seized"]),

    ("under-investigation", "Under Investigation", "Status",
     ["under investigation", "being investigated", "investigation ongoing",
      "case under probe"]),

    ("closed-cases", "Closed / Charge-sheeted", "Status",
     ["chargesheet filed", "case closed", "court submission", "trial commenced",
      "convicted", "acquitted", "discharge", "final report filed"]),
]


def _extract_snippets(text: str, keyword: str, context: int = 60) -> list[str]:
    """Return up to 2 context snippets around a keyword match."""
    snippets: list[str] = []
    lc_text = text.lower()
    start = 0
    for _ in range(2):
        idx = lc_text.find(keyword.lower(), start)
        if idx == -1:
            break
        s = max(0, idx - context)
        e = min(len(text), idx + len(keyword) + context)
        snippets.append("..." + text[s:e].strip() + "...")
        start = idx + 1
    return snippets


def classify_case_text(
    full_text: str,
    offence_nature: Optional[str] = None,
    offence_category: Optional[str] = None,
) -> ClassificationResult:
    """
    Classify a case based on extracted text content.
    Returns the best-matching folder slug with a confidence score.
    Low-confidence results (< 0.25) are routed to 'pending-classification'.

    Parameters
    ----------
    full_text:       Combined extracted document chunk text.
    offence_nature:  Case.offence_nature field (structured metadata).
    offence_category: Case.offence_category field (structured metadata).

    Returns
    -------
    ClassificationResult with folder_slug, folder_name, confidence, evidence_snippets.
    """
    search_text = " ".join(filter(None, [full_text, offence_nature, offence_category]))
    lc_text = search_text.lower()

    scores: dict[str, tuple[float, list[str]]] = {}  # slug → (score, snippets)

    for slug, name, group, keywords in FOLDER_RULES:
        if not keywords:
            continue  # skip dynamic/person-based folders
        hit_count = 0
        snippets: list[str] = []
        for kw in keywords:
            if kw.lower() in lc_text:
                hit_count += 1
                snippets.extend(_extract_snippets(search_text, kw))
        if hit_count > 0:
            # Score based on number of distinct matched keywords
            base_score = min(1.0, hit_count * 0.35)
            # Give specific substantive offence types priority over generic catch-all terms
            if slug in (
                "ndps-transport", "theft", "illicit-distillation", "cyber-crime",
                "sexual-offence", "death-investigation", "road-accident",
                "domestic-violence", "arms-explosives", "cheating-fraud"
            ):
                base_score = min(1.0, base_score * 1.25)
            scores[slug] = (round(base_score, 3), snippets[:4])

    if not scores:
        return ClassificationResult(
            folder_slug="pending-classification",
            folder_name="Pending Classification",
            confidence=0.0,
            evidence_snippets=[],
        )

    best_slug = max(scores, key=lambda s: scores[s][0])
    best_score, best_snippets = scores[best_slug]

    if best_score < 0.25:
        return ClassificationResult(
            folder_slug="pending-classification",
            folder_name="Pending Classification",
            confidence=best_score,
            evidence_snippets=best_snippets,
        )

    folder_name = next(
        (name for slug, name, _, _ in FOLDER_RULES if slug == best_slug),
        best_slug,
    )
    return ClassificationResult(
        folder_slug=best_slug,
        folder_name=folder_name,
        confidence=best_score,
        evidence_snippets=best_snippets,
    )
