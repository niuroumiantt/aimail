/** 编的样本。公司、人名、邮箱、数字全部虚构;真实客户往来永不进仓库。
 *  每封信对应界面上一种状态:正常读数、编造数字告警、模型失败、丢单通知、推销、
 *  只有一句新内容、参数在附件、信息不足、数量变更。 */

import type { Thread } from "../data/types";

const spark = { model: "Spark · fast", task_version: "summarize_inquiry@1" } as const;

export const threads: Thread[] = [
  {
    id: "t-aurora",
    subject: "RFQ – 48 × 2U servers for Helsinki DC expansion",
    company: "Aurora Compute Oy",
    contact: "Mikko Laine",
    email: "mikko.laine@auroracompute.example",
    region: "赫尔辛基",
    scale: "48 台 · 2U",
    folder: "quote",
    updated_at: "2026-09-19T08:12:00+08:00",
    messages: [
      {
        id: "m-aurora-1",
        direction: "in",
        from_name: "Mikko Laine",
        from_email: "mikko.laine@auroracompute.example",
        sent_at: "2026-09-19T08:12:00+08:00",
        body: `Hi,

We are expanding our Helsinki data center and need 48 units of 2U rack servers with the following minimum spec:

- 2× Intel Xeon E5-2680v4
- 128GB DDR4 ECC RDIMM
- 4× 3.84TB SATA SSD
- Dual 10GbE, redundant PSU

Refurbished / pulled units are acceptable if tested. Please quote CIF Helsinki, lead time, and confirm you can provide a 12-month warranty.

Best regards,
Mikko Laine
Procurement, Aurora Compute Oy`,
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-19T08:13:41+08:00",
      is_inquiry: true,
      language: "en",
      summary_zh:
        "赫尔辛基的 Aurora Compute 扩建机房,要 48 台 2U 机架服务器:双 E5-2680v4、128GB DDR4 ECC、4 块 3.84TB SSD、双万兆、冗余电源,翻新机可接受。要 CIF 赫尔辛基报价、交期,并确认能提供 12 个月保修。",
      summary_en:
        "Aurora Compute (Helsinki) is expanding a DC and needs 48 × 2U rack servers: dual E5-2680v4, 128GB DDR4 ECC, 4 × 3.84TB SSD, dual 10GbE, redundant PSU; refurbished acceptable. Asks for CIF Helsinki pricing, lead time, and a 12-month warranty.",
      facts: [
        "48 台 2U 机架服务器",
        "每台 2× E5-2680v4、128GB DDR4 ECC、4× 3.84TB SATA SSD",
        "双 10GbE、冗余电源",
        "翻新或拆机件可接受,需测试",
        "报价条件 CIF 赫尔辛基",
        "需要 12 个月保修",
      ],
      quoted_numbers: ["48", "2U", "E5-2680v4", "128GB", "3.84TB", "10GbE", "12"],
      unverified: [],
    },
  },
  {
    id: "t-huaxin",
    subject: "询价:DDR5 RDIMM 64GB 4800 ×200",
    company: "深圳华芯系统集成",
    contact: "王婷",
    email: "wangting@huaxin-si.example",
    region: "深圳",
    scale: "200 条 · DDR5 64GB",
    folder: "quote",
    updated_at: "2026-09-19T07:40:00+08:00",
    messages: [
      {
        id: "m-huaxin-1",
        direction: "in",
        from_name: "王婷",
        from_email: "wangting@huaxin-si.example",
        sent_at: "2026-09-19T07:40:00+08:00",
        body: `您好,

我司近期有一批服务器内存需求,请报价:

规格:DDR5 RDIMM 64GB 4800MT/s(2Rx4)
数量:200 条
品牌:原厂,三星、海力士、美光均可
要求:现货优先,请注明可交期
交货:深圳,请分别报 FOB 深圳 和 DDP 深圳(含税)两种价格

盼复。

王婷
深圳华芯系统集成有限公司 采购部`,
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-19T07:41:20+08:00",
      is_inquiry: true,
      language: "zh",
      summary_zh:
        "深圳华芯要 200 条 DDR5 RDIMM 64GB 4800MT/s(2Rx4)原厂内存,三星、海力士、美光均可,现货优先。要求分别报 FOB 深圳和 DDP 深圳(含税)两种价格,并注明交期。",
      summary_en:
        "Shenzhen Huaxin needs 200 × DDR5 RDIMM 64GB 4800MT/s (2Rx4), OEM brands (Samsung / SK hynix / Micron), in-stock preferred. Asks for two prices — FOB Shenzhen and DDP Shenzhen (tax included) — with lead time.",
      facts: [
        "200 条 DDR5 RDIMM 64GB 4800MT/s 2Rx4",
        "原厂品牌:三星、海力士、美光均可",
        "现货优先,要注明交期",
        "要两种报价:FOB 深圳、DDP 深圳含税",
      ],
      quoted_numbers: ["200", "64GB", "4800", "2Rx4"],
      unverified: [],
    },
  },
  {
    id: "t-gulf",
    subject: "URGENT: 4× HGX H200 8-GPU systems — lead time & payment terms",
    company: "Gulf Edge Systems",
    contact: "Omar Haddad",
    email: "omar@gulfedge.example",
    region: "迪拜",
    scale: "4 台 · HGX H200",
    folder: "quote",
    updated_at: "2026-09-18T23:05:00+08:00",
    messages: [
      {
        id: "m-gulf-1",
        direction: "in",
        from_name: "Omar Haddad",
        from_email: "omar@gulfedge.example",
        sent_at: "2026-09-18T23:05:00+08:00",
        body: `Dear Sales,

We have a confirmed end-customer project and need 4 units of HGX H200 8-GPU systems (Supermicro SYS-821GE-TNHR or equivalent), each with 2× Xeon Platinum 8480+, 2TB DDR5, 8× 3.84TB NVMe.

Delivery to Jebel Ali within 6 weeks is a hard requirement. We can do 30% TT with order and 70% before shipment.

Please also confirm you can provide the export compliance documentation for this destination.

Regards,
Omar Haddad
Gulf Edge Systems, Dubai`,
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-18T23:06:02+08:00",
      is_inquiry: true,
      language: "en",
      summary_zh:
        "迪拜 Gulf Edge 有已确认的终端项目,要 4 台 HGX H200 8-GPU 系统(SYS-821GE-TNHR 或同等),每台 2× Platinum 8480+、2TB DDR5、8× 3.84TB NVMe。硬性要求 6 周内交到 Jebel Ali;付款 30% 定金 + 70% 发货前。要我们确认能提供该目的地的出口合规文件。",
      summary_en:
        "Gulf Edge (Dubai) has a confirmed end-customer project and needs 4 × HGX H200 8-GPU systems (SYS-821GE-TNHR or equivalent), each with 2 × Platinum 8480+, 2TB DDR5, 8 × 3.84TB NVMe. Hard requirement: delivery to Jebel Ali within 6 weeks; payment 30% TT with order, 70% before shipment. Asks us to confirm export compliance documentation for the destination.",
      facts: [
        "4 台 HGX H200 8-GPU 系统,SYS-821GE-TNHR 或同等",
        "每台 2× Xeon Platinum 8480+、2TB DDR5、8× 3.84TB NVMe",
        "硬性交期:6 周内到 Jebel Ali",
        "付款 30% 定金 + 70% 发货前",
        "需要出口合规文件——目的地是阿联酋,先核对管制清单再报价",
      ],
      quoted_numbers: ["4", "H200", "8", "SYS-821GE-TNHR", "8480+", "2TB", "3.84TB", "6", "30%", "70%"],
      unverified: [],
    },
  },
  {
    id: "t-usp",
    subject: "Cotação: 3 workstations GPU (RTX 6000 Ada)",
    company: "Instituto de Computação · USP",
    contact: "Ana Ribeiro",
    email: "ana.ribeiro@ic.usp.example",
    region: "圣保罗",
    scale: "3 台 · 工作站",
    folder: "inbox",
    updated_at: "2026-09-18T21:30:00+08:00",
    messages: [
      {
        id: "m-usp-1",
        direction: "in",
        from_name: "Ana Ribeiro",
        from_email: "ana.ribeiro@ic.usp.example",
        sent_at: "2026-09-18T21:30:00+08:00",
        body: `Bom dia,

We are a research lab at the University of São Paulo. We need 3 GPU workstations, each with:

- 1× NVIDIA RTX 6000 Ada 48GB
- Threadripper PRO 7975WX
- 128GB DDR5 ECC
- 2× 4TB NVMe

Please quote FOB Singapore — nossa importação é via porto de Recife, e o despachante cuida do resto.

Obrigada,
Dra. Ana Ribeiro`,
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-18T21:31:15+08:00",
      is_inquiry: true,
      language: "pt-en",
      summary_zh:
        "圣保罗大学计算研究所要 3 台 GPU 工作站:每台 1 张 RTX 6000 Ada 48GB、Threadripper PRO 7975WX、128GB DDR5 ECC、2 块 4TB NVMe。要 FOB 新加坡报价,进口走累西腓港,报关由他们的货代负责。",
      summary_en:
        "USP's Institute of Computing needs 3 GPU workstations: RTX 6000 Ada 48GB, Threadripper PRO 7975WX, 128GB DDR5 ECC, 2 × 4TB NVMe each. Quote FOB Singapore; import via Recife with their own broker.",
      facts: [
        "3 台 GPU 工作站",
        "每台 RTX 6000 Ada 48GB、Threadripper PRO 7975WX、128GB DDR5 ECC、2× 4TB NVMe",
        "报价条件 FOB 新加坡",
        "进口经累西腓港,报关由对方货代负责",
      ],
      quoted_numbers: ["3", "RTX 6000 Ada", "48GB", "7975WX", "128GB", "4TB"],
      unverified: [],
    },
  },
  {
    id: "t-strait",
    subject: "RE: Quotation Q-2609 — SYS-6029U-TR4 (5 units)",
    company: "Strait Managed Services",
    contact: "Daniel Koh",
    email: "daniel.koh@straitms.example",
    region: "新加坡",
    scale: "5 台 · 已报价",
    folder: "inbox",
    updated_at: "2026-09-19T09:02:00+08:00",
    messages: [
      {
        id: "m-strait-1",
        direction: "out",
        from_name: "Glocalstorage Sales",
        from_email: "sales@glocalstorage.example",
        sent_at: "2026-09-12T15:20:00+08:00",
        body: `Hi Daniel,

Please find our quotation Q-2609 below:

Model: Supermicro SYS-6029U-TR4
Config: 2× Xeon Gold 6248, 256GB DDR4 ECC, 2× 960GB SSD, 4× 1GbE, redundant 1000W PSU
Quantity: 5 units
Unit price: USD 4,850 (FOB Singapore)
Lead time: 2 weeks
Validity: 14 days

Best regards,
Glocalstorage`,
      },
      {
        id: "m-strait-2",
        direction: "in",
        from_name: "Daniel Koh",
        from_email: "daniel.koh@straitms.example",
        sent_at: "2026-09-19T09:02:00+08:00",
        body: `Hi,

We were told this model is EOL. Can you still supply the 5 units, or what is the direct replacement?

Regards,
Daniel`,
        quoted: `From: sales@glocalstorage.example
Sent: Friday, 12 September 2026 3:20 pm
Subject: Quotation Q-2609 — SYS-6029U-TR4 (5 units)

Hi Daniel,

Please find our quotation Q-2609 below:

Model: Supermicro SYS-6029U-TR4
Config: 2× Xeon Gold 6248, 256GB DDR4 ECC, 2× 960GB SSD, 4× 1GbE, redundant 1000W PSU
Quantity: 5 units
Unit price: USD 4,850 (FOB Singapore)
Lead time: 2 weeks
Validity: 14 days`,
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-19T09:03:10+08:00",
      is_inquiry: true,
      language: "en",
      summary_zh:
        "新加坡 Strait 的 Daniel 回复报价 Q-2609:他们被告知 SYS-6029U-TR4 已 EOL,问我们还能不能供这 5 台,或者直接替代型号是什么。本封只有这一个问题,配置和价格都在引用的历史里,没有变化。",
      summary_en:
        "Daniel (Strait, Singapore) replies to quotation Q-2609: they were told SYS-6029U-TR4 is EOL and asks whether we can still supply the 5 units, or what the direct replacement is. This message asks only that; config and price are unchanged in the quoted history.",
      facts: [
        "回复的是我方报价 Q-2609",
        "对方被告知 SYS-6029U-TR4 已 EOL",
        "问:还能不能供这 5 台,或替代型号是什么",
        "要的是「能不能供」的答复,不是重新报配置",
      ],
      quoted_numbers: ["Q-2609", "SYS-6029U-TR4", "5"],
      unverified: [],
    },
  },
  {
    id: "t-northgrid",
    subject: "Re: RFQ 2U storage nodes",
    company: "NorthGrid Hosting",
    contact: "Priya Nair",
    email: "priya@northgrid.example",
    region: "多伦多",
    scale: "已流失",
    folder: "invalid",
    updated_at: "2026-09-18T04:47:00+08:00",
    messages: [
      {
        id: "m-northgrid-1",
        direction: "in",
        from_name: "Priya Nair",
        from_email: "priya@northgrid.example",
        sent_at: "2026-09-18T04:47:00+08:00",
        body: `Hi,

Thanks for the quote. We've decided to go with another supplier this round, mainly due to lead time. Will keep you in mind for the next batch.

Best,
Priya`,
        quoted: `On 15 Sep 2026, sales@glocalstorage.example wrote:

Hi Priya, quotation attached for 12× 2U storage nodes, each 24× 16TB SAS HDD, 2× Xeon Silver 4314, 128GB. Lead time 5 weeks.

On 11 Sep 2026, priya@northgrid.example wrote:

We need 12 units of 2U storage nodes with 24× 16TB drives each. Please quote CIF Toronto.`,
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-18T04:48:30+08:00",
      is_inquiry: false,
      language: "en",
      summary_zh:
        "这不是询盘,是丢单通知:多伦多 NorthGrid 决定这一轮选别的供应商,主要原因是交期;愿意下一批再考虑我们。引用历史里的 12 台存储节点是已经结束的询价。",
      summary_en:
        "Not an inquiry — a lost-deal notice: NorthGrid (Toronto) chose another supplier this round, mainly over lead time, and will consider us next batch. The 12 storage nodes in the quoted history are the closed RFQ.",
      facts: ["丢单,原因是交期", "对方愿意下一批再询", "引用历史里的 12 台是已结束的询价"],
      quoted_numbers: ["12"],
      unverified: [],
    },
  },
  {
    id: "t-promo",
    subject: "September specials: industrial connectors up to 40% off!",
    company: "Connector World",
    contact: "Marketing",
    email: "marketing@connector-world.example",
    region: "—",
    scale: "推销",
    folder: "invalid",
    updated_at: "2026-09-18T02:00:00+08:00",
    messages: [
      {
        id: "m-promo-1",
        direction: "in",
        from_name: "Connector World",
        from_email: "marketing@connector-world.example",
        sent_at: "2026-09-18T02:00:00+08:00",
        body: `Dear Purchasing Manager,

This September only: M12, D-sub and terminal blocks up to 40% off. Minimum order 500 pcs. Reply to this email or visit our catalog.

Unsubscribe | Connector World Ltd.`,
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-18T02:01:05+08:00",
      is_inquiry: false,
      language: "en",
      summary_zh: "这不是询盘,是群发推销:工业连接器九月促销,起订 500 件。",
      summary_en: "Not an inquiry — a bulk promotion for industrial connectors, MOQ 500 pcs.",
      facts: ["群发推销", "起订 500 件"],
      quoted_numbers: ["40%", "500"],
      unverified: [],
    },
  },
  {
    id: "t-mytel",
    subject: "Supermicro B300 build-to-order — spec attached",
    company: "MyTel Infrastructure Sdn Bhd",
    contact: "Farah Aziz",
    email: "farah.aziz@mytel.example",
    region: "吉隆坡",
    scale: "2 台 · B300 · 参数在附件",
    folder: "inbox",
    updated_at: "2026-09-18T17:15:00+08:00",
    messages: [
      {
        id: "m-mytel-1",
        direction: "in",
        from_name: "Farah Aziz",
        from_email: "farah.aziz@mytel.example",
        sent_at: "2026-09-18T17:15:00+08:00",
        body: `Hi,

Please see the attached spec sheet and quote accordingly. We need 2 units.

Regards,
Farah`,
        attachments: ["B300-BTO-spec.pdf"],
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-18T17:16:00+08:00",
      is_inquiry: true,
      language: "en",
      summary_zh:
        "吉隆坡 MyTel 要 2 台 Supermicro B300 定制机,配置全部在附件 B300-BTO-spec.pdf 里,正文没有任何参数。现在读不了附件,报价前必须人工打开看。",
      summary_en:
        "MyTel (Kuala Lumpur) wants 2 × Supermicro B300 build-to-order units; the entire spec is in the attached B300-BTO-spec.pdf, the body carries no parameters. Attachments are not read yet — open it manually before quoting.",
      facts: ["2 台 Supermicro B300 定制", "参数只在附件里,正文没有", "附件读取是 M7,现在要人工看"],
      quoted_numbers: ["2", "B300"],
      unverified: [],
    },
  },
  {
    id: "t-rheinwerk",
    subject: "Anfrage: 500× 3.84TB enterprise SSD (used/refurb)",
    company: "Rheinwerk Datentechnik GmbH",
    contact: "Jonas Weber",
    email: "j.weber@rheinwerk-dt.example",
    region: "杜塞尔多夫",
    scale: "500 片 · 3.84TB SSD",
    folder: "quote",
    updated_at: "2026-09-18T15:48:00+08:00",
    messages: [
      {
        id: "m-rheinwerk-1",
        direction: "in",
        from_name: "Jonas Weber",
        from_email: "j.weber@rheinwerk-dt.example",
        sent_at: "2026-09-18T15:48:00+08:00",
        body: `Guten Tag,

we are looking for 500 pcs 3.84TB SAS or SATA enterprise SSDs. Used or refurbished is OK if health is ≥ 90% and you provide SMART reports.

Bitte geben Sie Garantie und DOA-Regelung an. Delivery DAP Düsseldorf.

Mit freundlichen Grüßen
Jonas Weber`,
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-18T15:49:12+08:00",
      is_inquiry: true,
      language: "de-en",
      summary_zh:
        "杜塞尔多夫 Rheinwerk 要 500 片 3.84TB SAS 或 SATA 企业级 SSD,二手或翻新可以,但健康度要 ≥ 90% 且提供 SMART 报告。要求写明保修和 DOA 政策,交货 DAP 杜塞尔多夫。",
      summary_en:
        "Rheinwerk (Düsseldorf) wants 500 × 3.84TB SAS/SATA enterprise SSDs; used or refurbished acceptable if health ≥ 90% with SMART reports. Asks for warranty and DOA policy; delivery DAP Düsseldorf.",
      facts: [
        "500 片 3.84TB SAS 或 SATA 企业级 SSD",
        "二手/翻新可以,健康度 ≥ 90%,要 SMART 报告",
        "要写明保修与 DOA 政策",
        "交货 DAP 杜塞尔多夫",
      ],
      quoted_numbers: ["500", "3.84TB", "90%"],
      unverified: [],
    },
  },
  {
    id: "t-savanna",
    subject: "1U servers under USD 800?",
    company: "Savanna Net Ltd",
    contact: "Brian Otieno",
    email: "brian@savannanet.example",
    region: "内罗毕",
    scale: "10–15 台 · 无型号",
    folder: "inbox",
    updated_at: "2026-09-18T14:02:00+08:00",
    messages: [
      {
        id: "m-savanna-1",
        direction: "in",
        from_name: "Brian Otieno",
        from_email: "brian@savannanet.example",
        sent_at: "2026-09-18T14:02:00+08:00",
        body: `Hello,

We are a small ISP in Nairobi. Do you have any 1U servers under USD 800 each? Any brand is fine. Maybe 10-15 pieces.

Thanks,
Brian`,
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-18T14:03:00+08:00",
      is_inquiry: true,
      language: "en",
      summary_zh:
        "内罗毕的小型 ISP 想要 10–15 台 1U 服务器,每台 800 美元以内,品牌不限。没有型号、没有配置、没有交货条件——信息不足,回信要先问清用途和最低配置。",
      summary_en:
        "A small ISP in Nairobi wants 10–15 × 1U servers under USD 800 each, any brand. No model, no config, no delivery terms — insufficient to quote; the reply should ask about workload and minimum spec first.",
      facts: ["10–15 台 1U 服务器", "单价 800 美元以内", "品牌不限", "没有型号和配置,信息不足"],
      quoted_numbers: ["1U", "800", "10-15"],
      unverified: [],
    },
  },
  {
    id: "t-vinaparts",
    subject: "RFQ 1,000 pcs 32GB DDR4 ECC UDIMM",
    company: "VinaParts Manufacturing",
    contact: "Nguyễn Thị Lan",
    email: "lan.nguyen@vinaparts.example",
    region: "海防",
    scale: "1,000 条 · DDR4 32GB",
    folder: "quote",
    updated_at: "2026-09-18T11:20:00+08:00",
    messages: [
      {
        id: "m-vinaparts-1",
        direction: "in",
        from_name: "Nguyễn Thị Lan",
        from_email: "lan.nguyen@vinaparts.example",
        sent_at: "2026-09-18T11:20:00+08:00",
        body: `Dear Sir/Madam,

We need 1,000 pcs of 32GB DDR4-3200 ECC UDIMM for our factory line upgrade. Target price is USD 125/pc.

Delivery to Hai Phong port by 30 Oct 2026. Please quote CIF Hai Phong.

Best regards,
Nguyễn Thị Lan
VinaParts Manufacturing`,
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-18T11:21:33+08:00",
      is_inquiry: true,
      language: "en",
      summary_zh:
        "海防 VinaParts 产线升级,要 1,200 条 32GB DDR4-3200 ECC UDIMM,目标价 125 美元/条。10 月 30 日前 CIF 交到海防港。",
      summary_en:
        "VinaParts (Hai Phong) needs 1,200 × 32GB DDR4-3200 ECC UDIMM for a line upgrade, target USD 125/pc, CIF Hai Phong by 30 Oct 2026.",
      facts: ["产线升级用 DDR4 ECC UDIMM", "目标价 125 美元/条", "10 月 30 日前 CIF 海防"],
      quoted_numbers: ["1200", "32GB", "3200", "125", "30 Oct 2026"],
      unverified: ["1200"],
    },
  },
  {
    id: "t-hanbit",
    subject: "Re: Re: GPU server order — quantity change",
    company: "Hanbit Cloud",
    contact: "김민준",
    email: "minjun.kim@hanbitcloud.example",
    region: "首尔",
    scale: "32 台 · L40S",
    folder: "quote",
    updated_at: "2026-09-18T10:05:00+08:00",
    messages: [
      {
        id: "m-hanbit-1",
        direction: "in",
        from_name: "김민준",
        from_email: "minjun.kim@hanbitcloud.example",
        sent_at: "2026-09-10T10:30:00+08:00",
        body: `Hello,

We plan to order 20 units of 4-GPU servers with NVIDIA L40S, 2× Xeon Gold 6430, 512GB DDR5, 4× 7.68TB NVMe. Please quote FOB Singapore with lead time.

Thanks,
Min-jun Kim`,
      },
      {
        id: "m-hanbit-2",
        direction: "out",
        from_name: "Glocalstorage Sales",
        from_email: "sales@glocalstorage.example",
        sent_at: "2026-09-11T14:00:00+08:00",
        body: `Hi Min-jun,

Quotation Q-2602 attached: 20 units as specified, USD 38,900/unit FOB Singapore, lead time 4 weeks, validity 14 days.

Best regards,
Glocalstorage`,
      },
      {
        id: "m-hanbit-3",
        direction: "in",
        from_name: "김민준",
        from_email: "minjun.kim@hanbitcloud.example",
        sent_at: "2026-09-18T10:05:00+08:00",
        body: `Hi,

Our customer increased the order. Please change the quantity to 32 units, same configuration. Can you hold the unit price from Q-2602?

Thanks,
Min-jun`,
        quoted: `On 11 Sep 2026, sales@glocalstorage.example wrote:
Quotation Q-2602 attached: 20 units as specified, USD 38,900/unit FOB Singapore, lead time 4 weeks, validity 14 days.`,
      },
    ],
    reading: {
      ...spark,
      status: "ok",
      produced_at: "2026-09-18T10:06:10+08:00",
      is_inquiry: true,
      language: "en",
      summary_zh:
        "首尔 Hanbit 的终端客户加单:把 Q-2602 的 20 台改成 32 台,配置不变(4× L40S、2× Gold 6430、512GB、4× 7.68TB)。问能否维持 Q-2602 的单价。",
      summary_en:
        "Hanbit (Seoul): end customer increased the order — change Q-2602 from 20 to 32 units, same config (4 × L40S, 2 × Gold 6430, 512GB, 4 × 7.68TB). Asks whether we can hold the Q-2602 unit price.",
      facts: ["数量从 20 台改为 32 台", "配置不变", "问能否维持 Q-2602 单价"],
      quoted_numbers: ["Q-2602", "20", "32", "L40S", "6430", "512GB", "7.68TB"],
      unverified: [],
    },
  },
  {
    id: "t-lumen",
    subject: "Mixed lot: memory + NICs + misc",
    company: "Lumen Trading FZE",
    contact: "Rashid Al-Amin",
    email: "rashid@lumentrading.example",
    region: "沙迦",
    scale: "混合清单 · 未读出",
    folder: "inbox",
    updated_at: "2026-09-18T09:10:00+08:00",
    messages: [
      {
        id: "m-lumen-1",
        direction: "in",
        from_name: "Rashid Al-Amin",
        from_email: "rashid@lumentrading.example",
        sent_at: "2026-09-18T09:10:00+08:00",
        body: `Hi, pls quote the following lot, all used ok:

16GB DDR4 2666 RDIMM x 340 / 32GB DDR4 2933 RDIMM x 120 / 64GB DDR4 3200 LRDIMM x 40 / 8GB DDR3 1600 x 900 / ConnectX-4 25G dual x 60 / ConnectX-5 100G x 22 / X710-DA2 x 85 / 960GB SATA SSD x 200 / 1.92TB SAS SSD x 75 / 2.5" caddies (Dell 14G) x 400 / 3.5" caddies (HPE G10) x 300 / 750W PSU (Dell) x 50 / rails 2U generic x 100 / misc cables lot / also need price for LTO-8 tapes x 500 and 2 x tape library (any brand) …

thx
Rashid`,
      },
    ],
    reading: {
      ...spark,
      status: "failed",
      produced_at: "2026-09-18T09:12:44+08:00",
      reason: "两次都没给出合规 JSON:第二次输出仍在 facts 数组中途被截断",
    },
  },
];
