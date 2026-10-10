import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  SIGNED_IN,
  SIGNED_OUT,
  renderApp,
  stubFetch,
} from "../test/renderApp";

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("session bootstrap", () => {
  it("sends an anonymous visitor to the login screen", async () => {
    stubFetch({ session: SIGNED_OUT });

    renderApp(["/dashboard"]);

    expect(
      await screen.findByRole("button", { name: /continue with github/i }),
    ).toBeInTheDocument();
  });

  it("shows the signed-in identity on the dashboard", async () => {
    stubFetch({ session: SIGNED_IN });

    renderApp(["/dashboard"]);

    expect(await screen.findByText("arjun-dev")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /dependency health/i })).toBeInTheDocument();
  });

  it("never flashes the login screen while the session is still loading", async () => {
    // A session request that has not resolved yet must render the loader, not
    // a redirect to /login.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );

    renderApp(["/dashboard"]);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /continue with github/i }),
    ).not.toBeInTheDocument();
  });

  it("treats a failed session request as signed out rather than crashing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("offline"))),
    );

    renderApp(["/dashboard"]);

    expect(
      await screen.findByRole("button", { name: /continue with github/i }),
    ).toBeInTheDocument();
  });
});

describe("back-navigation guard", () => {
  it("shows the sign-out confirmation instead of the login screen", async () => {
    stubFetch({ session: SIGNED_IN });

    // A back gesture from /dashboard to /login is, for the router, simply a
    // render of the /login entry while authenticated.
    renderApp(["/dashboard", "/login"]);

    expect(await screen.findByRole("dialog", { name: /sign out\?/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /continue with github/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps the session when the confirmation is cancelled", async () => {
    const { calls } = stubFetch({ session: SIGNED_IN });
    const user = userEvent.setup();

    renderApp(["/dashboard", "/login"]);
    await screen.findByRole("dialog", { name: /sign out\?/i });

    await user.click(screen.getByRole("button", { name: /stay signed in/i }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("heading", { name: /dependency health/i })).toBeInTheDocument();
    expect(calls.filter((c) => c.includes("logout"))).toHaveLength(0);
  });

  it("logs out and shows the login screen only after an explicit confirm", async () => {
    const { calls } = stubFetch({ session: SIGNED_IN });
    const user = userEvent.setup();

    renderApp(["/dashboard", "/login"]);
    const dialog = await screen.findByRole("dialog", { name: /sign out\?/i });

    // Scoped to the dialog: the nav carries a "Sign out" button too, and it is
    // the confirm button that must be the one doing the signing out.
    await user.click(within(dialog).getByRole("button", { name: /^sign out$/i }));

    expect(
      await screen.findByRole("button", { name: /continue with github/i }),
    ).toBeInTheDocument();
    expect(calls).toContain("POST /api/auth/logout/");
  });
});

describe("back-forward cache restoration", () => {
  it("re-checks the session on a bfcache restore instead of trusting the frozen page", async () => {
    // The frozen page is the pre-login /login screen — that's what a
    // bfcache restore hands back verbatim, with no JavaScript re-run.
    const { fetchMock } = stubFetch({ session: SIGNED_OUT });

    renderApp(["/login"]);
    await screen.findByRole("button", { name: /continue with github/i });

    // Between the freeze and the restore, the user completed the OAuth
    // round trip via full-page redirects the frozen page never saw — the
    // server-side session is now authenticated even though the restored
    // page's own state still says otherwise.
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/api/auth/session/")) {
        return new Response(JSON.stringify(SIGNED_IN), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(null, { status: 404 });
    });

    act(() => {
      window.dispatchEvent(
        Object.assign(new Event("pageshow"), { persisted: true }),
      );
    });

    // A stale bfcache restore that isn't re-checked would leave this button
    // on screen forever; the guard depends on the fresh check replacing it.
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: /continue with github/i }),
      ).not.toBeInTheDocument(),
    );
  });

  it("ignores an ordinary pageshow (not a bfcache restore)", async () => {
    const { fetchMock } = stubFetch({ session: SIGNED_OUT });

    renderApp(["/login"]);
    await screen.findByRole("button", { name: /continue with github/i });
    const callsBefore = fetchMock.mock.calls.length;

    act(() => {
      window.dispatchEvent(
        Object.assign(new Event("pageshow"), { persisted: false }),
      );
    });

    // No extra session check for a normal, non-restored pageshow.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock.mock.calls.length).toBe(callsBefore);
  });
});

describe("sign-out button", () => {
  it("asks for confirmation rather than signing out immediately", async () => {
    const { calls } = stubFetch({ session: SIGNED_IN });
    const user = userEvent.setup();

    renderApp(["/dashboard"]);
    await screen.findByText("arjun-dev");

    await user.click(screen.getByRole("button", { name: /sign out/i }));

    expect(screen.getByRole("dialog", { name: /sign out\?/i })).toBeInTheDocument();
    expect(calls.filter((c) => c.includes("logout"))).toHaveLength(0);
  });

  it("closes the dialog on Escape without signing out", async () => {
    const { calls } = stubFetch({ session: SIGNED_IN });
    const user = userEvent.setup();

    renderApp(["/dashboard"]);
    await screen.findByText("arjun-dev");
    await user.click(screen.getByRole("button", { name: /sign out/i }));

    await user.keyboard("{Escape}");

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(calls.filter((c) => c.includes("logout"))).toHaveLength(0);
  });
});
