/**
 * Back-navigation guard.
 *
 * Phase 1 requires that "back-navigation alone can never log a user out or
 * expose the login screen". The naive implementations both fail that: a
 * popstate listener that calls `history.pushState` desynchronises the router
 * from the URL, and a listener that logs the user out turns a browser gesture
 * into a destructive act.
 *
 * So the guard is not a listener at all — it is a rule about what the `/login`
 * route may render. A signed-in user who arrives at `/login` by any means
 * (back gesture, typed URL, restored tab) is sent straight back to the page
 * they were on, carrying a flag that opens the logout confirmation. The login
 * screen renders only once the session is actually gone, which happens only
 * when they confirm.
 */

import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

/** Routes that show the signed-out experience. */
export const AUTH_ENTRY_PATHS = ["/", "/login"];

/** Where a signed-in user is sent when no better history exists. */
export const DEFAULT_APP_PATH = "/dashboard";

/**
 * Location-state flag asking the destination to open the logout confirmation.
 * Travelling in router state rather than in a query string keeps it out of the
 * address bar, so a shared or bookmarked URL never re-opens the dialog.
 */
export const CONFIRM_LOGOUT_STATE = "repoVitalsConfirmLogout";

export interface ConfirmLogoutState {
  [CONFIRM_LOGOUT_STATE]?: boolean;
}

export function isAuthEntryPath(pathname: string): boolean {
  return AUTH_ENTRY_PATHS.includes(normalise(pathname));
}

function normalise(pathname: string): string {
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }
  return pathname;
}

/**
 * Remembers the last in-app (non-login) location, so cancelling the dialog
 * puts the user back exactly where the back gesture took them from.
 */
export function useLastAppPath(): string {
  const location = useLocation();
  const lastAppPath = useRef(DEFAULT_APP_PATH);

  useEffect(() => {
    if (!isAuthEntryPath(location.pathname)) {
      lastAppPath.current = `${location.pathname}${location.search}`;
    }
  }, [location.pathname, location.search]);

  return lastAppPath.current;
}

/** Reads the confirm-logout flag off a router location's state. */
export function wantsLogoutConfirm(state: unknown): boolean {
  return Boolean(
    state && typeof state === "object" && CONFIRM_LOGOUT_STATE in state
      ? (state as ConfirmLogoutState)[CONFIRM_LOGOUT_STATE]
      : false,
  );
}
