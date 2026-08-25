import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { LogoutFlowProvider } from "./auth/LogoutFlow";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { useLastAppPath, CONFIRM_LOGOUT_STATE } from "./auth/backNavGuard";
import { FullPageLoader } from "./components/FullPageLoader";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";

/**
 * The `/login` route, and the back-navigation guard in one place.
 *
 * A signed-in user never sees the login screen: they are returned to the page
 * they came from, carrying a flag that opens the sign-out confirmation. That
 * covers the back gesture, a typed URL and a restored tab with the same rule,
 * and — unlike a popstate listener — it cannot leave the router's idea of the
 * location out of step with the address bar.
 */
function LoginRoute() {
  const { status } = useAuth();
  const lastAppPath = useLastAppPath();

  if (status === "loading") {
    return <FullPageLoader label="Checking your session" />;
  }

  if (status === "authenticated") {
    return (
      <Navigate to={lastAppPath} replace state={{ [CONFIRM_LOGOUT_STATE]: true }} />
    );
  }

  return <Login />;
}

export function App() {
  return (
    <LogoutFlowProvider>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<Dashboard />} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </LogoutFlowProvider>
  );
}
