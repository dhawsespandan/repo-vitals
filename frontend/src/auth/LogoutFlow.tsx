/**
 * Owns the sign-out confirmation, because two very different things ask for
 * it: the "Sign out" button in the nav, and the back-navigation guard on the
 * `/login` route. Sharing one piece of state keeps them from ever opening two
 * dialogs, and keeps the confirm/cancel behaviour identical whichever way the
 * user got here.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "./AuthContext";
import { LogoutConfirm } from "./LogoutConfirm";
import { wantsLogoutConfirm } from "./backNavGuard";

interface LogoutFlowValue {
  open: boolean;
  requestLogout: () => void;
}

const LogoutFlowContext = createContext<LogoutFlowValue | null>(null);

export function LogoutFlowProvider({ children }: { children: ReactNode }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);

  const requestLogout = useCallback(() => setOpen(true), []);
  const cancel = useCallback(() => setOpen(false), []);

  const confirm = useCallback(async () => {
    await logout();
    setOpen(false);
    navigate("/login", { replace: true });
  }, [logout, navigate]);

  // The back-navigation guard bounces a signed-in user off `/login` and asks,
  // through router state, for the dialog to open here. Consume the flag
  // immediately so a refresh of the restored page does not re-open it.
  useEffect(() => {
    if (!wantsLogoutConfirm(location.state)) return;
    setOpen(true);
    navigate(`${location.pathname}${location.search}`, {
      replace: true,
      state: null,
    });
  }, [location.state, location.pathname, location.search, navigate]);

  const value = useMemo<LogoutFlowValue>(
    () => ({ open, requestLogout }),
    [open, requestLogout],
  );

  return (
    <LogoutFlowContext.Provider value={value}>
      {children}
      <LogoutConfirm
        open={open}
        onCancel={cancel}
        onConfirm={() => {
          void confirm();
        }}
      />
    </LogoutFlowContext.Provider>
  );
}

export function useLogoutFlow(): LogoutFlowValue {
  const value = useContext(LogoutFlowContext);
  if (!value) {
    throw new Error("useLogoutFlow must be used inside <LogoutFlowProvider>.");
  }
  return value;
}
