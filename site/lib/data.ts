import fs from "fs";
import path from "path";

export type EquityPoint = { date: string; pnl: number; cumulative: number };

export type Summary = {
  generated_at: string;
  total_pnl_eur: number;
  n_theses_settled: number;
  n_theses_live: number;
  hit_rate: number | null;
  sharpe_daily_annualized: number | null;
  max_drawdown_eur: number;
  equity_curve: EquityPoint[];
  sample?: boolean;
};

export type ThesisRow = {
  id: string;
  created_at: string;
  status: string;
  strategy: string;
  direction: string;
  delivery_date: string;
  qh_indices: number[];
  expected_move: number;
  confidence: number;
  falsifier: string;
  rationale: string;
  risk_note: string | null;
  pnl_eur: number | null;
  feature_hash: string | null;
  playbook_version: number | null;
  prompt_version: string | null;
  post_mortem: string;
  attribution: string;
};

export type PlaybookVersion = {
  version: number;
  created_at: string;
  rationale: string | null;
  diff: string | null;
  auto_merged: boolean;
  approved: boolean;
  content: string;
};

function load<T>(name: string): T | null {
  // Live data (written by the nightly Reporter) wins; bundled sample is the fallback
  // so the site demos sensibly before the track record accumulates.
  for (const dir of ["public/data", "data/sample"]) {
    const p = path.join(process.cwd(), dir, name);
    if (fs.existsSync(p)) {
      const parsed = JSON.parse(fs.readFileSync(p, "utf-8"));
      if (dir === "data/sample" && !Array.isArray(parsed)) parsed.sample = true;
      return parsed as T;
    }
  }
  return null;
}

export function getSummary(): Summary | null {
  return load<Summary>("summary.json");
}

export function getTheses(): ThesisRow[] {
  return load<ThesisRow[]>("theses.json") ?? [];
}

export function getPlaybook(): PlaybookVersion[] {
  return load<PlaybookVersion[]>("playbook.json") ?? [];
}

export function isSample(): boolean {
  return !fs.existsSync(path.join(process.cwd(), "public/data", "summary.json"));
}
