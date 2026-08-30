import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { App } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import type { Repository, SessionResponse } from "../types";

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

export const REPOSITORY: Repository = {
  id: "b6b0a0f2-2a1e-4f5b-9d3c-7c1b2a3d4e5f",
  owner: "arjun-dev",
  name: "checkout-service",
  fullName: "arjun-dev/checkout-service",
  htmlUrl: "https://github.com/arjun-dev/checkout-service",
  defaultBranch: "main",
  visibility: "public",
  accessLevel: "owner",
  registeredAt: "2026-08-30T09:00:00Z",
};

/** What `POST /api/repositories/` should answer with. */
export interface RegisterStub {
  status: number;
  body: unknown;
}

interface StubOptions {
  session: SessionResponse;
  /** Status returned by POST /api/auth/logout/. */
  logoutStatus?: number;
  /** Rows returned by GET /api/repositories/. */
  repositories?: Repository[];
  register?: RegisterStub;
  /** Status returned by DELETE /api/repositories/{id}/. */
  deleteStatus?: number;
}

/**
 * Stubs `fetch` for the endpoints the SPA actually calls. Hand-rolled rather
 * than pulled from a mocking library: a handful of routes does not justify the
 * dependency, and an explicit switch makes it obvious in each test which calls
 * were expected.
 */
export function stubFetch({
  session,
  logoutStatus = 204,
  repositories = [],
  register,
  deleteStatus = 204,
}: StubOptions) {
  const calls: string[] = [];

  const json = (body: unknown, status: number) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push(`${method} ${url}`);

    if (url.endsWith("/api/auth/session/")) {
      return json(session, 200);
    }
    if (url.endsWith("/api/auth/logout/")) {
      return new Response(null, { status: logoutStatus });
    }
    if (url.endsWith("/api/repositories/") && method === "GET") {
      return json(repositories, 200);
    }
    if (url.endsWith("/api/repositories/") && method === "POST") {
      return json(register?.body ?? REPOSITORY, register?.status ?? 201);
    }
    if (url.includes("/api/repositories/") && method === "DELETE") {
      return new Response(null, { status: deleteStatus });
    }
    return json({ code: "not_found", message: "no" }, 404);
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
