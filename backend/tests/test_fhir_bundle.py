from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, DB_FILE, initialize_database
from app.mapping_service import save_mapping_to_db

@pytest.fixture(autouse=True)
def setup_test_db():
    initialize_database()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM icd11_namaste_mappings")
        conn.execute("DELETE FROM encounters")
        conn.execute("DELETE FROM patients")
        conn.execute("DELETE FROM prescriptions")
        conn.execute("DELETE FROM observations")
        
        # Seed test patient
        created_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO patients (id, name, gender, age, created_at) VALUES (?, ?, ?, ?, ?)",
            ("TEST-PT-1", "Test Patient", "Female", 30, created_at)
        )
        conn.commit()
    yield
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM icd11_namaste_mappings")
        conn.execute("DELETE FROM encounters")
        conn.execute("DELETE FROM patients")
        conn.execute("DELETE FROM prescriptions")
        conn.execute("DELETE FROM observations")
        conn.commit()

@pytest.fixture
def client():
    return TestClient(app)

def create_test_encounter(client, diagnosis="Test Diagnosis", namaste_code="T01", tm2_code="TM2-01"):
    # Add mapping to DB first so FHIR generation finds it
    mapping = {
        "namaste_code": namaste_code,
        "namaste_term": diagnosis,
        "namaste_english": diagnosis,
        "icd11_code": tm2_code,
        "icd11_term": f"TM2 {diagnosis}",
        "mapping_class": "CROSS_CODE_MAPPING",
        "biomedical_code": "BIO-01" if tm2_code else ""
    }
    save_mapping_to_db(mapping)
    
    response = client.post(
        "/api/encounters",
        json={
            "patient_id": "TEST-PT-1",
            "diagnosis": diagnosis,
            "namaste_code": namaste_code,
            "namaste_english": diagnosis,
            "tm2_code": tm2_code,
            "mapping_class": "CROSS_CODE_MAPPING" if tm2_code else "UNMAPPED",
            "biomedical_code": "BIO-01" if tm2_code else ""
        }
    )
    return response.json()["id"]

def test_1_valid_fhir_bundle(client):
    """TEST 1: Patient + Encounter + Condition → valid FHIR Bundle."""
    enc_id = create_test_encounter(client)
    
    response = client.get(f"/api/encounters/{enc_id}/fhir")
    assert response.status_code == 200
    bundle = response.json()
    
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert "entry" in bundle
    
    resource_types = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
    assert "Patient" in resource_types
    assert "Encounter" in resource_types
    assert "Condition" in resource_types
    
    # Check that there are no validation warnings
    assert "_validation_warnings" not in bundle

def test_2_condition_with_valid_mapping(client):
    """TEST 2: Condition with valid NAMASTE → ICD-11 mapping → all applicable coding represented correctly."""
    enc_id = create_test_encounter(client)
    
    response = client.get(f"/api/encounters/{enc_id}/fhir")
    bundle = response.json()
    
    condition = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Condition")
    codings = condition["code"]["coding"]
    
    systems = [c.get("system") for c in codings]
    assert "https://namaste.ayush.gov.in/terminology" in systems
    assert "http://id.who.int/icd/release/11/2026-01/mms" in systems
    assert "http://id.who.int/icd/entity" in systems # Biomedical code was added in fixture

def test_3_namaste_concept_no_icd11_mapping(client):
    """TEST 3: NAMASTE concept with no ICD-11 mapping → NAMASTE remains in Condition and no fake ICD-11 code is generated."""
    enc_id = create_test_encounter(client, tm2_code="")
    
    response = client.get(f"/api/encounters/{enc_id}/fhir")
    bundle = response.json()
    
    condition = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Condition")
    codings = condition["code"]["coding"]
    
    systems = [c.get("system") for c in codings]
    assert "https://namaste.ayush.gov.in/terminology" in systems
    assert "http://id.who.int/icd/release/11/2026-01/mms" not in systems
    assert len(codings) == 1

def test_4_prescription_generates_medication_request(client):
    """TEST 4: Prescription exists → MedicationRequest is generated."""
    enc_id = create_test_encounter(client)
    
    # Add prescription
    client.post(
        f"/api/encounters/{enc_id}/prescriptions",
        json={"medication": "Aspirin", "dosage": "100mg", "frequency": "Once daily"}
    )
    
    response = client.get(f"/api/encounters/{enc_id}/fhir")
    bundle = response.json()
    
    resource_types = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
    assert "MedicationRequest" in resource_types

def test_5_lab_result_generates_observation(client):
    """TEST 5: Lab result exists → Observation is generated."""
    enc_id = create_test_encounter(client)
    
    # Add observation
    client.post(
        f"/api/encounters/{enc_id}/observations",
        json={"observation_type": "Blood Pressure", "value": "120/80", "unit": "mmHg"}
    )
    
    response = client.get(f"/api/encounters/{enc_id}/fhir")
    bundle = response.json()
    
    resource_types = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
    assert "Observation" in resource_types

def test_6_empty_clinical_resources_not_generated(client):
    """TEST 6: No prescription/lab → corresponding resources are not unnecessarily generated."""
    enc_id = create_test_encounter(client)
    
    response = client.get(f"/api/encounters/{enc_id}/fhir")
    bundle = response.json()
    
    resource_types = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
    assert "MedicationRequest" not in resource_types
    assert "Observation" not in resource_types

def test_7_references_correct(client):
    """TEST 7: Multiple resources reference the correct Patient."""
    enc_id = create_test_encounter(client)
    
    # Add extras
    client.post(
        f"/api/encounters/{enc_id}/prescriptions",
        json={"medication": "Aspirin"}
    )
    client.post(
        f"/api/encounters/{enc_id}/observations",
        json={"observation_type": "Heart Rate", "value": "72"}
    )
    
    response = client.get(f"/api/encounters/{enc_id}/fhir")
    bundle = response.json()
    
    # Find patient fullUrl
    patient_entry = next(e for e in bundle["entry"] if e["resource"]["resourceType"] == "Patient")
    patient_url = patient_entry["fullUrl"]
    
    # Check all other resources reference this URL
    for entry in bundle["entry"]:
        resource = entry["resource"]
        if resource["resourceType"] != "Patient":
            assert resource["subject"]["reference"] == patient_url

def test_8_bundle_contains_only_valid_resources(client):
    """TEST 8: FHIR Bundle contains only valid/relevant resources."""
    enc_id = create_test_encounter(client)
    response = client.get(f"/api/encounters/{enc_id}/fhir")
    bundle = response.json()
    assert "_validation_warnings" not in bundle

def test_9_existing_mapping_works_unchanged(client):
    """TEST 9: Existing mapping-cache behavior continues to work."""
    # This just ensures we didn't break the existing terminology search API
    api_return_value = {
        "namaste_code": "TEST-FHIR-01",
        "namaste_term": "Test Term FHIR",
        "icd11_code": "TM2-FHIR",
        "mapping_class": "CROSS_CODE_MAPPING",
    }

    with patch("app.mapping_service.fetch_icd11_mapping_from_api", return_value=api_return_value) as mock_api:
        response = client.get("/api/terminology/TEST-FHIR-01")
        assert response.status_code == 200
        data = response.json()
        assert data["NAMASTE_CODE"] == "TEST-FHIR-01"
