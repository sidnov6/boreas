import type { Activity } from "@/lib/data";

const mono = { fontFamily: "var(--font-geist-mono), ui-monospace, monospace" } as const;

const fmt = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });

function verdictColor(verdict: string | null): { bg: string; fg: string } {
  switch (verdict) {
    case "act_worthy":
      return { bg: "var(--pos-tint)", fg: "var(--pos)" };
    case "interesting":
      return { bg: "var(--accent-tint)", fg: "var(--accent)" };
    default:
      return { bg: "transparent", fg: "var(--ink-3)" };
  }
}

function SystemNow({ now }: { now: NonNullable<Activity["system_now"]> }) {
  const items: [string, string][] = [
    ["residual load", now.residual_load_mw != null ? `${fmt.format(now.residual_load_mw)} MW` : "n/a"],
    ["wind divergence z", now.wind_div_z != null ? now.wind_div_z.toFixed(2) : "n/a"],
    ["wind error", now.wind_err_mw != null ? `${fmt.format(now.wind_err_mw)} MW` : "n/a"],
    ["DA price", now.da_price_eur != null ? `${now.da_price_eur.toFixed(1)} €/MWh` : "n/a"],
    ["ramp", now.ramp_mw_h != null ? `${fmt.format(now.ramp_mw_h)} MW/h` : "n/a"],
    ["observations stored", fmt.format(now.n_observations)],
  ];
  return (
    <div
      className="num mb-8 grid grid-cols-2 gap-x-6 gap-y-3 rounded-lg border p-4 text-[0.8125rem] sm:grid-cols-3 lg:grid-cols-6"
      style={{ ...mono, background: "var(--surface)", borderColor: "var(--hairline)" }}
    >
      {items.map(([label, value]) => (
        <div key={label}>
          <div>{value}</div>
          <div className="mt-0.5 text-[0.6875rem]" style={{ color: "var(--ink-3)", fontFamily: "var(--font-geist-sans), sans-serif" }}>
            {label}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function ActivityLog({ activity }: { activity: Activity }) {
  return (
    <div>
      {activity.system_now && <SystemNow now={activity.system_now} />}
      <div style={{ borderTop: "1px solid var(--hairline)" }}>
        {activity.cycles.map((c) => {
          const vc = verdictColor(c.verdict);
          return (
            <div
              key={c.ts + c.kind}
              className="grid grid-cols-[120px_92px_1fr] items-baseline gap-3 px-2 py-2.5 text-[0.8125rem] sm:grid-cols-[150px_100px_1fr]"
              style={{ borderBottom: "1px solid var(--hairline)" }}
            >
              <span className="num" style={{ ...mono, color: "var(--ink-2)" }}>
                {c.ts.slice(5, 16).replace("T", " ")} UTC
              </span>
              <span
                className="justify-self-start rounded-full px-2 py-0.5 text-[0.6875rem] font-medium"
                style={{ background: vc.bg, color: vc.fg }}
              >
                {c.verdict ?? c.kind}
              </span>
              <span style={{ color: "var(--ink-2)" }}>
                {c.thesis_id
                  ? "thesis executed — see table above"
                  : c.pass_reason || c.reason || "cycle completed"}
                {c.wind_div_z != null && (
                  <span className="num" style={{ ...mono, color: "var(--ink-3)" }}>
                    {" "}
                    · div z {c.wind_div_z.toFixed(2)}
                  </span>
                )}
              </span>
            </div>
          );
        })}
        {activity.cycles.length === 0 && (
          <p className="px-2 py-8 text-[0.875rem]" style={{ color: "var(--ink-2)" }}>
            No cycles logged yet — the scheduler runs the society every 15 minutes.
          </p>
        )}
      </div>
    </div>
  );
}
