import { useEffect, useState } from "react";
import Modal from "../components/Modal";
import {
  listReportSchedules, createReportSchedule, updateReportSchedule,
  toggleReportSchedule, deleteReportSchedule, runReportScheduleNow,
} from "../api/reportSchedules";
import type { ReportSchedule, ReportScheduleCreate, ReportType, ScheduleFrequency, ReportFormat } from "../types";

const REPORT_TYPES: { value: ReportType; label: string }[] = [
  { value: "SALES", label: "Sales Report" },
  { value: "INVENTORY", label: "Inventory Report" },
  { value: "CUSTOMER", label: "Customer Report" },
  { value: "PRODUCT_PERFORMANCE", label: "Product Performance" },
  { value: "STOCK_MOVEMENT", label: "Stock Movement" },
];

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const BLANK: ReportScheduleCreate = {
  name: "", report_type: "SALES", filters: {}, format: "CSV", frequency: "DAILY",
  execution_time: "09:00", recipients: [], is_active: true,
};

export default function ScheduledReports() {
  const [schedules, setSchedules] = useState<ReportSchedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ReportSchedule | null>(null);
  const [form, setForm] = useState<ReportScheduleCreate>(BLANK);
  const [recipientInput, setRecipientInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ReportSchedule | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    listReportSchedules()
      .then((r) => setSchedules(r.items))
      .catch(() => setError("Couldn't load scheduled reports."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const openCreate = () => {
    setEditing(null);
    setForm(BLANK);
    setRecipientInput("");
    setModalOpen(true);
  };

  const openEdit = (s: ReportSchedule) => {
    setEditing(s);
    setForm({
      name: s.name, report_type: s.report_type, filters: s.filters, format: s.format,
      frequency: s.frequency, execution_time: s.execution_time,
      day_of_week: s.day_of_week ?? undefined, day_of_month: s.day_of_month ?? undefined,
      recipients: s.recipients, is_active: s.is_active,
    });
    setRecipientInput(s.recipients.join(", "));
    setModalOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    const recipients = recipientInput.split(",").map((r) => r.trim()).filter(Boolean);
    const payload = { ...form, recipients };
    try {
      if (editing) {
        await updateReportSchedule(editing.id, payload);
      } else {
        await createReportSchedule(payload);
      }
      setModalOpen(false);
      load();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Couldn't save this schedule.");
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (s: ReportSchedule) => {
    await toggleReportSchedule(s.id);
    load();
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    await deleteReportSchedule(deleteTarget.id);
    setDeleteTarget(null);
    load();
  };

  const handleRunNow = async (s: ReportSchedule) => {
    await runReportScheduleNow(s.id);
    load();
  };

  return (
    <div className="mx-auto w-full max-w-6xl p-4 sm:p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-navy">Scheduled Reports</h1>
          <p className="text-sm text-slate-500">Recurring reports generated automatically and saved to Report History.</p>
        </div>
        <button className="btn-primary" onClick={openCreate}>+ New Schedule</button>
      </div>

      {error && <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">{error}</div>}

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Frequency</th>
                <th className="px-4 py-3">Time (UTC)</th>
                <th className="px-4 py-3">Format</th>
                <th className="px-4 py-3">Recipients</th>
                <th className="px-4 py-3">Last Run</th>
                <th className="px-4 py-3">Next Run</th>
                <th className="px-4 py-3">Active</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={10} className="px-4 py-8 text-center text-slate-400">Loading...</td></tr>}
              {!loading && schedules.length === 0 && (
                <tr><td colSpan={10} className="px-4 py-8 text-center text-slate-400">No scheduled reports yet.</td></tr>
              )}
              {!loading && schedules.map((s) => (
                <tr key={s.id} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-medium text-slate-800">{s.name}</td>
                  <td className="px-4 py-3 text-slate-600">{REPORT_TYPES.find((t) => t.value === s.report_type)?.label}</td>
                  <td className="px-4 py-3 text-slate-600 capitalize">{s.frequency.toLowerCase()}</td>
                  <td className="px-4 py-3 text-slate-600">{s.execution_time}</td>
                  <td className="px-4 py-3 text-slate-600">{s.format}</td>
                  <td className="max-w-[160px] truncate px-4 py-3 text-slate-500">{s.recipients.join(", ") || "—"}</td>
                  <td className="px-4 py-3 text-slate-500">
                    {s.last_run_at ? new Date(s.last_run_at).toLocaleString() : "Never"}
                    {s.last_run_status && (
                      <span className={`ml-1 ${s.last_run_status === "FAILED" ? "text-red-500" : "text-emerald-600"}`}>
                        ({s.last_run_status})
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{s.next_run_at && s.is_active ? new Date(s.next_run_at).toLocaleString() : "—"}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleToggle(s)}
                      className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${s.is_active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}
                    >
                      {s.is_active ? "Active" : "Inactive"}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button className="mr-3 text-sm font-medium text-slate-500 hover:underline" onClick={() => handleRunNow(s)}>Run Now</button>
                    <button className="mr-3 text-sm font-medium text-brand-500 hover:underline" onClick={() => openEdit(s)}>Edit</button>
                    <button className="text-sm font-medium text-red-600 hover:underline" onClick={() => setDeleteTarget(s)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {modalOpen && (
        <Modal title={editing ? "Edit Schedule" : "New Schedule"} onClose={() => setModalOpen(false)} wide>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="form-label">Name</label>
              <input className="form-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>

            <div>
              <label className="form-label">Report Type</label>
              <select className="form-input" value={form.report_type} disabled={!!editing} onChange={(e) => setForm({ ...form, report_type: e.target.value as ReportType })}>
                {REPORT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>

            <div>
              <label className="form-label">Export Format</label>
              <select className="form-input" value={form.format} onChange={(e) => setForm({ ...form, format: e.target.value as ReportFormat })}>
                <option value="CSV">CSV</option>
                <option value="PDF">PDF</option>
              </select>
            </div>

            <div>
              <label className="form-label">Frequency</label>
              <select className="form-input" value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value as ScheduleFrequency })}>
                <option value="DAILY">Daily</option>
                <option value="WEEKLY">Weekly</option>
                <option value="MONTHLY">Monthly</option>
              </select>
            </div>

            <div>
              <label className="form-label">Execution Time (UTC)</label>
              <input type="time" className="form-input" value={form.execution_time} onChange={(e) => setForm({ ...form, execution_time: e.target.value })} />
            </div>

            {form.frequency === "WEEKLY" && (
              <div>
                <label className="form-label">Day of Week</label>
                <select className="form-input" value={form.day_of_week ?? ""} onChange={(e) => setForm({ ...form, day_of_week: Number(e.target.value) })}>
                  <option value="">Select a day</option>
                  {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                </select>
              </div>
            )}
            {form.frequency === "MONTHLY" && (
              <div>
                <label className="form-label">Day of Month</label>
                <input type="number" min={1} max={28} className="form-input" value={form.day_of_month ?? ""} onChange={(e) => setForm({ ...form, day_of_month: Number(e.target.value) })} />
              </div>
            )}

            <div className="sm:col-span-2">
              <label className="form-label">Recipients (comma-separated emails)</label>
              <input className="form-input" value={recipientInput} onChange={(e) => setRecipientInput(e.target.value)} placeholder="admin@company.com, manager@company.com" />
              <p className="mt-1 text-xs text-slate-400">
                Recipients are stored for reference; each run is saved to Report History regardless — email delivery isn't wired up in this build yet.
              </p>
            </div>

            <div className="flex items-center gap-2 sm:col-span-2">
              <input type="checkbox" id="is_active" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
              <label htmlFor="is_active" className="text-sm text-slate-700">Active</label>
            </div>
          </div>

          <div className="mt-6 flex justify-end gap-3">
            <button className="btn-outline" disabled={saving} onClick={() => setModalOpen(false)}>Cancel</button>
            <button className="btn-primary" disabled={saving || !form.name} onClick={handleSave}>
              {saving ? "Saving..." : editing ? "Save Changes" : "Create Schedule"}
            </button>
          </div>
        </Modal>
      )}

      {deleteTarget && (
        <Modal title="Delete schedule?" onClose={() => setDeleteTarget(null)}>
          <p className="mb-4 text-sm text-slate-600">
            This permanently deletes "{deleteTarget.name}". Past reports it already generated stay in Report History.
          </p>
          <div className="flex justify-end gap-3">
            <button className="btn-outline" onClick={() => setDeleteTarget(null)}>Cancel</button>
            <button className="btn bg-red-600 text-white hover:bg-red-700" onClick={handleDelete}>Delete</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
