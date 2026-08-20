const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let message = `API request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the HTTP status message when the response is not JSON.
    }
    throw new Error(message);
  }

  return response.json();
}

export function healthCheckApi() {
  return request("/api/health");
}

export function listTerminologyApi(limit = 300, offset = 0) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return request(`/api/terminology?${params.toString()}`);
}

export function searchTerminologyApi(query, limit = 12) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return request(`/api/terminology/search?${params.toString()}`);
}

export function createEncounterApi(encounter) {
  return request("/api/encounters", {
    method: "POST",
    body: JSON.stringify(encounter),
  });
}

export function listEncountersApi(patientId) {
  const query = patientId ? `?patient_id=${encodeURIComponent(patientId)}` : "";
  return request(`/api/encounters${query}`);
}

export function createReviewApi(review) {
  return request("/api/reviews", {
    method: "POST",
    body: JSON.stringify(review),
  });
}

export function listReviewsApi() {
  return request("/api/reviews");
}

export function listPendingReviewsApi() {
  return request("/api/reviews/pending");
}

export function resetDemoDataApi() {
  return request("/api/demo/reset", { method: "POST" });
}

export function getAnalyticsSummaryApi() {
  return request("/api/analytics/summary");
}

export function getEncounterFhirApi(encounterId) {
  return request(`/api/encounters/${encounterId}/fhir`);
}

export function listPatientsApi() {
  return request("/api/patients");
}

export function getPatientApi(patientId) {
  return request(`/api/patients/${patientId}`);
}

export function createPatientApi(patient) {
  return request("/api/patients", {
    method: "POST",
    body: JSON.stringify(patient),
  });
}

export function createPrescriptionApi(encounterId, prescription) {
  return request(`/api/encounters/${encounterId}/prescriptions`, {
    method: "POST",
    body: JSON.stringify(prescription),
  });
}

export function createObservationApi(encounterId, observation) {
  return request(`/api/encounters/${encounterId}/observations`, {
    method: "POST",
    body: JSON.stringify(observation),
  });
}

export { API_BASE_URL };
