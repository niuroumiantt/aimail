/** API redirects are login challenges, not data responses. Never follow them in fetch. */
export const SESSION_EXPIRED_EVENT = "aimail:session-expired";
export const SESSION_EXPIRED_MESSAGE = "登录已过期，请重新登录";

export class SessionExpiredError extends Error {
  constructor() { super(SESSION_EXPIRED_MESSAGE); this.name = "SessionExpiredError"; }
}

export async function sessionFetch(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(path, { ...init, credentials: "same-origin", redirect: "manual" });
  if (response.type === "opaqueredirect" || response.status === 401) {
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    throw new SessionExpiredError();
  }
  return response;
}

export function signInUrl(): string {
  // Return only to this origin, retaining the current conversation and view.
  return `/oauth2/start?rd=${encodeURIComponent(window.location.href)}`;
}
