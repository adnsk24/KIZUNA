import { Search, ChevronRight, UserPlus, Loader2, ShieldCheck, AlertCircle, X, CheckCircle2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { listPatientsApi, createPatientApi } from "../services/apiService";

function generateMockPatient(abhaId) {
  const cleanId = abhaId.trim();
  const mockNames = [
    { name: "Meera Joshi", age: 45, gender: "Female", date_of_birth: "1981-04-12" },
    { name: "Ramesh Patel", age: 52, gender: "Male", date_of_birth: "1974-09-22" },
    { name: "Anita Verma", age: 34, gender: "Female", date_of_birth: "1992-02-18" },
    { name: "Suresh Kumar", age: 60, gender: "Male", date_of_birth: "1966-07-05" },
    { name: "Sunita Sharma", age: 29, gender: "Female", date_of_birth: "1997-11-30" },
    { name: "Amit Kumar", age: 38, gender: "Male", date_of_birth: "1988-06-14" },
    { name: "Rajesh Gupta", age: 41, gender: "Male", date_of_birth: "1985-12-03" },
    { name: "Kiran Devi", age: 65, gender: "Female", date_of_birth: "1961-01-25" }
  ];
  
  // Pick deterministic index using a simple char code sum
  let sum = 0;
  for (let i = 0; i < cleanId.length; i++) {
    sum += cleanId.charCodeAt(i);
  }
  const selected = mockNames[sum % mockNames.length];
  
  // Generate a random EMR ID like PT-005, PT-006, etc.
  const randomNum = Math.floor(100 + (sum % 900));
  const emrId = `PT-${randomNum}`;
  
  return {
    id: emrId,
    name: selected.name,
    age: selected.age,
    gender: selected.gender,
    date_of_birth: selected.date_of_birth,
    abha_id: cleanId,
  };
}

function Patients() {
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalStep, setModalStep] = useState("abha"); // abha, otp, profile, success
  const [abhaInput, setAbhaInput] = useState("");
  const [otpInput, setOtpInput] = useState("");
  const [mockPatient, setMockPatient] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState("");

  const fetchPatients = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listPatientsApi();
      setPatients(data.results || []);
    } catch (err) {
      console.error(err);
      setError("Failed to load patients from EMR database.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPatients();
  }, []);

  const filteredPatients = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();

    if (!query) {
      return patients;
    }

    return patients.filter((patient) =>
      [
        patient.id || "",
        patient.name || "",
        patient.gender || "",
        patient.abha_id || "",
      ].some((value) =>
        value.toLowerCase().includes(query)
      )
    );
  }, [patients, searchTerm]);

  // Modal Actions
  const handleOpenModal = () => {
    setAbhaInput("");
    setOtpInput("");
    setMockPatient(null);
    setModalStep("abha");
    setModalError("");
    setModalLoading(false);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
  };

  const handleVerifyAbha = () => {
    if (!abhaInput.trim()) {
      setModalError("Please enter a valid ABHA ID or Address.");
      return;
    }
    setModalError("");
    setModalLoading(true);
    
    // Simulate API request to ABDM Gateway
    setTimeout(() => {
      setModalLoading(false);
      setModalStep("otp");
    }, 1000);
  };

  const handleVerifyOtp = () => {
    if (!otpInput.trim()) {
      setModalError("Please enter the OTP.");
      return;
    }
    if (otpInput.trim() !== "123456") {
      setModalError("Invalid OTP. Use mock code 123456 for testing.");
      return;
    }
    
    setModalError("");
    setModalLoading(true);

    // Simulate E-KYC profile fetch from UIDAI/ABDM
    setTimeout(() => {
      setModalLoading(false);
      const generated = generateMockPatient(abhaInput);
      setMockPatient(generated);
      setModalStep("profile");
    }, 1000);
  };

  const handleAddPatient = async () => {
    if (!mockPatient) return;
    setModalError("");
    setModalLoading(true);

    try {
      await createPatientApi(mockPatient);
      await fetchPatients(); // Refresh EMR list
      setModalLoading(false);
      setModalStep("success");
    } catch (err) {
      setModalLoading(false);
      setModalError(err.message || "Failed to save patient to EMR database.");
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">
            Patients
          </h1>

          <p className="mt-1 text-sm text-slate-500">
            View patients and their clinical encounters.
          </p>
        </div>

        <button
          type="button"
          onClick={handleOpenModal}
          className="inline-flex w-fit items-center gap-2 rounded-md bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 transition"
        >
          <UserPlus size={16} />
          New Patient
        </button>
      </div>

      {/* Search */}
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="relative">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />

          <input
            type="text"
            value={searchTerm}
            onChange={(event) =>
              setSearchTerm(event.target.value)
            }
            placeholder="Search patients by name, ID, gender, or ABHA address..."
            className="w-full rounded-md border border-slate-300 py-2.5 pl-10 pr-4 text-sm text-slate-800 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100"
          />
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800 flex gap-2">
          <AlertCircle size={17} className="shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {/* Patient table */}
      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-5 py-4 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">
              Patient Records
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              {filteredPatients.length} patients registered
            </p>
          </div>
          {loading && <Loader2 size={16} className="animate-spin text-slate-400" />}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-5 py-3 font-medium">
                  Patient Name & ID
                </th>

                <th className="px-5 py-3 font-medium">
                  Age / Gender
                </th>

                <th className="px-5 py-3 font-medium">
                  ABHA Address
                </th>

                <th className="px-5 py-3 font-medium">
                  Status
                </th>

                <th className="px-5 py-3 font-medium">
                  Action
                </th>
              </tr>
            </thead>

            <tbody className="divide-y divide-slate-100">
              {filteredPatients.map((patient) => (
                <tr
                  key={patient.id}
                  className="hover:bg-slate-50"
                >
                  <td className="px-5 py-4">
                    <p className="font-medium text-slate-800">
                      {patient.name}
                    </p>

                    <p className="mt-0.5 text-xs text-slate-400 font-mono">
                      {patient.id}
                    </p>
                  </td>

                  <td className="px-5 py-4 text-slate-600">
                    {patient.age} years / {patient.gender}
                  </td>

                  <td className="px-5 py-4 text-slate-600 font-mono text-xs">
                    {patient.abha_id || "—"}
                  </td>

                  <td className="px-5 py-4">
                    <span className="inline-flex rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
                      Active
                    </span>
                  </td>

                  <td className="px-5 py-4">
                    <a
                      href={`/patients/${patient.id}`}
                      className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900"
                    >
                      View EMR
                      <ChevronRight size={15} />
                    </a>
                  </td>
                </tr>
              ))}

              {!loading && filteredPatients.length === 0 && (
                <tr>
                  <td
                    colSpan="5"
                    className="px-5 py-12 text-center text-sm text-slate-500"
                  >
                    No patient records found in EMR database.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* ABDM ABHA Authentication Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full border border-slate-200 shadow-2xl p-6 relative overflow-hidden">
            
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-4 mb-4">
              <div className="flex items-center gap-2">
                <ShieldCheck className="text-blue-600" size={20} />
                <h3 className="font-semibold text-slate-900">ABDM Registry Authentication</h3>
              </div>
              <button 
                onClick={handleCloseModal}
                disabled={modalLoading}
                className="text-slate-400 hover:text-slate-600 rounded-lg p-1 hover:bg-slate-50 disabled:opacity-50"
              >
                <X size={18} />
              </button>
            </div>

            {/* Step 1: ABHA Entry */}
            {modalStep === "abha" && (
              <div className="space-y-4">
                <div>
                  <h4 className="text-sm font-semibold text-slate-800">Verify ABHA ID / Address</h4>
                  <p className="text-xs text-slate-500 mt-1">
                    Enter the patient's Ayushman Bharat Health Account (ABHA) address or health number to initiate Aadhaar authentication.
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">ABHA Address / ID</label>
                  <input
                    type="text"
                    value={abhaInput}
                    onChange={(e) => setAbhaInput(e.target.value)}
                    placeholder="e.g. name@abdm or 12-3456-7890-1234"
                    disabled={modalLoading}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-50 font-mono disabled:bg-slate-50"
                  />
                </div>

                {modalError && (
                  <div className="text-xs text-red-600 bg-red-50 p-2.5 rounded-lg flex gap-1.5 items-start">
                    <AlertCircle size={14} className="shrink-0 mt-0.5" />
                    {modalError}
                  </div>
                )}

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={handleCloseModal}
                    disabled={modalLoading}
                    className="px-4 py-2 border border-slate-200 bg-white rounded-lg text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleVerifyAbha}
                    disabled={modalLoading}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition inline-flex items-center gap-1.5 disabled:opacity-50"
                  >
                    {modalLoading && <Loader2 size={14} className="animate-spin" />}
                    Request OTP
                  </button>
                </div>
              </div>
            )}

            {/* Step 2: OTP Verification */}
            {modalStep === "otp" && (
              <div className="space-y-4">
                <div>
                  <h4 className="text-sm font-semibold text-slate-800">Enter Aadhaar-linked OTP</h4>
                  <p className="text-xs text-slate-500 mt-1">
                    An OTP has been sent to the Aadhaar-registered mobile number associated with ABHA address <span className="font-mono text-slate-700 font-medium">{abhaInput}</span>.
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Enter 6-Digit OTP</label>
                  <input
                    type="text"
                    value={otpInput}
                    onChange={(e) => setOtpInput(e.target.value)}
                    maxLength={6}
                    placeholder="Enter 123456 for testing"
                    disabled={modalLoading}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-50 font-mono tracking-widest text-center text-lg disabled:bg-slate-50"
                  />
                </div>

                {modalError && (
                  <div className="text-xs text-red-600 bg-red-50 p-2.5 rounded-lg flex gap-1.5 items-start">
                    <AlertCircle size={14} className="shrink-0 mt-0.5" />
                    {modalError}
                  </div>
                )}

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => { setModalStep("abha"); setModalError(""); }}
                    disabled={modalLoading}
                    className="px-4 py-2 border border-slate-200 bg-white rounded-lg text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={handleVerifyOtp}
                    disabled={modalLoading}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition inline-flex items-center gap-1.5 disabled:opacity-50"
                  >
                    {modalLoading && <Loader2 size={14} className="animate-spin" />}
                    Confirm OTP
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Verified E-KYC Profile */}
            {modalStep === "profile" && mockPatient && (
              <div className="space-y-4">
                <div>
                  <h4 className="text-sm font-semibold text-slate-800 text-emerald-700 flex items-center gap-1.5">
                    <CheckCircle2 size={16} /> ABDM E-KYC Verified Successfully
                  </h4>
                  <p className="text-xs text-slate-500 mt-1">
                    The following demographic profile was fetched securely from the Aadhaar registry. Confirm to import this record into the EMR database.
                  </p>
                </div>

                <div className="border border-slate-100 rounded-xl bg-slate-50 p-4 space-y-3">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <p className="font-bold text-[9px] uppercase tracking-wider text-slate-400">Full Name</p>
                      <p className="font-medium text-slate-800 mt-0.5">{mockPatient.name}</p>
                    </div>
                    <div>
                      <p className="font-bold text-[9px] uppercase tracking-wider text-slate-400">Gender / Age</p>
                      <p className="font-medium text-slate-800 mt-0.5">{mockPatient.gender} / {mockPatient.age} Yrs</p>
                    </div>
                    <div>
                      <p className="font-bold text-[9px] uppercase tracking-wider text-slate-400">Date of Birth</p>
                      <p className="font-medium text-slate-800 mt-0.5">{mockPatient.date_of_birth}</p>
                    </div>
                    <div>
                      <p className="font-bold text-[9px] uppercase tracking-wider text-slate-400">Assigned EMR ID</p>
                      <p className="font-medium text-slate-800 mt-0.5 font-mono">{mockPatient.id}</p>
                    </div>
                  </div>
                  <div className="pt-2 border-t border-slate-200">
                    <p className="font-bold text-[9px] uppercase tracking-wider text-slate-400">ABHA ID / Address</p>
                    <p className="font-medium text-slate-700 mt-0.5 font-mono text-[11px]">{mockPatient.abha_id}</p>
                  </div>
                </div>

                {modalError && (
                  <div className="text-xs text-red-600 bg-red-50 p-2.5 rounded-lg flex gap-1.5 items-start">
                    <AlertCircle size={14} className="shrink-0 mt-0.5" />
                    {modalError}
                  </div>
                )}

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={handleCloseModal}
                    disabled={modalLoading}
                    className="px-4 py-2 border border-slate-200 bg-white rounded-lg text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleAddPatient}
                    disabled={modalLoading}
                    className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-sm font-semibold transition inline-flex items-center gap-1.5 disabled:opacity-50"
                  >
                    {modalLoading && <Loader2 size={14} className="animate-spin" />}
                    Add to EMR Database
                  </button>
                </div>
              </div>
            )}

            {/* Step 4: Success */}
            {modalStep === "success" && (
              <div className="text-center py-4 space-y-4">
                <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                  <CheckCircle2 size={28} />
                </div>
                <div>
                  <h4 className="text-base font-semibold text-slate-900">Patient Added Successfully</h4>
                  <p className="text-xs text-slate-500 mt-1 max-w-xs mx-auto">
                    The patient E-KYC profile has been registered in the database. You can now log clinical encounters for this patient.
                  </p>
                </div>

                <div className="pt-2">
                  <button
                    type="button"
                    onClick={handleCloseModal}
                    className="px-6 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-sm font-medium transition"
                  >
                    Close
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>
      )}
    </div>
  );
}

export default Patients;