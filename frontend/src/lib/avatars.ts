/** Deterministic gradient + initials for member avatars. */

const GRADIENTS = [
  "var(--grad-a)",
  "var(--grad-c)",
  "var(--grad-b)",
  "linear-gradient(135deg,#5E5CE6,#0A84FF)",
  "var(--grad-d)",
  "linear-gradient(135deg,#FF9F0A,#FF375F)",
  "linear-gradient(135deg,#30D0B0,#0A84FF)",
];

export function gradientFor(seed: number | string): string {
  const n =
    typeof seed === "number"
      ? seed
      : seed.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  return GRADIENTS[Math.abs(n) % GRADIENTS.length];
}

export function initials(name: string, count = 1): string {
  return name.slice(0, count);
}
