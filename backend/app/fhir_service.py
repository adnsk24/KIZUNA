"""
FHIR R4 resource generation for the KIZUNA AYUSH EMR interoperability prototype.

This module converts internal EMR data (encounters, patients, mappings, prescriptions,
observations) into FHIR R4-compliant JSON resources. It does NOT replace the database —
FHIR is the interoperability representation layer only.

FHIR version: R4 (4.0.1)
Spec: https://hl7.org/fhir/R4/

ABDM/NHA Gap Notes:
- No ABDM-specific structural definitions are configured; using generic FHIR R4.
- No ABHA integration; Patient identifier uses internal EMR ID only.
- No Consent resource; the application has no consent workflow.
- No digital signatures; Bundles are unsigned.
- Practitioner resource not generated; no practitioner table exists.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("kizuna.fhir_service")

# ---------------------------------------------------------------------------
# Coding system URIs
# ---------------------------------------------------------------------------
NAMASTE_SYSTEM = "https://namaste.ayush.gov.in/terminology"
ICD11_TM2_SYSTEM = "http://id.who.int/icd/release/11/2026-01/mms"
ICD11_FOUNDATION_SYSTEM = "http://id.who.int/icd/entity"
ABHA_SYSTEM = "https://healthid.abdm.gov.in/"
KIZUNA_ENCOUNTER_SYSTEM = "https://kizuna.ayush.gov.in/encounter"
KIZUNA_PATIENT_SYSTEM = "https://kizuna.ayush.gov.in/patient"
KIZUNA_MAPPING_EXT_BASE = "https://kizuna.ayush.gov.in/fhir/StructureDefinition"


def _uuid() -> str:
    """Generate a new UUID URN for FHIR resource fullUrl."""
    return f"urn:uuid:{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# Individual resource builders
# ---------------------------------------------------------------------------


def build_fhir_patient(patient: dict[str, Any]) -> dict[str, Any]:
    """
    Build a FHIR R4 Patient resource from internal patient data.

    Required fields in ``patient``: id, name.
    Optional fields: gender, date_of_birth, age, abha_id.
    """
    resource: dict[str, Any] = {
        "resourceType": "Patient",
        "identifier": [
            {
                "system": KIZUNA_PATIENT_SYSTEM,
                "value": str(patient.get("id", "")),
            }
        ],
    }

    # ABHA identifier — only if available
    abha_id = patient.get("abha_id", "")
    if abha_id:
        resource["identifier"].append(
            {
                "system": ABHA_SYSTEM,
                "value": abha_id,
            }
        )

    # Name
    name = patient.get("name", "")
    if name:
        parts = name.strip().split()
        name_entry: dict[str, Any] = {"use": "official", "text": name}
        if len(parts) >= 2:
            name_entry["family"] = parts[-1]
            name_entry["given"] = parts[:-1]
        elif len(parts) == 1:
            name_entry["given"] = parts
        resource["name"] = [name_entry]

    # Gender
    gender_raw = str(patient.get("gender", "")).strip().lower()
    gender_map = {"male": "male", "female": "female", "other": "other", "m": "male", "f": "female"}
    fhir_gender = gender_map.get(gender_raw)
    if fhir_gender:
        resource["gender"] = fhir_gender

    # Date of birth
    dob = patient.get("date_of_birth", "")
    if dob:
        resource["birthDate"] = str(dob)

    return resource


def build_fhir_encounter(
    encounter: dict[str, Any],
    patient_ref: str,
) -> dict[str, Any]:
    """
    Build a FHIR R4 Encounter resource from an internal encounter row.

    ``patient_ref`` should be the Bundle-internal Patient fullUrl (urn:uuid:...).
    """
    resource: dict[str, Any] = {
        "resourceType": "Encounter",
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "AMB",
            "display": "ambulatory",
        },
        "identifier": [
            {
                "system": KIZUNA_ENCOUNTER_SYSTEM,
                "value": str(encounter.get("id", "")),
            }
        ],
        "subject": {"reference": patient_ref},
    }

    # Encounter type
    resource["type"] = [
        {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": "185349003",
                    "display": "Encounter for check up",
                }
            ],
            "text": "AYUSH clinical encounter",
        }
    ]

    # Period
    created_at = encounter.get("created_at", "")
    if created_at:
        resource["period"] = {"start": created_at}

    return resource


def build_fhir_condition(
    encounter: dict[str, Any],
    mapping: dict[str, Any] | None,
    patient_ref: str,
    encounter_ref: str,
) -> dict[str, Any]:
    """
    Build a FHIR R4 Condition resource representing the AYUSH diagnosis.

    The Condition always includes the original NAMASTE coding. ICD-11 TM2 and
    biomedical/foundation codes are added ONLY if the mapping data actually contains them.
    No codes are invented.

    Mapping metadata (status, relationship, confidence, source, version, last_verified)
    is represented as FHIR extensions when available.
    """
    coding: list[dict[str, Any]] = []

    # --- NAMASTE coding (always present if code exists) ---
    namaste_code = (
        encounter.get("namaste_code")
        or (mapping.get("namaste_code") if mapping else "")
        or ""
    )
    namaste_term = (
        encounter.get("namaste_english")
        or encounter.get("namaste_term")
        or (mapping.get("namaste_english") if mapping else "")
        or (mapping.get("namaste_term") if mapping else "")
        or ""
    )
    if namaste_code:
        coding.append(
            {
                "system": NAMASTE_SYSTEM,
                "code": namaste_code,
                "display": namaste_term or namaste_code,
            }
        )

    # --- ICD-11 TM2 coding (only if actually mapped) ---
    tm2_code = encounter.get("tm2_code") or (mapping.get("icd11_code") if mapping else "") or ""
    tm2_term = encounter.get("tm2_term") or (mapping.get("icd11_term") if mapping else "") or ""
    tm2_uri = encounter.get("tm2_uri") or (mapping.get("icd11_uri") if mapping else "") or ""

    if tm2_code:
        tm2_entry: dict[str, Any] = {
            "system": ICD11_TM2_SYSTEM,
            "code": tm2_code,
        }
        if tm2_term:
            tm2_entry["display"] = tm2_term
        coding.append(tm2_entry)

    # --- ICD-11 Biomedicine / Foundation coding (only if present) ---
    bio_code = (
        encounter.get("biomedical_code")
        or (mapping.get("biomedical_code") if mapping else "")
        or ""
    )
    bio_term = (
        encounter.get("biomedical_term")
        or (mapping.get("biomedical_term") if mapping else "")
        or ""
    )
    if bio_code:
        bio_entry: dict[str, Any] = {
            "system": ICD11_FOUNDATION_SYSTEM,
            "code": bio_code,
        }
        if bio_term:
            bio_entry["display"] = bio_term
        coding.append(bio_entry)

    # Build the Condition resource
    resource: dict[str, Any] = {
        "resourceType": "Condition",
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }
            ]
        },
        "verificationStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                    "code": "confirmed",
                }
            ]
        },
        "subject": {"reference": patient_ref},
    }

    if encounter_ref:
        resource["encounter"] = {"reference": encounter_ref}

    if coding:
        resource["code"] = {
            "coding": coding,
            "text": encounter.get("diagnosis", namaste_term or ""),
        }

    # Record date
    created_at = encounter.get("created_at", "")
    if created_at:
        resource["recordedDate"] = created_at

    # Clinical notes
    clinical_notes = encounter.get("clinical_notes", "")
    if clinical_notes:
        resource["note"] = [{"text": clinical_notes}]

    # --- Mapping metadata as extensions ---
    extensions = _build_mapping_extensions(encounter, mapping)
    if extensions:
        resource["extension"] = extensions

    return resource


def _build_mapping_extensions(
    encounter: dict[str, Any],
    mapping: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Build FHIR extensions for mapping metadata that has an appropriate
    FHIR representation. Only includes data that actually exists.
    """
    extensions: list[dict[str, Any]] = []

    def _val(key: str) -> str:
        return str(
            encounter.get(key)
            or (mapping.get(key) if mapping else "")
            or ""
        ).strip()

    mapping_status = _val("mapping_status") or _val("mapping_class")
    if mapping_status:
        extensions.append(
            {
                "url": f"{KIZUNA_MAPPING_EXT_BASE}/mapping-status",
                "valueString": mapping_status,
            }
        )

    relationship = _val("relationship")
    if relationship:
        extensions.append(
            {
                "url": f"{KIZUNA_MAPPING_EXT_BASE}/mapping-relationship",
                "valueString": relationship,
            }
        )

    # Confidence
    confidence = encounter.get("confidence")
    if confidence is None and mapping:
        confidence = mapping.get("confidence")
    if confidence is not None and confidence != "":
        try:
            extensions.append(
                {
                    "url": f"{KIZUNA_MAPPING_EXT_BASE}/mapping-confidence",
                    "valueDecimal": round(float(confidence), 6),
                }
            )
        except (ValueError, TypeError):
            pass

    source = _val("source")
    if source:
        extensions.append(
            {
                "url": f"{KIZUNA_MAPPING_EXT_BASE}/mapping-source",
                "valueString": source,
            }
        )

    version = _val("version")
    if version:
        extensions.append(
            {
                "url": f"{KIZUNA_MAPPING_EXT_BASE}/mapping-version",
                "valueString": version,
            }
        )

    # last_verified — only available in mapping cache table
    last_verified = (mapping.get("last_verified") if mapping else "") or ""
    if last_verified:
        extensions.append(
            {
                "url": f"{KIZUNA_MAPPING_EXT_BASE}/mapping-last-verified",
                "valueDateTime": last_verified,
            }
        )

    return extensions


def build_fhir_medication_request(
    prescription: dict[str, Any],
    patient_ref: str,
    encounter_ref: str,
) -> dict[str, Any]:
    """
    Build a FHIR R4 MedicationRequest from a prescription row.

    Only called when a prescription actually exists.
    """
    medication = prescription.get("medication", "")
    if not medication:
        return {}

    resource: dict[str, Any] = {
        "resourceType": "MedicationRequest",
        "status": prescription.get("status", "active"),
        "intent": "order",
        "subject": {"reference": patient_ref},
        "encounter": {"reference": encounter_ref},
        "medicationCodeableConcept": {
            "text": medication,
        },
    }

    # Dosage instruction
    dosage_parts: dict[str, Any] = {}
    dosage_text_parts: list[str] = []

    dosage = prescription.get("dosage", "")
    if dosage:
        dosage_text_parts.append(dosage)

    frequency = prescription.get("frequency", "")
    if frequency:
        dosage_text_parts.append(frequency)

    route = prescription.get("route", "")
    if route:
        dosage_parts["route"] = {"text": route}
        dosage_text_parts.append(f"via {route}")

    duration = prescription.get("duration", "")
    if duration:
        dosage_text_parts.append(f"for {duration}")

    if dosage_text_parts:
        dosage_parts["text"] = " — ".join(dosage_text_parts)

    if dosage_parts:
        resource["dosageInstruction"] = [dosage_parts]

    # Authored on
    created_at = prescription.get("created_at", "")
    if created_at:
        resource["authoredOn"] = created_at

    return resource


def build_fhir_observation(
    observation: dict[str, Any],
    patient_ref: str,
    encounter_ref: str,
) -> dict[str, Any]:
    """
    Build a FHIR R4 Observation from an observation/lab-result row.

    Only called when an observation actually exists.
    """
    obs_type = observation.get("observation_type", "")
    if not obs_type:
        return {}

    resource: dict[str, Any] = {
        "resourceType": "Observation",
        "status": observation.get("status", "final"),
        "subject": {"reference": patient_ref},
        "encounter": {"reference": encounter_ref},
        "code": {
            "text": obs_type,
        },
    }

    # Value
    value = observation.get("value", "")
    unit = observation.get("unit", "")
    if value:
        try:
            numeric_value = float(value)
            quantity: dict[str, Any] = {"value": numeric_value}
            if unit:
                quantity["unit"] = unit
            resource["valueQuantity"] = quantity
        except (ValueError, TypeError):
            resource["valueString"] = str(value)
            if unit:
                resource["valueString"] += f" {unit}"

    # Effective date
    observed_at = observation.get("observed_at", "")
    if observed_at:
        resource["effectiveDateTime"] = observed_at
    else:
        created_at = observation.get("created_at", "")
        if created_at:
            resource["effectiveDateTime"] = created_at

    return resource


# ---------------------------------------------------------------------------
# Bundle assembly
# ---------------------------------------------------------------------------


def build_fhir_bundle(
    patient: dict[str, Any],
    encounter: dict[str, Any],
    mapping: dict[str, Any] | None,
    prescriptions: list[dict[str, Any]] | None = None,
    observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Assemble a complete FHIR R4 Bundle (type: collection) for a clinical encounter.

    The Bundle contains:
    - Patient (always)
    - Encounter (always)
    - Condition (always, with available coding)
    - MedicationRequest(s) (only if prescriptions exist)
    - Observation(s) (only if observations exist)

    Resources reference each other via urn:uuid: references.
    """
    entries: list[dict[str, Any]] = []

    # 1. Patient
    patient_url = _uuid()
    patient_resource = build_fhir_patient(patient)
    entries.append({"fullUrl": patient_url, "resource": patient_resource})

    # 2. Encounter
    encounter_url = _uuid()
    encounter_resource = build_fhir_encounter(encounter, patient_url)
    entries.append({"fullUrl": encounter_url, "resource": encounter_resource})

    # 3. Condition
    condition_url = _uuid()
    condition_resource = build_fhir_condition(
        encounter, mapping, patient_url, encounter_url
    )
    entries.append({"fullUrl": condition_url, "resource": condition_resource})

    # 4. MedicationRequest(s) — only if prescriptions exist
    if prescriptions:
        for rx in prescriptions:
            med_resource = build_fhir_medication_request(rx, patient_url, encounter_url)
            if med_resource:
                entries.append({"fullUrl": _uuid(), "resource": med_resource})

    # 5. Observation(s) — only if observations exist
    if observations:
        for obs in observations:
            obs_resource = build_fhir_observation(obs, patient_url, encounter_url)
            if obs_resource:
                entries.append({"fullUrl": _uuid(), "resource": obs_resource})

    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry": entries,
    }

    # Validate before returning
    errors = validate_fhir_bundle(bundle)
    if errors:
        logger.warning(f"FHIR Bundle validation warnings: {errors}")
        bundle["_validation_warnings"] = errors

    return bundle


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_fhir_bundle(bundle: dict[str, Any]) -> list[str]:
    """
    Validate internal consistency of a FHIR Bundle:
    - No broken references
    - Patient references are valid
    - Encounter references the correct Patient
    - Condition/MedicationRequest/Observation reference correct Patient/Encounter
    - Missing mappings do not produce fake ICD-11 codes
    - Empty clinical resources are not present
    """
    errors: list[str] = []
    entries = bundle.get("entry", [])

    if not entries:
        errors.append("Bundle contains no entries.")
        return errors

    # Collect all fullUrls
    full_urls = {entry["fullUrl"] for entry in entries if "fullUrl" in entry}

    # Collect resource types and their references
    patient_urls: set[str] = set()
    encounter_urls: set[str] = set()

    for entry in entries:
        resource = entry.get("resource", {})
        resource_type = resource.get("resourceType", "")
        full_url = entry.get("fullUrl", "")

        if resource_type == "Patient":
            patient_urls.add(full_url)
        elif resource_type == "Encounter":
            encounter_urls.add(full_url)

            # Check Encounter → Patient reference
            subject_ref = resource.get("subject", {}).get("reference", "")
            if subject_ref and subject_ref not in patient_urls:
                errors.append(
                    f"Encounter references Patient '{subject_ref}' which is not in the Bundle."
                )

        elif resource_type == "Condition":
            _validate_subject_encounter_refs(
                resource, "Condition", full_urls, patient_urls, encounter_urls, errors
            )

            # Check that no fake ICD-11 codes are present
            _validate_condition_coding(resource, errors)

        elif resource_type == "MedicationRequest":
            _validate_subject_encounter_refs(
                resource, "MedicationRequest", full_urls, patient_urls, encounter_urls, errors
            )
            # Ensure medication is not empty
            med = resource.get("medicationCodeableConcept", {})
            if not med.get("text") and not med.get("coding"):
                errors.append("MedicationRequest has no medication specified.")

        elif resource_type == "Observation":
            _validate_subject_encounter_refs(
                resource, "Observation", full_urls, patient_urls, encounter_urls, errors
            )
            # Ensure observation has a code
            code = resource.get("code", {})
            if not code.get("text") and not code.get("coding"):
                errors.append("Observation has no code/type specified.")

    return errors


def _validate_subject_encounter_refs(
    resource: dict[str, Any],
    resource_type: str,
    full_urls: set[str],
    patient_urls: set[str],
    encounter_urls: set[str],
    errors: list[str],
) -> None:
    """Validate that subject and encounter references point to valid Bundle entries."""
    subject_ref = resource.get("subject", {}).get("reference", "")
    if subject_ref and subject_ref not in patient_urls:
        errors.append(
            f"{resource_type} references Patient '{subject_ref}' which is not in the Bundle."
        )

    encounter_ref = resource.get("encounter", {}).get("reference", "")
    if encounter_ref and encounter_ref not in encounter_urls:
        errors.append(
            f"{resource_type} references Encounter '{encounter_ref}' which is not in the Bundle."
        )


def _validate_condition_coding(
    resource: dict[str, Any],
    errors: list[str],
) -> None:
    """
    Validate that the Condition coding does not contain fabricated ICD-11 codes.
    An ICD-11 coding entry must have a non-empty code value.
    """
    code = resource.get("code", {})
    codings = code.get("coding", [])

    for coding_entry in codings:
        system = coding_entry.get("system", "")
        code_val = coding_entry.get("code", "")

        if system in (ICD11_TM2_SYSTEM, ICD11_FOUNDATION_SYSTEM):
            if not code_val:
                errors.append(
                    f"Condition contains an ICD-11 coding entry with system '{system}' "
                    f"but an empty code. This would be a fabricated code."
                )
