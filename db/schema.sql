-- BOREAS canonical schema. One database holds everything:
-- observations (vintage-preserving), features, theses, paper book, playbook, run logs.
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Layer 2: canonical observation store.
-- Forecast vintages are NEVER overwritten: every revision is a new row keyed
-- by (series_id, zone, ts_event, ts_published, model_run, source). The db
-- layer only inserts a new vintage when the value actually changed, so the
-- table stays compact while remaining fully replayable.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS observations (
    series_id    TEXT             NOT NULL,
    zone         TEXT             NOT NULL DEFAULT 'DE_LU',
    ts_event     TIMESTAMPTZ      NOT NULL,
    ts_published TIMESTAMPTZ      NOT NULL,
    model_run    TEXT             NOT NULL DEFAULT '',
    value        DOUBLE PRECISION,
    unit         TEXT             NOT NULL DEFAULT '',
    source       TEXT             NOT NULL,
    inserted_at  TIMESTAMPTZ      NOT NULL DEFAULT now(),
    UNIQUE (series_id, zone, ts_event, ts_published, model_run, source)
);
SELECT create_hypertable('observations', 'ts_event', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS obs_series_event_idx
    ON observations (series_id, ts_event DESC, ts_published DESC);

-- ---------------------------------------------------------------------------
-- Layer 3: feature frames (one per 15-min cycle), stored whole for replay.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feature_frames (
    ts         TIMESTAMPTZ PRIMARY KEY,
    frame      JSONB       NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Layer 4: agent society artifacts.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind             TEXT        NOT NULL,            -- 'cycle' | 'reflection' | 'da_submission'
    feature_ts       TIMESTAMPTZ,
    sentinel_verdict TEXT,                            -- 'nothing' | 'interesting' | 'act_worthy'
    detail           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS theses (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    status           TEXT        NOT NULL DEFAULT 'proposed',
    -- proposed -> approved | rejected ; approved -> live -> settled | falsified | expired
    strategy         TEXT        NOT NULL,            -- 'da_curve' | 'da_rebap_spread'
    direction        TEXT        NOT NULL,            -- 'long' | 'short'
    delivery_date    DATE        NOT NULL,
    qh_indices       INTEGER[]   NOT NULL,            -- quarter-hours of delivery day, 0..95
    expected_move    DOUBLE PRECISION NOT NULL,       -- EUR/MWh
    confidence       DOUBLE PRECISION NOT NULL,       -- 0..1
    falsifier        TEXT        NOT NULL,
    rationale        TEXT        NOT NULL,
    feature_ts       TIMESTAMPTZ,
    feature_hash     TEXT,
    playbook_version INTEGER,
    prompt_version   TEXT,
    raw              JSONB       NOT NULL DEFAULT '{}'::jsonb,
    risk_note        TEXT,
    pnl_eur          DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS paper_orders (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thesis_id      UUID REFERENCES theses(id),
    strategy       TEXT             NOT NULL,
    delivery_start TIMESTAMPTZ      NOT NULL,
    delivery_end   TIMESTAMPTZ      NOT NULL,
    qty_mw         DOUBLE PRECISION NOT NULL,         -- signed: + long, - short
    ref_price      DOUBLE PRECISION,                  -- v1: baseline B_h ; v2: DA price
    created_at     TIMESTAMPTZ      NOT NULL DEFAULT now(),
    status         TEXT             NOT NULL DEFAULT 'open',  -- open | settled | cancelled
    settle_price   DOUBLE PRECISION,
    pnl_eur        DOUBLE PRECISION,
    settled_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS orders_status_idx ON paper_orders (status, delivery_start);

CREATE TABLE IF NOT EXISTS journal_entries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thesis_id   UUID REFERENCES theses(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    content     TEXT        NOT NULL,
    attribution JSONB       NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS playbook_versions (
    version     SERIAL PRIMARY KEY,
    content     TEXT        NOT NULL,
    diff        TEXT,
    rationale   TEXT,
    auto_merged BOOLEAN     NOT NULL DEFAULT TRUE,
    approved    BOOLEAN     NOT NULL DEFAULT TRUE,   -- structural diffs wait for approval
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Daily equity snapshots for the tearsheet.
CREATE TABLE IF NOT EXISTS equity_curve (
    as_of        DATE PRIMARY KEY,
    realized_pnl DOUBLE PRECISION NOT NULL,
    n_theses     INTEGER          NOT NULL DEFAULT 0,
    n_wins       INTEGER          NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ      NOT NULL DEFAULT now()
);
