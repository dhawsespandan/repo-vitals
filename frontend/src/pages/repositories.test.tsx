import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { REPOSITORY, SIGNED_IN, renderApp, stubFetch } from "../test/renderApp";

beforeEach(() => {
  vi.unstubAllGlobals();
});

async function openRegisterDialog() {
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: /register repository/i }),
  );
  return user;
}

describe("repository list", () => {
  it("renders the empty state before anything is registered", async () => {
    stubFetch({ session: SIGNED_IN, repositories: [] });

    renderApp(["/dashboard"]);

    expect(await screen.findByText(/no repositories yet/i)).toBeInTheDocument();
  });

  it("renders a card per registered repository", async () => {
    stubFetch({ session: SIGNED_IN, repositories: [REPOSITORY] });

    renderApp(["/dashboard"]);

    const card = await screen.findByTestId("repo-card");
    expect(within(card).getByText("checkout-service")).toBeInTheDocument();
    expect(
      within(card).getByText("arjun-dev/checkout-service"),
    ).toBeInTheDocument();
    // Nothing is scanned in Phase 2, and the card says so rather than
    // implying a score that does not exist.
    expect(within(card).getByText(/not scanned yet/i)).toBeInTheDocument();
  });
});

describe("registration outcomes", () => {
  it("adds the card when the server accepts the repository", async () => {
    stubFetch({ session: SIGNED_IN, repositories: [] });

    renderApp(["/dashboard"]);
    const user = await openRegisterDialog();

    await user.type(
      screen.getByLabelText(/repository url/i),
      "github.com/arjun-dev/checkout-service",
    );
    await user.click(screen.getByRole("button", { name: /^register$/i }));

    expect(await screen.findByTestId("repo-card")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-notice")).toHaveTextContent(
      /arjun-dev\/checkout-service is now monitored/i,
    );
  });

  it.each([
    [
      "no_write_access",
      403,
      "You need write or collaborator access on this repository to monitor it here.",
    ],
    [
      "ecosystem_unsupported",
      422,
      "This repository's dependency ecosystem isn't supported yet. We currently support Node.js/npm projects.",
    ],
    [
      "repo_inaccessible",
      404,
      "We couldn't access this repository. Check the link, or make sure it's public.",
    ],
    [
      "repo_empty",
      422,
      "This repository appears to be empty — there's nothing to scan.",
    ],
    [
      "private_repo_not_owned",
      403,
      "This private repository belongs to another owner. Repo Vitals only monitors private repositories in your own account.",
    ],
  ])(
    "shows the server's message verbatim for %s",
    async (code, status, message) => {
      stubFetch({
        session: SIGNED_IN,
        repositories: [],
        register: { status, body: { code, message } },
      });

      renderApp(["/dashboard"]);
      const user = await openRegisterDialog();

      await user.type(screen.getByLabelText(/repository url/i), "github.com/o/r");
      await user.click(screen.getByRole("button", { name: /^register$/i }));

      expect(await screen.findByTestId("register-feedback")).toHaveTextContent(
        message,
      );
      // A rejection must not create a card.
      expect(screen.queryByTestId("repo-card")).not.toBeInTheDocument();
    },
  );

  it("points at the existing row when the repository is already registered", async () => {
    stubFetch({
      session: SIGNED_IN,
      repositories: [REPOSITORY],
      register: {
        status: 200,
        body: {
          code: "already_registered",
          message: "You're already monitoring this repository.",
          repository: REPOSITORY,
        },
      },
    });

    renderApp(["/dashboard"]);
    const user = await openRegisterDialog();

    await user.type(
      screen.getByLabelText(/repository url/i),
      "github.com/arjun-dev/checkout-service",
    );
    await user.click(screen.getByRole("button", { name: /^register$/i }));

    // The dialog closes and the row the user was looking for is marked,
    // rather than a second card appearing.
    await waitFor(() =>
      expect(screen.queryByTestId("add-repo-backdrop")).not.toBeInTheDocument(),
    );
    expect(screen.getAllByTestId("repo-card")).toHaveLength(1);
    expect(screen.getByTestId("repo-card")).toHaveAttribute(
      "data-highlighted",
      "true",
    );
  });
});

describe("removal", () => {
  it("asks for confirmation and keeps the card when cancelled", async () => {
    stubFetch({ session: SIGNED_IN, repositories: [REPOSITORY] });

    renderApp(["/dashboard"]);
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: /remove arjun-dev\/checkout-service/i }),
    );
    await user.click(screen.getByRole("button", { name: /keep monitoring/i }));

    expect(screen.getByTestId("repo-card")).toBeInTheDocument();
  });

  it("removes the card once the deletion is confirmed", async () => {
    const { calls } = stubFetch({
      session: SIGNED_IN,
      repositories: [REPOSITORY],
    });

    renderApp(["/dashboard"]);
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", { name: /remove arjun-dev\/checkout-service/i }),
    );
    await user.click(screen.getByRole("button", { name: /^remove$/i }));

    await waitFor(() =>
      expect(screen.queryByTestId("repo-card")).not.toBeInTheDocument(),
    );
    expect(calls).toContain(`DELETE /api/repositories/${REPOSITORY.id}/`);
  });
});
