import { useEffect, useMemo, useState } from "react";
import { CalendarDays, ClipboardList, Loader2, RefreshCw, Search, XCircle } from "lucide-react";
import { listEncountersApi } from "../services/apiService";

function MappingBadge({ value }) {
  const styles = {
    DIRECT_CODE_ALIGNMENT: "border-emerald-200 bg-emerald-50 text-emerald-700",
    CROSS_CODE_MAPPING: "border-blue-200 bg-blue-50 text-blue-700",
    FOUNDATION_CONCEPT_ONLY: "border-amber-200 bg-amber-50 text-amber-700",
    UNMAPPED: "border-slate-200 bg-slate-100 text-slate-600",
  };
  const labels = {
    DIRECT_CODE_ALIGNMENT: "Direct alignment",
    CROSS_CODE_MAPPING: "Cross-code mapping",
    FOUNDATION_CONCEPT_ONLY: "Foundation only",
    UNMAPPED: "Unmapped",
  };
  const key = value || "UNMAPPED";
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium ${styles[key] || styles.UNMAPPED}`}>{labels[key] || key.replaceAll("_", " ")}</span>;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function Encounters() {
  const [encounters, setEncounters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");

  const loadEncounters = async (showRefreshState = false) => {
    try {
      if (showRefreshState) setRefreshing(true); else setLoading(true);
      setError(null);
      const data = await listEncountersApi();
      setEncounters(data.results || []);
    } catch (err) {
      setError(err.message || "Unable to load encounters.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { loadEncounters(); }, []);

  const filteredEncounters = useMemo(() => {
    const value = query.trim().toLowerCase();
    if (!value) return encounters;
    return encounters.filter((encounter) => [
      encounter.patient_id, encounter.diagnosis, encounter.namaste_code,
      encounter.namaste_english, encounter.tm2_code, encounter.tm2_term,
      encounter.mapping_class,
    ].filter(Boolean).some((field) => String(field).toLowerCase().includes(value)));
  }, [encounters, query]);

  const stats = useMemo(() => ({
    total: encounters.length,
    mapped: encounters.filter((item) => item.tm2_code).length,
    review: encounters.filter((item) => ["FOUNDATION_CONCEPT_ONLY", "UNMAPPED"].includes(item.mapping_class)).length,
  }), [encounters]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 pb-8">
      
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-emerald-500" /><span className="text-xs font-medium text-emerald-700">API connected</span></div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">Encounters</h1>
          <p className="mt-1 text-sm text-slate-500">Clinical encounters persisted through the interoperability API.</p>
        </div>
        <button type="button" onClick={() => loadEncounters(true)} disabled={loading || refreshing} className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50">
          <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {[
          ["Total encounters", stats.total, "All persisted clinical records"],
          ["With TM2 mapping", stats.mapped, "Records with a classified target code"],
          ["Needs terminology review", stats.review, "Foundation-only or unmapped"],
        ].map(([label, value, hint]) => (
          <div key={label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-medium text-slate-400">{label}</p>
            <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
            <p className="mt-1 text-[11px] text-slate-400">{hint}</p>
          </div>
        ))}
      </div>

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div><h2 className="text-sm font-semibold text-slate-900">Encounter records</h2><p className="mt-1 text-xs text-slate-500">Search across patient, diagnosis, source code, target code, and mapping state.</p></div>
          <div className="relative w-full sm:max-w-sm"><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search records..." className="w-full rounded-lg border border-slate-300 py-2.5 pl-9 pr-3 text-sm text-slate-800 outline-none focus:border-slate-400 focus:ring-4 focus:ring-slate-100" /></div>
        </div>

        {loading ? (
          <div className="flex min-h-[280px] items-center justify-center text-sm text-slate-500"><div className="flex items-center gap-2"><Loader2 size={17} className="animate-spin" />Loading encounters...</div></div>
        ) : error ? (
          <div className="p-6"><div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4"><XCircle size={18} className="mt-0.5 shrink-0 text-red-500" /><div><p className="text-sm font-medium text-red-800">Unable to load encounters</p><p className="mt-1 text-xs text-red-700">{error}</p><p className="mt-2 text-xs text-red-700">Make sure the FastAPI backend is running on port 8000.</p></div></div></div>
        ) : filteredEncounters.length === 0 ? (
          <div className="flex min-h-[280px] flex-col items-center justify-center px-6 text-center"><ClipboardList size={28} className="text-slate-300" /><p className="mt-3 text-sm font-medium text-slate-700">No encounters found</p><p className="mt-1 max-w-md text-xs leading-5 text-slate-500">{query ? "Try a different search term." : "Create an encounter from a patient record and it will appear here."}</p></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left">
              <thead className="border-b border-slate-200 bg-slate-50/80"><tr className="text-[10px] font-semibold uppercase tracking-wider text-slate-400"><th className="px-5 py-3">Patient</th><th className="px-5 py-3">Diagnosis</th><th className="px-5 py-3">NAMASTE</th><th className="px-5 py-3">ICD-11 TM2</th><th className="px-5 py-3">Mapping</th><th className="px-5 py-3">Created</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {filteredEncounters.map((encounter) => (
                  <tr key={encounter.id} className="transition-colors hover:bg-slate-50/70">
                    <td className="px-5 py-4"><p className="text-sm font-medium text-slate-800">{encounter.patient_id}</p><p className="mt-0.5 text-[11px] text-slate-400">Encounter #{encounter.id}</p></td>
                    <td className="px-5 py-4"><p className="max-w-[240px] text-sm text-slate-800">{encounter.diagnosis}</p></td>
                    <td className="px-5 py-4"><p className="text-xs font-medium text-slate-700">{encounter.namaste_english || encounter.namaste_term || "—"}</p><p className="mt-1 font-mono text-[11px] text-slate-400">{encounter.namaste_code || "—"}</p></td>
                    <td className="px-5 py-4"><p className="text-xs font-medium text-slate-700">{encounter.tm2_term || "No classified mapping"}</p><p className="mt-1 font-mono text-[11px] text-slate-400">{encounter.tm2_code || "—"}</p></td>
                    <td className="px-5 py-4"><MappingBadge value={encounter.mapping_class} /></td>
                    <td className="whitespace-nowrap px-5 py-4"><div className="flex items-center gap-1.5 text-xs text-slate-500"><CalendarDays size={13} />{formatDate(encounter.created_at)}</div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>


    </div>
  );
}

export default Encounters;
