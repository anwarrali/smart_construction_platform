/**
 * StructIQ brand mark.
 *
 * The symbol is a chamfered structural frame — the plan of a braced core, the
 * cut corner of a section detail — with a two-node connection tail leaving its
 * lower-right chamfer. The frame is the *Struct*: enclosure, structure, the
 * thing being built. The tail is the *IQ*: a relationship travelling out of the
 * structure, through a junction node, to a resolved decision point. That is the
 * whole product argument in one glyph, and it is why the tail is drawn in the
 * accent colour while the frame stays in ink.
 *
 * Everything is built from a single 32x32 grid so the mark stays exactly on
 * geometry from a 16px favicon up to a hero lockup. Strokes are geometric, not
 * optical: the chamfer is a true 45°, and the tail runs on that same diagonal,
 * so the symbol reads as drawn rather than illustrated.
 */

import { useTranslation } from "react-i18next";


type MarkProps = {
  /** Rendered size in px. The mark is on a 32-unit grid and scales cleanly. */
  size?: number;
  /** Colour of the structural frame. Defaults to the current text colour. */
  frameClassName?: string;
  /** Colour of the connection tail. Defaults to the brand accent. */
  tailClassName?: string;
  className?: string;
};

/**
 * The standalone symbol.
 *
 * Below roughly 20px the ring in the tail closes up visually, which is fine —
 * it degrades to a dot and a node, and the silhouette still reads.
 */
export const StructIQMark = ({
  size = 32,
  frameClassName = "text-brand-ink",
  tailClassName = "text-brand-accent",
  className = "",
}: MarkProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 32 32"
    fill="none"
    role="img"
    aria-label="StructIQ"
    className={`shrink-0 ${className}`}
  >
    {/* The structural frame: a square with both diagonals cut, drawn as a
        closed chamfered octagon so the corners read as fabricated joints. */}
    <path
      d="M10.5 2.6 H17.5 L24.4 9.5 V16.5 L17.5 23.4 H10.5 L3.6 16.5 V9.5 Z"
      className={frameClassName}
      stroke="currentColor"
      strokeWidth="3"
      strokeLinejoin="round"
    />

    {/* The connection tail, on the same 45° as the chamfer it leaves.
        Drawn as two segments with a gap so the junction reads as an open
        node rather than a blob — no background-coloured knockout needed,
        which keeps the mark safe on any surface. */}
    <g className={tailClassName} stroke="currentColor" strokeLinecap="round">
      <path d="M21.7 20.7 L23.1 22.1" strokeWidth="3" />
      <circle cx="25.1" cy="24.1" r="1.85" strokeWidth="1.6" />
      <path d="M27.1 26.1 L27.9 26.9" strokeWidth="3" />
      <circle cx="29" cy="28" r="2.6" fill="currentColor" stroke="none" />
    </g>
  </svg>
);

type WordmarkProps = {
  /** Height of the wordmark's cap line, in px. */
  size?: number;
  className?: string;
};

/**
 * The wordmark alone: "Struct" in ink, "IQ" in the accent.
 *
 * Set in the interface face rather than as outlines so it stays crisp at every
 * size and picks up the Arabic fallback stack automatically — the Latin
 * wordmark is the brand in both locales, which is normal practice for
 * engineering software sold across scripts.
 */
export const StructIQWordmark = ({ size = 20, className = "" }: WordmarkProps) => (
  <span
    className={`font-semibold leading-none tracking-heading ${className}`}
    style={{ fontSize: size, fontFamily: "Inter, system-ui, sans-serif" }}
  >
    <span className="text-brand-ink">Struct</span>
    <span className="text-brand-accent">IQ</span>
  </span>
);

type LockupProps = {
  /** `full` adds the descriptor line beneath the wordmark. */
  variant?: "full" | "compact" | "symbol";
  size?: number;
  /** Inverts the frame and wordmark to read on a dark ground. */
  inverted?: boolean;
  className?: string;
};

/**
 * The primary lockup: symbol, wordmark, and — at `full` — the descriptor.
 *
 * One lockup system serves the sidebar, the sign-in page and the landing
 * header; only the variant changes. That is what stops the product picking up
 * three slightly different logos in three different places.
 */
export const StructIQLogo = ({
  variant = "compact",
  size = 28,
  inverted = false,
  className = "",
}: LockupProps) => {
  const { t } = useTranslation();
  const frame = inverted ? "text-white" : "text-brand-ink";
  const word = inverted ? "text-white" : "text-brand-ink";

  if (variant === "symbol") {
    return <StructIQMark size={size} frameClassName={frame} className={className} />;
  }

  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <StructIQMark size={size} frameClassName={frame} />
      <span className="flex flex-col justify-center">
        <span
          className="font-semibold leading-none tracking-heading"
          style={{ fontSize: size * 0.66 }}
        >
          <span className={word}>Struct</span>
          <span className="text-brand-accent">IQ</span>
        </span>
        {variant === "full" && (
          <span
            className={`mt-1.5 whitespace-nowrap font-semibold uppercase leading-none ${
              inverted ? "text-white/55" : "text-muted-foreground"
            }`}
            style={{ fontSize: Math.max(8, size * 0.245), letterSpacing: "0.14em" }}
          >
            {t("brand.descriptor", { defaultValue: "Smart Construction Management" })}
          </span>
        )}
      </span>
    </span>
  );
};
