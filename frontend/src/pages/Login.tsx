import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, Link } from "react-router-dom";
import { login } from "../api/auth";
import { useAuth } from "../context/AuthContext";
import type { LoginPayload } from "../types";

export default function Login() {
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginPayload>();

  const onSubmit = async (data: LoginPayload) => {
    setServerError(null);
    setIsSubmitting(true);
    try {
      const tokens = await login(data);
      await setSession(tokens);
      navigate("/dashboard");
    } catch (err: any) {
      setServerError(err?.response?.data?.detail ?? "Invalid email or password");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">Sign in to RetailPulse</h1>
        <p className="mt-2 mb-6 text-sm text-slate-500">
          Access your company's analytics dashboard.
        </p>

        {serverError && (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">
            {serverError}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="mb-4">
            <label className="form-label">Email</label>
            <input
              type="email"
              className={`form-input ${errors.email ? "input-error" : ""}`}
              {...register("email", { required: "Email is required" })}
            />
            {errors.email && <span className="form-error-text">{errors.email.message}</span>}
          </div>

          <div className="mb-2">
            <label className="form-label">Password</label>
            <input
              type="password"
              className={`form-input ${errors.password ? "input-error" : ""}`}
              {...register("password", { required: "Password is required" })}
            />
            {errors.password && <span className="form-error-text">{errors.password.message}</span>}
          </div>

          <div className="mb-4 text-right text-sm">
            <Link to="/forgot-password" className="text-brand-500 hover:underline">
              Forgot password?
            </Link>
          </div>

          <button type="submit" className="btn-primary w-full" disabled={isSubmitting}>
            {isSubmitting ? "Signing in..." : "Sign In"}
          </button>

          <p className="mt-4 text-center text-sm text-slate-600">
            Don't have a company yet?{" "}
            <Link to="/register" className="font-medium text-brand-500 hover:underline">Register</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
