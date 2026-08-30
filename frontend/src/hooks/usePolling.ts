import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Poll while something is still happening, and stop the moment it isn't.
 *
 * Scans are background threads answered by a status endpoint (§2, §10 Phase
 * 3), so the UI's only way to learn a scan finished is to ask again. Three
 * rules make that cheap enough to be respectable on a free tier:
 *
 * **It stops on a terminal state.** `shouldContinue` decides; when it says no,
 * no further request is scheduled. A poll that keeps running after the answer
 * arrived is the version of this that quietly burns a dyno.
 *
 * **It pauses when the tab is hidden and resumes on focus.** A backgrounded
 * tab left open overnight would otherwise spend the night asking a sleeping
 * Render instance about a scan that finished eight hours ago. Resuming fires
 * one immediate request rather than waiting out the interval, because the
 * common case is a user coming back to see whether it is done.
 *
 * **Only one request is ever in flight.** The next tick is scheduled after the
 * previous response lands, not on a fixed clock, so a slow reply cannot stack
 * requests behind it.
 */
export interface PollingOptions<T> {
  /** Fetches the current state. Rejections are handed to `onError`. */
  fetcher: () => Promise<T>;
  /** True while the state means "still working". */
  shouldContinue: (value: T) => boolean;
  /** Milliseconds between the end of one request and the start of the next. */
  intervalMs?: number;
  /** Whether to poll at all — false while the caller has nothing to watch. */
  enabled?: boolean;
  onResult: (value: T) => void;
  onError?: (error: unknown) => void;
}

export function usePolling<T>({
  fetcher,
  shouldContinue,
  intervalMs = 3000,
  enabled = true,
  onResult,
  onError,
}: PollingOptions<T>) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelled = useRef(false);
  const [polling, setPolling] = useState(false);

  // The callbacks are read through refs so that a caller passing inline
  // closures — which is every caller — does not restart the loop on each
  // render. Restarting on every render is the bug that turns a 3 s poll into
  // a request per keystroke.
  const refs = useRef({ fetcher, shouldContinue, onResult, onError });
  refs.current = { fetcher, shouldContinue, onResult, onError };

  const clear = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const tick = useCallback(async () => {
    if (cancelled.current) return;
    try {
      const value = await refs.current.fetcher();
      if (cancelled.current) return;
      refs.current.onResult(value);

      if (!refs.current.shouldContinue(value)) {
        setPolling(false);
        return;
      }
      setPolling(true);
      // Hidden tabs stop scheduling. `visibilitychange` below restarts them.
      if (typeof document !== "undefined" && document.hidden) return;
      timer.current = setTimeout(() => void tick(), intervalMs);
    } catch (error) {
      if (cancelled.current) return;
      setPolling(false);
      refs.current.onError?.(error);
    }
  }, [intervalMs]);

  useEffect(() => {
    cancelled.current = false;
    if (!enabled) {
      clear();
      setPolling(false);
      return () => clear();
    }

    void tick();

    const onVisible = () => {
      // Ask straight away rather than waiting out an interval: someone
      // returning to the tab is asking "is it done?" by the act of returning.
      if (!document.hidden && !cancelled.current) {
        clear();
        void tick();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);

    return () => {
      cancelled.current = true;
      clear();
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [enabled, clear, tick]);

  /** Fetch now, outside the schedule — used after an action changes state. */
  const refresh = useCallback(() => {
    clear();
    void tick();
  }, [clear, tick]);

  return { polling, refresh };
}
