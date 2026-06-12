import type { PlaybookVersion } from "@/lib/data";

const mono = { fontFamily: "var(--font-geist-mono), ui-monospace, monospace" } as const;

export default function Playbook({ versions }: { versions: PlaybookVersion[] }) {
  return (
    <div style={{ borderTop: "1px solid var(--hairline)" }}>
      {versions.map((v) => (
        <article
          key={v.version}
          className="grid gap-1 py-5 sm:grid-cols-[140px_1fr] sm:gap-6"
          style={{ borderBottom: "1px solid var(--hairline)" }}
        >
          <div className="num text-[0.75rem] leading-6" style={{ ...mono, color: "var(--ink-2)" }}>
            v{v.version}
            <br />
            {v.created_at.slice(0, 10)}
            {!v.approved && (
              <>
                <br />
                <span style={{ color: "var(--neg)" }}>awaiting approval</span>
              </>
            )}
            {!v.auto_merged && v.approved && (
              <>
                <br />
                <span style={{ color: "var(--accent)" }}>human-approved</span>
              </>
            )}
          </div>
          <div>
            <p className="text-[0.9375rem] leading-relaxed prose-thesis">{v.rationale}</p>
            {v.diff && (
              <pre
                className="num mt-2 overflow-x-auto whitespace-pre-wrap text-[0.8125rem] leading-relaxed"
                style={{ ...mono, color: "var(--ink-3)" }}
              >
                {v.diff}
              </pre>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
