import { useState } from "react";
import NotificationCenter from "./NotificationCenter";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { UserRole } from "../types";

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5 shrink-0">
      <path d={d} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

interface NavItem {
  to: string;
  label: string;
  icon: JSX.Element;
  roles?: UserRole[];
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const ADMIN_ANALYST: UserRole[] = ["COMPANY_ADMIN", "SUPER_ADMIN", "ANALYST"];
const ADMIN_ONLY: UserRole[] = ["COMPANY_ADMIN", "SUPER_ADMIN"];

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { to: "/dashboard", label: "Dashboard", icon: <Icon d="M3 12l2-2 7-7 7 7 2 2M5 10v10a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V10" /> },
      { to: "/analytics", label: "Analytics", icon: <Icon d="M4 19V5m0 14h16M8 19v-6m4 6V9m4 10v-4" />, roles: ADMIN_ANALYST },
    ],
  },
  {
    label: "Sales",
    items: [
      { to: "/sales", label: "Sales", icon: <Icon d="M3 3h2l.4 2M7 13h10l3-8H5.4M7 13 5.4 5M7 13l-2.3 4.6A1 1 0 0 0 5.6 19H17M9 22a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm8 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z" />, roles: ADMIN_ANALYST },
      { to: "/customers", label: "Customers", icon: <Icon d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7 4h4m-2-2v4" />, roles: ADMIN_ANALYST },
      { to: "/customer-analytics", label: "Customer Analytics", icon: <Icon d="M9 19v-6m4 6V9m4 10V5M5 19h14" />, roles: ADMIN_ANALYST },
    ],
  },
  {
    label: "Inventory",
    items: [
      { to: "/inventory", label: "Inventory", icon: <Icon d="M3 7 12 3l9 4-9 4-9-4Zm0 0v10l9 4m0-14v14m9-14v10l-9 4" />, roles: ADMIN_ANALYST },
      { to: "/products", label: "Products", icon: <Icon d="M20 7 12 3 4 7m16 0-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />, roles: ADMIN_ONLY },
      { to: "/categories", label: "Categories", icon: <Icon d="M4 4h7v7H4zm9 0h7v7h-7zm0 9h7v7h-7zM4 13h7v7H4z" />, roles: ADMIN_ONLY },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { to: "/forecasting", label: "Demand Forecasting", icon: <Icon d="M3 17 9 11l4 4 8-8M15 7h6v6" />, roles: ADMIN_ANALYST },
      { to: "/inventory/forecast", label: "Inventory Forecast", icon: <Icon d="M9 19v-6m4 6V11m4 8V7m4 12V3" />, roles: ADMIN_ANALYST },
      { to: "/reports", label: "Reports", icon: <Icon d="M9 17v-6m4 6V7m4 10v-4M5 21h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2Z" />, roles: ADMIN_ANALYST },
    ],
  },
  {
    label: "Data",
    items: [
      {
  to: "/data-quality",
  label: "Data Quality",
  icon: <Icon d="M9 12l2 2 4-4m5 2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />,
  roles: ADMIN_ONLY,
},
      { to: "/data-import", label: "Data Import", icon: <Icon d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />, roles: ADMIN_ONLY },
      { to: "/scheduled-reports", label: "Scheduled Reports", icon: <Icon d="M12 8v4l3 3m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />, roles: ADMIN_ONLY },
      { to: "/audit-logs", label: "Audit Logs", icon: <Icon d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m-6 7h6m-6 4h6" />, roles: ADMIN_ONLY },
    ],
  },
  {
    label: "Account",
    items: [
      { to: "/profile", label: "Profile", icon: <Icon d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" /> },
    ],
  },
];

export default function AppShell() {
  const { user, logout } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const visibleGroups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.roles || (user && item.roles.includes(user.role))),
  })).filter((group) => group.items.length > 0);

  const sidebarContent = (
    <>
      <div className="flex h-16 shrink-0 items-center gap-2.5 border-b border-slate-100 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-500 text-sm font-bold text-white">
          R
        </div>
        <span className="text-base font-semibold text-navy">RetailPulse</span>
        {/* Close button only shown inside the mobile drawer. */}
        <button
          className="ml-auto rounded-md p-1 text-slate-400 hover:bg-slate-100 lg:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-label="Close menu"
        >
          <Icon d="M6 18 18 6M6 6l12 12" />
        </button>
      </div>

      <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-5">
        {visibleGroups.map((group) => (
          <div key={group.label}>
            <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{group.label}</p>
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={() => setDrawerOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-brand-50 text-brand-700"
                        : "text-slate-600 hover:bg-slate-50 hover:text-navy"
                    }`
                  }
                >
                  {item.icon}
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="shrink-0 border-t border-slate-100 p-3">
        <div className="flex items-center gap-3 rounded-md px-2 py-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">
            {user?.name?.[0]?.toUpperCase() ?? "?"}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-navy">{user?.name}</p>
            <p className="truncate text-xs text-slate-500">{user?.role.replace("_", " ")}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => logout()}
          className="mt-1 flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-navy"
        >
          <Icon d="M9 21H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h4m5 14 5-5-5-5m5 5H9" />
          Log out
        </button>
      </div>
    </>
  );

  return (
    <div className="min-h-screen w-full max-w-[100vw] overflow-x-hidden bg-paper">
      {/* Mobile top bar — hidden on desktop (lg:hidden), where the fixed sidebar takes over. */}
      <div className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-4 lg:hidden">
        <button
          className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100"
          onClick={() => setDrawerOpen(true)}
          aria-label="Open menu"
        >
          <Icon d="M4 6h16M4 12h16M4 18h16" />
        </button>
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-500 text-xs font-bold text-white">
          R
        </div>
        <span className="text-sm font-semibold text-navy">RetailPulse</span>
        <div className="ml-auto"><NotificationCenter /></div>
      </div>

      {/* Backdrop, mobile drawer only */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      {/* Sidebar: slide-over drawer on mobile, permanent fixed column on desktop (lg:). */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 max-w-[80vw] transform flex-col border-r border-slate-200 bg-white transition-transform duration-200 ease-in-out
          ${drawerOpen ? "translate-x-0" : "-translate-x-full"}
          lg:w-60 lg:max-w-none lg:translate-x-0`}
      >
        {sidebarContent}
      </aside>

      <div className="flex min-h-screen min-w-0 flex-col lg:ml-60">
        <div className="sticky top-0 z-30 hidden h-14 items-center justify-end border-b border-slate-200 bg-white/90 px-6 backdrop-blur lg:flex">
          <NotificationCenter />
        </div>
        <main className="min-w-0 flex-1 overflow-x-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
