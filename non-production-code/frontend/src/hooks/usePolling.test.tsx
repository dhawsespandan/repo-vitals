import { act, render } from "@testing-library/react";
import { StrictMode, useCallback, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePolling } from "./usePolling";

/**
 * The property under test is "exactly one loop", and it is the one that broke.
 *
 * The first version guarded the loop with a single `cancelled` boolean ref.
 * When the effect re-ran — React StrictMode's double mount in development, or
 * `enabled` flipping in production — the cleanup set it true and the new run
 * set it straight back to false, so a request already in flight from the old
 * run resolved, read `false`, and scheduled its own timer. Two chains, then
 * three, polling the same endpoint for as long as the tab stayed open.
 *
 * Nothing in the UI shows that. It was found by counting requests in a real
 * browser, which is why it is pinned here.
 */

interface ProbeProps {
  fetcher: () => Promise<{ done: boolean }>;
  enabled?: boolean;
}

function Probe({ fetcher, enabled = true }: ProbeProps) {
  const [value, setValue] = useState<{ done: boolean } | null>(null);
  usePolling({
    fetcher: useCallback(fetcher, [fetcher]),
    shouldContinue: (result: { done: boolean }) => !result.done,
    enabled,
    onResult: setValue,
  });
  return <span data-testid="value">{String(value?.done)}</span>;
}

describe("usePolling", () => {
  let calls: number;
  let answer: { done: boolean };

  const fetcher = () => {
    calls += 1;
    return Promise.resolve(answer);
  };

  beforeEach(() => {
    calls = 0;
    answer = { done: false };
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** Let pending microtasks and any due timers run inside `act`. */
  const advance = async (ms: number) => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  };

  it("schedules exactly one request per interval, even under StrictMode", async () => {
    render(
      <StrictMode>
        <Probe fetcher={fetcher} />
      </StrictMode>,
    );
    await advance(0);

    // StrictMode's double mount issues two immediate requests; what matters is
    // that only one *loop* survives it.
    const afterMount = calls;

    await advance(3000);
    expect(calls - afterMount).toBe(1);

    await advance(3000);
    expect(calls - afterMount).toBe(2);

    await advance(9000);
    expect(calls - afterMount).toBe(5);
  });

  it("stops as soon as the state is terminal", async () => {
    answer = { done: true };

    render(<Probe fetcher={fetcher} />);
    await advance(0);
    const afterMount = calls;

    await advance(30000);

    // A finished repository does not need a request every three seconds for as
    // long as the tab stays open.
    expect(calls).toBe(afterMount);
  });

  it("makes no request at all while disabled", async () => {
    render(<Probe fetcher={fetcher} enabled={false} />);

    await advance(10000);

    expect(calls).toBe(0);
  });

  it("does not schedule while the tab is hidden", async () => {
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);

    render(<Probe fetcher={fetcher} />);
    await advance(0);
    const afterMount = calls;

    await advance(30000);
    expect(calls).toBe(afterMount);

    // Coming back to the tab asks "is it done?" by the act of returning, so
    // the answer should not wait out an interval.
    hidden.mockReturnValue(false);
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await Promise.resolve();
    });
    expect(calls).toBeGreaterThan(afterMount);
  });

  it("unmounting ends the loop", async () => {
    const { unmount } = render(<Probe fetcher={fetcher} />);
    await advance(0);
    const afterMount = calls;

    unmount();
    await advance(30000);

    expect(calls).toBe(afterMount);
  });
});
