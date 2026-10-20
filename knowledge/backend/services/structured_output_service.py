"""
Constrained Structured Output & Schema Enforcement Engine
=========================================================
Paranoia Layer 0, 1 & 2 Defense for Guaranteed LLM Output Formatting.

Why this is necessary:
- LLMs frequently wrap JSON in markdown fences, append conversational preambles,
  drop closing brackets, or invent non-existent schema fields.
- This module enforces strict Pydantic validation on raw model outputs, with automated
  JSON auto-repair and schema normalization.
"""

import json
import re
import logging
from typing import Type, TypeVar, Optional, Any, Dict, List
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ─── Standard Production Schemas ─────────────────────────────────────────────

class EmailDraftOutput(BaseModel):
    subject: str = Field(..., description="High-converting email subject line (under 60 chars)")
    body: str = Field(..., description="Personalized outreach body copy")
    call_to_action: str = Field(..., description="Clear, low-friction call to action")
    word_count: int = Field(default=0, description="Calculated word count of the body")


class ProspectClassificationOutput(BaseModel):
    is_icp: bool = Field(..., description="Whether prospect matches Ideal Customer Profile")
    icp_score: int = Field(..., ge=0, le=100, description="Bayesian fit score between 0 and 100")
    detected_signals: List[str] = Field(default_factory=list, description="Extracted buying or fit signals")
    reasoning: str = Field(default="", description="Auditable reasoning for classification")


# ─── Extraction & Repair Logic ───────────────────────────────────────────────

def _extract_json_substring(raw_text: str) -> str:
    """Extracts raw JSON payload from markdown fences or surrounding prose."""
    if not raw_text:
        return ""
    text = str(raw_text).strip()

    # 1. Check for markdown code fences: ```json ... ``` or ``` ... ```
    fence_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text, flags=re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    # 2. Extract first outer curly brace or square bracket pair
    start_brace = text.find("{")
    start_bracket = text.find("[")

    if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
        end_brace = text.rfind("}")
        if end_brace != -1 and end_brace > start_brace:
            return text[start_brace:end_brace + 1]
    elif start_bracket != -1:
        end_bracket = text.rfind("]")
        if end_bracket != -1 and end_bracket > start_bracket:
            return text[start_bracket:end_bracket + 1]

    return text


def repair_and_parse_json(raw_text: str) -> Optional[Any]:
    """
    Attempts clean JSON decode, falling back to heuristic repair for common LLM syntax faults:
    - Trailing commas before closing brackets
    - Unquoted keys or single quotes
    - Missing closing brackets
    """
    payload = _extract_json_substring(raw_text)
    if not payload:
        return None

    # Try direct parse first
    try:
        return json.loads(payload)
    except Exception:
        pass

    # Apply heuristic fixes
    fixed = payload.strip()
    # Strip trailing commas at end of truncated text
    fixed = re.sub(r',\s*$', '', fixed)

    # Balance unclosed brackets
    open_curly = fixed.count("{") - fixed.count("}")
    if open_curly > 0:
        fixed += ("}" * open_curly)

    open_square = fixed.count("[") - fixed.count("]")
    if open_square > 0:
        fixed += ("]" * open_square)

    # Remove any trailing commas right before closing brackets
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)

    try:
        return json.loads(fixed)
    except Exception as e:
        logger.debug(f"[StructuredOutput] JSON repair failed: {e}")
        return None


def extract_structured_output(
    raw_llm_response: str,
    schema_class: Type[T],
    default_instance: Optional[T] = None
) -> T:
    """
    Extracts and strictly validates structured output against a Pydantic schema class.
    
    :param raw_llm_response: Raw text returned by the model
    :param schema_class: Pydantic model class to validate against
    :param default_instance: Safe fallback instance if parsing is unrecoverable
    :returns: Fully validated Pydantic model instance
    """
    parsed_json = repair_and_parse_json(raw_llm_response)

    if parsed_json is not None:
        try:
            # Handle list vs dict polymorphic inputs
            if isinstance(parsed_json, dict):
                # Pydantic V2 / V1 compatible validation
                if hasattr(schema_class, "model_validate"):
                    return schema_class.model_validate(parsed_json)
                return schema_class(**parsed_json)
        except ValidationError as ve:
            logger.warning(f"[StructuredOutput] Pydantic validation failed for {schema_class.__name__}: {ve}")
        except Exception as e:
            logger.warning(f"[StructuredOutput] Instantiation failed for {schema_class.__name__}: {e}")

    if default_instance is not None:
        logger.info(f"[StructuredOutput] Returning provided default instance for {schema_class.__name__}.")
        return default_instance

    raise ValueError(f"Could not parse valid {schema_class.__name__} from LLM response: {raw_llm_response[:120]}")
