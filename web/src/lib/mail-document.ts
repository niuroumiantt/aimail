import createDOMPurify from "dompurify";
import documentStyles from "@/tokens/mail-document.css?inline";
import fontStyles from "@/fonts/package/fonts.css?inline";

const rasterImage = /^data:image\/(?:png|jpeg|gif|webp|avif);base64,[a-z\d+/=\s]+$/i;

/** Sender HTML is never attached to the application document. CSP also blocks CSS requests. */
export function mailDocument(html: string, inlineImages: Record<string, string> = {}, loadExternalImages = false) {
  const purifier = createDOMPurify(window);
  let blockedImages = false;
  let externalImages = false;
  purifier.addHook("afterSanitizeAttributes", node => {
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
  const clean = purifier.sanitize(html, {
    USE_PROFILES: { html: true }, FORCE_BODY: true, ADD_TAGS: ["style"],
    FORBID_TAGS: ["base", "link", "meta", "form", "input", "button", "textarea", "select", "option", "iframe", "object", "embed", "audio", "video", "source", "track"],
    FORBID_ATTR: ["srcdoc", "srcset", "formaction", "action", "ping", "download", "autofocus", "nonce"],
  });
  const csp = `default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src data:${loadExternalImages ? " https: http:" : ""}; font-src 'self' data:; connect-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'`;
  return {
    blockedImages,
    externalImages,
    srcDoc: `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${csp}"><meta name="referrer" content="no-referrer"><style>${fontStyles}\n${documentStyles}</style></head><body>${clean}</body></html>`,
  };
}
