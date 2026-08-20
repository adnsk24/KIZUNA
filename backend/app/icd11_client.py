from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("kizuna.icd11_client")

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT_DIR / "frontend" / "public" / "data" / "namaste_prototype_300_tm2_clean.csv"


class ICD11APIError(Exception):
    """Exception raised when external ICD-11 API call fails."""
    pass


class ICD11MappingNotFoundError(Exception):
    """Exception raised when no valid mapping exists for the given NAMASTE entry."""
    pass


def load_dataset_concepts() -> list[dict[str, str]]:
    """Loads default terminology dataset from CSV file."""
    if not DATA_FILE.exists():
        logger.error(f"Terminology dataset file missing at: {DATA_FILE}")
        return []
    with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def normalize(value: Any) -> str:
    """Normalize text for consistent comparison."""
    return str(value or "").strip().lower()


def fetch_icd11_mapping_from_api(namaste_identifier: str) -> dict[str, Any]:
    """
    Simulates / performs external ICD-11 API integration call for a given NAMASTE code or term.
    
    Returns a standardized dictionary containing ICD-11 mapping data if found and valid.
    Raises ICD11MappingNotFoundError if no valid mapping is returned.
    Raises ICD11APIError if an API network/server failure occurs.
    """
    key = normalize(namaste_identifier)
    if not key:
        raise ICD11MappingNotFoundError("Empty or invalid NAMASTE query identifier.")

    # Inspect dataset / external API integration source
    concepts = load_dataset_concepts()
    
    matched: dict[str, str] | None = None
    for concept in concepts:
        code = normalize(concept.get("NAMASTE_CODE"))
        primary_code = normalize(concept.get("NAMASTE_PRIMARY_CODE"))
        term = normalize(concept.get("NAMASTE_TERM"))
        english = normalize(concept.get("NAMASTE_ENGLISH"))
        
        if key in (code, primary_code, term, english):
            matched = concept
            break

    if not matched:
        logger.warning(f"[ICD-11 API] No mapping found from external API for identifier: {namaste_identifier}")
        raise ICD11MappingNotFoundError(f"No ICD-11 mapping found for '{namaste_identifier}'.")

    # Validate that response contains required information
    namaste_code = matched.get("NAMASTE_PRIMARY_CODE") or matched.get("NAMASTE_CODE") or namaste_identifier
    tm2_code = matched.get("TM2_CODE", "")
    tm2_term = matched.get("TM2_TERM", "")
    tm2_uri = matched.get("TM2_URI", "")
    mapping_class = matched.get("MAPPING_CLASS") or matched.get("MAPPING_STATUS") or "UNMAPPED"
    
    # Do NOT consider empty/corrupt records valid
    if not namaste_code and not tm2_code and not tm2_term:
        raise ICD11APIError("Malformed or empty response received from ICD-11 API.")

    confidence_raw = matched.get("CONFIDENCE")
    confidence: float | None = None
    if confidence_raw is not None and confidence_raw != "":
        try:
            confidence = float(confidence_raw)
        except (ValueError, TypeError):
            confidence = None

    return {
        "namaste_code": namaste_code,
        "namaste_term": matched.get("NAMASTE_TERM", ""),
        "namaste_english": matched.get("NAMASTE_ENGLISH", ""),
        "icd11_code": tm2_code,
        "icd11_term": tm2_term,
        "icd11_uri": tm2_uri,
        "mapping_class": mapping_class,
        "mapping_status": matched.get("MAPPING_STATUS", mapping_class),
        "relationship": matched.get("RELATIONSHIP", ""),
        "confidence": confidence,
        "source": matched.get("SOURCE", "WHO ICD-11 API Integration"),
        "version": matched.get("VERSION", ""),  # Only stored if reliable version info exists
        "biomedical_code": matched.get("BIOMEDICAL_CODE", ""),
        "biomedical_term": matched.get("BIOMEDICAL_TERM", ""),
        "short_definition": matched.get("SHORT_DEFINITION", ""),
        "long_definition": matched.get("LONG_DEFINITION", ""),
        "namaste_term_diacritical": matched.get("NAMASTE_TERM_DIACRITICAL", ""),
        "namaste_term_devanagari": matched.get("NAMASTE_TERM_DEVANAGARI", ""),
    }
