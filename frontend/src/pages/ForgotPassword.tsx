import { Link } from "react-router-dom";

/**
 * Placeholder screen. Task 1 scope covers registration, login, JWT auth,
 * and profile only — password reset is a separate backend flow (email
 * token generation/verification) to be implemented in a later task.
 */
export default function ForgotPassword() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">Forgot password</h1>
        <p className="mt-2 mb-4 text-sm text-slate-500">
          This flow will be implemented in a follow-up task. For now, please contact your
          company admin to reset your password.
        </p>
        <Link to="/login" className="text-sm font-medium text-brand-500 hover:underline">
          Back to sign in
        </Link>
      </div>
    </div>
  );
}
