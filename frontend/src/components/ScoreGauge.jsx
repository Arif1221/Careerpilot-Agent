import React from "react";

// Score gauge styled like an aircraft instrument dial -- a literal nod to
// "Pilot" in CareerPilot AI, and a deliberate alternative to the generic
// circular-progress-ring pattern.
export default function ScoreGauge({ score }) {
  const clamped = Math.max(0, Math.min(100, score));
  const startAngle = -120;
  const sweep = 240;
  const needleAngle = startAngle + (clamped / 100) * sweep;

  const ticks = [0, 20, 40, 60, 80, 100];

  const polarToCartesian = (cx, cy, r, angleDeg) => {
    const angleRad = ((angleDeg - 90) * Math.PI) / 180;
    return {
      x: cx + r * Math.cos(angleRad),
      y: cy + r * Math.sin(angleRad),
    };
  };

  const cx = 120;
  const cy = 130;
  const r = 96;

  const arcStart = polarToCartesian(cx, cy, r, startAngle);
  const arcEnd = polarToCartesian(cx, cy, r, startAngle + sweep);

  const band =
    clamped >= 75 ? "gauge-band--strong" : clamped >= 45 ? "gauge-band--mid" : "gauge-band--weak";

  return (
    <div className="score-gauge">
      <svg viewBox="0 0 240 210" className="score-gauge__svg">
        {/* Outer bezel */}
        <circle cx={cx} cy={cy} r={r + 14} className="score-gauge__bezel" />

        {/* Background arc */}
        <path
          d={`M ${arcStart.x} ${arcStart.y} A ${r} ${r} 0 1 1 ${arcEnd.x} ${arcEnd.y}`}
          className="score-gauge__track"
        />

        {/* Tick marks + labels */}
        {ticks.map((t) => {
          const angle = startAngle + (t / 100) * sweep;
          const outer = polarToCartesian(cx, cy, r, angle);
          const inner = polarToCartesian(cx, cy, r - 10, angle);
          const labelPos = polarToCartesian(cx, cy, r - 26, angle);
          return (
            <g key={t}>
              <line
                x1={inner.x}
                y1={inner.y}
                x2={outer.x}
                y2={outer.y}
                className="score-gauge__tick"
              />
              <text x={labelPos.x} y={labelPos.y} className="score-gauge__tick-label">
                {t}
              </text>
            </g>
          );
        })}

        {/* Needle */}
        <g transform={`rotate(${needleAngle} ${cx} ${cy})`} className="score-gauge__needle-group">
          <polygon points={`${cx - 4},${cy} ${cx + 4},${cy} ${cx},${cy - r + 22}`} className="score-gauge__needle" />
        </g>
        <circle cx={cx} cy={cy} r={7} className="score-gauge__hub" />

        {/* Digital readout */}
        <text x={cx} y={cy + 46} textAnchor="middle" className={`score-gauge__value ${band}`}>
          {clamped}
        </text>
        <text x={cx} y={cy + 64} textAnchor="middle" className="score-gauge__unit">
          MATCH SCORE
        </text>
      </svg>
    </div>
  );
}
