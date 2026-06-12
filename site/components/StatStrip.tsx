import type { Summary } from "@/lib/data";

const eur = new Intl.NumberFormat("de-DE", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

function Stat({ label, value, tone }: { label: string; value: string; tone?: "pos" | "neg" }) {
  const color = tone === "pos" ? "var(--pos)" : tone === "neg" ? "var(--neg)" : "var(--ink)";
  return (
    <div className="flex flex-col gap-1">
      <span
        className="num text-[1.5rem] leading-tight font-medium"
        style={{ fontFamily: "var(--font-geist-mono), ui-monospace, monospace", color }}
      >
        {value}
      </span>
      <span className="text-[0.75rem]" style={{ color: "var(--ink-2)" }}>
        {label}
      </span>
    </div>
  );
}

export default function StatStrip({ summary }: { summary: Summary }) {
  const pnl = summary.total_pnl_eur;
  return (
    <div
      className="grid grid-cols-2 gap-y-6 border-y py-6 sm:grid-cols-3 lg:grid-cols-6"
      style={{ borderColor: "var(--hairline)" }}
    >
      <Stat
        label="Cumulative P&L, paper"
        value={(pnl >= 0 ? "+" : "−") + eur.format(Math.abs(pnl))}
        tone={pnl >= 0 ? "pos" : "neg"}
      />
      <Stat
        label="Hit rate"
        value={summary.hit_rate != null ? `${(summary.hit_rate * 100).toFixed(1)} %` : "n/a"}
      />
      <Stat
        label="Sharpe, annualized"
        value={summary.sharpe_daily_annualized != null ? summary.sharpe_daily_annualized.toFixed(2) : "n/a"}
      />
      <Stat
        label="Max drawdown"
        value={"−" + eur.format(Math.abs(summary.max_drawdown_eur))}
        tone="neg"
      />
      <Stat label="Theses settled" value={String(summary.n_theses_settled)} />
      <Stat label="Live theses" value={String(summary.n_theses_live)} />
    </div>
  );
}
