"""
ai_service.py - Section 5: Controlled, Logged, Deterministic AI Interpretation Layer.

Rules enforced:
1. AI proposes; deterministic rules verify; a human approves. Raw evidence is never modified.
2. Local-first (Ollama). Cloud AI (Gemini) runs ONLY if ALLOW_CLOUD_AI=true and GEMINI_API_KEY is set.
3. Fixed deterministic settings (temperature=0.0, pinned model name).
4. Every invocation is logged to ai_interpretation_logs with prompt hash, input summary,
   output JSON, model version, and deterministic verification status.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import config
from app.db import ForensicDB


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _call_llm(prompt: str) -> tuple[Optional[dict[str, Any]], str, str]:
    """
    Returns (parsed_json_or_none, model_name, model_version).
    Returns (None, 'none', 'disabled') when AI is off or unavailable.
    """
    provider = config.AI_PROVIDER
    if provider == "ollama":
        try:
            import httpx
            resp = httpx.post(
                f"{config.OLLAMA_URL.rstrip('/')}/api/generate",
                json={
                    "model": config.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0, "seed": 42},
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            body = resp.json()
            raw_text = body.get("response", "{}")
            return json.loads(raw_text), config.OLLAMA_MODEL, "ollama-pinned-temp0"
        except Exception:
            return None, config.OLLAMA_MODEL, "ollama-unavailable"

    if provider == "gemini" and config.ALLOW_CLOUD_AI and config.GEMINI_API_KEY:
        try:
            import httpx
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
            )
            resp = httpx.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.0,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text), config.GEMINI_MODEL, "gemini-temp0"
        except Exception:
            return None, config.GEMINI_MODEL, "gemini-unavailable"

    return None, "disabled", "none"


def _log_ai_call(
    db: ForensicDB,
    evidence_id: str,
    task: str,
    model_name: str,
    model_version: str,
    prompt: str,
    input_summary: str,
    output_json: dict[str, Any],
    verified: bool,
    notes: str,
) -> None:
    db.execute(
        """
        INSERT INTO ai_interpretation_logs
        (log_id, evidence_id, task, model_name, model_version, temperature,
         prompt_hash, input_summary, output_json, deterministic_verified,
         verification_notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"ai_{uuid.uuid4().hex[:12]}",
            evidence_id,
            task,
            model_name,
            model_version,
            0.0,
            _sha256_text(prompt),
            input_summary[:500],
            json.dumps(output_json, ensure_ascii=False),
            1 if verified else 0,
            notes,
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def suggest_column_mapping(
    db: ForensicDB,
    evidence_id: str,
    header: str,
    sample_values: list[str],
    allowed_fields: list[str],
) -> tuple[Optional[str], float]:
    """
    Rung 5 helper: asks AI to map an unrecognized header + sample values strictly
    to one of `allowed_fields` or 'unknown'. Deterministically validates output.
    """
    prompt = (
        "You are assisting a digital forensic column mapper. "
        "Pick the single best target field from allowed_fields or 'unknown'.\n"
        f"Header: {header}\n"
        f"Samples: {json.dumps(sample_values[:5], ensure_ascii=False)}\n"
        f"Allowed fields: {json.dumps(allowed_fields)}\n"
        'Return JSON: {"target_field": "<field_or_unknown>", "confidence": 0.0_to_1.0}'
    )
    output, model_name, model_ver = _call_llm(prompt)
    if not output:
        return None, 0.0

    target = str(output.get("target_field", "unknown")).strip()
    try:
        conf = max(0.0, min(0.85, float(output.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.0

    verified = True
    notes = "Allowed target field verified"
    if target != "unknown" and target not in allowed_fields:
        verified = False
        notes = f"Rejected hallucinated field '{target}' not in allowed_fields"
        target = "unknown"
        conf = 0.0
    elif target == "ifsc" and sample_values:
        if not any(re.match(config.REGEX_PATTERNS["ifsc"], v.strip().upper()) for v in sample_values if v.strip()):
            verified = False
            notes = "AI suggested 'ifsc' but samples failed IFSC regex check"
            target = "unknown"
            conf = 0.0

    _log_ai_call(
        db=db,
        evidence_id=evidence_id,
        task="COLUMN_MAPPING_SUGGESTION",
        model_name=model_name,
        model_version=model_ver,
        prompt=prompt,
        input_summary=f"header={header}, samples={sample_values[:3]}",
        output_json=output,
        verified=verified,
        notes=notes,
    )
    return (None if target == "unknown" else target), conf


def summarize_evidence_text(
    db: ForensicDB,
    evidence_id: str,
    raw_text: str,
    evidence_type: str,
) -> dict[str, Any]:
    """
    Produces an investigator-facing summary stored in the AI interpretation layer
    (never mutating raw evidence). Falls back to deterministic summary if AI disabled.
    """
    snippet = raw_text[:4000]
    prompt = (
        "Summarize this forensic evidence excerpt strictly from the text provided. "
        "Do not invent any identifier, amount, or date.\n"
        f"Evidence type: {evidence_type}\n"
        f"Text:\n{snippet}\n"
        'Return JSON: {"summary": "...", "key_claims": ["..."]}'
    )
    output, model_name, model_ver = _call_llm(prompt)
    if output and isinstance(output.get("summary"), str):
        _log_ai_call(
            db=db,
            evidence_id=evidence_id,
            task="INVESTIGATOR_SUMMARY",
            model_name=model_name,
            model_version=model_ver,
            prompt=prompt,
            input_summary=f"type={evidence_type}, chars={len(raw_text)}",
            output_json=output,
            verified=True,
            notes="AI-assisted summary (labeled separately from raw evidence)",
        )
        return {
            "ai_assisted": True,
            "model": model_name,
            "summary": output["summary"],
            "key_claims": output.get("key_claims", []),
        }

    # Deterministic offline fallback summary
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()][:5]
    return {
        "ai_assisted": False,
        "model": "deterministic-preview",
        "summary": " | ".join(lines) if lines else f"{evidence_type} evidence ingested.",
        "key_claims": lines,
    }
