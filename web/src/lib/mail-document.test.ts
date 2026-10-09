import { expect, it } from "vitest";
import { mailDocument } from "./mail-document";

function body(html: string, images?: Record<string, string>) {
  return new DOMParser().parseFromString(mailDocument(html, images).srcDoc, "text/html");
}

it("preserves sender paragraphs, lists, tables, styles and exact text", () => {
  const html = '<p style="font-weight:bold">Part K4-123: USD 25</p><ul><li>10 units</li></ul><table><tr><td>32GB</td></tr></table>';
  const doc = body(html);
  expect(doc.querySelector("p")?.textContent).toBe("Part K4-123: USD 25");
  expect(doc.querySelector("p")?.style.fontWeight).toBe("bold");
  expect(doc.querySelector("li")?.textContent).toBe("10 units");
  expect(doc.querySelector("td")?.textContent).toBe("32GB");
});

it("removes active content and gives sender CSS no network access", () => {
  const doc = body('<meta http-equiv="refresh" content="0;url=https://evil.example"><base href="https://evil.example"><script>parent.pwned=1</script><iframe srcdoc="evil"></iframe><form action="https://evil.example"><input autofocus></form><p onclick="parent.pwned=1">Safe</p><style>p{background:url(https://evil.example/track)}</style>');
  expect(doc.body.querySelector("script,iframe,form,input,meta,base")).toBeNull();
  expect(doc.querySelector("p")?.getAttribute("onclick")).toBeNull();
  const csp = doc.head.querySelector('[http-equiv="Content-Security-Policy"]')?.getAttribute("content");
  expect(csp).toContain("default-src 'none'");
  expect(csp).toContain("script-src 'none'");
  expect(csp).toContain("img-src data:");
  expect(csp).toContain("form-action 'none'");
});

it("resolves CID raster images and blocks external, missing and SVG images", () => {
  const data = "data:image/png;base64,aGVsbG8=";
  const html = '<img src="cid:logo%40x"><img src="https://evil.example/track" srcset="https://evil.example/2x 2x"><img src="cid:missing"><img src="data:image/svg+xml;base64,PHN2Zy8+">';
  const result = mailDocument(html, { "logo@x": data });
  const images = body(html, { "logo@x": data }).querySelectorAll("img");
  expect(images[0].getAttribute("src")).toBe(data);
  for (const img of Array.from(images).slice(1)) {
    expect(img.hasAttribute("src")).toBe(false);
    expect(img.hasAttribute("srcset")).toBe(false);
  }
  expect(result.blockedImages).toBe(true);
});

it("preserves safe links while stripping executable URLs", () => {
  const doc = body('<a href="https://example.test/spec">spec</a><a href="mailto:sales@example.test">mail</a><a href="javascript:alert(1)">bad</a>');
  const links = doc.querySelectorAll("a");
  expect(links[0].getAttribute("href")).toBe("https://example.test/spec");
  expect(links[0].getAttribute("rel")).toBe("noopener noreferrer");
  expect(links[1].getAttribute("href")).toBe("mailto:sales@example.test");
  expect(links[2].hasAttribute("href")).toBe(false);
});

it("only permits external images after the explicit per-message opt-in", () => {
  const html = '<img src="https://example.test/logo"><img src="//example.test/banner">';
  expect(mailDocument(html).externalImages).toBe(true);
  const result = mailDocument(html, {}, true);
  const doc = new DOMParser().parseFromString(result.srcDoc, 'text/html');
  expect(result.blockedImages).toBe(false);
  expect(doc.querySelectorAll('img')[1].getAttribute('src')).toBe('https://example.test/banner');
  expect(doc.head.querySelector('[http-equiv="Content-Security-Policy"]')?.getAttribute('content')).toContain('img-src data: https: http:');
});
