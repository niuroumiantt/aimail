import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";

const here = join(__dirname);
const pkg = join(here, "package");
const read = (name: string) => readFileSync(join(pkg, name));

describe("shared self-hosted fonts", () => {
  test("font package matches its manifest byte for byte", () => {
    const manifest = JSON.parse(read("manifest.json").toString()) as { files: Record<string, { sha256: string }> };
    const names = Object.keys(manifest.files);
    expect(names.length).toBeGreaterThanOrEqual(6);
    for (const name of names) {
      expect(createHash("sha256").update(read(name)).digest("hex"), name).toBe(manifest.files[name].sha256);
    }
    expect(readdirSync(pkg).filter((f) => !names.includes(f) && f !== "manifest.json")).toEqual([]);
  });

  test("theme and font package declare the same stack and nothing loads from Google Fonts", () => {
    const fonts = read("fonts.css").toString();
    const stack = /--font-sans:([^;]+);--font-mono:([^;]+);/.exec(fonts);
    expect(stack).not.toBeNull();
    const theme = readFileSync(join(here, "..", "tokens", "theme.css")).toString().replace(/\s+/g, " ");
    expect(theme).toContain("--font-sans: " + stack![1].trim() + ";");
    expect(theme).toContain("--font-mono: " + stack![2].trim() + ";");
    expect(stack![1]).toMatch(/^"Inter", "Noto Sans SC"/);
    const html = readFileSync(join(here, "..", "..", "index.html")).toString();
    expect(html).not.toMatch(/fonts\.googleapis\.com|fonts\.gstatic\.com/);
    expect(readFileSync(join(here, "..", "main.tsx")).toString()).toContain('import "./fonts/index.css"');
  });
});
