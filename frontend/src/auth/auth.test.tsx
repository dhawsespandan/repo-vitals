import { screen, waitFor, within } from "@testing-library/react";
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
