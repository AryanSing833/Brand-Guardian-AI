import json
import re
from typing import List, Dict, Any

import requests

from utils import get_logger

logger = get_logger("llm_engine")

# ---------------------------------------------------------------------------
# Ollama Configuration
# ---------------------------------------------------------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"


# ---------------------------------------------------------------------------
# Prompt Template
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a fair and objective Brand Compliance Auditor.

You will be provided with:
1. TRANSCRIPT — spoken words extracted from a video advertisement.
2. ON-SCREEN TEXT — text detected via OCR from the video frames.
3. REGULATORY RULES — potentially relevant policy excerpts retrieved from official guidelines.

IMPORTANT GUIDELINES FOR YOUR ANALYSIS:
- The regulatory rules are provided as REFERENCE only. They may or may not apply to this specific video.
- Do NOT assume the video is violating any rule. Many advertisements are perfectly compliant.
- Only flag a violation if the video content CLEARLY AND SPECIFICALLY contradicts a rule.
- Vague or generic matches are NOT violations. The violation must be concrete and evidence-based.
- If the rules provided do not closely relate to the actual video content, that means no violation exists for those rules.
- It is completely normal and expected that many videos will PASS with no violations.

YOUR TASK:
- Objectively compare the video content against the regulatory rules.
- Determine whether the video is COMPLIANT or NON-COMPLIANT.
- Only flag genuine, clear violations — not hypothetical or weak matches.
- Assign a severity level (low / medium / high) ONLY if there is a real violation.
- Provide a confidence score between 0.0 and 1.0 for your overall assessment.

IF VIOLATIONS ARE FOUND:
- failure_reasons: Clear, specific reasons WHY each violation occurred. Quote or reference what in the transcript or on-screen content caused the failure.
- recommendations: Actionable, practical advice on HOW TO FIX each issue.

RESPOND WITH VALID JSON ONLY — no markdown, no commentary, no code fences.
Use exactly this schema:

{
    "violation": true or false,
    "violated_rules": ["rule 1 description", "rule 2 description"],
    "failure_reasons": ["specific reason why rule 1 was violated", "specific reason for rule 2"],
    "recommendations": ["how to fix issue 1", "how to fix issue 2"],
    "explanation": "Concise summary of findings",
    "severity": "low" or "medium" or "high" or "none",
    "confidence": 0.0 to 1.0
}

If no violations are found, set "violation" to false, "violated_rules" to [], "failure_reasons" to [], "recommendations" to [], and "severity" to "none".
"""


def _build_user_prompt(
    transcript: str,
    ocr_text: List[str],
    retrieved_rules: List[str],
) -> str:
    """Assemble the user-facing prompt with all evidence."""
    if retrieved_rules:
        rules_block = "\n\n".join(
            f"--- Rule Chunk {i} ---\n{rule}"
            for i, rule in enumerate(retrieved_rules, start=1)
        )
    else:
        rules_block = "(No closely matching regulatory rules were found for this video content.)"

    ocr_block = "\n".join(f"• {t}" for t in ocr_text) if ocr_text else "(none detected)"

    return f"""=== TRANSCRIPT ===
{transcript}

=== ON-SCREEN TEXT (OCR) ===
{ocr_block}

=== REGULATORY RULES (reference only — may or may not apply) ===
{rules_block}

Based on the above, determine whether this video advertisement is COMPLIANT or NON-COMPLIANT.
Only flag violations that are clearly and specifically supported by the evidence.
If the video content does not clearly violate any of the referenced rules, mark it as compliant.
Return your verdict as JSON."""


# ---------------------------------------------------------------------------
# Ollama Interaction
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str) -> str:
    """
    Send a prompt to the local Ollama API and return the generated text.

    Uses the non-streaming endpoint for simplicity.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": 0.1,       # Low temp for deterministic output
            "num_predict": 3072,      # Max tokens (room for reasons + recommendations)
        },
    }

    logger.info(f"Calling Ollama ({OLLAMA_MODEL}) …")
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=300)
    except requests.ConnectionError:
        raise RuntimeError(
            "Cannot reach Ollama at http://localhost:11434. "
            "Ensure Ollama is running (`ollama serve`) and the mistral model is pulled."
        )
    except requests.Timeout:
        raise RuntimeError("Ollama request timed out (300 s). The model may be overloaded.")

    # Handle HTTP errors from Ollama (e.g. CUDA crash, OOM, model issues)
    if resp.status_code != 200:
        try:
            err_body = resp.json()
            err_msg = err_body.get("error", resp.text[:300])
        except Exception:
            err_msg = resp.text[:300]
        logger.error(f"Ollama returned HTTP {resp.status_code}: {err_msg}")
        raise RuntimeError(
            f"Ollama returned an error (HTTP {resp.status_code}): {err_msg}. "
            "If you see a CUDA error, restart Ollama with CPU mode: "
            "set OLLAMA_GPU_LAYERS=0 then run 'ollama serve'."
        )

    data = resp.json()
    return data.get("response", "")


# ---------------------------------------------------------------------------
# Response Parsing
# ---------------------------------------------------------------------------

def _parse_llm_response(raw: str) -> Dict[str, Any]:
    """
    Extract a JSON object from the LLM's raw text output.

    Handles common quirks: markdown code fences, leading/trailing junk.
    """
    # Strip markdown code fences if present
    cleaned = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # Try direct JSON parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fallback: find first { … } block
    brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback: handle truncated JSON (missing closing brace)
    brace_start = cleaned.find("{")
    if brace_start != -1:
        fragment = cleaned[brace_start:]
        # Count unmatched braces and close them
        open_braces = fragment.count("{") - fragment.count("}")
        repaired = fragment + "}" * open_braces
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    # If all parsing fails, return a safe fallback
    logger.warning("Could not parse LLM response as JSON. Returning raw text as explanation.")
    return {
        "violation": False,
        "violated_rules": [],
        "failure_reasons": [],
        "recommendations": [],
        "explanation": f"LLM output could not be parsed: {raw[:500]}",
        "severity": "low",
        "confidence": 0.0,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_compliance_report(
    transcript: str,
    ocr_text: List[str],
    retrieved_rules: List[str],
) -> Dict[str, Any]:
    """
    Generate a structured compliance report by prompting the local Mistral model.

    Args:
        transcript:      Speech-to-text output from the video.
        ocr_text:        List of on-screen text segments.
        retrieved_rules: Relevant policy chunks from the knowledge base.

    Returns:
        Dict matching the compliance report schema:
        {
            "violation": bool,
            "violated_rules": [...],
            "explanation": str,
            "severity": "low" | "medium" | "high",
            "confidence": float
        }
    """
    user_prompt = _build_user_prompt(transcript, ocr_text, retrieved_rules)
    raw_response = _call_ollama(user_prompt)
    logger.info(f"Raw LLM response ({len(raw_response)} chars) received.")

    report = _parse_llm_response(raw_response)

    # Enforce schema defaults for any missing keys
    report.setdefault("violation", False)
    report.setdefault("violated_rules", [])
    report.setdefault("failure_reasons", [])
    report.setdefault("recommendations", [])
    report.setdefault("explanation", "No explanation provided.")
    report.setdefault("severity", "low")
    report.setdefault("confidence", 0.0)

    # Normalize failure_reasons and recommendations to lists (LLM may return string)
    for key in ("failure_reasons", "recommendations"):
        val = report[key]
        if isinstance(val, str) and val.strip():
            report[key] = [val]
        elif not isinstance(val, list):
            report[key] = []

    # Clamp confidence to [0, 1]
    report["confidence"] = max(0.0, min(1.0, float(report["confidence"])))

    logger.info(
        f"Verdict: violation={report['violation']}, "
        f"severity={report['severity']}, "
        f"confidence={report['confidence']:.2f}"
    )
    return report
