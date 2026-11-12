-- Phase 1 建表（与 app/models.py 对齐，Postgres 16 + pgvector）
-- 本地默认用 SQLite 自动建表；切 Postgres 时先执行本文件，再启动服务。

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS tasks (
  id            VARCHAR(24) PRIMARY KEY,
  workspace     VARCHAR(64) NOT NULL DEFAULT '默认工作区',
  title         VARCHAR(200) NOT NULL,
  goal          TEXT NOT NULL,
  status        VARCHAR(32) NOT NULL DEFAULT 'queued',
  progress      INTEGER NOT NULL DEFAULT 0,
  priority      VARCHAR(8) NOT NULL DEFAULT 'P0',
  owner         VARCHAR(64) NOT NULL DEFAULT '我',
  created_at    TIMESTAMP NOT NULL DEFAULT now(),
  updated_at    TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runs (
  id                  VARCHAR(24) PRIMARY KEY,
  task_id             VARCHAR(24) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  status              VARCHAR(32) NOT NULL DEFAULT 'queued',
  total_steps         INTEGER NOT NULL DEFAULT 0,
  done_steps          INTEGER NOT NULL DEFAULT 0,
  tool_calls          INTEGER NOT NULL DEFAULT 0,
  slots_used          INTEGER NOT NULL DEFAULT 1,
  slots_total         INTEGER NOT NULL DEFAULT 16,
  pending_approval_id VARCHAR(32),
  error               TEXT,
  started_at          TIMESTAMP NOT NULL DEFAULT now(),
  finished_at         TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id);

CREATE TABLE IF NOT EXISTS steps (
  id           SERIAL PRIMARY KEY,
  run_id       VARCHAR(24) NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  seq          INTEGER NOT NULL,
  agent        VARCHAR(64) NOT NULL,
  title        VARCHAR(200) NOT NULL,
  tool         VARCHAR(64) NOT NULL DEFAULT 'llm.generate',
  args         JSONB NOT NULL DEFAULT '{}'::jsonb,
  status       VARCHAR(32) NOT NULL DEFAULT 'queued',
  output       TEXT,
  duration_ms  INTEGER NOT NULL DEFAULT 0,
  started_at   TIMESTAMP,
  finished_at  TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_steps_run ON steps(run_id, seq);

CREATE TABLE IF NOT EXISTS approvals (
  id          VARCHAR(32) PRIMARY KEY,
  run_id      VARCHAR(24) NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  step_id     INTEGER NOT NULL,
  step_seq    INTEGER NOT NULL,
  risk        VARCHAR(16) NOT NULL,
  action      VARCHAR(64) NOT NULL,
  summary     TEXT NOT NULL,
  detail      JSONB NOT NULL DEFAULT '{}'::jsonb,
  status      VARCHAR(24) NOT NULL DEFAULT 'pending',
  idem_key    VARCHAR(160) NOT NULL UNIQUE,
  note        TEXT,
  decided_by  VARCHAR(64),
  created_at  TIMESTAMP NOT NULL DEFAULT now(),
  decided_at  TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_approvals_run ON approvals(run_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

CREATE TABLE IF NOT EXISTS tools (
  name        VARCHAR(64) PRIMARY KEY,
  label       VARCHAR(64) NOT NULL,
  risk        VARCHAR(16) NOT NULL,
  whitelist   JSONB NOT NULL DEFAULT '[]'::jsonb,
  description TEXT NOT NULL DEFAULT '',
  enabled     BOOLEAN NOT NULL DEFAULT true
);

-- Phase 2 技能系统 v1：技能 = 提示词模板 + 工具组合 + 参数预设
CREATE TABLE IF NOT EXISTS skills (
  name             VARCHAR(64) PRIMARY KEY,
  label            VARCHAR(64) NOT NULL DEFAULT '',
  description      TEXT NOT NULL DEFAULT '',
  prompt_template  TEXT NOT NULL DEFAULT '',
  tools            JSONB NOT NULL DEFAULT '[]'::jsonb,
  args_preset      JSONB NOT NULL DEFAULT '{}'::jsonb,
  enabled          BOOLEAN NOT NULL DEFAULT true,
  created_at       TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_providers (
  id         VARCHAR(24) PRIMARY KEY,
  name       VARCHAR(64) NOT NULL,
  provider   VARCHAR(32) NOT NULL,
  model      VARCHAR(64) NOT NULL,
  base_url   VARCHAR(200) NOT NULL,
  api_key    TEXT NOT NULL DEFAULT '',
  is_default BOOLEAN NOT NULL DEFAULT false,
  enabled    BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
  id         SERIAL PRIMARY KEY,
  run_id     VARCHAR(24) NOT NULL,
  seq        INTEGER NOT NULL,
  type       VARCHAR(48) NOT NULL,
  payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_events(run_id, seq);

CREATE TABLE IF NOT EXISTS deliverables (
  id         SERIAL PRIMARY KEY,
  run_id     VARCHAR(24) NOT NULL,
  task_id    VARCHAR(24) NOT NULL,
  filename   VARCHAR(200) NOT NULL,
  path       VARCHAR(400) NOT NULL,
  size       INTEGER NOT NULL DEFAULT 0,
  sha256     VARCHAR(64) NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversations (
  id         VARCHAR(24) PRIMARY KEY,
  workspace  VARCHAR(64) NOT NULL DEFAULT '默认工作区',
  title      VARCHAR(200) NOT NULL,
  subtitle   VARCHAR(200) NOT NULL DEFAULT '',
  unread     INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  updated_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
  id              SERIAL PRIMARY KEY,
  conversation_id VARCHAR(24) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role            VARCHAR(16) NOT NULL,
  agent           VARCHAR(64) NOT NULL DEFAULT '',
  content         TEXT NOT NULL,
  run_id          VARCHAR(24),
  attachment      JSONB,
  created_at      TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_convo ON messages(conversation_id, id);
