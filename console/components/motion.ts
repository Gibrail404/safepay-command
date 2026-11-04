"use client";
import { useEffect, useState } from "react";

/** True when the visitor asked their system for less motion. Animations then jump to their final state. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(q.matches);
    const on = () => setReduced(q.matches);
    q.addEventListener("change", on);
    return () => q.removeEventListener("change", on);
  }, []);
  return reduced;
}

/** Counts a number up or down to its target. With reduced motion it simply shows the target. */
export function useCountTo(target: number, ms = 500): number {
  const reduced = usePrefersReducedMotion();
  const [value, setValue] = useState(target);
  useEffect(() => {
    if (reduced) { setValue(target); return; }
    let raf = 0;
    const from = value, t0 = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / ms);
      setValue(from + (target - from) * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, reduced]);
  return value;
}
