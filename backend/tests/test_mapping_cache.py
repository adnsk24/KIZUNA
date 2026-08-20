from __future__ import annotations

import sqlite3
import threading
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app, DB_FILE, initialize_database
from app.mapping_service import get_mapping_from_db, save_mapping_to_db, get_or_fetch_mapping
from app.icd11_client import ICD11APIError, ICD11MappingNotFoundError


@pytest.fixture(autouse=True)
def setup_test_db():
    """Ensure clean test environment before each test."""
    initialize_database()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM icd11_namaste_mappings")
        conn.commit()
    yield
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM icd11_namaste_mappings")
        conn.commit()


@pytest.fixture
def client():
    return TestClient(app)


def test_case_a_mapping_exists_in_database(client):
    """
    Test Case A: Mapping exists in database.
    - Database mapping is returned.
    - ICD-11 API is NOT called.
    """
    # Pre-populate database with a mapping
    sample_mapping = {
        "namaste_code": "TEST-A01",
        "namaste_term": "Test Term A",
        "namaste_english": "Test Term English A",
        "icd11_code": "TM2-A01",
        "icd11_term": "Test ICD11 Term A",
        "icd11_uri": "http://id.who.int/icd/entity/12345",
        "mapping_class": "CROSS_CODE_MAPPING",
        "confidence": 0.95,
        "source": "Cached Source",
        "version": "V1",
    }
    save_mapping_to_db(sample_mapping)

    with patch("app.mapping_service.fetch_icd11_mapping_from_api") as mock_api:
        response = client.get("/api/terminology/TEST-A01")
        assert response.status_code == 200
        data = response.json()
        
        # Verify returned data came from database
        assert data["NAMASTE_CODE"] == "TEST-A01"
        assert data["TM2_CODE"] == "TM2-A01"
        
        # Verify API was NOT called
        mock_api.assert_not_called()


def test_case_b_mapping_does_not_exist_in_db_fetches_and_saves(client):
    """
    Test Case B: Mapping does not exist in database.
    - ICD-11 API is called.
    - Successful mapping is saved.
    - Mapping is returned.
    """
    api_return_value = {
        "namaste_code": "TEST-B01",
        "namaste_term": "Test Term B",
        "namaste_english": "Test English B",
        "icd11_code": "TM2-B01",
        "icd11_term": "Test ICD11 B",
        "icd11_uri": "http://id.who.int/icd/entity/67890",
        "mapping_class": "CROSS_CODE_MAPPING",
        "mapping_status": "TM2_MAPPED",
        "relationship": "EXACT",
        "confidence": 0.88,
        "source": "External ICD-11 API",
        "version": "2026-01",
    }

    with patch("app.mapping_service.fetch_icd11_mapping_from_api", return_value=api_return_value) as mock_api:
        response = client.get("/api/terminology/TEST-B01")
        assert response.status_code == 200
        data = response.json()

        # Verify API was called
        mock_api.assert_called_once_with("TEST-B01")
        assert data["NAMASTE_CODE"] == "TEST-B01"
        assert data["TM2_CODE"] == "TM2-B01"

        # Verify record was saved to database
        db_record = get_mapping_from_db("TEST-B01")
        assert db_record is not None
        assert db_record["namaste_code"] == "TEST-B01"
        assert db_record["icd11_code"] == "TM2-B01"


def test_case_c_api_fails_no_invalid_mapping_saved(client):
    """
    Test Case C: Mapping does not exist and ICD-11 API fails.
    - No invalid mapping is saved in DB.
    - Appropriate error is returned.
    """
    with patch("app.mapping_service.fetch_icd11_mapping_from_api", side_effect=ICD11APIError("External API standard 500 error")):
        response = client.get("/api/terminology/TEST-C01")
        assert response.status_code == 502
        assert "External API standard 500 error" in response.json()["detail"]

        # Verify nothing was saved to database
        db_record = get_mapping_from_db("TEST-C01")
        assert db_record is None


def test_case_d_repeated_search_does_not_create_duplicates(client):
    """
    Test Case D: Mapping already exists.
    - Repeated search does not create duplicate records.
    """
    # First request fetches and saves
    client.get("/api/terminology/AAB-53")

    with sqlite3.connect(DB_FILE) as conn:
        count_first = conn.execute("SELECT COUNT(*) FROM icd11_namaste_mappings WHERE UPPER(namaste_code) = 'AAB-53'").fetchone()[0]
    assert count_first == 1

    # Second request
    client.get("/api/terminology/AAB-53")

    with sqlite3.connect(DB_FILE) as conn:
        count_second = conn.execute("SELECT COUNT(*) FROM icd11_namaste_mappings WHERE UPPER(namaste_code) = 'AAB-53'").fetchone()[0]
    assert count_second == 1


def test_case_e_simultaneous_concurrent_requests():
    """
    Test Case E: Two simultaneous requests for the same new mapping.
    - Database constraints/logic prevent duplicate mappings.
    """
    api_data = {
        "namaste_code": "CONCUR-01",
        "namaste_term": "Concurrent Term",
        "namaste_english": "Concurrent English",
        "icd11_code": "TM2-CONCUR",
        "icd11_term": "Concurrent ICD11",
        "mapping_class": "CROSS_CODE_MAPPING",
    }

    exceptions = []

    def fetch_and_save():
        try:
            with patch("app.mapping_service.fetch_icd11_mapping_from_api", return_value=api_data):
                get_or_fetch_mapping("CONCUR-01")
        except Exception as e:
            exceptions.append(e)

    t1 = threading.Thread(target=fetch_and_save)
    t2 = threading.Thread(target=fetch_and_save)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # Neither thread should throw unhandled database integrity error
    assert len(exceptions) == 0

    with sqlite3.connect(DB_FILE) as conn:
        count = conn.execute("SELECT COUNT(*) FROM icd11_namaste_mappings WHERE UPPER(namaste_code) = 'CONCUR-01'").fetchone()[0]
    assert count == 1


def test_case_f_invalid_api_response_not_cached(client):
    """
    Test Case F: API returns no valid mapping / not found.
    - Do not cache invalid/empty data.
    """
    with patch("app.mapping_service.fetch_icd11_mapping_from_api", side_effect=ICD11MappingNotFoundError("No ICD-11 mapping found for 'NONEXISTENT-999'.")):
        response = client.get("/api/terminology/NONEXISTENT-999")
        assert response.status_code == 404

        # Verify DB remains empty for this code
        db_record = get_mapping_from_db("NONEXISTENT-999")
        assert db_record is None
