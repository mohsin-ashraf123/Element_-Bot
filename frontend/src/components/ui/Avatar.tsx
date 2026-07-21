import { gradientFor, initials } from "../../lib/avatars";

type Props = {
  name: string;
  seed?: number | string;
  mini?: boolean;
  chars?: number;
  style?: React.CSSProperties;
};

export function Avatar({ name, seed, mini, chars = 1, style }: Props) {
  return (
    <span
      className={mini ? "mini-av" : "avatar"}
      style={{ background: gradientFor(seed ?? name), ...style }}
    >
      {initials(name, chars)}
    </span>
  );
}
