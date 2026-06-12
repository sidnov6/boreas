import EquityChart from "@/components/EquityChart";
import Playbook from "@/components/Playbook";
import StatStrip from "@/components/StatStrip";
import ThesesTable from "@/components/ThesesTable";
import { getPlaybook, getSummary, getTheses, isSample } from "@/lib/data";

export default function Home() {
  const summary = getSummary();
  const theses = getTheses();
  const playbook = getPlaybook();
  const sample = isSample();

  return (
    <div className="mx-auto max-w-[1120px] px-6">
      <header
        className="flex h-16 items-center justify-between"
        style={{ borderBottom: "1px solid var(--hairline)" }}
      >
        <span className="text-[0.9375rem] font-semibold tracking-tight">BOREAS</span>
        <nav className="flex items-center gap-6 text-[0.8125rem]" style={{ color: "var(--ink-2)" }}>
          <a href="#record" className="hover:underline">Record</a>
          <a href="#theses" className="hover:underline">Theses</a>
          <a href="#playbook" className="hover:underline">Playbook</a>
          <a href="#method" className="hover:underline">Method</a>
        </nav>
      </header>

      <main>
        <section className="pt-16 pb-12">
          <h1 className="text-[1.5rem] font-semibold leading-tight tracking-tight">
            An autonomous agent paper-trading German power, in public.
          </h1>
          <p className="mt-3 max-w-[65ch] text-[1rem] leading-relaxed" style={{ color: "var(--ink-2)" }}>
            BOREAS builds its own wind and solar nowcast from DWD ICON-D2 weather fields, compares it
            with the TSO forecasts behind the EPEX day-ahead auction for zone DE-LU, and takes paper
            positions on 15-minute products when the two disagree. Every thesis, settlement and
            playbook revision below is generated and published by the system itself.
            {sample && (
              <span style={{ color: "var(--ink-3)" }}>
                {" "}
                Figures currently shown are sample data while the live record accumulates.
              </span>
            )}
          </p>
        </section>

        {summary && (
          <section id="record" className="scroll-mt-20">
            <StatStrip summary={summary} />
            <div className="mt-12">
              <EquityChart curve={summary.equity_curve} />
            </div>
          </section>
        )}

        <section id="theses" className="scroll-mt-20 pt-24">
          <h2 className="mb-6 text-[1.25rem] font-semibold tracking-tight">Theses</h2>
          <ThesesTable theses={theses} />
        </section>

        <section id="playbook" className="scroll-mt-20 pt-24">
          <h2 className="mb-2 text-[1.25rem] font-semibold tracking-tight">Playbook changelog</h2>
          <p className="mb-6 max-w-[65ch] text-[0.9375rem]" style={{ color: "var(--ink-2)" }}>
            After every settlement the Reflector attributes the outcome and may amend the playbook
            the Analyst trades from. Small amendments merge automatically; structural changes wait
            for human approval.
          </p>
          <Playbook versions={playbook} />
        </section>

        <section id="method" className="scroll-mt-20 pt-24 pb-24">
          <h2 className="mb-2 text-[1.25rem] font-semibold tracking-tight">Method</h2>
          <div className="max-w-[65ch] text-[0.9375rem] leading-relaxed" style={{ color: "var(--ink-2)" }}>
            <p>
              Real-time EPEX intraday continuous prices are licensed, so BOREAS trades two precisely
              defined paper conventions. Before the 12:00 CET auction gate it positions against a
              rolling 90-day regression baseline from TSO-forecast residual load to price; settlement
              is the published auction price. Intraday it trades the spread between day-ahead and the
              reBAP imbalance price, settling on preliminary reBAP when published. Sizing is capped
              fractional Kelly inside hard-coded limits. Data: ENTSO-E Transparency, SMARD and
              Energy-Charts, Open-Meteo (ICON-D2), regelleistung.net and Netztransparenz.
            </p>
            <p className="mt-4">
              No real money is traded. P&L is gross of fees and market impact. This is a research
              artifact, not investment advice.
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}
