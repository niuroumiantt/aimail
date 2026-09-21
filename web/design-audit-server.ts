/// <reference types="node" />
import { mkdir, open } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import type { Plugin } from "vite";

/** Local prototype only. Identity is explicitly demo, never supplied as a trusted employee. */
export function designAuditServer(): Plugin {
  const directory = join(homedir(), ".local", "state", "mail2leads");
  let queue = Promise.resolve();
  return {
    name: "mail2leads-design-audit",
    configureServer(server) {
      server.middlewares.use("/__design/audit", async (req, res) => {
        res.setHeader("Content-Type", "application/json");
        res.setHeader("Cache-Control", "no-store");
        if (req.method !== "POST") { res.statusCode = 405; res.end(JSON.stringify({ error: "Write-only design event endpoint" })); return; }
        if (!req.headers["content-type"]?.startsWith("application/json")) { res.statusCode = 415; res.end("{}"); return; }
        try {
          if (req.headers.origin && new URL(req.headers.origin).host !== req.headers.host) { res.statusCode = 403; res.end("{}"); return; }
          let raw = "";
          for await (const chunk of req) { raw += chunk.toString(); if (Buffer.byteLength(raw) > 262144) { res.statusCode = 413; res.end(JSON.stringify({ error: "Event too large" })); return; } }
          const body = JSON.parse(raw);
          if (typeof body.action !== "string" || !/^[a-z][a-z._]{1,63}$/.test(body.action)) { res.statusCode = 400; res.end("{}"); return; }
          const id = randomUUID();
          const entry = JSON.stringify({ id, recorded_at: new Date().toISOString(), actor: "local-design-demo", identity_verified: false, action: body.action, detail: body.detail, client_time: body.client_time });
          const write = queue.then(async () => {
            await mkdir(directory, { recursive: true, mode: 0o700 });
            const file = await open(join(directory, "design-audit.jsonl"), "a", 0o600);
            try { await file.writeFile(entry + "\n"); await file.sync(); } finally { await file.close(); }
          });
          queue = write.catch(() => {});
          await write;
          res.end(JSON.stringify({ recorded: true, id }));
        } catch {
          res.statusCode = 503; res.end(JSON.stringify({ error: "Audit write failed" }));
        }
      });
    },
  };
}
