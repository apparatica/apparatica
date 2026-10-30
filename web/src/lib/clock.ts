import { useEffect, useEffectEvent, useState } from "react";

/** `Date.now()`, read again every `intervalMs` while it is set: the times of a running check. */
export function useNow(intervalMs: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (intervalMs === null) return;
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

// A countdown shows whole seconds: a few reads a second keep it on time.
const COUNTDOWN_TICK_MS = 250;

/** The milliseconds left until `until` (`Date.now()` time), null once it has come; `onEnd` runs
 * then. `from` is when the wait began: the time to count from before the first tick. */
export function useCountdown(
  until: number | null,
  from: number | null,
  onEnd?: () => void,
): number | null {
  const [now, setNow] = useState(() => Date.now());
  const end = useEffectEvent(() => onEnd?.());
  useEffect(() => {
    if (until === null) return;
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      const time = Date.now();
      setNow(time);
      if (time < until) timer = setTimeout(tick, Math.min(COUNTDOWN_TICK_MS, until - time));
      else end();
    };
    timer = setTimeout(tick, 0);
    return () => clearTimeout(timer);
  }, [until]);
  if (until === null) return null;
  const left = until - Math.max(now, from ?? now);
  return left > 0 ? left : null;
}
