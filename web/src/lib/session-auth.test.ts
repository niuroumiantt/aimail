import { afterEach, expect, it, vi } from "vitest";
import { SESSION_EXPIRED_EVENT, SessionExpiredError, sessionFetch, signInUrl } from "./session-auth";

afterEach(() => vi.unstubAllGlobals());

it.each(["redirect", "unauthorized"])("surfaces a %s as session expiry without following login or retrying", async mode => {
  const challenge = mode === "redirect" ? { type: "opaqueredirect", status: 0 } : new Response(null, { status: 401 });
  const fetcher = vi.fn().mockResolvedValue(challenge);
  vi.stubGlobal("fetch", fetcher);
  const listener = vi.fn();
  window.addEventListener(SESSION_EXPIRED_EVENT, listener);
  try {
    const signal = new AbortController().signal;
    await expect(sessionFetch("/api/session", { signal, headers: { "X-Mailbox-Address": "sales@example.test" } })).rejects.toBeInstanceOf(SessionExpiredError);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith("/api/session", expect.objectContaining({ redirect: "manual", credentials: "same-origin", signal, headers: { "X-Mailbox-Address": "sales@example.test" } }));
    expect(listener).toHaveBeenCalledTimes(1);
  } finally { window.removeEventListener(SESSION_EXPIRED_EVENT, listener); }
});

it("preserves permission errors and normal responses without announcing expiry", async () => {
  const forbidden = new Response(null, { status: 403 });
  const success = Response.json({ ok: true });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(forbidden).mockResolvedValueOnce(success));
  const listener = vi.fn();
  window.addEventListener(SESSION_EXPIRED_EVENT, listener);
  try {
    expect(await sessionFetch("/api/mailbox")).toBe(forbidden);
    expect(await sessionFetch("/api/session")).toBe(success);
    expect(listener).not.toHaveBeenCalled();
  } finally { window.removeEventListener(SESSION_EXPIRED_EVENT, listener); }
});

it("does not replay a write when authentication expires", async () => {
  const fetcher = vi.fn().mockResolvedValue({ type: "opaqueredirect", status: 0 });
  vi.stubGlobal("fetch", fetcher);
  await expect(sessionFetch("/api/send", { method: "POST", body: "human-approved-content" })).rejects.toBeInstanceOf(SessionExpiredError);
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher).toHaveBeenCalledWith("/api/send", expect.objectContaining({ method: "POST", body: "human-approved-content", redirect: "manual" }));
});

it("builds a same-origin login route retaining the exact current page", () => {
  const url = new URL(signInUrl(), window.location.origin);
  expect(url.origin).toBe(window.location.origin);
  expect(url.pathname).toBe("/oauth2/start");
  expect(url.searchParams.get("rd")).toBe(window.location.href);
});
