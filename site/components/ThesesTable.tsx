"use client";

import { useState } from "react";
import type { ThesisRow } from "@/lib/data";

const eur = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });

const mono = { fontFamily: "var(--font-geist-mono), ui-monospace, monospace" } as const;

function Pnl({ value }: { value: number | null }) {
  if (value == null)
    return (
      <span className="num" style={{ ...mono, color: "var(--ink-3)" }}>
        open
      </span>
    );
  const pos = value >= 0;
  return (
    <span className="num" style={{ ...mono, color: pos ? "var(--pos)" : "var(--neg)" }}>
      {pos ? "+" : "−"}
      {eur.format(Math.abs(value))}
    </span>
  );
}

function OutcomeBadge({ t }: { t: ThesisRow }) {
  if (t.status === "live")
    return (
      <span
        className="rounded-full px-2 py-0.5 text-[0.6875rem] font-medium"
        style={{ background: "var(--accent-tint)", color: "var(--accent)" }}
      >
        live
      </span>
    );
  const win = (t.pnl_eur ?? 0) >= 0;
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[0.6875rem] font-medium"
      style={{
        background: win ? "var(--pos-tint)" : "var(--neg-tint)",
        color: win ? "var(--pos)" : "var(--neg)",
      }}
    >
      {win ? "+ win" : "− loss"}
    </span>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[0.6875rem] font-medium uppercase" style={{ color: "var(--ink-2)", letterSpacing: "0.06em" }}>
        {label}
      </div>
      <div className="mt-1 text-[0.9375rem] leading-relaxed prose-thesis">{children}</div>
    </div>
  );
}

function Row({ t }: { t: ThesisRow }) {
  const [open, setOpen] = useState(false);
  const qh = t.qh_indices;
  const window = qh.length ? `Q${Math.min(...qh)}–Q${Math.max(...qh)}` : "—";
  return (
    <div data-open={open} style={{ borderBottom: "1px solid var(--hairline)" }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="row-hover grid w-full grid-cols-[64px_56px_1fr_80px] items-center gap-3 px-2 py-3 text-left text-[0.875rem] transition-colors sm:grid-cols-[88px_120px_96px_72px_1fr_96px_72px]"
        style={{ transitionDuration: "var(--dur-fast)" }}
      >
        <span className="num" style={{ ...mono, color: "var(--ink-2)" }}>
          <span className="sm:hidden">{t.created_at.slice(5, 10)}</span>
          <span className="hidden sm:inline">
            {t.created_at.slice(5, 10)} {t.created_at.slice(11, 16)}
          </span>
        </span>
        <span className="hidden sm:inline" style={{ color: "var(--ink-2)" }}>
          {t.strategy === "da_curve" ? "DA curve" : "DA–reBAP"}
        </span>
        <span className="num hidden sm:inline" style={mono}>
          {window}
        </span>
        <span className="font-medium">{t.direction}</span>
        <span className="truncate" style={{ color: "var(--ink-2)" }}>
          {t.rationale}
        </span>
        <span className="text-right">
          <Pnl value={t.pnl_eur} />
        </span>
        <span className="hidden items-center justify-end gap-2 sm:flex">
          <OutcomeBadge t={t} />
          <span aria-hidden className="chevron text-[0.75rem]" style={{ color: "var(--ink-3)" }}>
            ›
          </span>
        </span>
      </button>
      <div className="expand-grid" data-open={open}>
        <div>
          <div className="grid gap-5 px-2 pb-6 pt-1 sm:grid-cols-2">
            <Detail label="Thesis">{t.rationale}</Detail>
            <div className="flex flex-col gap-5">
              <Detail label="Falsifier">{t.falsifier}</Detail>
              <Detail label="Risk officer">{t.risk_note || "—"}</Detail>
            </div>
            {t.post_mortem && <Detail label={`Post-mortem · ${t.attribution.replace("_", " ")}`}>{t.post_mortem}</Detail>}
            <div className="num text-[0.75rem] leading-loose" style={{ ...mono, color: "var(--ink-3)" }}>
              delivery {t.delivery_date} · {qh.length} quarter-hours
              <br />
              confidence {t.confidence.toFixed(2)} · expected {t.expected_move > 0 ? "+" : ""}
              {t.expected_move} €/MWh
              <br />
              features {t.feature_hash ?? "—"} · playbook v{t.playbook_version ?? "—"} · prompt{" "}
              {t.prompt_version ?? "—"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ThesesTable({ theses }: { theses: ThesisRow[] }) {
  const [filter, setFilter] = useState<"all" | "settled" | "live">("all");
  const rows = theses.filter((t) => (filter === "all" ? true : t.status === filter));
  return (
    <div>
      <div className="mb-2 flex justify-end">
        <select
          aria-label="Filter theses"
          value={filter}
          onChange={(e) => setFilter(e.target.value as typeof filter)}
          className="rounded border bg-transparent px-1.5 py-1 text-[0.75rem]"
          style={{ borderColor: "var(--hairline)", color: "var(--ink-2)" }}
        >
          <option value="all">all</option>
          <option value="settled">settled</option>
          <option value="live">live</option>
        </select>
      </div>
      <div
        className="mb-3 grid w-full grid-cols-[64px_56px_1fr_80px] gap-3 px-2 text-[0.6875rem] font-medium uppercase sm:grid-cols-[88px_120px_96px_72px_1fr_96px_72px]"
        style={{ color: "var(--ink-2)", letterSpacing: "0.06em" }}
      >
        <span>Opened</span>
        <span className="hidden sm:inline">Strategy</span>
        <span className="hidden sm:inline">Window</span>
        <span>Side</span>
        <span>Thesis</span>
        <span className="text-right">P&L €</span>
        <span className="hidden sm:inline" aria-hidden />
      </div>
      <div style={{ borderTop: "1px solid var(--hairline)" }}>
        {rows.map((t) => (
          <Row key={t.id} t={t} />
        ))}
        {rows.length === 0 && (
          <p className="px-2 py-8 text-[0.875rem]" style={{ color: "var(--ink-2)" }}>
            No theses in this filter yet. The agent only trades when its own weather-derived nowcast
            disagrees with the TSO forecast; quiet markets produce no entries.
          </p>
        )}
      </div>
    </div>
  );
}
