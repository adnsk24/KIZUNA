import { useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, Search, AlertTriangle, Loader2, XCircle, FileCheck2, Database, Plus } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { searchTerminologyApi, createEncounterApi } from "../services/apiService";

const patientData = {
  "PT-001": { name: "Meera Joshi", age: 45, gender: "Female", id: "PT-001" },
  "PT-002": { name: "Ramesh Patel", age: 52, gender: "Male", id: "PT-002" },
  "PT-003": { name: "Anita Verma", age: 34, gender: "Female", id: "PT-003" },
  "PT-004": { name: "Suresh Kumar", age: 60, gender: "Male", id: "PT-004" },
};

const statusMeta = {
  DIRECT_CODE_ALIGNMENT: { label: "Direct alignment", classes: "border-emerald-200 bg-emerald-50 text-emerald-700", icon: CheckCircle2 },
  CROSS_CODE_MAPPING: { label: "Cross-code mapping", classes: "border-blue-200 bg-blue-50 text-blue-700", icon: Database },
  FOUNDATION_CONCEPT_ONLY: { label: "Foundation only", classes: "border-amber-200 bg-amber-50 text-amber-700", icon: AlertTriangle },
  UNMAPPED: { label: "Unmapped", classes: "border-slate-200 bg-slate-100 text-slate-600", icon: XCircle },
};

function MappingStatus({ status }) {
  const meta = statusMeta[status] || statusMeta.UNMAPPED;
  const Icon = meta.icon;
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold ${meta.classes}`}><Icon size={14} />{meta.label}</span>;
}

function EvidenceField({ label, value, mono = false }) {
  return <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3.5"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</p><p className={`mt-1.5 break-words text-xs text-slate-700 ${mono ? "font-mono" : ""}`}>{value || "Not available"}</p></div>;
}

function MappingPreview({ concept }) {
  const status = concept.MAPPING_CLASS || concept.MAPPING_STATUS || "UNMAPPED";
  const hasTarget = Boolean(concept.TM2_CODE || concept.TM2_TERM);
  return <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
    <div className="flex flex-col gap-3 border-b border-slate-100 bg-slate-50/70 px-6 py-5 sm:flex-row sm:items-center sm:justify-between"><div><div className="flex items-center gap-2"><FileCheck2 size={17} className="text-slate-500" /><h2 className="text-sm font-semibold text-slate-950">Terminology decision</h2></div><p className="mt-1 text-xs text-slate-500">Review the API-backed mapping before saving the encounter.</p></div><MappingStatus status={status} /></div>
    <div className="p-6">
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_52px_1fr] lg:items-stretch">
        <div className="rounded-2xl border border-slate-200 p-5"><div className="flex items-center justify-between"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">NAMASTE</p><span className="font-mono text-[11px] text-slate-400">{concept.NAMASTE_CODE || "—"}</span></div><h3 className="mt-5 text-lg font-semibold text-slate-950">{concept.NAMASTE_ENGLISH || concept.NAMASTE_TERM || "Unnamed concept"}</h3><p className="mt-2 text-xs text-slate-500">Source terminology concept</p></div>
        <div className="flex items-center justify-center"><div className="flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white shadow-sm"><span className="text-slate-400">→</span></div></div>
        <div className={`rounded-2xl border p-5 ${hasTarget ? "border-blue-100 bg-blue-50/40" : "border-amber-100 bg-amber-50/40"}`}><div className="flex items-center justify-between"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">ICD-11 TM2</p><span className="font-mono text-[11px] text-slate-500">{concept.TM2_CODE || "No code"}</span></div><h3 className="mt-5 text-lg font-semibold text-slate-950">{concept.TM2_TERM || "No classified mapping"}</h3><p className="mt-2 text-xs text-slate-500">{hasTarget ? "Target terminology concept" : "Foundation or unresolved state"}</p></div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4"><EvidenceField label="Relationship" value={concept.RELATIONSHIP} /><EvidenceField label="Confidence" value={concept.CONFIDENCE !== undefined && concept.CONFIDENCE !== "" ? `${Math.round(Number(concept.CONFIDENCE) * 100)}%` : "Not calculated"} /><EvidenceField label="Source" value={concept.SOURCE} /><EvidenceField label="Version" value={concept.VERSION} mono /></div>
      {!hasTarget && <div className="mt-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-5 text-amber-800"><AlertTriangle size={16} className="mt-0.5 shrink-0" /><div><strong>No classified TM2 code is recorded.</strong> This encounter can still be saved, but it should remain visible in the human-review workflow.</div></div>}
    </div>
  </section>;
}

export default function NewEncounterApi() {
  const { patientId } = useParams();
  const patient = patientData[patientId] || patientData["PT-001"];
  const [diagnosis, setDiagnosis] = useState("");
  const [clinicalNotes, setClinicalNotes] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [selectedConcept, setSelectedConcept] = useState(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedEncounter, setSavedEncounter] = useState(null);
  const [error, setError] = useState("");

  const [prescriptions, setPrescriptions] = useState([]);
  const [observations, setObservations] = useState([]);
  


  const status = selectedConcept?.MAPPING_CLASS || selectedConcept?.MAPPING_STATUS || "UNMAPPED";
  const canSave = Boolean(selectedConcept) && !saving;

  useEffect(() => {
    const query = diagnosis.trim();
    if (!query || selectedConcept) { setSuggestions([]); return; }
    const timer = setTimeout(async () => {
      try { setSearching(true); setError(""); const data = await searchTerminologyApi(query, 12); setSuggestions(data.results || []); }
      catch (err) { setError(`Terminology API unavailable: ${err.message}`); setSuggestions([]); }
      finally { setSearching(false); }
    }, 250);
    return () => clearTimeout(timer);
  }, [diagnosis, selectedConcept]);

  const selectConcept = (concept) => {
    setSelectedConcept(concept);
    setDiagnosis(concept.NAMASTE_ENGLISH || concept.NAMASTE_TERM || "");
    setShowSuggestions(false);
    setSavedEncounter(null);
    setError("");
  };

  const handleAddPrescription = () => {
    setPrescriptions([...prescriptions, { medication: "", dosage: "", frequency: "", duration: "" }]);
  };

  const updatePrescription = (index, field, value) => {
    const newRx = [...prescriptions];
    newRx[index][field] = value;
    setPrescriptions(newRx);
  };

  const handleAddObservation = () => {
    setObservations([...observations, { observation_type: "", value: "", unit: "" }]);
  };

  const updateObservation = (index, field, value) => {
    const newObs = [...observations];
    newObs[index][field] = value;
    setObservations(newObs);
  };

  const handleSave = async () => {
    if (!selectedConcept) return;
    try {
      setSaving(true); setError("");
      const validPrescriptions = prescriptions.filter(rx => rx.medication.trim() !== "");
      const validObservations = observations.filter(obs => obs.observation_type.trim() !== "");
      
      const result = await createEncounterApi({
        patient_id: patient.id,
        diagnosis: diagnosis.trim(),
        clinical_notes: clinicalNotes.trim(),
        namaste_code: selectedConcept.NAMASTE_CODE || "",
        namaste_term: selectedConcept.NAMASTE_TERM || "",
        namaste_english: selectedConcept.NAMASTE_ENGLISH || "",
        tm2_code: selectedConcept.TM2_CODE || "",
        tm2_term: selectedConcept.TM2_TERM || "",
        mapping_class: status,
        confidence: selectedConcept.CONFIDENCE === "" || selectedConcept.CONFIDENCE == null ? null : Number(selectedConcept.CONFIDENCE),
        source: selectedConcept.SOURCE || "",
        prescriptions: validPrescriptions,
        observations: validObservations,
      });
      setSavedEncounter(result);
    } catch (err) { setError(`Unable to save encounter: ${err.message}`); }
    finally { setSaving(false); }
  };
  


  return <div className="space-y-6">
    <Link to={`/patients/${patient.id}`} className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 transition hover:text-slate-900"><ArrowLeft size={16} />Back to patient</Link>

    <header className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-7"><div className="absolute -right-16 -top-20 h-48 w-48 rounded-full bg-blue-50" /><div className="relative"><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-slate-100 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">Clinical workflow</span><span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-emerald-700"><span className="status-dot" />API connected</span></div><h1 className="mt-4 text-2xl font-semibold tracking-tight text-slate-950">New Encounter</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Search the terminology service, inspect the mapping decision, add clinical notes, and persist the complete encounter.</p></div></header>

    <section className="surface-lift rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Patient</p><h2 className="mt-2 text-lg font-semibold text-slate-950">{patient.name}</h2><p className="mt-1 text-sm text-slate-500">{patient.age} years · {patient.gender} · <span className="font-mono text-xs">{patient.id}</span></p></div><div className="rounded-xl bg-slate-50 px-4 py-3 text-xs text-slate-500"><span className="font-medium text-slate-700">Encounter mode</span><br />Terminology-integrated</div></div></section>

    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm"><div className="border-b border-slate-100 px-6 py-5"><h2 className="text-sm font-semibold text-slate-950">Clinical information</h2><p className="mt-1 text-xs text-slate-500">Search by diagnosis, NAMASTE code, or terminology term.</p></div><div className="space-y-5 p-6">
      <div className="relative"><label htmlFor="diagnosis-api" className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">Diagnosis / terminology concept</label><div className="relative"><Search size={17} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" /><input id="diagnosis-api" value={diagnosis} onChange={(e) => { setDiagnosis(e.target.value); setSelectedConcept(null); setSavedEncounter(null); setShowSuggestions(true); }} onFocus={() => setShowSuggestions(Boolean(diagnosis.trim()))} placeholder="Try tremor, contracture, osteoarthritis..." className="w-full rounded-xl border border-slate-200 bg-slate-50 py-3.5 pl-11 pr-11 text-sm text-slate-800 outline-none transition focus:border-blue-300 focus:bg-white focus:ring-4 focus:ring-blue-50" />{searching && <Loader2 size={17} className="absolute right-3.5 top-1/2 -translate-y-1/2 animate-spin text-slate-400" />}</div>
        {showSuggestions && diagnosis.trim() && !selectedConcept && <div className="absolute left-6 right-6 z-30 mt-2 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">{suggestions.length ? suggestions.map((concept) => <button key={`${concept.NAMASTE_CODE}-${concept.NAMASTE_TERM}`} type="button" onClick={() => selectConcept(concept)} className="block w-full border-b border-slate-100 px-5 py-4 text-left transition last:border-0 hover:bg-slate-50"><div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><span className="text-sm font-semibold text-slate-900">{concept.NAMASTE_ENGLISH || concept.NAMASTE_TERM || "Unnamed concept"}</span><MappingStatus status={concept.MAPPING_CLASS || concept.MAPPING_STATUS} /></div><p className="mt-1.5 text-xs text-slate-500">NAMASTE {concept.NAMASTE_CODE || "—"}{concept.TM2_CODE ? ` · ICD-11 TM2 ${concept.TM2_CODE}` : " · no classified TM2 code"}</p></button>) : <div className="px-5 py-5 text-sm text-slate-500">No terminology concepts found.</div>}</div>}
      </div>
      <div><label htmlFor="notes-api" className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-500">Clinical notes</label><textarea id="notes-api" value={clinicalNotes} onChange={(e) => setClinicalNotes(e.target.value)} rows={4} placeholder="Symptoms, observations, examination notes, or context..." className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none transition focus:border-blue-300 focus:bg-white focus:ring-4 focus:ring-blue-50" /></div>
    </div></section>

    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
        <div>
          <h2 className="text-sm font-semibold text-slate-950">Prescriptions</h2>
          <p className="mt-1 text-xs text-slate-500">Optional: Add medications to include in FHIR output.</p>
        </div>
        <button onClick={handleAddPrescription} className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-200">
          <Plus size={14} /> Add Medication
        </button>
      </div>
      {prescriptions.length > 0 && <div className="space-y-4 p-6">
        {prescriptions.map((rx, idx) => (
          <div key={idx} className="flex gap-3">
            <input placeholder="Medication (e.g. Ashwagandha)" value={rx.medication} onChange={e => updatePrescription(idx, "medication", e.target.value)} className="w-1/3 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            <input placeholder="Dosage" value={rx.dosage} onChange={e => updatePrescription(idx, "dosage", e.target.value)} className="w-1/5 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            <input placeholder="Frequency" value={rx.frequency} onChange={e => updatePrescription(idx, "frequency", e.target.value)} className="w-1/5 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            <input placeholder="Duration" value={rx.duration} onChange={e => updatePrescription(idx, "duration", e.target.value)} className="w-1/5 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
          </div>
        ))}
      </div>}
    </section>

    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
        <div>
          <h2 className="text-sm font-semibold text-slate-950">Observations</h2>
          <p className="mt-1 text-xs text-slate-500">Optional: Add lab results or vitals.</p>
        </div>
        <button onClick={handleAddObservation} className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-200">
          <Plus size={14} /> Add Observation
        </button>
      </div>
      {observations.length > 0 && <div className="space-y-4 p-6">
        {observations.map((obs, idx) => (
          <div key={idx} className="flex gap-3">
            <input placeholder="Type (e.g. Blood Pressure)" value={obs.observation_type} onChange={e => updateObservation(idx, "observation_type", e.target.value)} className="w-1/3 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            <input placeholder="Value" value={obs.value} onChange={e => updateObservation(idx, "value", e.target.value)} className="w-1/3 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            <input placeholder="Unit" value={obs.unit} onChange={e => updateObservation(idx, "unit", e.target.value)} className="w-1/3 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
          </div>
        ))}
      </div>}
    </section>

    {selectedConcept && <MappingPreview concept={selectedConcept} />}

    {error && <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><XCircle size={18} className="mt-0.5 shrink-0" />{error}</div>}
    {savedEncounter && <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4"><CheckCircle2 size={18} className="mt-0.5 shrink-0 text-emerald-600" /><div><p className="text-sm font-semibold text-emerald-900">Encounter saved successfully</p><p className="mt-1 text-xs text-emerald-700">Database encounter ID: <span className="font-mono">{savedEncounter.id}</span></p></div></div>}

    <div className="flex flex-col-reverse gap-3 border-t border-slate-200 pt-5 sm:flex-row sm:items-center sm:justify-end"><Link to={`/patients/${patient.id}`} className="inline-flex justify-center rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-600 transition hover:bg-slate-50">Cancel</Link><button type="button" disabled={!canSave} onClick={handleSave} className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-950 px-6 py-3 text-sm font-semibold text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40">{saving && <Loader2 size={16} className="animate-spin" />}{saving ? "Saving encounter..." : "Save encounter"}</button></div>
  

  </div>;
}
