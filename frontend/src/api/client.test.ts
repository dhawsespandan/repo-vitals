import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, getSession } from "./client";

function mockFetch(response: Response) {
  const fetchMock = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) => response,
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Narrows the recorded call to the shape every assertion below wants. */
function callArgs(
  fetchMock: ReturnType<typeof mockFetch>,
  index = 0,
): [string, RequestInit] {
  const call = fetchMock.mock.calls[index];
  if (!call) throw new Error(`fetch was not called ${index + 1} time(s)`);
  return [String(call[0]), call[1] ?? {}];
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  document.cookie = "csrftoken=csrf-value-123";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("api client", () => {
  it("prefixes /api and sends credentials", async () => {
    const fetchMock = mockFetch(json({ authenticated: false, user: null }));

    await getSession();

    const [url, init] = callArgs(fetchMock);
    expect(url).toBe("/api/auth/session/");
    expect(init.credentials).toBe("include");
  });

  it("does not send a CSRF header on safe methods", async () => {
    const fetchMock = mockFetch(json({}));

    await api.get("/health/");

    const headers = new Headers(callArgs(fetchMock)[1].headers);
    expect(headers.has("X-CSRFToken")).toBe(false);
  });

  it("echoes the CSRF cookie on unsafe methods", async () => {
    const fetchMock = mockFetch(new Response(null, { status: 204 }));

    await api.post("/auth/logout/");

    const headers = new Headers(callArgs(fetchMock)[1].headers);
    expect(headers.get("X-CSRFToken")).toBe("csrf-value-123");
  });

  it("returns undefined for a 204 rather than trying to parse a body", async () => {
    mockFetch(new Response(null, { status: 204 }));

    await expect(api.post("/auth/logout/")).resolves.toBeUndefined();
  });

  it("raises ApiError carrying the backend code", async () => {
    mockFetch(json({ code: "no_write_access", message: "You need write access." }, 403));

    await expect(api.get("/repositories/")).rejects.toMatchObject({
      code: "no_write_access",
      status: 403,
      message: "You need write access.",
    });
  });

  it("still raises ApiError when the body is not JSON", async () => {
    mockFetch(new Response("<html>502</html>", { status: 502 }));

    const error = await api.get("/health/").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("error");
  });
});
