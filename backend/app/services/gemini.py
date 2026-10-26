import os
import json
import time
import logging
from typing import Dict, Any, Optional, List
from ..config import settings

logger = logging.getLogger(__name__)

# Tried after the configured model when it is overloaded, timing out, rate-limited or retired
FALLBACK_TEXT_MODELS = ("gemini-3-flash-preview", "gemini-flash-lite-latest")
_UNHEALTHY_MARKERS = ("503", "UNAVAILABLE", "504", "DEADLINE_EXCEEDED", "429", "RESOURCE_EXHAUSTED", "404", "NOT_FOUND")


class GeminiService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.client = None
        self._cooldown_until: Dict[str, float] = {}
        if self.api_key and self.api_key != "YOUR_GEMINI_API_KEY_HERE":
            try:
                from google import genai
                from google.genai import types
                self.client = genai.Client(
                    api_key=self.api_key,
                    # Grounded answers over several passages take longer than 10 s; an overloaded model
                    # gives up after 30 s and the next fallback model is tried
                    http_options=types.HttpOptions(timeout=30000)
                )
            except Exception as e:
                logger.warning(f"Failed to initialize google-genai client: {e}")

    def _get_candidate_models(self) -> List[str]:
        """Configured model first, then fallbacks; models in cooldown are skipped while others remain."""
        if getattr(self, '_quota_exhausted', False):
            return []
        primary = settings.GEMINI_TEXT_MODEL or FALLBACK_TEXT_MODELS[0]
        models = [primary] + [m for m in FALLBACK_TEXT_MODELS if m != primary]
        now = time.time()
        healthy = [m for m in models if self._cooldown_until.get(m, 0) <= now]
        return healthy or models[-1:]

    def _note_failure(self, model: str, error: Exception) -> None:
        """Put an overloaded, timing-out, rate-limited or retired model aside for a while."""
        msg = str(error)
        if any(marker in msg for marker in _UNHEALTHY_MARKERS):
            seconds = 6 * 3600 if ("404" in msg or "NOT_FOUND" in msg) else 600
            self._cooldown_until[model] = time.time() + seconds
            logger.warning(f"Gemini model {model} unavailable ({msg[:80]}); skipping it for {seconds // 60} min.")

    def extract_structured_case(self, raw_text: str, language_hint: str = "en") -> Dict[str, Any]:
        """
        Extract structured FIR fields from raw text, narrative, or OCR output
        using Gemini with strict JSON schema.
        """
        if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
            return self._rule_based_fallback_extraction("")

        if self.client:
            try:
                prompt = f"""
You are an expert Andhra Pradesh Law Enforcement and FIR data extraction assistant.
Extract structured fields from the following FIR text into a valid JSON object.
CRITICAL EXTRACTION RULES:
1. Do NOT assume this is an excise or liquor offence unless explicitly stated in the text.
2. If a field is not present or unmentioned, set its value to null.
3. Do NOT invent facts, FIR numbers, accused names, quantities, dates, vehicle numbers, or legal sections.
4. Extract the offence nature exactly as recorded or described in the document.

Language: {language_hint}
Raw FIR Text:
\"\"\"
{raw_text}
\"\"\"

Return ONLY a JSON object with this exact schema:
{{
    "fir_number": "FIR number or null",
    "year": 2024,
    "district": "District name (or null if not mentioned)",
    "station": "Police or Excise Station name (or null if not mentioned)",
    "mandal": "Mandal name or null",
    "village": "Village name or null",
    "offence_date": "YYYY-MM-DD or null",
    "detection_date": "YYYY-MM-DD or null",
    "registration_date": "YYYY-MM-DD or null",
    "offence_nature": "Nature of offence as explicitly recorded, or null",
    "contraband_type": "Type of contraband or seized property if explicitly stated, or null",
    "seized_quantity": 0.0,
    "seized_unit": "Litres/Kgs/Bottles/Packets/Grams or null",
    "accused_names": ["Name 1", "Name 2"],
    "witness_names": ["Witness 1"],
    "seizing_officer_name": "Officer name or null",
    "seizing_officer_rank": "Rank or null",
    "vehicle_details": "Vehicle registration or description (or null if not present)",
    "law_sections": ["Legal sections explicitly mentioned in document"],
    "narrative_summary": "Factual 2-3 sentence summary of the document narrative or null"
}}
"""
                for model_candidate in self._get_candidate_models():
                    try:
                        response = self.client.models.generate_content(
                            model=model_candidate,
                            contents=prompt
                        )
                        if response and response.text:
                            txt = response.text.strip()
                            if txt.startswith("```json"):
                                txt = txt[7:]
                            if txt.endswith("```"):
                                txt = txt[:-3]
                            return json.loads(txt.strip())
                    except Exception as model_err:
                        logger.warning(f"Structured extraction with {model_candidate} failed: {model_err}")
            except Exception as e:
                logger.warning(f"Gemini API structured extraction unavailable ({e}), using deterministic extractor.")

        # Rule-based fallback parser
        return self._rule_based_fallback_extraction(raw_text)

    def extract_text_from_image(self, image_path: str, mime_type: str = "image/jpeg") -> str:
        """
        Multimodal OCR using Gemini 2.0 Flash to extract printed and handwritten text
        from FIR photographs, WhatsApp images, and scanned evidence receipts.
        """
        if self.client and os.path.exists(image_path):
            try:
                from PIL import Image
                img = Image.open(image_path)
                prompt = (
                    "You are a specialized legal document OCR assistant for the Andhra Pradesh Prohibition & Excise Department. "
                    "Extract and transcribe ALL visible text from this FIR document or evidence photograph verbatim. "
                    "Include printed titles, handwritten officer notes, crime numbers, accused person details, contraband type, "
                    "seized quantity, vehicle registration numbers, witnesses, and police/excise station jurisdiction. "
                    "Preserve Telugu, English, and Hindi text accurately. Return ONLY the transcribed text verbatim."
                )
                for model_candidate in self._get_candidate_models():
                    try:
                        response = self.client.models.generate_content(
                            model=model_candidate,
                            contents=[img, prompt]
                        )
                        if response and response.text and len(response.text.strip()) > 10:
                            return response.text.strip()
                    except Exception as model_err:
                        logger.warning(f"Gemini image OCR with {model_candidate} failed: {model_err}")
            except Exception as e:
                logger.warning(f"Gemini image OCR failed: {e}")

        # No OCR result: return nothing rather than placeholder text that would be indexed as evidence
        return ""

    def translate_for_search(self, query: str) -> Optional[str]:
        """English rendering of a Telugu/Hindi question, used only to search English documents."""
        if not self.client or not self._get_candidate_models():
            return None
        prompt = ("Translate this police/excise investigation question into English for a document search. "
                  "Keep names, numbers and legal terms. Return only the translation.\n\n" + query)
        for model_candidate in self._get_candidate_models():
            try:
                response = self.client.models.generate_content(model=model_candidate, contents=prompt)
                text_ = (response.text or "").strip() if response else ""
                return text_[:500] or None
            except Exception as e:
                logger.warning(f"Query translation with {model_candidate} failed: {e}")
                self._note_failure(model_candidate, e)
        return None

    def answer_from_sources(
        self,
        query: str,
        sources: List[Dict[str, Any]],
        language: str = "en",
        legal_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Answer strictly from numbered source passages. Returns
        {"status": "ANSWERED" | "NOT_FOUND" | "UNAVAILABLE", "text": str, "used": [source numbers]}.
        An answer without [S#] citations is treated as NOT_FOUND because it cannot be traced.
        """
        if not self.client or not self._get_candidate_models():
            return {"status": "UNAVAILABLE", "text": "", "used": []}
        lang_name = {"te": "Telugu", "hi": "Hindi"}.get(language, "English")
        blocks = []
        for i, s in enumerate(sources, start=1):
            where = []
            if s.get("section_ref"):
                where.append(s["section_ref"])
            if s.get("physical_page_number") and not s.get("is_image"):
                where.append(f"page {s['physical_page_number']}")
            kind = s.get("doc_category") or "DOCUMENT"
            # Provenance labels apply to reference material; FIRs and evidence are case records
            origin = ((s.get("source_type") or "UNVERIFIED")
                      if kind in ("LEGAL_ACT", "CIRCULAR", "INVESTIGATION_GUIDE", "REFERENCE") else "CASE RECORD")
            blocks.append(
                f"[S{i}] {s.get('document_title') or 'Document'} | {kind} | source: {origin}"
                + (f" | {', '.join(where)}" if where else "") + f"\n{s.get('chunk_text', '')}"
            )
        legal_instructions = (
            "\nThis question involves law. Structure the answer under these headings, written exactly as shown:\n"
            "\"What the FIR/record states\" - use only FIR/evidence sources.\n"
            "\"What the official legal source states\" - use only LEGAL_ACT sources and quote the provision.\n"
            "\"Suggestions for officer review\" - decision support, not a legal determination.\n"
            "Do not copy these instructions into the answer. Omit a heading if no source supports it. Never assert\n"
            "guilt; describe allegations as allegations.\n"
            if legal_mode else ""
        )
        prompt = f"""You are the FIR VisionAI research assistant for the Andhra Pradesh Prohibition & Excise Department.
Answer the officer's question using ONLY the numbered source passages below.

Rules:
- Every factual sentence must end with the citation(s) it relies on, like [S1] or [S2][S4].
- Use only passages that directly answer the question; ignore passages that merely share words with it.
- Do not use outside knowledge. Do not invent facts, names, dates, quantities, page numbers or legal sections.
- Copy names, places, numbers and dates exactly as the source writes them, even if they look misspelt
  (sources may be OCR text); do not correct or complete them.
- Reference sources marked SYNTHETIC or UNVERIFIED are not official texts; say so if you rely on them.
  Sources marked CASE RECORD are the officer's own case documents.
- FIR forms record the incident under labels such as "Occurrence of offence", "Place of occurrence",
  "Acts & Sections", "Complainant / Informant" and "Accused"; read those entries as the incident details.
- If the passages answer only part of the question, answer that part and say plainly which details the
  sources do not contain.
- If the passages do not contain enough information to answer, reply with exactly: NOT_FOUND
- Write the answer in {lang_name}.{legal_instructions}

Question: {query}

Sources:
{chr(10).join(blocks)}
"""
        for model_candidate in self._get_candidate_models():
            try:
                response = self.client.models.generate_content(model=model_candidate, contents=prompt)
                answer = (response.text or "").strip() if response else ""
                if not answer or answer.upper().startswith("NOT_FOUND"):
                    return {"status": "NOT_FOUND", "text": "", "used": []}
                import re as _re
                used = sorted({int(n) for n in _re.findall(r"\[S(\d+)\]", answer) if 0 < int(n) <= len(sources)})
                if not used:
                    return {"status": "NOT_FOUND", "text": "", "used": []}
                return {"status": "ANSWERED", "text": answer, "used": used}
            except Exception as model_err:
                logger.warning(f"Grounded answer generation with {model_candidate} failed: {model_err}")
                # Try the next model instead of disabling generation for the whole process
                self._note_failure(model_candidate, model_err)
        return {"status": "UNAVAILABLE", "text": "", "used": []}

    def answer_app_question(self, question: str, guide: List[Dict[str, Any]], language: str = "en",
                            history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """
        Short answer about using the application, only from the verified guide passages given.
        Returns {"status": "ANSWERED" | "NOT_FOUND" | "UNAVAILABLE", "text": str, "used": [guide numbers]}.
        """
        if not self.client or not self._get_candidate_models():
            return {"status": "UNAVAILABLE", "text": "", "used": []}
        lang_name = {"te": "Telugu", "hi": "Hindi"}.get(language, "English")
        blocks = "\n".join(f"[G{i}] {g['title']}\n{g['text']}" for i, g in enumerate(guide, start=1))
        convo = "\n".join(f"{t.get('role', 'user')}: {t.get('text', '')[:300]}" for t in (history or [])[-6:])
        prompt = f"""You are the FIR VisionAI voice assistant for officers of the Andhra Pradesh Prohibition & Excise Department.
Answer the officer's question about using the application using ONLY the guide passages below.

Rules:
- Use only facts in the passages; never invent buttons, pages, menus, metrics or steps.
- If a passage says a feature is not available or is a placeholder, say so and give the alternative it names.
- Answer in {lang_name}, in 2 to 4 short spoken sentences; when a passage gives numbered steps and the
  question asks how to do something, give those steps as a numbered list (one short line each).
- Keep button, menu and page names exactly as written in the passages (in English); do not mention URLs or paths.
- End each sentence with the passage it relies on, like [G1].
- If the passages do not answer the question, reply with exactly: NOT_FOUND

Earlier conversation (for follow-up questions only):
{convo or '(none)'}

Question: {question}

Guide passages:
{blocks}
"""
        for model_candidate in self._get_candidate_models():
            try:
                response = self.client.models.generate_content(model=model_candidate, contents=prompt)
                text_ = (response.text or "").strip() if response else ""
                if not text_ or text_.upper().startswith("NOT_FOUND"):
                    return {"status": "NOT_FOUND", "text": "", "used": []}
                import re as _re
                cited = " ".join(_re.findall(r"\[(G\d+(?:\s*,\s*G?\d+)*)\]", text_))
                used = sorted({int(n) for n in _re.findall(r"\d+", cited) if 0 < int(n) <= len(guide)})
                return {"status": "ANSWERED", "text": text_, "used": used or [1]}
            except Exception as e:
                logger.warning(f"App-guide answer with {model_candidate} failed: {e}")
                self._note_failure(model_candidate, e)
        return {"status": "UNAVAILABLE", "text": "", "used": []}

    def summarize_fir_record(self, sources: List[Dict[str, Any]], field_keys: List[str]) -> Dict[str, Any]:
        """
        Structured summary of one FIR record in English, Telugu and Hindi from the same numbered
        sources, in a single call so all three languages rest on identical evidence.
        Returns {"status": "OK" | "UNAVAILABLE" | "QUOTA_EXHAUSTED" | "FAILED", "data": {...},
        "model": str, "error": str}.
        """
        if not self.client:
            return {"status": "UNAVAILABLE", "error": "No Gemini API key is configured."}
        models = self._get_candidate_models()
        if not models:
            return {"status": "QUOTA_EXHAUSTED", "error": "The Gemini quota is exhausted."}
        blocks = []
        for i, s in enumerate(sources, start=1):
            where = f" | page {s['page']}" if s.get("page") else ""
            note = " | OCR text, low confidence" if s.get("ocr_uncertain") else (" | OCR text" if s.get("ocr") else "")
            blocks.append(f"[S{i}] {s['label']}{where}{note}\n{s['text']}")
        keys = ", ".join(field_keys)
        prompt = f"""You summarise historical FIR records for the Andhra Pradesh Prohibition & Excise Department.
Use ONLY the numbered sources below. They are the FIR record's own text (often OCR) and the
officer-approved registered case fields.

Produce one JSON object:
{{
  "ocr_uncertain": true/false,   // true if any detail you used is hard to read or ambiguous in the OCR
  "languages": {{
    "en": {{"overview": {{"text": "...", "citations": [1]}}, "fields": {{"<key>": {{"text": "...", "citations": [1, 2]}}}}}},
    "te": {{ same structure, written in Telugu }},
    "hi": {{ same structure, written in Hindi }}
  }}
}}
The "fields" object must contain exactly these keys: {keys}.

Rules:
- Every statement must come from the sources; list the source numbers it relies on in "citations".
- If the sources do not contain a field, set its text to exactly NOT_IN_SOURCE with empty citations.
  Never guess, infer or complete missing details.
- Write allegations as allegations ("alleged", "according to the complaint"); do not state guilt or
  treat a complaint's claims as established facts.
- Copy names, FIR numbers, dates, amounts, quantities, vehicle numbers and legal section numbers
  exactly as the source writes them, in every language (keep them in their original script and
  digits). Do not correct OCR spellings.
- If sources disagree, describe both versions under "ambiguities" with their citations.
- "missing_information" lists important details the record does not contain or that are unreadable.
- "investigation_progress" only from what the sources record (status, actions taken); otherwise NOT_IN_SOURCE.
- "overview": 2-4 sentences.
- Telugu and Hindi must say exactly what the English says, with the same citations; translate legal
  terms faithfully and keep section numbers unchanged.
- Return only the JSON object.

Sources:
{chr(10).join(blocks)}
"""
        last_error = ""
        for model_candidate in models:
            try:
                from google.genai import types
                response = self.client.models.generate_content(
                    model=model_candidate, contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        # Three languages of structured output take longer than a chat answer
                        http_options=types.HttpOptions(timeout=180000),
                    ),
                )
                raw = (response.text or "").strip() if response else ""
                if raw.startswith("```"):
                    raw = raw.strip("`").split("\n", 1)[-1]
                data = json.loads(raw)
                if not isinstance(data, dict) or not isinstance(data.get("languages"), dict):
                    raise ValueError("summary JSON has no 'languages' object")
                return {"status": "OK", "data": data, "model": model_candidate}
            except Exception as e:
                last_error = f"{type(e).__name__}: {str(e)[:200]}"
                logger.warning(f"FIR summary with {model_candidate} failed: {last_error}")
                self._note_failure(model_candidate, e)
        quota = any(m in last_error for m in ("429", "RESOURCE_EXHAUSTED"))
        return {"status": "QUOTA_EXHAUSTED" if quota else "FAILED", "error": last_error}

    def generate_grounded_answer(
        self,
        query: str,
        context_snippets: List[Dict[str, Any]],
        mode: str = "PDF_ONLY",
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Generate answer grounded STRICTLY in retrieved context snippets.
        Mode A: PDF_ONLY -> Must ONLY use the selected PDF and include physical page citations.
        Mode A (Image): IMAGE_ONLY -> Must ONLY use the selected image OCR and cite the image source.
        Mode B: CROSS_CASE -> May use authorized cross-case snippets with case citations.
        """
        is_image_mode = (mode == "IMAGE_ONLY")

        if not context_snippets:
            if is_image_mode:
                if language == "te":
                    msg = "మీరు అప్లోడ్ చేసిన FIR చిత్రంలో కోరిన సమాచారం కనుగొనబడలేదు."
                elif language == "hi":
                    msg = "अपलोड की गई FIR छवि में मांगी गई जानकारी नहीं मिली।"
                else:
                    msg = "The requested information was not found in the uploaded FIR image."
            elif mode == "PDF_ONLY":
                if language == "te":
                    msg = "మీరు అప్లోడ్ చేసిన FIR PDFలో కోరిన సమాచారం కనుగొనబడలేదు."
                elif language == "hi":
                    msg = "अपलोड की गई FIR PDF में मांगी गई जानकारी नहीं मिली।"
                else:
                    msg = "The requested information was not found in the uploaded FIR PDF."
            elif mode == "KNOWLEDGE_BASE_ONLY":
                if language == "te":
                    msg = "ఎంచుకున్న అధీకృత నాలెడ్జ్ బేస్ పత్రాల్లో కోరిన సమాచారం కనుగొనబడలేదు."
                elif language == "hi":
                    msg = "चयनित अधिकृत नॉलेज बेस दस्तावेज़ों में मांगी गई जानकारी नहीं मिली।"
                else:
                    msg = "The requested information was not found in the selected authorized Knowledge Base documents."
            else:
                msg = "సంబంధిత రికార్డులు కనుగొనబడలేదు." if language == "te" else "कोई प्रासंगिक रिकॉर्ड नहीं मिला।" if language == "hi" else "No relevant authorized records were found."
            return {"answer": msg, "citations": []}

        # Check for missing fact patterns before calling LLM
        q_lower = query.lower()
        if any(term in q_lower for term in ["criminal history", "previous convictions", "prior cases", "past offences", "గత నేర చరిత్ర", "पिछला आपराधिक इतिहास"]):
            has_history = any(

                any(kw in s.get("text", "").lower() for kw in ["convicted", "prior case", "previous fir", "past offence", "earlier case", "antecedents"])

                for s in context_snippets

            )

            if not has_history and (mode == "PDF_ONLY" or is_image_mode):
                if is_image_mode:
                    msg = (
                        "మీరు అప్లోడ్ చేసిన FIR చిత్రంలో కోరిన సమాచారం కనుగొనబడలేదు." if language == "te"
                        else "अपलोड की गई FIR छवि में मांगी गई जानकारी नहीं मिली।" if language == "hi"
                        else "The requested information was not found in the uploaded FIR image."
                    )
                else:
                    msg = (
                        "మీరు అప్లోడ్ చేసిన FIR PDFలో కోరిన సమాచారం కనుగొనబడలేదు." if language == "te"
                        else "अपलोड की गई FIR PDF में मांगी गई जानकारी नहीं मिली।" if language == "hi"
                        else "The requested information was not found in the uploaded FIR PDF."
                    )
                return {"answer": msg, "citations": []}

        # Format context
        formatted_context = ""
        for idx, s in enumerate(context_snippets):
            p_num = s.get("physical_page_number", 1)
            doc_id = s.get("document_id", "")
            case_num = s.get("fir_number", "")
            doc_name = s.get("document_name") or s.get("source_label") or f"Doc {doc_id[:8]}"
            cat = s.get("category", "")
            s_text = s.get("text", "")
            if is_image_mode:
                formatted_context += f"\n--- Source Image Segment [{idx+1}] (Evidence Image: {doc_name}) ---\n{s_text}\n"
            elif mode == "KNOWLEDGE_BASE_ONLY":
                page_info = f"Page {p_num}" if p_num else "Image/Record"
                formatted_context += f"\n--- Knowledge Base Document [{idx+1}] ({doc_name} | Category: {cat} | {page_info}) ---\n{s_text}\n"
            else:
                formatted_context += f"\n--- Source Segment [{idx+1}] (PDF Physical Page: {p_num}, Case: {case_num}) ---\n{s_text}\n"

        if is_image_mode:
            prompt = f"""
You are the AI FIR Assistance Assistant for the Andhra Pradesh Excise Department.
STRICT RULE: Answer the officer's question using ONLY the provided Image Evidence Segments.
Do NOT use outside knowledge, do NOT invent facts, and do NOT assume details.

MODE: IMAGE_ONLY
LANGUAGE: {language}

Officer's Query:
\"{query}\"

Provided Image Evidence:
{formatted_context}

INSTRUCTIONS:
1. If the query cannot be answered directly from the evidence above, answer EXACTLY:
   - For English: "The requested information was not found in the uploaded FIR image."
   - For Telugu: "మీరు అప్లోడ్ చేసిన FIR చిత్రంలో కోరిన సమాచారం కనుగొనబడలేదు."
   - For Hindi: "अपलोड की गई FIR छवि में मांगी गई जानकारी नहीं मिली।"
2. If evidence IS present, provide a factual answer.
3. At the end of the answer, cite the source as:
   - For English: **Source:** Uploaded FIR Image.
   - For Telugu: **మూలం:** అప్లోడ్ చేసిన FIR చిత్రం.
   - For Hindi: **स्रोत:** अपलोड की गई FIR छवि।
"""
        elif mode == "KNOWLEDGE_BASE_ONLY":
            prompt = f"""
You are the AI FIR Assistance Assistant for the Andhra Pradesh Excise Department.
STRICT RULE: Answer the officer's question using ONLY the provided Knowledge Base Document Segments.
Do NOT use outside knowledge, do NOT invent facts, and do NOT assume details.

MODE: KNOWLEDGE_BASE_ONLY
LANGUAGE: {language}

Officer's Query:
\"{query}\"

Provided Knowledge Base Evidence:
{formatted_context}

INSTRUCTIONS:
1. If the query cannot be answered directly from the knowledge base documents above, answer EXACTLY:
   - For English: "The requested information was not found in the selected authorized Knowledge Base documents."
   - For Telugu: "ఎంచుకున్న అధీకృత నాలెడ్జ్ బేస్ పత్రాల్లో కోరిన సమాచారం కనుగొనబడలేదు."
   - For Hindi: "चयनित अधिकृत नॉलेज बेस दस्तावेज़ों में मांगी गई जानकारी नहीं मिली।"
2. If evidence IS present, provide a clear, factual, and accurate answer based on the departmental documents.
3. Explicitly cite the title of the document, legal act section, or circular number used.
"""
        else:
            prompt = f"""
You are the AI FIR Assistance Assistant for the Andhra Pradesh Excise Department.
STRICT RULE: Answer the officer's question using ONLY the provided Source Segments.
Do NOT use outside knowledge, do NOT invent facts, and do NOT assume details.

MODE: {mode}
LANGUAGE: {language}

Officer's Query:
\"{query}\"

Provided Evidence:
{formatted_context}

INSTRUCTIONS:
1. If the query cannot be answered directly from the evidence above, answer EXACTLY:
   - For English: "The requested information was not found in the uploaded FIR PDF."
   - For Telugu: "మీరు అప్లోడ్ చేసిన FIR PDFలో కోరిన సమాచారం కనుగొనబడలేదు."
   - For Hindi: "अपलोड की गई FIR PDF में मांगी गई जानकारी नहीं मिली।"
2. If evidence IS present, provide a factual answer.
3. At the end of every claim, provide exact physical PDF page citations.
   Format:
   - For English: **Source:** Uploaded FIR PDF, PDF page X. (or PDF pages X, Y)
   - For Telugu: **మూలం:** అప్లోడ్ చేసిన FIR PDF, PDF పేజీ X.
   - For Hindi: **स्रोत:** अपलोड की गई FIR PDF, PDF पृष्ठ X।
"""

        if self.client:
            for model_candidate in self._get_candidate_models():
                try:
                    response = self.client.models.generate_content(
                        model=model_candidate,
                        contents=prompt
                    )
                    if response and response.text:
                        ans_text = response.text.strip()
                        # If the answer indicates not found, no positive citation
                        is_not_found = any(nf in ans_text.lower() for nf in [
                            "not found in the uploaded",
                            "not found in the selected",
                            "కనుగొనబడలేదు",
                            "जानकारी नहीं मिली"
                        ])
                        if is_not_found:
                            return {
                                "answer": ans_text,
                                "citations": []
                            }

                        if is_image_mode:
                            doc_id = context_snippets[0].get("document_id", "") if context_snippets else ""
                            first_snippet = context_snippets[0] if context_snippets else {}
                            excerpt = first_snippet.get("text", "")[:250].strip()
                            return {
                                "answer": ans_text,
                                "citations": [
                                    {
                                        "document_id": doc_id,
                                        "source_label": "Uploaded FIR Image (Page 1)",
                                        "physical_page_number": 1,
                                        "evidence_excerpt": excerpt,
                                        "verification_status": "VERIFIED_EXTRACTED_TEXT"
                                    }
                                ]
                            }
                        else:
                            page_snippets = {}
                            for s in context_snippets:
                                p = int(s.get("physical_page_number", 1)) if s.get("physical_page_number") else 1
                                if p not in page_snippets:
                                    page_snippets[p] = s
                            if not page_snippets:
                                page_snippets[1] = {}

                            default_doc_id = context_snippets[0].get("document_id", "") if context_snippets else ""
                            return {
                                "answer": ans_text,
                                "citations": [
                                    {
                                        "physical_page_number": p,
                                        "document_id": s.get("document_id", default_doc_id),
                                        "source_label": f"PDF Page {p}",
                                        "evidence_excerpt": (s.get("text") or "")[:250].strip(),
                                        "verification_status": "VERIFIED_EXTRACTED_TEXT"
                                    }
                                    for p, s in page_snippets.items()
                                ]
                            }
                except Exception as model_err:
                    logger.warning(f"Gemini grounded answer with {model_candidate} failed: {model_err}")
                    err_msg = str(model_err).lower()
                    if any(net_err in err_msg for net_err in ["getaddrinfo", "disconnected", "connection", "connecttimeout", "timed out", "unreachable", "429", "resource_exhausted", "quota", "rate limit"]):
                        self._quota_exhausted = True
                        break

        # Grounded local synthesis fallback when API call fails
        return self._local_grounded_fallback(query, context_snippets, mode, language)

    def _rule_based_fallback_extraction(self, text: str) -> Dict[str, Any]:
        """Extract fields using comprehensive regex and heuristic rules from actual text evidence."""
        import re
        from datetime import datetime as _dt

        text = text or ""
        if not isinstance(text, str):
            text = str(text)

        # FIR / Crime number
        fir_match = re.search(
            r'(?:FIR(?:\s*No\.?)?|Cr\.?\s*No\.?|Crime\s*No\.?|Case\s*No\.?)[.:\s/]+([A-Z0-9/_-]+)',
            text, re.IGNORECASE)

        # Quantity and unit
        qty_match = re.search(
            r'(\d+(?:\.\d+)?)\s*(litres?|liters?|ltrs?|kgs?|kilograms?|bottles?|packets?|grams?|sovereigns?|tola)',
            text, re.IGNORECASE)

        # Accused / suspects
        accused_match = re.search(
            r'(?:Accused(?:\s*Person)?|A1|A-1|Suspect|Perpetrator)[.:\s]+([A-Za-z\s]+?)(?:,|\n|age|s/o|d/o|w/o|residing|resident|$)',
            text, re.IGNORECASE)

        # Vehicle
        vehicle_match = re.search(
            r'(?:Vehicle|Auto|Car|Motorcycle|Bike|Tractor|Lorry|Truck|Conveyance)[.:\s]+([A-Z0-9\s-]+)',
            text, re.IGNORECASE)

        # Sections
        sec_match = re.search(
            r'(?:Sec(?:tion)?\.?\s*([0-9A-Za-z\(\)\s,/]+(?:Act|IPC|BNS|BNSS|Excise|NDPS|MVA)?))',
            text, re.IGNORECASE)

        # Offence description (avoid matching Date of Occurrence or Place of Occurrence)
        offence_match = re.search(
            r'(?<!Date of\s)(?<!Place of\s)(?:Nature\s+of\s+Offence|Offence|Allegation|Crime\s+Nature)\s*[:\-]\s*([^\n\r]+)',
            text, re.IGNORECASE)
        if not offence_match:
            offence_match = re.search(
                r'(?<!Date of\s)(?<!Place of\s)\b(?:Offence|Allegation)\b[.:\s]+([^\n\r]+)',
                text, re.IGNORECASE)

        # Contraband / seized material / property
        contraband_match = re.search(
            r'(?:Contraband|Seized material|Stolen property|Property seized|Item seized)[.:\s]+([^\n\.]+)',
            text, re.IGNORECASE)

        # ── District detection: colon/hyphen/slash pattern, Telugu, then word-match ──
        detected_district = None
        dist_label = re.search(
            r'(?:District|Dist\.?|Revenue\s+District|జిల్లా|जिला)\s*[:\-\/\.]?\s*([A-Za-z\u0C00-\u0C7F\u0900-\u097F\s\.]+?)(?:\s*[,\n\r;]|$)',
            text, re.IGNORECASE
        )
        if dist_label:
            candidate_d = dist_label.group(1).strip()
            # Clean common filler words
            candidate_d = re.sub(r'^(?:is|at|in|name|of|the)\s+', '', candidate_d, flags=re.IGNORECASE).strip()
            if len(candidate_d) >= 3 and not any(fp in candidate_d.lower() for fp in ["page", "evidence", "document", "hash"]):
                detected_district = candidate_d.title()

        if not detected_district:
            known_districts = [
                # Andhra Pradesh
                "Anakapalli", "Ananthapuramu", "Anantapur", "Annamayya", "Bapatla", "Chittoor",
                "Konaseema", "East Godavari", "Eluru", "Guntur", "Kakinada",
                "Krishna", "Kurnool", "Nandyal", "NTR", "Palnadu", "Prakasam",
                "Srikakulam", "Tirupati", "Visakhapatnam", "Vizag", "Vizianagaram",
                "West Godavari", "YSR Kadapa", "Kadapa", "Amaravati",
                # Telangana
                "Hyderabad", "Rangareddy", "Medchal", "Warangal", "Karimnagar",
                "Nalgonda", "Nizamabad", "Khammam", "Mahbubnagar", "Adilabad",
                # Tamil Nadu
                "Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem",
                "Tirunelveli", "Vellore", "Erode", "Tiruppur", "Kancheepuram",
                "Thanjavur", "Dindigul", "Cuddalore", "Villupuram", "Nagapattinam",
                # Karnataka
                "Bengaluru", "Bangalore", "Mysuru", "Hubli", "Mangaluru", "Belagavi", "Kalaburagi",
                # Maharashtra
                "Mumbai", "Pune", "Nagpur", "Nashik", "Aurangabad", "Solapur",
                # Others
                "Delhi", "Kolkata", "Ahmedabad", "Surat", "Jaipur", "Lucknow",
                "Kanpur", "Patna", "Bhopal", "Indore", "Thiruvananthapuram", "Kochi",
            ]
            for dist in known_districts:
                if re.search(rf'\b{re.escape(dist)}\b', text, re.IGNORECASE):
                    detected_district = dist
                    break

        # ── Station: colon/dash/slash label first, then inline regex ──
        detected_station = None
        filler_phrases = ["physical page", "scanned document", "transcribed", "official evidence", "cryptographic", "hash"]
        stn_label = re.search(
            r'(?:Police\s*Station|Excise\s*Station|SEB\s*Station|P\.?S\.?|Thana|Station|పోలీస్\s*స్టేషన్|ఎక్సైజ్\s*స్టేషన్|थाना)\s*[:\-\/,]?\s*([^\n\r,;]+)',
            text, re.IGNORECASE
        )
        if stn_label:
            raw_station = stn_label.group(1).strip()
            # Clean common filler prefixes
            raw_station = re.sub(r'^(?:is|at|in|name|of|the)\s+', '', raw_station, flags=re.IGNORECASE).strip()
            if len(raw_station) >= 3 and not any(fp in raw_station.lower() for fp in filler_phrases):
                detected_station = raw_station

        if not detected_station:
            # Inline station pattern with P.S., Thana, or Station suffix
            station_match = re.search(
                r'\b([A-Za-z][A-Za-z\s]{1,30}?\s*(?:Town|Rural|Traffic|Excise|Urban|South|North|East|West|Central|District)?\s*(?:Police\s*Station|Excise\s*Station|SEB\s*Station|P\.?S\.?|Thana))\b',
                text, re.IGNORECASE
            )
            if station_match:
                raw_station = station_match.group(1).strip()
                if not any(fp in raw_station.lower() for fp in filler_phrases):
                    detected_station = raw_station

        # ── Complainant / Informant ──
        complainant_match = re.search(
            r'(?:Complainant|Informant|Complainee|Reporting Officer)[.:\s]+([A-Za-z][A-Za-z\s\.]{2,50}?)(?:,|\n|age|s/o|d/o|designation|rank|$)',
            text, re.IGNORECASE)
        complainant_name = complainant_match.group(1).strip() if complainant_match else None

        # ── Seizing / Investigating Officer ──
        io_match = re.search(
            r'(?:Seizing Officer|Investigating Officer|SI|PSI|ASI|Inspector|Sub-Inspector|DSP)[.:\s]+([A-Za-z][A-Za-z\s\.]{2,50}?)(?:,|\n|rank|designation|badge|$)',
            text, re.IGNORECASE)
        io_name = io_match.group(1).strip() if io_match else None
        io_rank_match = re.search(r'\b(Inspector|Sub-Inspector|SI|PSI|ASI|DSP|SP|DySP|Constable)\b', text, re.IGNORECASE)
        io_rank = io_rank_match.group(1) if io_rank_match else None

        # ── Date of occurrence ──
        date_match = re.search(
            r'(?:Date\s+of\s+(?:Occurrence|Offence|Incident)|On\s+(?:or\s+about)?|Dated?)[.:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})',
            text, re.IGNORECASE)
        offence_date_raw = date_match.group(1).strip() if date_match else None
        offence_date = None
        if offence_date_raw:
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
                try:
                    offence_date = _dt.strptime(offence_date_raw, fmt).strftime("%Y-%m-%d")
                    break
                except Exception:
                    pass
            if not offence_date:
                offence_date = offence_date_raw

        # ── Registration date ──
        reg_date_match = re.search(
            r'(?:Registration\s+Date|Registered\s+on|Booked\s+on|FIR\s+Date)[.:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})',
            text, re.IGNORECASE)
        reg_date_raw = reg_date_match.group(1).strip() if reg_date_match else None
        reg_date = None
        if reg_date_raw:
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
                try:
                    reg_date = _dt.strptime(reg_date_raw, fmt).strftime("%Y-%m-%d")
                    break
                except Exception:
                    pass
            if not reg_date:
                reg_date = reg_date_raw

        # ── Financial loss / amount ──
        fin_match = re.search(r'(?:Rs\.?|INR|\u20b9|Amount|Loss|Value)[.:\s]*(\d[\d,\.]+)', text, re.IGNORECASE)
        financial_loss_amount = fin_match.group(1).replace(",", "").strip() if fin_match else None

        # ── Witness names ──
        witness_matches = re.findall(
            r'(?:Witness|Panch\s*Witness|Panch)[.:\s]+([A-Za-z][A-Za-z\s\.]{2,40}?)(?:,|\n|s/o|d/o|age|$)',
            text, re.IGNORECASE)
        witness_names = [w.strip() for w in witness_matches if len(w.strip()) > 2][:4]

        # ── Phone number ──
        phone_match = re.search(r'\b(\+91[-\s]?)?([6-9]\d{9})\b', text)
        phone_number = phone_match.group(0).strip() if phone_match else None

        # ── Place of occurrence ──
        place_match = re.search(
            r'(?:Place\s+of\s+(?:Occurrence|Incident)|At\s+about|Near|Location)[.:\s]+([^\n\r]{3,120})',
            text, re.IGNORECASE)
        place_of_occurrence = place_match.group(1).strip() if place_match else None

        # ── Village / Mandal ──
        village_match = re.search(r'(?:Village|Gram|Panchayat)[.:\s]+([A-Za-z\s]{3,40}?)(?:,|\n|Mandal|$)', text, re.IGNORECASE)
        mandal_match = re.search(r'(?:Mandal|Tehsil|Taluka|Block)[.:\s]+([A-Za-z\s]{3,40}?)(?:,|\n|District|$)', text, re.IGNORECASE)

        # ── Offence nature ──
        detected_offence = None
        if offence_match:
            detected_offence = offence_match.group(1).strip()
        else:
            try:
                from .classification import classify_case_text
                clf = classify_case_text(full_text=text)
                if clf.confidence >= 0.25 and clf.folder_slug != "pending-classification":
                    detected_offence = clf.folder_name
            except Exception:
                pass

        # ── Narrative summary: built from extracted facts ──
        narrative_parts = []
        if detected_offence:
            narrative_parts.append(f"Offence: {detected_offence}.")
        if place_of_occurrence:
            narrative_parts.append(f"Location: {place_of_occurrence}.")
        if offence_date:
            narrative_parts.append(f"Date of occurrence: {offence_date}.")
        if complainant_name:
            narrative_parts.append(f"Complainant/Informant: {complainant_name}.")
        if accused_match and accused_match.group(1).strip():
            narrative_parts.append(f"Accused: {accused_match.group(1).strip()}.")
        if qty_match and contraband_match:
            narrative_parts.append(
                f"Seized: {qty_match.group(1)} {qty_match.group(2)} of {contraband_match.group(1).strip()}."
            )
        if financial_loss_amount:
            narrative_parts.append(f"Financial loss: Rs. {financial_loss_amount}.")
        if not narrative_parts:
            lines = [l.strip() for l in text.split('\n')
                     if l.strip() and not l.strip().startswith('[Physical Page')]
            narrative_parts = lines[:4]
        narrative_summary = " ".join(narrative_parts) if narrative_parts else None

        return {
            "fir_number": fir_match.group(1).strip() if fir_match else None,
            "fir_no": fir_match.group(1).strip() if fir_match else None,
            "crime_number": fir_match.group(1).strip() if fir_match else None,
            "year": 2024,
            "district": detected_district,
            "district_name": detected_district,
            "station": detected_station,
            "police_station": detected_station,
            "excise_station": detected_station,
            "mandal": mandal_match.group(1).strip() if mandal_match else None,
            "village": village_match.group(1).strip() if village_match else None,
            "offence_date": offence_date,
            "detection_date": None,
            "registration_date": reg_date,
            "offence_nature": detected_offence,
            "crime_type": detected_offence,
            "contraband_type": contraband_match.group(1).strip() if contraband_match else None,
            "seized_quantity": float(qty_match.group(1)) if qty_match else None,
            "seized_unit": qty_match.group(2).capitalize() if qty_match else None,
            "accused_names": [accused_match.group(1).strip()]
                             if accused_match and len(accused_match.group(1).strip()) > 2 else [],
            "witness_names": witness_names,
            "seizing_officer_name": io_name,
            "seizing_officer_rank": io_rank,
            "vehicle_details": vehicle_match.group(0).strip() if vehicle_match else None,
            "law_sections": [sec_match.group(0).strip()] if sec_match else [],
            "narrative_summary": narrative_summary,
            # Extra fields for richer extraction
            "complainant_name": complainant_name,
            "place_of_occurrence": place_of_occurrence,
            "incident_description": detected_offence,
            "financial_loss_amount": financial_loss_amount,
            "phone_number": phone_number,
        }

    def _local_grounded_fallback(self, query: str, snippets: List[Dict[str, Any]], mode: str, language: str) -> Dict[str, Any]:
        """Deterministic grounded fallback adhering strictly to document context."""
        import re

        is_image = (mode == "IMAGE_ONLY")

        # Missing information standardized messages
        if is_image:
            if language == "te":
                missing_msg = "మీరు అప్లోడ్ చేసిన FIR చిత్రంలో కోరిన సమాచారం కనుగొనబడలేదు."
            elif language == "hi":
                missing_msg = "अपलोड की गई FIR छवि में मांगी गई जानकारी नहीं मिली।"
            else:
                missing_msg = "The requested information was not found in the uploaded FIR image."
        elif mode == "PDF_ONLY":
            if language == "te":
                missing_msg = "మీరు అప్లోడ్ చేసిన FIR PDFలో కోరిన సమాచారం కనుగొనబడలేదు."
            elif language == "hi":
                missing_msg = "अपलोड की गई FIR PDF में मांगी गई जानकारी नहीं मिली।"
            else:
                missing_msg = "The requested information was not found in the uploaded FIR PDF."
        elif mode == "KNOWLEDGE_BASE_ONLY":
            if language == "te":
                missing_msg = "ఎంచుకున్న అధీకృత నాలెడ్జ్ బేస్ పత్రాల్లో కోరిన సమాచారం కనుగొనబడలేదు."
            elif language == "hi":
                missing_msg = "चयनित अधिकृत नॉलेज बेस दस्तावेज़ों में मांगी गई जानकारी नहीं मिली।"
            else:
                missing_msg = "The requested information was not found in the selected authorized Knowledge Base documents."
        else:
            if language == "te":
                missing_msg = "మీ అధికార పరిధిలోని రికార్డులలో తగిన సమాచారం లభించలేదు."
            elif language == "hi":
                missing_msg = "आपके अधिकार क्षेत्र के रिकॉर्ड में कोई प्रासंगिक जानकारी नहीं मिली।"
            else:
                missing_msg = "No relevant authorized records were found within your jurisdiction."

        if not snippets:
            return {"answer": missing_msg, "citations": []}

        # Combine text from all available snippets
        combined_text = "\n\n".join(s.get("text", "") for s in snippets if s.get("text"))
        first_s = snippets[0]
        doc_id = first_s.get("document_id", "")
        page = 1 if is_image else first_s.get("physical_page_number", 1)
        if is_image:
            source_lbl = "Uploaded FIR Image (Page 1)"
        elif mode == "KNOWLEDGE_BASE_ONLY":
            source_lbl = first_s.get("source_label") or first_s.get("document_name") or f"Knowledge Base Document (Page {page})"
        else:
            source_lbl = f"PDF Page {page}"

        q_lower = query.lower()

        # Check for explicitly missing facts (e.g. criminal history)
        if any(term in q_lower for term in ["criminal history", "previous convictions", "prior cases", "past offences", "గత నేర చరిత్ర", "पिछला आपराधिक इतिहास"]):
            has_history = any(
                any(kw in s.get("text", "").lower() for kw in ["convicted", "prior case", "previous fir", "past offence", "earlier case", "antecedents"])
                for s in snippets
            )
            if not has_history:
                return {"answer": missing_msg, "citations": []}

        # Parse structured fields from the entire combined text
        parsed = self._rule_based_fallback_extraction(combined_text)

        # ── 1. PERSONS / NAMES QUERY ──
        if any(w in q_lower for w in ["person", "persons", "name", "names", "who", "whom", "accused", "complainant", "witness", "suspect", "father", "husband", "వ్యక్తి", "పేర్లు", "నిందితుడు", "नाम", "व्यक्ति", "आरोपी"]):
            persons = []
            # Complainant
            m_comp = re.search(r'(?:Details of Complainant|Complainant|Informant)[\s\S]*?(?:Name\s*:\s*|:\s*)([A-Za-z][A-Za-z\s\.]{1,40})', combined_text, re.I)
            if m_comp:
                cname = m_comp.group(1).split('\n')[0].strip()
                cname = re.sub(r'^(?:is|mr|mrs|ms|shri)\.?\s*', '', cname, flags=re.I)
                if len(cname) > 2 and cname.lower() not in ["details", "none", "written", "oral"]:
                    extra = []
                    m_age = re.search(r'(?:Age|Date of Birth / Age)\s*:\s*([^\n\r,]+)', combined_text, re.I)
                    if m_age: extra.append(f"Age: {m_age.group(1).strip()}")
                    m_occ = re.search(r'Occupation\s*:\s*([^\n\r,]+)', combined_text, re.I)
                    if m_occ: extra.append(f"Occupation: {m_occ.group(1).strip()}")
                    m_addr = re.search(r'Address\s*:\s*([^\n\r]+)', combined_text, re.I)
                    if m_addr: extra.append(f"Address: {m_addr.group(1).strip()}")
                    extra_str = f" ({', '.join(extra)})" if extra else ""
                    persons.append(f"**Complainant / Informant:** {cname}{extra_str}")
            elif parsed.get("complainant_name"):
                persons.append(f"**Complainant / Informant:** {parsed['complainant_name']}")

            # Father's / Relative's Name
            m_father = re.search(r"(?:Father'?s?|Husband'?s?)(?:\s*/\s*Husband'?s?)?\s*Name\s*:\s*([A-Za-z][A-Za-z\s\.]{1,40})", combined_text, re.I)
            if m_father:
                fname = m_father.group(1).split('\n')[0].strip()
                if len(fname) > 2:
                    persons.append(f"**Father's / Relative's Name:** {fname}")

            # Accused Persons
            m_acc = re.findall(r'(?:Accused(?:\s*Person)?|Suspect|Perpetrator|A[1-9])\s*[:\-]\s*([^\n\r,;]+)', combined_text, re.I)
            for a in m_acc:
                a_clean = a.strip()
                if len(a_clean) > 2 and not any(fp in a_clean.lower() for fp in ["unknown", "not known", "details"]):
                    persons.append(f"**Accused Person:** {a_clean}")
            if parsed.get("accused_names"):
                for an in parsed["accused_names"]:
                    if not any(an.lower() in p.lower() for p in persons):
                        persons.append(f"**Accused Person:** {an}")
            if not any("Accused" in p for p in persons):
                if re.search(r'(?:fake website|unknown|unidentified|cyber criminal|online fraudster)', combined_text, re.I):
                    persons.append("**Accused / Suspect:** Unknown perpetrator / operator of fraudulent website")

            # Investigating / Seizing Officer
            if parsed.get("seizing_officer_name"):
                rank_str = f" ({parsed['seizing_officer_rank']})" if parsed.get("seizing_officer_rank") else ""
                persons.append(f"**Investigating / Seizing Officer:** {parsed['seizing_officer_name']}{rank_str}")

            # Generic Name patterns
            generic_names = re.findall(r'(?<!Father\'s )(?<!Husband\'s )\bName\s*:\s*([A-Za-z][A-Za-z\s\.]{2,40})', combined_text, re.I)
            for gn in generic_names:
                gn_clean = gn.split('\n')[0].strip()
                if len(gn_clean) > 2 and not any(gn_clean.lower() in p.lower() for p in persons):
                    persons.append(f"**Identified Person:** {gn_clean}")

            if persons:
                ans_body = "The following persons/names are recorded in this document:\n\n" + "\n".join(f"- {p}" for p in persons)
                return {
                    "answer": f"{ans_body}\n\n**Source:** {source_lbl}.",
                    "citations": [{
                        "physical_page_number": page,
                        "document_id": doc_id,
                        "source_label": source_lbl,
                        "evidence_excerpt": ans_body[:250],
                        "verification_status": "VERIFIED_EXTRACTED_TEXT"
                    }]
                }

        # ── 2. SECTIONS / LAW / ACTS QUERY ──
        if any(w in q_lower for w in ["section", "sections", "act", "acts", "law", "charge", "charges", "ipc", "bns", "సెక్షన్", "చట్టం", "धारा"]):
            sections = []
            m_sec = re.findall(r'(?:Sections?\s*of\s*Law|Under\s*Section|U/s|Sec\.?)\s*[:\-]?\s*([^\n\r]+)', combined_text, re.I)
            for s in m_sec:
                s_clean = s.strip()
                if len(s_clean) > 2 and s_clean not in sections:
                    sections.append(s_clean)
            if parsed.get("law_sections"):
                for ls in parsed["law_sections"]:
                    if ls not in sections:
                        sections.append(ls)
            if sections:
                ans_body = f"The legal sections and acts recorded in this document are: **{', '.join(sections)}**."
                return {
                    "answer": f"{ans_body}\n\n**Source:** {source_lbl}.",
                    "citations": [{
                        "physical_page_number": page,
                        "document_id": doc_id,
                        "source_label": source_lbl,
                        "evidence_excerpt": ans_body[:250],
                        "verification_status": "VERIFIED_EXTRACTED_TEXT"
                    }]
                }

        # ── 3. OFFENCE / NATURE OF CRIME / BRIEF FACTS ──
        if any(w in q_lower for w in ["offence", "crime", "nature", "allegation", "facts", "what happened", "నేరం", "వివరాలు", "अपराध"]):
            ans_parts = []
            if parsed.get("offence_nature"):
                ans_parts.append(f"**Nature of Offence:** {parsed['offence_nature']}")
            # Brief facts
            m_facts = re.search(r'(?:Brief Facts(?:\s*of\s*the\s*Complaint)?|Facts|Substance of Information)\s*[:\-]\s*([^\n\r]+(?:\n[^\n\r]+){0,3})', combined_text, re.I)
            if m_facts:
                ans_parts.append(f"**Brief Facts:** {m_facts.group(1).strip()}")
            elif parsed.get("narrative_summary"):
                ans_parts.append(f"**Summary:** {parsed['narrative_summary']}")
            if ans_parts:
                ans_body = "\n\n".join(ans_parts)
                return {
                    "answer": f"{ans_body}\n\n**Source:** {source_lbl}.",
                    "citations": [{
                        "physical_page_number": page,
                        "document_id": doc_id,
                        "source_label": source_lbl,
                        "evidence_excerpt": ans_body[:250],
                        "verification_status": "VERIFIED_EXTRACTED_TEXT"
                    }]
                }

        # ── 4. FINANCIAL LOSS / AMOUNT / CONTRABAND / SEIZED ITEMS ──
        if any(w in q_lower for w in ["amount", "loss", "money", "rupees", "inr", "seized", "quantity", "contraband", "డబ్బు", "స్వాధీనం", "राशि", "नुकसान"]):
            ans_parts = []
            if parsed.get("financial_loss_amount"):
                ans_parts.append(f"**Financial Loss:** ₹{parsed['financial_loss_amount']}")
            if parsed.get("contraband_type"):
                qty = f" ({parsed['seized_quantity']} {parsed['seized_unit'] or ''})" if parsed.get("seized_quantity") else ""
                ans_parts.append(f"**Contraband / Seized Items:** {parsed['contraband_type']}{qty}")
            # Check for generic amount
            m_amt = re.search(r'(?:amount of|loss of|sum of|value of)\s*[:\s]*([^\n\r,\.]+)', combined_text, re.I)
            if m_amt and not ans_parts:
                ans_parts.append(f"**Amount / Value:** {m_amt.group(1).strip()}")
            if ans_parts:
                ans_body = "\n\n".join(ans_parts)
                return {
                    "answer": f"{ans_body}\n\n**Source:** {source_lbl}.",
                    "citations": [{
                        "physical_page_number": page,
                        "document_id": doc_id,
                        "source_label": source_lbl,
                        "evidence_excerpt": ans_body[:250],
                        "verification_status": "VERIFIED_EXTRACTED_TEXT"
                    }]
                }

        # ── 5. PLACE / LOCATION / STATION / DISTRICT ──
        if any(w in q_lower for w in ["where", "place", "location", "station", "district", "thana", "address", "ఎక్కడ", "స్టేషన్", "स्थान", "थाना"]):
            loc_parts = []
            if parsed.get("district"): loc_parts.append(f"**District:** {parsed['district']}")
            if parsed.get("station"): loc_parts.append(f"**Police / Excise Station:** {parsed['station']}")
            if parsed.get("place_of_occurrence"): loc_parts.append(f"**Place of Occurrence:** {parsed['place_of_occurrence']}")
            if loc_parts:
                ans_body = "\n".join(f"- {lp}" for lp in loc_parts)
                return {
                    "answer": f"Location details recorded in this document:\n\n{ans_body}\n\n**Source:** {source_lbl}.",
                    "citations": [{
                        "physical_page_number": page,
                        "document_id": doc_id,
                        "source_label": source_lbl,
                        "evidence_excerpt": ans_body[:250],
                        "verification_status": "VERIFIED_EXTRACTED_TEXT"
                    }]
                }

        # ── 6. SUMMARY / OVERVIEW QUERY ──
        is_summary = any(k in q_lower for k in ["summar", "overview", "brief", "details", "explain", "సారాంశం", "వివరాలు", "सारांश"])
        if is_summary:
            summary_points = []
            if parsed.get("district") or parsed.get("station"):
                summary_points.append(f"**Jurisdiction:** {parsed.get('station', 'Station')} ({parsed.get('district', 'District')})")
            if parsed.get("offence_nature"):
                summary_points.append(f"**Offence Nature:** {parsed['offence_nature']}")
            if parsed.get("complainant_name"):
                summary_points.append(f"**Complainant:** {parsed['complainant_name']}")
            if parsed.get("law_sections"):
                summary_points.append(f"**Sections of Law:** {', '.join(parsed['law_sections'])}")
            if parsed.get("place_of_occurrence"):
                summary_points.append(f"**Place of Occurrence:** {parsed['place_of_occurrence']}")
            if parsed.get("financial_loss_amount"):
                summary_points.append(f"**Financial Loss:** ₹{parsed['financial_loss_amount']}")
            if parsed.get("contraband_type"):
                qty = f" ({parsed['seized_quantity']} {parsed['seized_unit'] or ''})" if parsed.get("seized_quantity") else ""
                summary_points.append(f"**Seized Property:** {parsed['contraband_type']}{qty}")

            if summary_points:
                ans_body = "### Case Summary from Document Evidence:\n\n" + "\n".join(f"- {sp}" for sp in summary_points)
                return {
                    "answer": f"{ans_body}\n\n**Source:** {source_lbl}.",
                    "citations": [{
                        "physical_page_number": page,
                        "document_id": doc_id,
                        "source_label": source_lbl,
                        "evidence_excerpt": ans_body[:250],
                        "verification_status": "VERIFIED_EXTRACTED_TEXT"
                    }]
                }

        # ── 7. GENERIC QUERY: Extract matching lines across all text ──
        stop_words = {"what", "which", "where", "when", "who", "whom", "how", "many", "the", "and", "this", "that", "with", "from", "for", "are", "was", "were", "tell", "show", "give", "please", "about", "section", "act", "excise", "department", "andhra", "pradesh", "govt", "government"}
        query_words = [w for w in re.findall(r'\b[A-Za-z0-9_]{3,}\b', q_lower) if w not in stop_words]
        matching_lines = []
        for line in combined_text.split('\n'):
            line_str = line.strip()
            if not line_str or len(line_str) < 5:
                continue
            line_lower = line_str.lower()
            if any(qw in line_lower for qw in query_words):
                if line_str not in matching_lines:
                    matching_lines.append(line_str)

        if matching_lines:
            ans_body = "According to the document evidence:\n\n" + "\n".join(f"• {ml}" for ml in matching_lines[:6])
            return {
                "answer": f"{ans_body}\n\n**Source:** {source_lbl}.",
                "citations": [{
                    "physical_page_number": page,
                    "document_id": doc_id,
                    "source_label": source_lbl,
                    "evidence_excerpt": ans_body[:250],
                    "verification_status": "VERIFIED_EXTRACTED_TEXT"
                }]
            }

        # ── 8. Truly missing information fallback ──
        return {"answer": missing_msg, "citations": []}

gemini_service = GeminiService()
