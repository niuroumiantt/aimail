import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AccountMenu } from "./account-menu";

afterEach(() => vi.unstubAllGlobals());

it("uses the email name when SSO supplies an opaque UUID instead of a person's name", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ identity: "larry@example.test", username: "67d2d532-33da-4f2d-b30f-07039e900000" }) })));
  render(<AccountMenu />);
  expect(await screen.findByText("larry")).toBeInTheDocument();
  expect(screen.queryByText(/67d2d532/)).not.toBeInTheDocument();
});

it("keeps the person's configured display name", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ identity: "larry@example.test", username: "Larry Xie" }) })));
  render(<AccountMenu />);
  expect(await screen.findByText("Larry Xie")).toBeInTheDocument();
});

it("replaces the indefinite loading label when the login proxy redirects the session request", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ type: "opaqueredirect", status: 0 })));
  render(<AccountMenu />);
  expect(await screen.findByText("登录已过期")).toBeInTheDocument();
  expect(screen.queryByText("正在读取账号…")).not.toBeInTheDocument();
});
