import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { App } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import type { SessionResponse } from "../types";

export const SIGNED_IN: SessionResponse = {
  authenticated: true,
  user: {
    id: "6e1f7f6e-1f4a-4e0a-9c8a-4c2b6a5d0e11",
    username: "arjun-dev",
    name: "Arjun D",
    email: "arjun@example.com",
    avatarUrl: "",
  },
};

export const SIGNED_OUT: SessionResponse = { authenticated: false, user: null };

interface StubOptions {
  session: SessionResponse;
  /** Status returned by POST /api/auth/logout/. */
  logoutStatus?: number;
}

/**
 * Stubs `fetch` for the two Phase 1 endpoints. Hand-rolled rather than pulled
 * from a mocking library: two routes do not justify the dependency, and an
 * explicit switch makes it obvious in each test which calls were expected.
 */
export function stubFetch({ session, logoutStatus = 204 }: StubOptions) {
  const calls: string[] = [];

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push(`${method} ${url}`);

    if (url.endsWith("/api/auth/session/")) {
      return new Response(JSON.stringify(session), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.endsWith("/api/auth/logout/")) {
      return new Response(null, { status: logoutStatus });
    }
    return new Response(JSON.stringify({ code: "not_found", message: "no" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  });

  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function renderApp(initialEntries: string[] = ["/dashboard"]) {
  return render(
    <MemoryRouter
      initialEntries={initialEntries}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
