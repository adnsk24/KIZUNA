import {
  ArrowLeft,
  CalendarDays,
  Plus,
  ArrowRight,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getPatientApi, listEncountersApi } from "../services/apiService";

function formatDate(isoString) {
  if (!isoString) return "Date unknown";
  try {
    const date = new Date(isoString);
    return date.toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric"
    });
  } catch {
    return isoString;
  }
}

function PatientDetails() {
  const { patientId } = useParams();
  const [patient, setPatient] = useState(null);
  const [encounters, setEncounters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadPatientDetails() {
      try {
        setLoading(true);
        setError(null);
        
        // Fetch patient details
        const profile = await getPatientApi(patientId);
        setPatient(profile);
        
        // Fetch patient encounters
        const encounterList = await listEncountersApi(patientId);
        setEncounters(encounterList.results || []);
      } catch (err) {
        console.error("Failed to load patient EMR:", err);
        setError("Unable to load patient profile or encounters from EMR database.");
      } finally {
        setLoading(false);
      }
    }
    loadPatientDetails();
  }, [patientId]);

  if (loading) {
    return (
      <div className="flex h-[350px] items-center justify-center">
        <div className="text-center space-y-3">
          <Loader2 className="animate-spin mx-auto text-slate-400" size={36} />
          <p className="text-sm text-slate-500 font-medium">Loading clinical record...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <Link
          to="/patients"
          className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 transition"
        >
          <ArrowLeft size={16} />
          Back to Patients
        </Link>
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 flex gap-2">
          <AlertCircle size={17} className="shrink-0 mt-0.5" />
          {error}
        </div>
      </div>
    );
  }

  if (!patient) {
    return (
      <div className="space-y-6">
        <Link
          to="/patients"
          className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 transition"
        >
          <ArrowLeft size={16} />
          Back to Patients
        </Link>
        <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-500 space-y-2">
          <p className="font-semibold text-slate-800">Patient Not Found</p>
          <p>No patient record exists with EMR ID "{patientId}".</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back */}
      <Link
        to="/patients"
        className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 transition"
      >
        <ArrowLeft size={16} />
        Back to Patients
      </Link>

      {/* Patient header */}
      <section className="rounded-lg border border-slate-200 bg-white">
        <div className="flex flex-col gap-5 px-5 py-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-600">
              {patient.name
                .split(" ")
                .map((name) => name[0])
                .join("")}
            </div>

            <div>
              <h1 className="text-lg font-semibold text-slate-900">
                {patient.name}
              </h1>

              <p className="mt-1 text-sm text-slate-500">
                {patient.age} years · {patient.gender} ·{" "}
                <span className="font-mono text-xs">{patient.id}</span>
                {patient.abha_id && (
                  <>
                    {" · "}
                    <span className="font-mono text-xs text-slate-400">ABHA: {patient.abha_id}</span>
                  </>
                )}
              </p>
            </div>
          </div>

          <Link
            to={`/patients/${patient.id}/encounters/new`}
            className="inline-flex w-fit items-center gap-2 rounded-md bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 transition"
          >
            <Plus size={16} />
            New Encounter
          </Link>
        </div>
      </section>

      {/* Encounters */}
      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-sm font-semibold text-slate-900">
            Recent Encounters
          </h2>

          <p className="mt-1 text-xs text-slate-500">
            Previous clinical encounters and terminology activity.
          </p>
        </div>

        <div className="divide-y divide-slate-100">
          {encounters.map((encounter) => (
            <div
              key={encounter.id}
              className="flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-center sm:justify-between hover:bg-slate-50/50"
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 text-slate-400">
                  <CalendarDays size={17} />
                </div>

                <div>
                  <p className="text-sm font-medium text-slate-800">
                    {encounter.diagnosis}
                  </p>

                  <p className="mt-1 text-xs text-slate-500 font-mono">
                    {formatDate(encounter.created_at)} · ENC-{encounter.id}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <span
                  className={`rounded-md border px-2.5 py-1 text-xs font-medium ${
                    encounter.mapping_class === "DIRECT_CODE_ALIGNMENT" || encounter.mapping_class === "CROSS_CODE_MAPPING"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : encounter.mapping_class === "FOUNDATION_CONCEPT_ONLY"
                      ? "border-amber-200 bg-amber-50 text-amber-700"
                      : "border-slate-200 bg-slate-50 text-slate-600"
                  }`}
                >
                  {encounter.mapping_class === "DIRECT_CODE_ALIGNMENT"
                    ? "Direct"
                    : encounter.mapping_class === "CROSS_CODE_MAPPING"
                    ? "Mapped"
                    : encounter.mapping_class === "FOUNDATION_CONCEPT_ONLY"
                    ? "Foundation"
                    : "Unmapped"}
                </span>

                <Link
                  to={`/encounters`}
                  className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900 transition"
                >
                  View
                  <ArrowRight size={15} />
                </Link>
              </div>
            </div>
          ))}

          {encounters.length === 0 && (
            <div className="px-5 py-10 text-center text-sm text-slate-500">
              No previous clinical encounters recorded for this patient.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

export default PatientDetails;