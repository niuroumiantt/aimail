-- mail2leads 数据模式。SQLite,WAL。多邮箱从第一天起(mailbox_id 无处不在)。
-- 原文表(message、attachment)INSERT 之后永不修改、永不删除:触发器在最下面(宪法第三条)。
-- 派生表以 `-- derived` 标记,必须带四个署名字段(tools/guard_attribution.py 核对)。

CREATE TABLE IF NOT EXISTS mailbox (
  id INTEGER PRIMARY KEY,
  address TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thread (
  id INTEGER PRIMARY KEY,
  mailbox_id INTEGER NOT NULL REFERENCES mailbox(id),
  subject TEXT NOT NULL,
  subject_key TEXT NOT NULL,                 -- 去掉 Re:/Fwd: 后的小写主题,归并用
  contact_email TEXT NOT NULL,               -- 对方(来信是发件人,去信是收件人)
  contact_name TEXT NOT NULL DEFAULT '',
  folder TEXT NOT NULL DEFAULT 'inbox' CHECK (folder IN ('inbox', 'quote', 'replied', 'invalid')),
  first_at TEXT NOT NULL,
  last_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS thread_recent ON thread (mailbox_id, last_at DESC);
CREATE INDEX IF NOT EXISTS thread_key ON thread (mailbox_id, subject_key, contact_email);

CREATE TABLE IF NOT EXISTS message (
  id INTEGER PRIMARY KEY,
  mailbox_id INTEGER NOT NULL REFERENCES mailbox(id),
  thread_id INTEGER NOT NULL REFERENCES thread(id),
  message_id TEXT NOT NULL,                  -- RFC 5322 Message-ID;缺失时用 sha256:<原文哈希>
  in_reply_to TEXT NOT NULL DEFAULT '',
  refs TEXT NOT NULL DEFAULT '',             -- References 头,空格分隔
  direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
  from_name TEXT NOT NULL DEFAULT '',
  from_email TEXT NOT NULL,
  to_emails TEXT NOT NULL DEFAULT '',        -- 逗号分隔
  subject TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  received_at TEXT NOT NULL,
  body_new TEXT NOT NULL,                    -- 本封新增的正文
  body_quoted TEXT NOT NULL DEFAULT '',      -- 引用的历史
  raw BLOB NOT NULL,                         -- RFC822 原文,一个字节都不动
  raw_sha256 TEXT NOT NULL UNIQUE,
  UNIQUE (mailbox_id, message_id)
);
CREATE INDEX IF NOT EXISTS message_by_thread ON message (thread_id, sent_at);

CREATE TABLE IF NOT EXISTS attachment (
  id INTEGER PRIMARY KEY,
  message_id INTEGER NOT NULL REFERENCES message(id),
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  content BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS attachment_by_message ON attachment (message_id);

CREATE TABLE IF NOT EXISTS ingest_cursor (
  mailbox_id INTEGER NOT NULL REFERENCES mailbox(id),
  folder TEXT NOT NULL,
  uid_validity INTEGER NOT NULL,
  last_uid INTEGER NOT NULL,
  PRIMARY KEY (mailbox_id, folder)
);

-- derived
CREATE TABLE IF NOT EXISTS message_reading (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES message(id),
  model TEXT NOT NULL,
  task_version TEXT NOT NULL,
  produced_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
  payload TEXT NOT NULL,                     -- JSON:合同的输出 + unverified
  reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS reading_by_source ON message_reading (source_id, produced_at DESC);

-- 推送发件箱:线索的每次变化一条,送到为止(M8)
CREATE TABLE IF NOT EXISTS outbox (
  id INTEGER PRIMARY KEY,
  mailbox_id INTEGER NOT NULL REFERENCES mailbox(id),
  event TEXT NOT NULL CHECK (event IN ('lead.confirmed', 'lead.updated')),
  lead_id INTEGER NOT NULL REFERENCES lead(id),
  payload TEXT NOT NULL,                     -- JSON:lead@1,记事件当时的样子
  created_at TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_at TEXT NOT NULL,
  delivered_at TEXT,
  last_error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS outbox_due ON outbox (delivered_at, next_at);

-- derived
CREATE TABLE IF NOT EXISTS attachment_text (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES attachment(id),
  model TEXT NOT NULL,                       -- 谁读的:pypdf x / openpyxl x / stdlib
  task_version TEXT NOT NULL,
  produced_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
  text TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS attachment_text_by_source ON attachment_text (source_id, produced_at DESC);

-- derived
CREATE TABLE IF NOT EXISTS lead_suggestion (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES message(id),
  thread_id INTEGER NOT NULL REFERENCES thread(id),
  model TEXT NOT NULL,
  task_version TEXT NOT NULL,
  produced_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'confirmed', 'dismissed', 'failed')),
  payload TEXT NOT NULL,                     -- JSON:合同的输出 + unverified
  reason TEXT NOT NULL DEFAULT '',
  decided_by TEXT NOT NULL DEFAULT '',
  decided_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS suggestion_by_status ON lead_suggestion (status, produced_at DESC);

-- 线索是人确认过的事实(宪法第五条):confirmed_by 非空,写它的接口必须带人的身份。
CREATE TABLE IF NOT EXISTS lead (
  id INTEGER PRIMARY KEY,
  mailbox_id INTEGER NOT NULL REFERENCES mailbox(id),
  thread_id INTEGER NOT NULL REFERENCES thread(id),
  suggestion_id INTEGER REFERENCES lead_suggestion(id),
  company TEXT NOT NULL,
  contact TEXT NOT NULL DEFAULT '',
  wants TEXT NOT NULL,
  quantity TEXT NOT NULL DEFAULT '',
  region TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'quote'
    CHECK (status IN ('quote', 'quoted', 'following', 'won', 'lost')),
  next_step TEXT NOT NULL DEFAULT '',
  confirmed_by TEXT NOT NULL CHECK (confirmed_by <> ''),
  confirmed_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS lead_recent ON lead (mailbox_id, updated_at DESC);

-- derived
CREATE TABLE IF NOT EXISTS reply_draft (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES message(id),   -- 针对哪封来信起的草
  thread_id INTEGER NOT NULL REFERENCES thread(id),
  model TEXT NOT NULL,
  task_version TEXT NOT NULL,
  produced_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
  payload TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS draft_by_thread ON reply_draft (thread_id, produced_at DESC);

-- 人发出去的信(宪法第二条):sent_by 非空;正文同时以 direction='out' 落进 message 表,线程里能看到。
CREATE TABLE IF NOT EXISTS outbound (
  id INTEGER PRIMARY KEY,
  mailbox_id INTEGER NOT NULL REFERENCES mailbox(id),
  thread_id INTEGER NOT NULL REFERENCES thread(id),
  message_pk INTEGER NOT NULL REFERENCES message(id),
  draft_id INTEGER REFERENCES reply_draft(id),
  sent_by TEXT NOT NULL CHECK (sent_by <> ''),
  sent_at TEXT NOT NULL,
  transport_result TEXT NOT NULL DEFAULT ''
);

-- 原文不可变。谁想改,数据库直接拒绝,不靠代码自觉。
CREATE TRIGGER IF NOT EXISTS message_no_update BEFORE UPDATE ON message
BEGIN
  SELECT RAISE(ABORT, '原文不可变:message 不允许 UPDATE');
END;
CREATE TRIGGER IF NOT EXISTS message_no_delete BEFORE DELETE ON message
BEGIN
  SELECT RAISE(ABORT, '原文不可变:message 不允许 DELETE');
END;
CREATE TRIGGER IF NOT EXISTS attachment_no_update BEFORE UPDATE ON attachment
BEGIN
  SELECT RAISE(ABORT, '原文不可变:attachment 不允许 UPDATE');
END;
CREATE TRIGGER IF NOT EXISTS attachment_no_delete BEFORE DELETE ON attachment
BEGIN
  SELECT RAISE(ABORT, '原文不可变:attachment 不允许 DELETE');
END;
