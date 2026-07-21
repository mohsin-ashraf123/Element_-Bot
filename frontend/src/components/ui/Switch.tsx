import { useState } from "react";
import clsx from "clsx";

export function Switch({
  defaultOn = false,
  onChange,
}: {
  defaultOn?: boolean;
  onChange?: (on: boolean) => void;
}) {
  const [on, setOn] = useState(defaultOn);
  return (
    <button
      type="button"
      className={clsx("switch", on && "on")}
      aria-pressed={on}
      onClick={() => {
        const next = !on;
        setOn(next);
        onChange?.(next);
      }}
    />
  );
}
