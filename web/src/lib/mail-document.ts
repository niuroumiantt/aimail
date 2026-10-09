import createDOMPurify from "dompurify";
import documentStyles from "@/tokens/mail-document.css?inline";
import fontStyles from "@/fonts/package/fonts.css?inline";

const rasterImage = /^data:image\/(?:png|jpeg|gif|webp|avif);base64,[a-z\d+/=\s]+$/i;

/** Typography is deterministic: text nodes, links and table/list structure are never rewritten. */
function readingStyle(node: Element) {
  const element = node as HTMLElement;
  const style = element.style;
  if (!style) return;
  const weight = style.fontWeight;
  const italic = style.fontStyle;
  const decoration = style.textDecorationLine || style.textDecoration;
  const alignment = style.textAlign || element.getAttribute("align");
  const hidden = style.display === "none" || style.visibility === "hidden" || style.getPropertyValue("mso-hide") === "all";
  const imageWidth = element.tagName === "IMG" ? style.width || element.getAttribute("width") || "" : "";
  element.removeAttribute("style");
  for (const attribute of ["align", "width", "height"]) element.removeAttribute(attribute);
  if (/^(bold|bolder|[6-9]00)$/.test(weight)) style.fontWeight = "600";
  if (/^(italic|oblique)/.test(italic)) style.fontStyle = "italic";
  const lines = ["underline", "line-through"].filter(value => decoration.split(/\s+/).includes(value));
  if (lines.length) style.textDecorationLine = lines.join(" ");
  if (/^(TD|TH)$/.test(element.tagName) && /^(left|right|center|start|end)$/.test(alignment ?? "")) style.textAlign = alignment!;
  if (hidden) element.hidden = true;
  // Keep modest signature/logo dimensions; fixed document and table widths are discarded.
  if (/^\d+(?:px)?$/.test(imageWidth)) element.setAttribute("width", String(Math.min(640, Math.max(1, parseInt(imageWidth)))));
}

function readingStructure(fragment: DocumentFragment) {
  for (const node of fragment.querySelectorAll("p,div")) {
    if (!node.textContent?.replace(/\u00a0/g, " ").trim()
      && Array.from(node.querySelectorAll("*")).every(child => /^(BR|SPAN|FONT)$/.test(child.tagName))) {
      node.setAttribute("data-mail-spacer", "true");
    }
  }
  for (const table of fragment.querySelectorAll("table")) {
    if (table.getAttribute("role") === "presentation" || table.querySelector("table")) continue;
    const rows = Array.from(table.rows);
    if (table.querySelector("th") || (rows.length > 1 && rows.some(row => row.cells.length > 1))) table.setAttribute("data-mail-table", "grid");
  }
}

/** Sender HTML is never attached to the application document. CSP also blocks CSS requests. */
export function mailDocument(html: string, inlineImages: Record<string, string> = {}, loadExternalImages = false) {
  const purifier = createDOMPurify(window);
  let blockedImages = false;
  let externalImages = false;
  purifier.addHook("afterSanitizeAttributes", node => {
    readingStyle(node);
    if (node.tagName === "IMG") {
      const source = node.getAttribute("src") ?? "";
      let image = source;
      if (image.startsWith("//")) image = `https:${image}`;
      if (/^cid:/i.test(source)) {
        try { image = inlineImages[decodeURIComponent(source.slice(4))] ?? ""; }
        catch { image = ""; }
      }
      if (rasterImage.test(image) || (loadExternalImages && /^https?:\/\//i.test(image))) node.setAttribute("src", image);
      else {
        node.removeAttribute("src");
        blockedImages = true;
        if (/^https?:\/\//i.test(image)) externalImages = true;
        if (!node.getAttribute("alt")) node.setAttribute("alt", "图片未加载");
      }
    }
    if (node.tagName === "A") {
      const href = node.getAttribute("href") ?? "";
      if (/^(?:https?:|mailto:|tel:)/i.test(href)) {
        node.setAttribute("target", "_blank");
        node.setAttribute("rel", "noopener noreferrer");
      } else if (!href.startsWith("#")) node.removeAttribute("href");
    }
  });
  const fragment = purifier.sanitize(html, {
    USE_PROFILES: { html: true }, FORCE_BODY: true, RETURN_DOM_FRAGMENT: true, ALLOW_DATA_ATTR: false,
    FORBID_TAGS: ["style", "base", "link", "meta", "form", "input", "button", "textarea", "select", "option", "iframe", "object", "embed", "audio", "video", "source", "track", "marquee"],
    FORBID_ATTR: ["class", "bgcolor", "background", "color", "face", "size", "border", "cellpadding", "cellspacing", "srcdoc", "srcset", "formaction", "action", "ping", "download", "autofocus", "nonce"],
  });
  readingStructure(fragment);
  const container = document.createElement("div");
  container.append(fragment);
  const clean = container.innerHTML;
  const csp = `default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src data:${loadExternalImages ? " https: http:" : ""}; font-src 'self' data:; connect-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'`;
  return {
    blockedImages,
    externalImages,
    srcDoc: `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${csp}"><meta name="referrer" content="no-referrer"><style>${fontStyles}\n${documentStyles}</style></head><body>${clean}</body></html>`,
  };
}
