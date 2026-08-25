import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "./AuthContext";
import { AppShell } from "../components/AppShell";
import { FullPageLoader } from "../components/FullPageLoader";

/**
 * Gate for every signed-in route.
 *
 * While the session is still being fetched it renders a loader rather than a
 * redirect: bouncing to `/login` first and to the dashboard a moment later is
 * what produces the login-screen flash on a hard refresh, and it would also
 * lose the location the user actually asked for.
 */
export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <FullPageLoader label="Checking your session" />;
  }

  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
