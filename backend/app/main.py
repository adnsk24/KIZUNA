from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.icd11_client import ICD11APIError, ICD11MappingNotFoundError
from app.mapping_service import get_or_fetch_mapping, save_mapping_to_db, get_mapping_from_db
from app.fhir_service import build_fhir_bundle
from app.cloud_db import download_db, trigger_upload

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("kizuna.main")

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT_DIR / "frontend" / "public" / "data" / "namaste_prototype_300_tm2_clean.csv"
if not DATA_FILE.exists():
    DATA_FILE = Path(__file__).resolve().parent / "data" / "namaste_prototype_300_tm2_clean.csv"
DB_FILE = Path(__file__).resolve().parents[1] / "kizuna.db"

app = FastAPI(
    title="Team Tenacious Interoperability API",
    version="0.1.0",
    description="REST API for NAMASTE–ICD-11 TM2 terminology mapping, clinical encounter integration, mapping evidence, and human review.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EncounterCreate(BaseModel):
    patient_id: str = Field(min_length=1)
    diagnosis: str = Field(min_length=1)
    clinical_notes: str = ""
    namaste_code: str = ""
    namaste_term: str = ""
    namaste_english: str = ""
    tm2_code: str = ""
    tm2_term: str = ""
    tm2_uri: str = ""
    mapping_class: str = "UNMAPPED"
    mapping_status: str = "UNMAPPED"
    relationship: str = ""
    confidence: float | None = None
    source: str = ""
    version: str = ""
    biomedical_code: str = ""
    biomedical_term: str = ""
    short_definition: str = ""
    long_definition: str = ""
    namaste_term_diacritical: str = ""
    namaste_term_devanagari: str = ""
    prescriptions: list[dict[str, Any]] | None = None
    observations: list[dict[str, Any]] | None = None


class ReviewCreate(BaseModel):
    encounter_id: int
    decision: str = Field(pattern="^(REVIEW|APPROVED|REJECTED)$")
    reviewer: str = "Clinical Reviewer"
    notes: str = ""


class PatientCreate(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    gender: str = ""
    date_of_birth: str = ""
    age: int | None = None
    abha_id: str = ""


class PrescriptionCreate(BaseModel):
    medication: str = Field(min_length=1)
    dosage: str = ""
    frequency: str = ""
    route: str = ""
    duration: str = ""
    status: str = "active"


class ObservationCreate(BaseModel):
    observation_type: str = Field(min_length=1)
    value: str = ""
    unit: str = ""
    status: str = "final"
    observed_at: str = ""


def db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_database() -> None:
    with db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS encounters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                diagnosis TEXT NOT NULL,
                clinical_notes TEXT NOT NULL DEFAULT '',
                namaste_code TEXT NOT NULL DEFAULT '',
                namaste_term TEXT NOT NULL DEFAULT '',
                namaste_english TEXT NOT NULL DEFAULT '',
                tm2_code TEXT NOT NULL DEFAULT '',
                tm2_term TEXT NOT NULL DEFAULT '',
                tm2_uri TEXT NOT NULL DEFAULT '',
                mapping_class TEXT NOT NULL DEFAULT 'UNMAPPED',
                mapping_status TEXT NOT NULL DEFAULT 'UNMAPPED',
                relationship TEXT NOT NULL DEFAULT '',
                confidence REAL,
                source TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '',
                biomedical_code TEXT NOT NULL DEFAULT '',
                biomedical_term TEXT NOT NULL DEFAULT '',
                short_definition TEXT NOT NULL DEFAULT '',
                long_definition TEXT NOT NULL DEFAULT '',
                namaste_term_diacritical TEXT NOT NULL DEFAULT '',
                namaste_term_devanagari TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER NOT NULL,
                decision TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL,
                FOREIGN KEY (encounter_id) REFERENCES encounters(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS patients (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                gender TEXT NOT NULL DEFAULT '',
                date_of_birth TEXT NOT NULL DEFAULT '',
                age INTEGER,
                abha_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS prescriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER NOT NULL,
                medication TEXT NOT NULL,
                dosage TEXT NOT NULL DEFAULT '',
                frequency TEXT NOT NULL DEFAULT '',
                route TEXT NOT NULL DEFAULT '',
                duration TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                FOREIGN KEY (encounter_id) REFERENCES encounters(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER NOT NULL,
                observation_type TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                unit TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'final',
                observed_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (encounter_id) REFERENCES encounters(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS icd11_namaste_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namaste_code TEXT NOT NULL UNIQUE,
                namaste_term TEXT NOT NULL DEFAULT '',
                namaste_english TEXT NOT NULL DEFAULT '',
                icd11_code TEXT NOT NULL DEFAULT '',
                icd11_term TEXT NOT NULL DEFAULT '',
                icd11_uri TEXT NOT NULL DEFAULT '',
                mapping_class TEXT NOT NULL DEFAULT 'UNMAPPED',
                mapping_status TEXT NOT NULL DEFAULT 'UNMAPPED',
                relationship TEXT NOT NULL DEFAULT '',
                confidence REAL,
                source TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '',
                biomedical_code TEXT NOT NULL DEFAULT '',
                biomedical_term TEXT NOT NULL DEFAULT '',
                short_definition TEXT NOT NULL DEFAULT '',
                long_definition TEXT NOT NULL DEFAULT '',
                namaste_term_diacritical TEXT NOT NULL DEFAULT '',
                namaste_term_devanagari TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_verified TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_namaste_code_unique ON icd11_namaste_mappings(namaste_code)"
        )
        
        migrations = {
            "tm2_uri": "TEXT NOT NULL DEFAULT ''",
            "mapping_status": "TEXT NOT NULL DEFAULT 'UNMAPPED'",
            "relationship": "TEXT NOT NULL DEFAULT ''",
            "version": "TEXT NOT NULL DEFAULT ''",
            "biomedical_code": "TEXT NOT NULL DEFAULT ''",
            "biomedical_term": "TEXT NOT NULL DEFAULT ''",
            "short_definition": "TEXT NOT NULL DEFAULT ''",
            "long_definition": "TEXT NOT NULL DEFAULT ''",
            "namaste_term_diacritical": "TEXT NOT NULL DEFAULT ''",
            "namaste_term_devanagari": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in migrations.items():
            ensure_column(connection, "encounters", column, definition)
        connection.commit()


def load_terminology() -> list[dict[str, str]]:
    if not DATA_FILE.exists():
        raise HTTPException(status_code=500, detail="Terminology dataset is unavailable.")
    with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def format_mapping_for_api(mapping: dict[str, Any]) -> dict[str, Any]:
    """Formats database mapping dict to preserve compatibility with existing frontend keys."""
    return {
        "NAMASTE_CODE": mapping.get("namaste_code", ""),
        "NAMASTE_TERM": mapping.get("namaste_term", ""),
        "NAMASTE_ENGLISH": mapping.get("namaste_english", ""),
        "TM2_CODE": mapping.get("icd11_code", ""),
        "TM2_TERM": mapping.get("icd11_term", ""),
        "TM2_URI": mapping.get("icd11_uri", ""),
        "MAPPING_CLASS": mapping.get("mapping_class", "UNMAPPED"),
        "MAPPING_STATUS": mapping.get("mapping_status", "UNMAPPED"),
        "RELATIONSHIP": mapping.get("relationship", ""),
        "CONFIDENCE": mapping.get("confidence"),
        "SOURCE": mapping.get("source", ""),
        "VERSION": mapping.get("version", ""),
        "BIOMEDICAL_CODE": mapping.get("biomedical_code", ""),
        "BIOMEDICAL_TERM": mapping.get("biomedical_term", ""),
        "SHORT_DEFINITION": mapping.get("short_definition", ""),
        "LONG_DEFINITION": mapping.get("long_definition", ""),
        "NAMASTE_TERM_DIACRITICAL": mapping.get("namaste_term_diacritical", ""),
        "NAMASTE_TERM_DEVANAGARI": mapping.get("namaste_term_devanagari", ""),
        **mapping,
    }


@app.on_event("startup")
def startup() -> None:
    # Attempt to download the database file from the cloud first
    downloaded = download_db(DB_FILE)
    
    initialize_database()
    
    # Seed demo patients if they don't exist
    demo_patients = [
        {"id": "PT-001", "name": "Meera Joshi", "age": 45, "gender": "Female"},
        {"id": "PT-002", "name": "Ramesh Patel", "age": 52, "gender": "Male"},
        {"id": "PT-003", "name": "Anita Verma", "age": 34, "gender": "Female"},
        {"id": "PT-004", "name": "Suresh Kumar", "age": 60, "gender": "Male"},
    ]
    created_at = datetime.now(timezone.utc).isoformat()
    seeded_any = False
    with db_connection() as connection:
        for p in demo_patients:
            existing = connection.execute("SELECT id FROM patients WHERE id = ?", (p["id"],)).fetchone()
            if not existing:
                connection.execute(
                    "INSERT INTO patients (id, name, age, gender, created_at) VALUES (?, ?, ?, ?, ?)",
                    (p["id"], p["name"], p["age"], p["gender"], created_at)
                )
                seeded_any = True
        connection.commit()
        
    # Trigger initial upload if we didn't download it from cloud, or if we seeded new patients
    if not downloaded or seeded_any:
        trigger_upload(DB_FILE)


@app.get("/api/health", tags=["System"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "team-tenacious-interoperability-api", "version": app.version}


@app.get("/api/terminology", tags=["Terminology Mapping"])
def list_terminology(
    limit: int = Query(default=300, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    concepts = load_terminology()
    results = concepts[offset : offset + limit]
    return {
        "count": len(results),
        "total": len(concepts),
        "offset": offset,
        "limit": limit,
        "results": results,
    }


@app.get("/api/mappings/cached", tags=["Terminology Mapping"])
def list_cached_mappings() -> dict[str, Any]:
    """Retrieve all NAMASTE ↔ ICD-11 mappings currently cached in the local database."""
    with db_connection() as connection:
        rows = connection.execute("SELECT * FROM icd11_namaste_mappings ORDER BY id DESC").fetchall()
    results = [format_mapping_for_api(dict(row)) for row in rows]
    return {"count": len(results), "results": results}


@app.get("/api/terminology/search", tags=["Terminology Mapping"])
def search_terminology(
    q: str = Query(min_length=1),
    limit: int = Query(default=12, ge=1, le=50),
) -> dict[str, Any]:
    query = normalize(q)
    results: list[dict[str, Any]] = []
    
    # Try cache / API fallback for exact code or term
    try:
        mapping = get_or_fetch_mapping(q)
        if mapping:
            results.append(format_mapping_for_api(mapping))
    except Exception:
        pass

    searchable_fields = (
        "NAMASTE_PRIMARY_CODE", "NAMASTE_CODE", "NAMASTE_TERM", "NAMASTE_ENGLISH",
        "NAMASTE_TERM_DIACRITICAL", "NAMASTE_TERM_DEVANAGARI", "TM2_CODE", "TM2_TERM",
        "SHORT_DEFINITION", "LONG_DEFINITION", "BIOMEDICAL_CODE", "BIOMEDICAL_TERM", "RELATIONSHIP",
    )
    existing_codes = {r.get("NAMASTE_CODE") or r.get("namaste_code") for r in results if r}
    
    for concept in load_terminology():
        code = concept.get("NAMASTE_CODE")
        if code in existing_codes:
            continue
        if any(query in normalize(concept.get(field)) for field in searchable_fields):
            results.append(concept)
        if len(results) >= limit:
            break
    return {"query": q, "count": len(results), "results": results}


@app.get("/api/terminology/{namaste_code}", tags=["Terminology Mapping"])
def get_terminology(namaste_code: str) -> dict[str, Any]:
    try:
        mapping = get_or_fetch_mapping(namaste_code)
        return format_mapping_for_api(mapping)
    except ICD11MappingNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except ICD11APIError as err:
        raise HTTPException(status_code=502, detail=str(err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {err}")


@app.post("/api/encounters", status_code=201, tags=["Encounters"])
def create_encounter(payload: EncounterCreate) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    with db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO encounters (
                patient_id, diagnosis, clinical_notes, namaste_code, namaste_term, namaste_english,
                tm2_code, tm2_term, tm2_uri, mapping_class, mapping_status, relationship, confidence,
                source, version, biomedical_code, biomedical_term, short_definition, long_definition,
                namaste_term_diacritical, namaste_term_devanagari, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.patient_id, payload.diagnosis, payload.clinical_notes, payload.namaste_code,
                payload.namaste_term, payload.namaste_english, payload.tm2_code, payload.tm2_term,
                payload.tm2_uri, payload.mapping_class, payload.mapping_status, payload.relationship,
                payload.confidence, payload.source, payload.version, payload.biomedical_code,
                payload.biomedical_term, payload.short_definition, payload.long_definition,
                payload.namaste_term_diacritical, payload.namaste_term_devanagari, created_at,
            ),
        )
        encounter_id = cursor.lastrowid
        
        # Save optional prescriptions
        if payload.prescriptions:
            for rx in payload.prescriptions:
                connection.execute(
                    """
                    INSERT INTO prescriptions (
                        encounter_id, medication, dosage, frequency, route, duration, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        encounter_id, 
                        rx.get("medication", ""), 
                        rx.get("dosage", ""), 
                        rx.get("frequency", ""), 
                        rx.get("route", ""), 
                        rx.get("duration", ""), 
                        rx.get("status", "active"), 
                        created_at
                    )
                )
                
        # Save optional observations
        if payload.observations:
            for obs in payload.observations:
                connection.execute(
                    """
                    INSERT INTO observations (
                        encounter_id, observation_type, value, unit, status, observed_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        encounter_id, 
                        obs.get("observation_type", ""), 
                        obs.get("value", ""), 
                        obs.get("unit", ""), 
                        obs.get("status", "final"), 
                        obs.get("observed_at", ""), 
                        created_at
                    )
                )
                
        connection.commit()
    trigger_upload(DB_FILE)
    return {"id": encounter_id, "status": "created", "created_at": created_at}


@app.get("/api/encounters", tags=["Encounters"])
def list_encounters(patient_id: str | None = None) -> dict[str, Any]:
    with db_connection() as connection:
        if patient_id:
            rows = connection.execute("SELECT * FROM encounters WHERE patient_id = ? ORDER BY id DESC", (patient_id,)).fetchall()
        else:
            rows = connection.execute("SELECT * FROM encounters ORDER BY id DESC").fetchall()
    return {"count": len(rows), "results": [dict(row) for row in rows]}


@app.get("/api/encounters/{encounter_id}", tags=["Encounters"])
def get_encounter(encounter_id: int) -> dict[str, Any]:
    with db_connection() as connection:
        row = connection.execute("SELECT * FROM encounters WHERE id = ?", (encounter_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Encounter not found.")
    return dict(row)


@app.get("/api/encounters/{encounter_id}/fhir", tags=["FHIR Interoperability"])
def get_encounter_fhir_bundle(encounter_id: int) -> dict[str, Any]:
    """Generate a FHIR R4 Bundle for the specified clinical encounter."""
    with db_connection() as connection:
        encounter = connection.execute("SELECT * FROM encounters WHERE id = ?", (encounter_id,)).fetchone()
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found.")
        encounter_dict = dict(encounter)
        
        patient = connection.execute("SELECT * FROM patients WHERE id = ?", (encounter_dict["patient_id"],)).fetchone()
        if not patient:
            # Fallback to minimal patient dict if missing (shouldn't happen with seeded data)
            patient_dict = {"id": encounter_dict["patient_id"], "name": f"Patient {encounter_dict['patient_id']}"}
        else:
            patient_dict = dict(patient)
            
        prescriptions = connection.execute("SELECT * FROM prescriptions WHERE encounter_id = ?", (encounter_id,)).fetchall()
        observations = connection.execute("SELECT * FROM observations WHERE encounter_id = ?", (encounter_id,)).fetchall()
        
    mapping_data = get_mapping_from_db(encounter_dict.get("namaste_code", ""))
    
    return build_fhir_bundle(
        patient=patient_dict,
        encounter=encounter_dict,
        mapping=mapping_data,
        prescriptions=[dict(rx) for rx in prescriptions] if prescriptions else None,
        observations=[dict(obs) for obs in observations] if observations else None,
    )


@app.post("/api/patients", status_code=201, tags=["Patients"])
def create_patient(payload: PatientCreate) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO patients (id, name, gender, date_of_birth, age, abha_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, gender=excluded.gender, date_of_birth=excluded.date_of_birth,
                age=excluded.age, abha_id=excluded.abha_id
            """,
            (payload.id, payload.name, payload.gender, payload.date_of_birth, payload.age, payload.abha_id, created_at)
        )
        connection.commit()
    trigger_upload(DB_FILE)
    return {"id": payload.id, "status": "saved"}


@app.get("/api/patients", tags=["Patients"])
def list_patients() -> dict[str, Any]:
    with db_connection() as connection:
        rows = connection.execute("SELECT * FROM patients ORDER BY name").fetchall()
    return {"count": len(rows), "results": [dict(row) for row in rows]}


@app.get("/api/patients/{patient_id}", tags=["Patients"])
def get_patient(patient_id: str) -> dict[str, Any]:
    with db_connection() as connection:
        row = connection.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return dict(row)


@app.post("/api/encounters/{encounter_id}/prescriptions", status_code=201, tags=["Encounters"])
def create_prescription(encounter_id: int, payload: PrescriptionCreate) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    with db_connection() as connection:
        encounter = connection.execute("SELECT id FROM encounters WHERE id = ?", (encounter_id,)).fetchone()
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found.")
        
        cursor = connection.execute(
            """
            INSERT INTO prescriptions (
                encounter_id, medication, dosage, frequency, route, duration, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (encounter_id, payload.medication, payload.dosage, payload.frequency, payload.route, payload.duration, payload.status, created_at)
        )
        connection.commit()
    trigger_upload(DB_FILE)
    return {"id": cursor.lastrowid, "status": "created"}


@app.post("/api/encounters/{encounter_id}/observations", status_code=201, tags=["Encounters"])
def create_observation(encounter_id: int, payload: ObservationCreate) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    with db_connection() as connection:
        encounter = connection.execute("SELECT id FROM encounters WHERE id = ?", (encounter_id,)).fetchone()
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found.")
        
        cursor = connection.execute(
            """
            INSERT INTO observations (
                encounter_id, observation_type, value, unit, status, observed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (encounter_id, payload.observation_type, payload.value, payload.unit, payload.status, payload.observed_at, created_at)
        )
        connection.commit()
    trigger_upload(DB_FILE)
    return {"id": cursor.lastrowid, "status": "created"}


@app.post("/api/reviews", status_code=201, tags=["Human Review"])
def create_review(payload: ReviewCreate) -> dict[str, Any]:
    reviewed_at = datetime.now(timezone.utc).isoformat()
    with db_connection() as connection:
        encounter = connection.execute("SELECT id FROM encounters WHERE id = ?", (payload.encounter_id,)).fetchone()
        if encounter is None:
            raise HTTPException(status_code=404, detail="Encounter not found.")
        cursor = connection.execute(
            "INSERT INTO reviews (encounter_id, decision, reviewer, notes, reviewed_at) VALUES (?, ?, ?, ?, ?)",
            (payload.encounter_id, payload.decision, payload.reviewer, payload.notes, reviewed_at),
        )
        connection.commit()
    trigger_upload(DB_FILE)
    return {"id": cursor.lastrowid, "status": "recorded", "reviewed_at": reviewed_at}


def review_query(select: str, where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with db_connection() as connection:
        rows = connection.execute(
            f"""
            {select}
            FROM encounters e
            LEFT JOIN reviews r ON r.id = (
                SELECT r2.id FROM reviews r2
                WHERE r2.encounter_id = e.id
                ORDER BY r2.id DESC LIMIT 1
            )
            {where}
            ORDER BY e.id DESC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


REVIEWABLE_SQL = "e.mapping_class IN ('FOUNDATION_CONCEPT_ONLY', 'UNMAPPED')"
REVIEWED_SQL = "r.decision IN ('APPROVED', 'REJECTED')"
PENDING_SQL = f"({REVIEWABLE_SQL}) AND (r.id IS NULL OR r.decision = 'REVIEW')"

REVIEW_SELECT = """
SELECT e.*, r.id AS review_id, r.decision AS review_decision,
       r.reviewer AS review_reviewer, r.notes AS review_notes,
       r.reviewed_at AS review_reviewed_at
"""


@app.get("/api/reviews/pending", tags=["Human Review"])
def list_pending_reviews() -> dict[str, Any]:
    results = review_query(REVIEW_SELECT, f"WHERE {PENDING_SQL}")
    return {"count": len(results), "results": results}


@app.get("/api/reviews", tags=["Human Review"])
def list_reviews() -> dict[str, Any]:
    results = review_query(REVIEW_SELECT, f"WHERE {REVIEWABLE_SQL} AND {REVIEWED_SQL}")
    return {"count": len(results), "results": results}


@app.post("/api/demo/reset", tags=["Demo & Administration"])
def reset_demo_data() -> dict[str, Any]:
    """Clear all locally stored encounter and review records for a clean demo state."""
    with db_connection() as connection:
        review_count = connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        encounter_count = connection.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]
        connection.execute("DELETE FROM reviews")
        connection.execute("DELETE FROM encounters")
        connection.execute("DELETE FROM sqlite_sequence WHERE name IN ('reviews', 'encounters')")
        connection.commit()
    trigger_upload(DB_FILE)
    return {
        "status": "reset",
        "deleted_reviews": review_count,
        "deleted_encounters": encounter_count,
        "message": "All locally stored encounter and review records were removed. Terminology source data was not modified.",
    }


@app.get("/api/analytics/summary", tags=["Analytics"])
def analytics_summary() -> dict[str, Any]:
    with db_connection() as connection:
        total = connection.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]
        mapping_rows = connection.execute(
            "SELECT mapping_class, COUNT(*) AS count FROM encounters GROUP BY mapping_class"
        ).fetchall()
        review_rows = connection.execute(
            """
            SELECT r.decision, COUNT(*) AS count
            FROM reviews r
            JOIN (
                SELECT encounter_id, MAX(id) AS latest_id
                FROM reviews
                GROUP BY encounter_id
            ) latest ON latest.latest_id = r.id
            GROUP BY r.decision
            """
        ).fetchall()
        pending = connection.execute(
            f"""
            SELECT COUNT(*) FROM encounters e
            LEFT JOIN reviews r ON r.id = (
                SELECT r2.id FROM reviews r2
                WHERE r2.encounter_id = e.id
                ORDER BY r2.id DESC LIMIT 1
            )
            WHERE {PENDING_SQL}
            """
        ).fetchone()[0]

    mapping = {row["mapping_class"]: row["count"] for row in mapping_rows}
    reviews = {row["decision"]: row["count"] for row in review_rows}
    mapped = mapping.get("DIRECT_CODE_ALIGNMENT", 0) + mapping.get("CROSS_CODE_MAPPING", 0)

    return {
        "total_encounters": total,
        "mapped_encounters": mapped,
        "mapped_rate": round((mapped / total) * 100, 1) if total else 0,
        "review_required": pending,
        "mapping_distribution": {
            "DIRECT_CODE_ALIGNMENT": mapping.get("DIRECT_CODE_ALIGNMENT", 0),
            "CROSS_CODE_MAPPING": mapping.get("CROSS_CODE_MAPPING", 0),
            "FOUNDATION_CONCEPT_ONLY": mapping.get("FOUNDATION_CONCEPT_ONLY", 0),
            "UNMAPPED": mapping.get("UNMAPPED", 0),
        },
        "review_distribution": {
            "PENDING": pending,
            "APPROVED": reviews.get("APPROVED", 0),
            "REJECTED": reviews.get("REJECTED", 0),
            "REVIEW": reviews.get("REVIEW", 0),
        },
    }
