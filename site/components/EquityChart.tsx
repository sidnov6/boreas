"use client";

import { useMemo, useRef, useState } from "react";
import type { EquityPoint } from "@/lib/data";

const W = 1040;
const H = 380;
const PAD = { top: 16, right: 12, bottom: 28, left: 56 };

const eur = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });

export default function EquityChart({ curve }: { curve: EquityPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const { path, area, points, yTicks, y0 } = useMemo(() => {
    const xs = curve.map((_, i) => i);
    const ys = curve.map((p) => p.cumulative);
    const yMin = Math.min(0, ...ys);
    const yMax = Math.max(0, ...ys);
    const span = yMax - yMin || 1;
    const x = (i: number) =>
      PAD.left + (xs.length > 1 ? (i / (xs.length - 1)) * (W - PAD.left - PAD.right) : 0);
    const y = (v: number) =>
      PAD.top + (1 - (v - yMin) / span) * (H - PAD.top - PAD.bottom);

    const pts = curve.map((p, i) => ({ cx: x(i), cy: y(p.cumulative), ...p }));
    const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.cx.toFixed(1)},${p.cy.toFixed(1)}`).join("");
    const a =
      d +
      `L${pts[pts.length - 1].cx.toFixed(1)},${y(yMin).toFixed(1)}` +
      `L${pts[0].cx.toFixed(1)},${y(yMin).toFixed(1)}Z`;

    const step = niceStep(span / 4);
    const ticks: number[] = [];
    for (let v = Math.ceil(yMin / step) * step; v <= yMax; v += step) ticks.push(v);
    return { path: d, area: a, points: pts, yTicks: ticks.map((v) => ({ v, py: y(v) })), y0: y(0) };
  }, [curve]);

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || points.length === 0) return;
    const px = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0;
    let bestD = Infinity;
    points.forEach((p, i) => {
      const d = Math.abs(p.cx - px);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    setHover(best);
  }

  const h = hover != null ? points[hover] : null;

  return (
    <figure
      className="rounded-lg border p-4"
      style={{ background: "var(--surface)", borderColor: "var(--hairline)" }}
    >
      <figcaption className="mb-2 flex items-baseline justify-between">
        <span className="text-[0.875rem] font-medium">Cumulative realized P&L, EUR</span>
        <span className="flex items-center gap-4 text-[0.75rem]" style={{ color: "var(--ink-3)" }}>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="inline-block h-[2px] w-4" style={{ background: "var(--accent)" }} />
            BOREAS
          </span>
          <span className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-0 w-4 border-t border-dashed"
              style={{ borderColor: "var(--baseline-line)" }}
            />
            Baseline (0)
          </span>
        </span>
      </figcaption>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full touch-none select-none"
        role="img"
        aria-label="Equity curve of cumulative realized paper P&L in euros"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {yTicks.map(({ v, py }) => (
          <g key={v}>
            <line x1={PAD.left} x2={W - PAD.right} y1={py} y2={py} stroke="var(--hairline)" strokeWidth="1" />
            <text
              x={PAD.left - 8}
              y={py + 4}
              textAnchor="end"
              fontSize="12"
              fill="var(--ink-3)"
              style={{ fontFamily: "var(--font-geist-mono), monospace" }}
            >
              {eur.format(v)}
            </text>
          </g>
        ))}
        {/* baseline at zero: by construction, the strategy is measured against B_h, so 0 = baseline */}
        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y0}
          y2={y0}
          stroke="var(--baseline-line)"
          strokeWidth="1"
          strokeDasharray="4 4"
        />
        <path d={area} fill="var(--accent)" opacity="0.05" />
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.75" />
        {h && (
          <g>
            <line x1={h.cx} x2={h.cx} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--ink-3)" strokeWidth="1" />
            <circle cx={h.cx} cy={h.cy} r="3.5" fill="var(--accent)" />
          </g>
        )}
        {points.length > 0 &&
          [0, points.length - 1].map((i) => (
            <text
              key={i}
              x={points[i].cx}
              y={H - 8}
              textAnchor={i === 0 ? "start" : "end"}
              fontSize="12"
              fill="var(--ink-3)"
              style={{ fontFamily: "var(--font-geist-mono), monospace" }}
            >
              {points[i].date}
            </text>
          ))}
      </svg>
      <div
        className="num mt-2 h-5 text-[0.75rem]"
        style={{ color: "var(--ink-2)", fontFamily: "var(--font-geist-mono), monospace" }}
        aria-live="polite"
      >
        {h
          ? `${h.date}   day ${h.pnl >= 0 ? "+" : "−"}${eur.format(Math.abs(h.pnl))} €   cumulative ${
              h.cumulative >= 0 ? "+" : "−"
            }${eur.format(Math.abs(h.cumulative))} €`
          : " "}
      </div>
    </figure>
  );
}

function niceStep(raw: number): number {
  const pow = Math.pow(10, Math.floor(Math.log10(Math.abs(raw) || 1)));
  const n = raw / pow;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * pow;
}
