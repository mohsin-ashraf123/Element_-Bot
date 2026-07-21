import { useEffect, useState } from "react";

/** Animated count-up percentage (matches the design's dashboard flourish). */
export function CountUp({ value, suffix = "%" }: { value: number; suffix?: string }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    let current = 0;
    const step = Math.max(1, Math.round(value / 28));
    const id = setInterval(() => {
      current += step;
      if (current >= value) {
        current = value;
        clearInterval(id);
      }
      setDisplay(current);
    }, 22);
    return () => clearInterval(id);
  }, [value]);

  return (
    <>
      {display}
      {suffix}
    </>
  );
}
