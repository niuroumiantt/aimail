/** 界面看到的数据形状。服务端(M2 起)的 JSON 与这里一致;样本(fixtures/)也照这个写。 */

export type Folder = "inbox" | "quote" | "replied" | "invalid";

export type Attribution = {
  /** 谁算的,例如 "Spark · fast" —— 宪法第三条:派生物有署名 */
  model: string;
  /** 任务合同的版本,例如 "summarize_inquiry@1" */
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
  attachments?: string[];
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
  messages: Message[];
  reading?: Reading;
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
