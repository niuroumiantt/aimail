import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { createDemoInboxState, demoInboxReducer, InboxDesignReview } from "./inbox-design-review";

const mainCustomer = "purchasing@obsidian.example";
const reader = () => within(screen.getByRole("main", { name: "邮件阅读区" }));
const customerPanel = () => within(screen.getByRole("complementary", { name: "客户需求栏" }));
const gpuProject = () => within(customerPanel().getByRole("article", { name: "H200 GPU 服务器采购" }));
const storageProject = () => within(customerPanel().getByRole("article", { name: "2U 存储节点采购" }));

it("keeps latest customer requirements in a sibling pane while reading old mail and other projects", () => {
  const { container } = render(<InboxDesignReview />);
  const workspace = container.querySelector(".ir-workspace")!;
  const customer = screen.getByRole("complementary", { name: "客户需求栏" });
  expect(customer.parentElement).toBe(workspace);
  expect(container.querySelector(".ir-reader-scroll")!.contains(customer)).toBe(false);
  expect(gpuProject().getByText("2 台", { exact: true })).toBeInTheDocument();
  expect(storageProject().getByText("12 台", { exact: true })).toBeInTheDocument();
  fireEvent.click(customerPanel().getByRole("button", { name: "查看来源邮件：客户最初询价 · 4 台" }));
  expect(reader().getByRole("heading", { name: "H200 GPU 服务器 · 最初 4 台询价" })).toBeInTheDocument();
  expect(reader().getByText(/我们计划为新加坡机房采购 4 台/)).toBeInTheDocument();
  expect(gpuProject().getByText("2 台", { exact: true })).toBeInTheDocument();
  expect(storageProject().getByText("12 台", { exact: true })).toBeInTheDocument();
  fireEvent.click(customerPanel().getByRole("button", { name: "查看来源邮件：独立存储需求 · 12 台" }));
  expect(reader().getByRole("heading", { name: "独立项目：2U 存储节点 · 12 台" })).toBeInTheDocument();
  expect(gpuProject().getByText("2 台", { exact: true })).toBeInTheDocument();
  fireEvent.click(gpuProject().getByRole("button", { name: /查看原文来源/ }));
  expect(reader().getByRole("heading", { name: "Re: H200 采购 · 数量调整为 2 台" })).toBeInTheDocument();
});

it("clusters full correspondence by contact while retaining actual outbound sender and separate project topics", () => {
  render(<InboxDesignReview />);
  const list = within(screen.getByRole("region", { name: "邮件列表" }));
  const contact = list.getByRole("button", { name: "曜石计算，purchasing@obsidian.example，4 封往来，4 条买卖线索" });
  expect(contact).toHaveAttribute("aria-expanded", "true");
  expect(list.getByText("6 位联系人 · 9 封往来")).toBeInTheDocument();
  expect(list.getByRole("button", { name: /最初 4 台询价/ })).toBeInTheDocument();
  expect(list.getByRole("button", { name: /数量调整为 2 台/ })).toBeInTheDocument();
  expect(list.getByRole("button", { name: /独立项目：2U 存储节点/ })).toBeInTheDocument();
  fireEvent.click(list.getByRole("button", { name: /我方报价，青岚贸易（我方）/ }));
  expect(reader().getByText("sales@qinglan.example", { exact: true })).toBeInTheDocument();
  expect(reader().getByText("收件人：purchasing@obsidian.example")).toBeInTheDocument();
  expect(reader().getByText("我方历史发出邮件")).toBeInTheDocument();
  expect(gpuProject().getByText("2 台", { exact: true })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox", { name: "按联系人聚拢" }));
  expect(list.queryByRole("button", { name: "曜石计算，purchasing@obsidian.example，4 封往来，4 条买卖线索" })).not.toBeInTheDocument();
  expect(list.getByRole("button", { name: /我方报价，青岚贸易（我方）/ })).toBeInTheDocument();
  expect(customerPanel().getByText("4 封往来 · 当前示例邮箱内该联系人全部往来")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "搜索示例邮件" }), { target: { value: "曜石计算" } });
  expect(list.getByRole("button", { name: /我方报价，青岚贸易（我方）/ })).toBeInTheDocument();
  expect(list.getByText("4 封示例邮件")).toBeInTheDocument();
  expect(gpuProject().getByText("2 台", { exact: true })).toBeInTheDocument();
});

it("refreshes unchanged fixture sources without replacing snapshots and updates only the changed project for new mail", () => {
  const initial = createDemoInboxState();
  const refreshed = demoInboxReducer(initial, { type: "refresh" });
  expect(refreshed.messages).toBe(initial.messages);
  expect(refreshed.snapshots).toBe(initial.snapshots);
  expect(refreshed.snapshots[mainCustomer].version).toBe(1);
  expect(refreshed.notice).toMatch(/没有新邮件/);
  const added = demoInboxReducer(refreshed, { type: "demo-new-mail" });
  expect(added.messages).toHaveLength(initial.messages.length + 1);
  expect(added.snapshots[mainCustomer].sourceRevision).not.toBe(initial.snapshots[mainCustomer].sourceRevision);
  expect(added.snapshots[mainCustomer].sourceRevision).toContain("gpu-new");
  expect(added.snapshots[mainCustomer].version).toBe(2);
  expect(added.snapshots[mainCustomer].projects[0].quantity).toBe("3 台");
  expect(added.snapshots[mainCustomer].projects[0].sourceId).toBe("gpu-new");
  expect(added.snapshots[mainCustomer].projects[1]).toBe(initial.snapshots[mainCustomer].projects[1]);
  expect(added.snapshots["stock@polaris.example"]).toBe(initial.snapshots["stock@polaris.example"]);
  const unchangedAgain = demoInboxReducer(added, { type: "refresh" });
  expect(unchangedAgain.snapshots).toBe(added.snapshots);
  expect(unchangedAgain.snapshots[mainCustomer].version).toBe(2);
  expect(demoInboxReducer(added, { type: "demo-new-mail" }).messages).toBe(added.messages);
});

it("updates the cumulative fixture to 3 units even when an old source is open, with the new source independently reachable", () => {
  render(<InboxDesignReview />);
  fireEvent.click(customerPanel().getByRole("button", { name: "查看来源邮件：客户最初询价 · 4 台" }));
  fireEvent.click(screen.getByRole("button", { name: "演示新增来信" }));
  expect(reader().getByRole("heading", { name: "H200 GPU 服务器 · 最初 4 台询价" })).toBeInTheDocument();
  expect(gpuProject().getByText("3 台", { exact: true })).toBeInTheDocument();
  expect(storageProject().getByText("12 台", { exact: true })).toBeInTheDocument();
  expect(customerPanel().getByText("示例 v2")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "刷新演示" }));
  expect(gpuProject().getByText("3 台", { exact: true })).toBeInTheDocument();
  expect(customerPanel().getByText("示例 v2")).toBeInTheDocument();
  fireEvent.click(gpuProject().getByRole("button", { name: /查看原文来源/ }));
  expect(reader().getByRole("heading", { name: "Re: H200 采购 · 最终调整为 3 台" })).toBeInTheDocument();
  expect(reader().getByText(/请把 H200 GPU 服务器数量从 2 台调整为 3 台/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "示例来信已加入" })).toBeDisabled();
});

it("opens and retains local drafts without changing customer scope or requirements, and offers mobile customer navigation", () => {
  const { container } = render(<InboxDesignReview />);
  fireEvent.click(screen.getByRole("button", { name: "回复草稿" }));
  const editor = screen.getByRole("textbox", { name: "编辑本地回复草稿" });
  expect(editor).toHaveFocus();
  fireEvent.change(editor, { target: { value: "收到，我们按最新 2 台更新报价。" } });
  expect(gpuProject().getByText("2 台", { exact: true })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "保留草稿" }));
  expect(screen.getByText("草稿已保留在当前预览中，未发送")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "回复草稿" }));
  expect(screen.getByRole("textbox", { name: "编辑本地回复草稿" })).toHaveValue("收到，我们按最新 2 台更新报价。");
  expect(screen.queryByRole("button", { name: /^发送/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "客户需求" }));
  expect(container.querySelector(".ir-workspace")).toHaveAttribute("data-mobile-view", "customer");
  fireEvent.click(screen.getByRole("button", { name: "返回邮件原文" }));
  expect(container.querySelector(".ir-workspace")).toHaveAttribute("data-mobile-view", "mail");
  expect(gpuProject().getByText("2 台", { exact: true })).toBeInTheDocument();
});

it("keeps buyer and supplier mail in leads while bills and subscriptions remain ordinary mail", () => {
  render(<InboxDesignReview />);
  fireEvent.click(screen.getByRole("checkbox", { name: "按联系人聚拢" }));
  fireEvent.click(screen.getByRole("button", { name: "买卖线索，6 封" }));
  const list = within(screen.getByRole("region", { name: "邮件列表" }));
  expect(list.getByRole("button", { name: /200 条现货供应/ })).toBeInTheDocument();
  expect(list.getByRole("button", { name: /更新报价与质保/ })).toBeInTheDocument();
  expect(list.queryByRole("button", { name: /办公服务账单/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "日常邮件，3 封" }));
  expect(list.getByRole("button", { name: /办公服务账单/ })).toBeInTheDocument();
  expect(list.getByRole("button", { name: /本周数据中心与 AI 行业新闻/ })).toBeInTheDocument();
  expect(customerPanel().getByRole("region", { name: "日常邮件信息" })).toBeInTheDocument();
  expect(customerPanel().queryByRole("region", { name: "累计需求摘要" })).not.toBeInTheDocument();
  const mobile = within(screen.getByRole("navigation", { name: "移动端邮件分类" }));
  fireEvent.click(mobile.getByRole("button", { name: "全部邮件9" }));
  fireEvent.change(screen.getByRole("textbox", { name: "搜索示例邮件" }), { target: { value: "not-present" } });
  expect(list.getByText("没有匹配的示例邮件")).toBeInTheDocument();
});

it("supports keyboard navigation resizing, bounds and one-click hide/restore", () => {
  render(<InboxDesignReview />);
  const resize = screen.getByRole("separator", { name: "调整左侧面板宽度" });
  fireEvent.keyDown(resize, { key: "ArrowRight" });
  expect(resize).toHaveAttribute("aria-valuenow", "196");
  for (let index = 0; index < 12; index++) fireEvent.keyDown(resize, { key: "ArrowLeft" });
  expect(resize).toHaveAttribute("aria-valuenow", "160");
  fireEvent.keyDown(resize, { key: "Home" });
  expect(resize).toHaveAttribute("aria-valuenow", "184");
  fireEvent.click(screen.getByRole("button", { name: "隐藏左侧面板" }));
  expect(screen.queryByRole("separator", { name: "调整左侧面板宽度" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "展开左侧面板" }));
  expect(screen.getByRole("separator", { name: "调整左侧面板宽度" })).toHaveAttribute("aria-valuenow", "184");
});
