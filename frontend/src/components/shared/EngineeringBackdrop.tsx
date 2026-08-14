/**
 * Ambient engineering backdrop.
 *
 * An abstract structural drawing — column grid, floor plate, section marks and
 * a setting-out line — rendered in hairlines at very low opacity. It is
 * decoration with a purpose: it tells you, before you read a single word, that
 * this is engineering software. It must never compete with content, so
 * everything here is drawn at 1px in the border colour and sits behind a
 * gradient that fades it out toward the middle of the page.
 */
export const EngineeringBackdrop = ({ className = "" }: { className?: string }) => (
  <div aria-hidden="true" className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}>
    {/* Fine grid with a coarser sheet grid over it. */}
    <div className="absolute inset-0 blueprint-field-major" />

    <svg
      className="absolute inset-0 h-full w-full text-foreground/[0.07] dark:text-foreground/[0.10]"
      viewBox="0 0 1440 900"
      preserveAspectRatio="xMidYMid slice"
      fill="none"
      stroke="currentColor"
      strokeWidth="1"
      vectorEffect="non-scaling-stroke"
    >
      {/* ── Axonometric frame, lower left: three bays of a structural grid ── */}
      <g strokeLinecap="square">
        <path d="M96 700 L96 470 M236 740 L236 510 M376 780 L376 550 M516 820 L516 590" />
        <path d="M96 470 L236 510 L376 550 L516 590" />
        <path d="M96 560 L236 600 L376 640 L516 680" />
        <path d="M96 650 L236 690 L376 730 L516 770" />
        {/* Bracing to two bays only, so the drawing reads as a fragment. */}
        <path d="M96 470 L236 600 M236 510 L376 640" strokeDasharray="4 5" />
      </g>

      {/* ── Floor plate, upper right: a partial plan with a core ── */}
      <g transform="translate(940 96)">
        <rect x="0" y="0" width="380" height="270" />
        <path d="M0 78 L380 78 M0 186 L380 186 M132 0 L132 270 M264 0 L264 270" strokeDasharray="3 6" />
        {/* Core */}
        <rect x="150" y="96" width="72" height="72" />
        <path d="M150 96 L222 168 M222 96 L150 168" strokeWidth="0.75" />
        {/* Setting-out dimension line with terminators */}
        <path d="M0 300 L380 300" />
        <path d="M0 294 L0 306 M380 294 L380 306 M132 296 L132 304 M264 296 L264 304" />
      </g>

      {/* ── Section mark and centre line running across the sheet ── */}
      <g>
        <path d="M0 430 L1440 430" strokeDasharray="28 8 4 8" strokeWidth="0.75" />
        <circle cx="712" cy="430" r="16" />
        <path d="M712 414 L712 446 M696 430 L728 430" strokeWidth="0.75" />
      </g>

      {/* ── Registration marks in the sheet corners ── */}
      <g strokeWidth="1">
        <path d="M40 40 L40 76 M40 40 L76 40" />
        <path d="M1400 40 L1400 76 M1400 40 L1364 40" />
        <path d="M40 860 L40 824 M40 860 L76 860" />
        <path d="M1400 860 L1400 824 M1400 860 L1364 860" />
      </g>
    </svg>

    {/* Fades the drawing out behind the form so nothing competes with it. */}
    <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,hsl(var(--background))_18%,hsl(var(--background)/0.72)_46%,transparent_78%)]" />
  </div>
);
