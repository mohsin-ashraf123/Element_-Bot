import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../../lib/auth";

export function ProtectedRoute() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="auth-loading">
        <div className="auth-loading-card">
          <div className="auth-logo">
            <span className="auth-logo-dot" />
          </div>
          <p>Loading PairFlow…</p>
        </div>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}
