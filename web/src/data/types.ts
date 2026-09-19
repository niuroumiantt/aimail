/** 界面看到的数据形状。服务端(M2 起)的 JSON 与这里一致;样本(fixtures/)也照这个写。 */

export type Folder = "inbox" | "quote" | "replied" | "invalid";

export type Attribution = {
  /** 谁算的,例如 "Spark · fast" —— 宪法第三条:派生物有署名 */
  model: string;
  /** 任务合同的版本,例如 "summarize_inquiry@3" */
  task_version: string;
  /** ISO 时间 */
  produced_at: string;
};

export type Reading =
  | (Attribution & {
      status: "ok";
      is_inquiry: boolean;
      language: string;
      summary_zh: string;
      summary_en: string;
      facts: string[];
      quoted_numbers: string[];
      /** 摘要里引用、但原文里找不到的数字。非空 = 摘要不可信(宪法第四条) */
      unverified: string[];
    })
  | (Attribution & {
      status: "failed";
      /** 模型没给出合规输出的原因。界面必须显示失败,不许显示空白(宪法第六条) */
      reason: string;
    });

/** 一份附件在线程里的样子。文字不随线程下发,点开再取 */
export type AttachmentRef = {
  id: string;
  name: string;
  size: number;
  /** ok = 读出文字了;failed = 读不出(原因在 reason);none = 还没读 */
  read: "ok" | "failed" | "none";
  reason?: string;
};

/** 附件里读出来的文字。派生物:代码读的,带署名落库(ADR 见 README 附件一节) */
export type AttachmentText = {
  id: string;
  name: string;
  status: "ok" | "failed" | "none";
  text: string;
  reason: string;
};

/** 推送发件箱的状态:线索一变就 POST 给下游(OA / PO / 合同),送没送到都看得见 */
export type OutboxStatus = {
  /** 没配 webhook 就是 false,界面什么都不显示 */
  configured: boolean;
  pending: number;
  /** 试过、没送到、还会再试的 */
  failed: number;
  delivered: number;
  last_error: string;
};

export type Message = {
  id: string;
  direction: "in" | "out";
  from_name: string;
  from_email: string;
  sent_at: string;
  /** 本封新增的正文 */
  body: string;
  /** 引用的历史,默认折叠 */
  quoted?: string;
  attachments?: AttachmentRef[];
};

/** 这位客户此前的一条往来。代码从不可变记录里查出来的(ADR-0005),不是模型写的 */
export type HistoryItem = {
  id: string;
  subject: string;
  first_at: string;
  last_at: string;
  folder: Folder;
  replied: boolean;
  lead_status: LeadStatus | "";
  /** 最后一封来信的原文开头 */
  excerpt: string;
};

export type Thread = {
  id: string;
  subject: string;
  company: string;
  contact: string;
  email: string;
  region: string;
  /** 一句话的规模提示,列表里显示,例如 "48 台 · 2U" */
  scale: string;
  folder: Folder;
  updated_at: string;
  /** 详情才有;列表里是空数组 */
  messages: Message[];
  reading?: Reading;
  /** 同一位客户的其他线程。详情才有;空数组 = 第一次来信 */
  history?: HistoryItem[];
};

export type Priority = "high" | "normal" | "low";

/** 模型提出的线索建议 —— 建议不是事实(宪法第五条),人确认后才成为 Lead */
export type LeadSuggestion = Attribution & {
  id: string;
  thread_id: string;
  company: string;
  contact: string;
  wants: string;
  quantity: string;
  region: string;
  priority: Priority;
  /** 建议里引用、但原文里找不到的数字。非空 = 别急着确认 */
  unverified?: string[];
};

/** 模型起的回信草稿。人改人发;正文里留 [姓名] 占位,没换掉发不出去(宪法第二条) */
export type ReplyDraft =
  | (Attribution & {
      id: string;
      status: "ok";
      language: string;
      subject: string;
      body: string;
      /** 草稿向客户提的问题 */
      open_questions: string[];
      quoted_numbers: string[];
      /** 草稿里引用、但来信里找不到的数字。非空 = 发之前先核对(宪法第四条) */
      unverified: string[];
    })
  | (Attribution & { id: string; status: "failed"; reason: string });

/** 人按下「发送」时交给服务端的内容;令牌由数据源在发送那一刻签取,界面不持有 */
export type SendRequest = {
  to: string[];
  subject: string;
  body: string;
  /** 从哪份草稿改出来的;纯手写就没有 */
  draft_id?: string;
};

export type LeadStatus = "quote" | "quoted" | "following" | "won" | "lost";

export type Lead = {
  id: string;
  thread_id: string;
  company: string;
  contact: string;
  wants: string;
  quantity: string;
  region: string;
  status: LeadStatus;
  confirmed_by: string;
  confirmed_at: string;
  next_step: string;
};
