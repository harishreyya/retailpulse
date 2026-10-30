import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import AppShell from "./components/AppShell";

import Register from "./pages/Register";
import Login from "./pages/Login";
import ForgotPassword from "./pages/ForgotPassword";
import Dashboard from "./pages/Dashboard";
import Profile from "./pages/Profile";
import Categories from "./pages/Categories";
import Products from "./pages/Products";
import Sales from "./pages/Sales";
import Inventory from "./pages/inventory";
import Analytics from "./pages/Analytics";
import Customers from "./pages/Customers";
import CustomerProfile from "./pages/CustomerProfile";
import CustomerAnalytics from "./pages/CustomerAnalytics";
import Forecasting from "./pages/Forecasting";
import InventoryForecast from "./pages/InventoryForecast";
import DataImport from "./pages/DataImport";
import Reports from "./pages/Reports";
import ScheduledReports from "./pages/ScheduledReports";
import AuditLogs from "./pages/AuditLogs";
import DataQuality from "./pages/DataQuality";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/register" element={<Register />} />
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />

            <Route element={<ProtectedRoute />}>
              <Route element={<AppShell />}>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/profile" element={<Profile />} />
              </Route>
            </Route>

            <Route element={<ProtectedRoute allowedRoles={["COMPANY_ADMIN", "SUPER_ADMIN"]} />}>
              <Route element={<AppShell />}>
                <Route path="/categories" element={<Categories />} />
                <Route path="/products" element={<Products />} />
                <Route path="/data-import" element={<DataImport />} />
                <Route path="/scheduled-reports" element={<ScheduledReports />} />
                <Route path="/audit-logs" element={<AuditLogs />} />
                <Route path="/data-quality" element={<DataQuality />} />
              </Route>
            </Route>

            <Route element={<ProtectedRoute allowedRoles={["COMPANY_ADMIN", "SUPER_ADMIN", "ANALYST"]} />}>
              <Route element={<AppShell />}>
                <Route path="/sales" element={<Sales />} />
                <Route path="/inventory" element={<Inventory />} />
                <Route path="/analytics" element={<Analytics />} />
                <Route path="/reports" element={<Reports />} />
                <Route path="/customers" element={<Customers />} />
                <Route path="/customers/:customerId" element={<CustomerProfile />} />
                <Route path="/customer-analytics" element={<CustomerAnalytics />} />
                <Route path="/forecasting" element={<Forecasting />} />
                <Route path="/inventory/forecast" element={<InventoryForecast />} />
              </Route>
            </Route>

            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
