/**
 * Session state for the whole app, bootstrapped once from `/api/auth/session/`.
 *
 * `status` is deliberately three-valued. Collapsing "still checking" into
 * "signed out" is what makes an authenticated user see a flash of the login
 * screen on every cold load, and Phase 1's acceptance criteria say the login
 * screen appears only on a deliberate act.
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

import { GITHUB_LOGIN_URL, getSession, postLogout } from "../api/client";
import type { User } from "../types";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export interface AuthValue {
  status: AuthStatus;
  user: User | null;
  login: () => void;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<User | null>(null);

  const refresh = useCallback(async () => {
    try {
      const session = await getSession();
      setUser(session.user);
      setStatus(session.authenticated ? "authenticated" : "anonymous");
    } catch {
      // A network failure is not proof of being signed out, but the app has
      // nothing to render without a session either. Treat it as anonymous and
      // let the user retry by signing in.
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    // The OAuth dance is several full-page redirects (this app -> GitHub ->
    // the callback -> /dashboard), not in-app route changes. Pressing Back
    // from /dashboard can restore the *frozen* pre-login page straight from
    // the browser's back-forward cache: no JavaScript re-runs, including this
    // very session check, so the stale anonymous UI reappears untouched and
    // the back-navigation guard — which depends on this check running — never
    // gets a chance to intervene. `pageshow` with `event.persisted` is the
    // documented signal for exactly this restoration; force a fresh check
    // (through "loading", so a stale render never flashes) whenever it fires.
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        setStatus("loading");
        void refresh();
      }
    };
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, [refresh]);

  const login = useCallback(() => {
    // Full navigation: the OAuth dance needs the browser, not fetch.
    window.location.assign(GITHUB_LOGIN_URL);
  }, []);

  const logout = useCallback(async () => {
    try {
      await postLogout();
    } finally {
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  const value = useMemo<AuthValue>(
    () => ({ status, user, login, logout, refresh }),
    [status, user, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside <AuthProvider>.");
  }
  return value;
}
