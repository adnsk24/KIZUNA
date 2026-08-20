from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.icd11_client import (
    ICD11APIError,
    ICD11MappingNotFoundError,
    fetch_icd11_mapping_from_api,
)

logger = logging.getLogger("kizuna.mapping_service")

DB_FILE = Path(__file__).resolve().parents[1] / "kizuna.db"


def db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def normalize_code(code: str) -> str:
    return str(code or "").strip().upper()


def get_mapping_from_db(namaste_code: str) -> dict[str, Any] | None:
    """Checks the database for an existing cached mapping by NAMASTE code."""
    norm_code = normalize_code(namaste_code)
    if not norm_code:
        return None
        
    with db_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM icd11_namaste_mappings 
            WHERE UPPER(namaste_code) = ? 
               OR UPPER(namaste_code) LIKE (? || '(%')
               OR ? LIKE (UPPER(namaste_code) || '(%')
            """,
            (norm_code, norm_code, norm_code),
        ).fetchone()
        
    if row:
        return dict(row)
    return None


def save_mapping_to_db(mapping: dict[str, Any]) -> dict[str, Any]:
    """
    Saves a successfully obtained ICD-11 ↔ NAMASTE mapping into the database.
    Uses SQLite ON CONFLICT clause to handle concurrent requests safely without duplicate entries.
    """
    now = datetime.now(timezone.utc).isoformat()
    namaste_code = normalize_code(mapping.get("namaste_code", ""))
    
    if not namaste_code:
        raise ValueError("Cannot save mapping without a valid NAMASTE code.")
        
    with db_connection() as conn:
        conn.execute(
            """
            INSERT INTO icd11_namaste_mappings (
                namaste_code, namaste_term, namaste_english, icd11_code, icd11_term,
                icd11_uri, mapping_class, mapping_status, relationship, confidence,
                source, version, biomedical_code, biomedical_term, short_definition,
                long_definition, namaste_term_diacritical, namaste_term_devanagari,
                created_at, updated_at, last_verified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(namaste_code) DO UPDATE SET
                namaste_term = excluded.namaste_term,
                namaste_english = excluded.namaste_english,
                icd11_code = excluded.icd11_code,
                icd11_term = excluded.icd11_term,
                icd11_uri = excluded.icd11_uri,
                mapping_class = excluded.mapping_class,
                mapping_status = excluded.mapping_status,
                relationship = excluded.relationship,
                confidence = excluded.confidence,
                source = excluded.source,
                version = excluded.version,
                biomedical_code = excluded.biomedical_code,
                biomedical_term = excluded.biomedical_term,
                short_definition = excluded.short_definition,
                long_definition = excluded.long_definition,
                namaste_term_diacritical = excluded.namaste_term_diacritical,
                namaste_term_devanagari = excluded.namaste_term_devanagari,
                updated_at = excluded.updated_at,
                last_verified = excluded.last_verified
            """,
            (
                namaste_code,
                mapping.get("namaste_term", ""),
                mapping.get("namaste_english", ""),
                mapping.get("icd11_code", ""),
                mapping.get("icd11_term", ""),
                mapping.get("icd11_uri", ""),
                mapping.get("mapping_class", "UNMAPPED"),
                mapping.get("mapping_status", "UNMAPPED"),
                mapping.get("relationship", ""),
                mapping.get("confidence"),
                mapping.get("source", ""),
                mapping.get("version", ""),  # Only populated if provided by API
                mapping.get("biomedical_code", ""),
                mapping.get("biomedical_term", ""),
                mapping.get("short_definition", ""),
                mapping.get("long_definition", ""),
                mapping.get("namaste_term_diacritical", ""),
                mapping.get("namaste_term_devanagari", ""),
                now,
                now,
                now,
            ),
        )
        conn.commit()

    from app.cloud_db import trigger_upload
    trigger_upload(DB_FILE)

    saved = get_mapping_from_db(namaste_code)
    if not saved:
        raise RuntimeError(f"Failed to retrieve mapping after saving for code: {namaste_code}")
    return saved


def get_or_fetch_mapping(namaste_identifier: str) -> dict[str, Any]:
    """
    Main mapping cache service flow:
    1. Check local database cache for existing mapping.
    2. If found (Cache Hit): Return directly without calling API.
    3. If not found (Cache Miss): Call external ICD-11 API.
    4. Save valid result to database cache.
    5. Return result to user.
    """
    code_query = normalize_code(namaste_identifier)
    
    # 1. Check local database
    cached = get_mapping_from_db(code_query)
    if cached:
        logger.info(f"[DATABASE/CACHE] Retrieved ICD-11 ↔ NAMASTE mapping for '{code_query}' from database cache.")
        return cached

    # 2. Cache Miss - Call ICD-11 API
    logger.info(f"[ICD-11 API] Cache miss for '{namaste_identifier}'. Calling external ICD-11 API.")
    api_result = fetch_icd11_mapping_from_api(namaste_identifier)

    # 3. Save result in local database
    saved_result = save_mapping_to_db(api_result)
    logger.info(f"[DATABASE/SAVE] Successfully cached mapping for '{saved_result['namaste_code']}' in database.")
    
    return saved_result
