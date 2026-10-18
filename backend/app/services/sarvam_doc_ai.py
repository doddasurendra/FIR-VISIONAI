"""
Official Sarvam AI Document Intelligence Service.
Integrates Sarvam Document AI (Sarvam Vision 1.5) for:
1. Digitise: Full-document OCR, layout-faithful reading-order blocks, and markdown content per page.
2. Extract: Schema-based structured key-value extraction with source citations and confidence scores.
"""
from __future__ import annotations

import os
import json
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
import httpx
from pypdf import PdfReader, PdfWriter

from ..config import settings

logger = logging.getLogger(__name__)

# Terminal states for Sarvam AI Doc AI jobs
TERMINAL_STATES = {"completed", "partially_completed", "failed", "rejected"}
MAX_PAGES_PER_JOB = 10


def convert_field_list_to_json_schema(fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convert a list of UI field definitions:
      [{'key': 'fir_number', 'data_type': 'string', 'description': '...', ...}]
    into the JSON Schema required by Sarvam AI Extract:
      {'type': 'object', 'properties': {'fir_number': {'type': 'string', 'description': '...'}}}
    """
    type_mapping = {
        "string": "string",
        "text": "string",
        "number": "number",
        "float": "number",
        "integer": "integer",
        "int": "integer",
        "boolean": "boolean",
        "bool": "boolean",
        "array": "array",
        "list": "array",
        "object": "object",
    }

    properties: Dict[str, Any] = {}
    for f in fields:
        k = f.get("key")
        if not k:
            continue
        raw_type = str(f.get("data_type", "string")).lower()
        json_type = type_mapping.get(raw_type, "string")
        desc = f.get("description") or f.get("label") or k.replace("_", " ").title()
        prop: Dict[str, Any] = {
            "type": json_type,
            "description": desc,
        }
        if json_type == "array":
            prop["items"] = {"type": "string", "description": f"Individual {desc}"}
        properties[k] = prop

    return {
        "type": "object",
        "properties": properties,
    }


class SarvamDocAIService:
    def __init__(self):
        self.base_url = (getattr(settings, "SARVAM_BASE_URL", None) or "https://api.sarvam.ai").rstrip("/")
        self.api_key = getattr(settings, "SARVAM_API_KEY", None)

    def is_available(self) -> bool:
        """Check if a valid Sarvam API key is configured."""
        return bool(self.api_key and len(self.api_key.strip()) > 10 and self.api_key != "your_sarvam_api_key_here")

    def _get_headers(self) -> Dict[str, str]:
        if not self.is_available():
            raise ValueError("SARVAM_API_KEY is not configured or invalid.")
        return {
            "api-subscription-key": self.api_key.strip()
        }

    async def _poll_job_status(
        self,
        client: httpx.AsyncClient,
        job_id: str,
        max_wait_seconds: int = 120,
        poll_interval: float = 3.0,
    ) -> Dict[str, Any]:
        """Poll the job status endpoint until a terminal state is reached."""
        headers = self._get_headers()
        url = f"{self.base_url}/doc-ai/v1/job/{job_id}/status"
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed > max_wait_seconds:
                raise TimeoutError(f"Sarvam AI job {job_id} timed out after {int(elapsed)} seconds.")

            try:
                resp = await client.get(url, headers=headers, timeout=30.0)
                if resp.status_code == 404:
                    raise ValueError(f"Job {job_id} not found on Sarvam API.")
                if resp.status_code in (401, 403):
                    raise PermissionError(f"Sarvam API authentication failed: {resp.text}")
                if resp.status_code == 429:
                    logger.warning("Sarvam API rate limit hit during polling; backing off 5s...")
                    time.sleep(5.0)
                    continue

                resp.raise_for_status()
                st_data = resp.json()
                current_status = (st_data.get("status") or "").lower()

                if current_status in TERMINAL_STATES:
                    return st_data

            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                logger.warning(f"Network transient error polling job {job_id}: {e}")

            time.sleep(poll_interval)

    async def digitise(
        self,
        file_path: str,
        mime_type: str = "application/pdf",
        language: str = "en-IN",
    ) -> Dict[str, Any]:
        """
        Run Sarvam AI Digitise on a file (up to 10 pages).
        Returns full per-page content, blocks, and document layout.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        headers = self._get_headers()
        url = f"{self.base_url}/doc-ai/v1/job/digitise"
        filename = os.path.basename(file_path)

        async with httpx.AsyncClient() as client:
            with open(file_path, "rb") as f:
                files = {"file": (filename, f, mime_type)}
                data = {
                    "output_format": "json",
                    "language": language or "en-IN",
                }
                resp = await client.post(url, headers=headers, files=files, data=data, timeout=90.0)

            if resp.status_code != 201 and resp.status_code != 200:
                raise RuntimeError(f"Sarvam Digitise failed ({resp.status_code}): {resp.text}")

            job_info = resp.json()
            job_id = job_info.get("job_id")
            if not job_id:
                raise ValueError("No job_id returned by Sarvam Digitise API.")

            # Poll for completion
            status_data = await self._poll_job_status(client, job_id)
            status_str = status_data.get("status", "").lower()
            if status_str not in ("completed", "partially_completed"):
                raise RuntimeError(f"Sarvam Digitise job {job_id} terminated with status: {status_str}")

            # Fetch results
            results_url = f"{self.base_url}/doc-ai/v1/job/{job_id}/results?format=json"
            res_resp = await client.get(results_url, headers=headers, timeout=60.0)
            res_resp.raise_for_status()
            results = res_resp.json()
            results["sarvam_job_id"] = job_id
            return results

    async def extract(
        self,
        file_path: str,
        schema: Optional[Dict[str, Any]] = None,
        config_id: Optional[str] = None,
        mime_type: str = "application/pdf",
        language: str = "en-IN",
    ) -> Dict[str, Any]:
        """
        Run Sarvam AI Extract on a file (up to 10 pages).
        Returns structured fields in 'result' and leaf confidence/sources in 'annotations'.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        headers = self._get_headers()
        url = f"{self.base_url}/doc-ai/v1/job/extract"
        filename = os.path.basename(file_path)

        data: Dict[str, Any] = {
            "output_format": "json",
            "language": language or "en-IN",
        }
        if config_id:
            data["config_id"] = config_id
        elif schema:
            data["schema"] = json.dumps(schema)
        else:
            raise ValueError("Either 'schema' or 'config_id' must be provided to Sarvam Extract.")

        async with httpx.AsyncClient() as client:
            with open(file_path, "rb") as f:
                files = {"file": (filename, f, mime_type)}
                resp = await client.post(url, headers=headers, files=files, data=data, timeout=90.0)

            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Sarvam Extract failed ({resp.status_code}): {resp.text}")

            job_info = resp.json()
            job_id = job_info.get("job_id")
            if not job_id:
                raise ValueError("No job_id returned by Sarvam Extract API.")

            # Poll for completion
            status_data = await self._poll_job_status(client, job_id)
            status_str = status_data.get("status", "").lower()
            if status_str not in ("completed", "partially_completed"):
                raise RuntimeError(f"Sarvam Extract job {job_id} terminated with status: {status_str}")

            # Fetch results
            results_url = f"{self.base_url}/doc-ai/v1/job/{job_id}/results?format=json"
            res_resp = await client.get(results_url, headers=headers, timeout=60.0)
            res_resp.raise_for_status()
            results = res_resp.json()
            results["sarvam_job_id"] = job_id
            return results

    async def process_document(
        self,
        file_path: str,
        mime_type: str,
        schema_fields: List[Dict[str, Any]],
        config_id: Optional[str] = None,
        language: str = "en-IN",
    ) -> Dict[str, Any]:
        """
        Execute full end-to-end Sarvam Document AI pipeline:
        1. Digitise: full verbatim document OCR + per-page layout.
        2. Extract: schema-based field extraction + annotations (confidence & citations).
        Handles page-batching for PDFs > 10 pages automatically.
        """
        if not self.is_available():
            raise ValueError("SARVAM_API_KEY is not configured or invalid.")

        is_pdf = mime_type == "application/pdf"
        total_pages = 1
        if is_pdf and os.path.exists(file_path):
            try:
                reader = PdfReader(file_path)
                total_pages = len(reader.pages)
            except Exception:
                total_pages = 1

        # Check if batching is needed (PDF > 10 pages)
        if is_pdf and total_pages > MAX_PAGES_PER_JOB:
            return await self._process_multi_batch_pdf(file_path, mime_type, schema_fields, config_id, language, total_pages)

        # Single-batch standard flow (<= 10 pages or image)
        # Convert schema fields to Sarvam JSON Schema if config_id not provided
        sarvam_schema = None
        if not config_id:
            sarvam_schema = convert_field_list_to_json_schema(schema_fields)

        # 1. Run Extract
        extract_res = await self.extract(
            file_path=file_path,
            schema=sarvam_schema,
            config_id=config_id,
            mime_type=mime_type,
            language=language,
        )

        # 2. Run Digitise (for full-document verbatim text per page)
        try:
            digitise_res = await self.digitise(
                file_path=file_path,
                mime_type=mime_type,
                language=language,
            )
        except Exception as e:
            logger.warning(f"Sarvam Digitise pass failed: {e}. Relying on Extract result and local page text.")
            digitise_res = None

        # Build clean per-page text from Digitise
        pages_text_map: Dict[int, str] = {}
        if digitise_res and "documents" in digitise_res:
            for doc_item in digitise_res["documents"]:
                for page_item in doc_item.get("pages", []):
                    p_num = page_item.get("page_num", 1)
                    blocks = page_item.get("blocks", [])
                    sorted_blocks = sorted(blocks, key=lambda b: b.get("reading_order", 0))
                    page_text = "\n\n".join(b.get("text", "").strip() for b in sorted_blocks if b.get("text"))
                    pages_text_map[p_num] = page_text

        return {
            "extract": extract_res,
            "digitise": digitise_res,
            "pages_text_map": pages_text_map,
            "sarvam_job_id": extract_res.get("sarvam_job_id"),
            "total_pages": total_pages,
            "provider": "Sarvam Document AI (Sarvam Vision 1.5)",
        }

    async def _process_multi_batch_pdf(
        self,
        file_path: str,
        mime_type: str,
        schema_fields: List[Dict[str, Any]],
        config_id: Optional[str],
        language: str,
        total_pages: int,
    ) -> Dict[str, Any]:
        """Split PDF into 10-page batches and aggregate results with adjusted page citations."""
        reader = PdfReader(file_path)
        batch_size = MAX_PAGES_PER_JOB
        num_batches = (total_pages + batch_size - 1) // batch_size
        logger.info(f"Splitting {total_pages}-page PDF into {num_batches} batches of up to {batch_size} pages for Sarvam AI.")

        aggregated_result: Dict[str, Any] = {}
        aggregated_annotations: Dict[str, Any] = {}
        aggregated_pages_text: Dict[int, str] = {}
        last_job_id = None

        sarvam_schema = None if config_id else convert_field_list_to_json_schema(schema_fields)

        import tempfile

        for b_idx in range(num_batches):
            start_p = b_idx * batch_size
            end_p = min(start_p + batch_size, total_pages)
            page_offset = start_p  # Offset to add to batch page numbers

            writer = PdfWriter()
            for p in range(start_p, end_p):
                writer.add_page(reader.pages[p])

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_f:
                writer.write(tmp_f)
                tmp_path = tmp_f.name

            try:
                # Run extract on batch
                batch_extract = await self.extract(
                    file_path=tmp_path,
                    schema=sarvam_schema,
                    config_id=config_id,
                    mime_type="application/pdf",
                    language=language,
                )
                last_job_id = batch_extract.get("sarvam_job_id")

                # Merge result fields (prioritizing non-null values)
                batch_res_fields = batch_extract.get("result", {})
                for k, v in batch_res_fields.items():
                    if v is not None and (k not in aggregated_result or aggregated_result[k] is None):
                        aggregated_result[k] = v
                    elif isinstance(v, list) and isinstance(aggregated_result.get(k), list):
                        # Union lists without duplicates
                        for item in v:
                            if item not in aggregated_result[k]:
                                aggregated_result[k].append(item)

                # Merge annotations with offset page numbers
                batch_ann = batch_extract.get("annotations", {})
                for k, ann in batch_ann.items():
                    if isinstance(ann, dict):
                        # Adjust page_num in sources
                        adjusted_sources = []
                        for src in ann.get("sources", []):
                            src_copy = dict(src)
                            if "page_num" in src_copy:
                                src_copy["page_num"] = src_copy["page_num"] + page_offset
                            adjusted_sources.append(src_copy)
                        ann_copy = dict(ann)
                        ann_copy["sources"] = adjusted_sources
                        if k not in aggregated_annotations:
                            aggregated_annotations[k] = ann_copy
                    elif isinstance(ann, list):
                        for item in ann:
                            if isinstance(item, dict):
                                for src in item.get("sources", []):
                                    if "page_num" in src:
                                        src["page_num"] = src["page_num"] + page_offset

                # Run digitise on batch
                try:
                    batch_digitise = await self.digitise(
                        file_path=tmp_path,
                        mime_type="application/pdf",
                        language=language,
                    )
                    if batch_digitise and "documents" in batch_digitise:
                        for doc_item in batch_digitise["documents"]:
                            for page_item in doc_item.get("pages", []):
                                p_num = page_item.get("page_num", 1) + page_offset
                                blocks = page_item.get("blocks", [])
                                sorted_blocks = sorted(blocks, key=lambda b: b.get("reading_order", 0))
                                page_text = "\n\n".join(b.get("text", "").strip() for b in sorted_blocks if b.get("text"))
                                aggregated_pages_text[p_num] = page_text
                except Exception as e:
                    logger.warning(f"Batch {b_idx+1} digitise failed: {e}")

            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

        return {
            "extract": {
                "type": "extract",
                "status": "completed",
                "result": aggregated_result,
                "annotations": aggregated_annotations,
                "sarvam_job_id": last_job_id,
            },
            "digitise": {"type": "digitise", "status": "completed"},
            "pages_text_map": aggregated_pages_text,
            "sarvam_job_id": last_job_id,
            "total_pages": total_pages,
            "provider": "Sarvam Document AI (Sarvam Vision 1.5 - Multi-Batch)",
        }


sarvam_doc_ai = SarvamDocAIService()
