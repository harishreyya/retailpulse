import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, Link } from "react-router-dom";
import { registerCompany } from "../api/auth";
import { useAuth } from "../context/AuthContext";
import type { CompanyRegisterPayload } from "../types";

export default function Register() {
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<CompanyRegisterPayload>();

  const password = watch("password");

  const onSubmit = async (data: CompanyRegisterPayload) => {
    setServerError(null);
    setIsSubmitting(true);
    try {
      const result = await registerCompany(data);
      await setSession(result.tokens, result.user);
      navigate("/dashboard");
    } catch (err: any) {
      setServerError(err?.response?.data?.detail ?? "Registration failed. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-2xl rounded-xl bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-bold text-slate-900">Register your company</h1>
        <p className="mt-2 mb-6 text-sm text-slate-500">
          Create your company workspace and admin account on RetailPulse Analytics.
        </p>

        {serverError && (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">
            {serverError}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="form-label">Company Name</label>
              <input
                className={`form-input ${errors.company_name ? "input-error" : ""}`}
                {...register("company_name", { required: "Company name is required" })}
              />
              {errors.company_name && <span className="form-error-text">{errors.company_name.message}</span>}
            </div>

            <div>
              <label className="form-label">Industry</label>
              <input className="form-input" {...register("industry")} />
            </div>

            <div>
              <label className="form-label">Company Email</label>
              <input
                type="email"
                className={`form-input ${errors.company_email ? "input-error" : ""}`}
                {...register("company_email", { required: "Company email is required" })}
              />
              {errors.company_email && <span className="form-error-text">{errors.company_email.message}</span>}
            </div>

            <div>
              <label className="form-label">Company Phone Number</label>
              <input className="form-input" {...register("company_phone")} />
            </div>

            <div className="sm:col-span-2">
              <label className="form-label">Company Address</label>
              <input className="form-input" {...register("company_address")} />
            </div>
          </div>

          <p className="mb-3 mt-6 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Owner / Admin details
          </p>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="form-label">Owner Name</label>
              <input
                className={`form-input ${errors.owner_name ? "input-error" : ""}`}
                {...register("owner_name", { required: "Owner name is required" })}
              />
              {errors.owner_name && <span className="form-error-text">{errors.owner_name.message}</span>}
            </div>

            <div>
              <label className="form-label">Owner Email</label>
              <input
                type="email"
                className={`form-input ${errors.owner_email ? "input-error" : ""}`}
                {...register("owner_email", { required: "Owner email is required" })}
              />
              {errors.owner_email && <span className="form-error-text">{errors.owner_email.message}</span>}
            </div>

            <div>
              <label className="form-label">Password</label>
              <input
                type="password"
                className={`form-input ${errors.password ? "input-error" : ""}`}
                {...register("password", {
                  required: "Password is required",
                  minLength: { value: 8, message: "Password must be at least 8 characters" },
                })}
              />
              {errors.password && <span className="form-error-text">{errors.password.message}</span>}
            </div>

            <div>
              <label className="form-label">Confirm Password</label>
              <input
                type="password"
                className={`form-input ${errors.confirm_password ? "input-error" : ""}`}
                {...register("confirm_password", {
                  required: "Please confirm your password",
                  validate: (value) => value === password || "Passwords do not match",
                })}
              />
              {errors.confirm_password && <span className="form-error-text">{errors.confirm_password.message}</span>}
            </div>
          </div>

          <button type="submit" className="btn-primary mt-6 w-full" disabled={isSubmitting}>
            {isSubmitting ? "Creating account..." : "Register Company"}
          </button>

          <p className="mt-4 text-center text-sm text-slate-600">
            Already have an account?{" "}
            <Link to="/login" className="font-medium text-brand-500 hover:underline">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
