import { useAuth } from "../context/AuthContext";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="block text-xs text-slate-500">{label}</span>
      <div className="text-sm text-slate-900">{value}</div>
    </div>
  );
}

export default function Profile() {
  const { user } = useAuth();

  if (!user) return null;

  return (
    <div className="max-w-3xl p-6">
      <h1 className="mb-4 text-2xl font-bold text-slate-900">My Profile</h1>

      <div className="rounded-lg bg-white p-6 shadow-sm">
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <Field label="Name" value={user.name} />
          <Field label="Email" value={user.email} />
          <Field label="Company" value={user.company.name} />

          <div>
            <span className="block text-xs text-slate-500">Role</span>
            <span className="mt-0.5 inline-block rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-semibold text-brand-700">
              {user.role.replace("_", " ")}
            </span>
          </div>

          <div>
            <span className="block text-xs text-slate-500">Account Status</span>
            <span
              className={`mt-0.5 inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                user.status === "ACTIVE"
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-slate-200 text-slate-700"
              }`}
            >
              {user.status}
            </span>
          </div>

          <Field
            label="Last Login"
            value={user.last_login ? new Date(user.last_login).toLocaleString() : "Never"}
          />
        </div>

        <hr className="my-6 border-slate-200" />

        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Company Details
        </p>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <Field label="Industry" value={user.company.industry ?? "—"} />
          <Field label="Company Email" value={user.company.email} />
          <Field label="Phone" value={user.company.phone ?? "—"} />
          <Field label="Address" value={user.company.address ?? "—"} />
        </div>
      </div>
    </div>
  );
}
