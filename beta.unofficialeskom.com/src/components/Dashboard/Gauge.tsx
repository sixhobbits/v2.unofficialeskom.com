type Props = {
  value: number | null;
  min?: number;
  max?: number;
};

// Half-circle gauge in a 200×130 viewBox. Because the viewBox is a coordinate
// system (not pixels), every visual element scales together when the SVG
// renders at any size — no resize observers, no pixel-tuning per breakpoint.

const CX = 100;
const CY = 100;
const R = 75;
const STROKE = 14;
const TICKS = [0, 20, 40, 60, 80, 100];

// Map a value in [min, max] to a point on the half-circle.
// 0 → angle 180° (left), max → angle 0° (right). SVG y is flipped.
function pointAt(v: number, min: number, max: number, r: number) {
  const frac = Math.max(0, Math.min(1, (v - min) / (max - min)));
  const angle = Math.PI * (1 - frac);
  return {x: CX + r * Math.cos(angle), y: CY - r * Math.sin(angle)};
}

function arcPath(fromV: number, toV: number, min: number, max: number, r: number) {
  const a = pointAt(fromV, min, max, r);
  const b = pointAt(toV, min, max, r);
  // Half-circle gauge sweeps at most 180°, so SVG's "large-arc" flag is always 0.
  // sweep=1 (clockwise on screen) draws over the top: left → top → right.
  return `M ${a.x} ${a.y} A ${r} ${r} 0 0 1 ${b.x} ${b.y}`;
}

export function Gauge({value, min = 0, max = 100}: Props) {
  const v = value ?? 0;
  const clamped = Math.max(min, Math.min(max, v));
  const frac = (clamped - min) / (max - min);

  // Color buckets: red < 50%, yellow 50–70%, green ≥ 70% (of the value range).
  const color = frac < 0.5 ? '#e53935' : frac < 0.7 ? '#fdd835' : '#43a047';

  return (
    <svg
      viewBox="-5 -5 210 130"
      width="100%"
      height="100%"
      preserveAspectRatio="xMidYMid meet"
      style={{display: 'block'}}
    >
      {/* track */}
      <path
        d={arcPath(min, max, min, max, R)}
        stroke="#e6e6e6"
        strokeWidth={STROKE}
        strokeLinecap="round"
        fill="none"
      />
      {/* filled */}
      {clamped > min && (
        <path
          d={arcPath(min, clamped, min, max, R)}
          stroke={color}
          strokeWidth={STROKE}
          strokeLinecap="round"
          fill="none"
        />
      )}
      {/* axis labels (outside the arc) */}
      {TICKS.map((t) => {
        const p = pointAt(t, min, max, R + STROKE / 2 + 8);
        const anchor =
          t === 0 || t < min + (max - min) * 0.25
            ? 'end'
            : t === max || t > min + (max - min) * 0.75
              ? 'start'
              : 'middle';
        return (
          <text
            key={t}
            x={p.x}
            y={p.y + 3}
            fontSize={9}
            fill="#888"
            textAnchor={anchor}
            style={{fontFamily: 'inherit'}}
          >
            {t}
          </text>
        );
      })}
      {/* big number */}
      <text
        x={CX}
        y={CY - 5}
        textAnchor="middle"
        fontSize={42}
        fontWeight={700}
        fill="currentColor"
        style={{fontFamily: 'inherit'}}
      >
        {Math.round(clamped)}
      </text>
    </svg>
  );
}
