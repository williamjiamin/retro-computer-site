#!/usr/bin/env python3
"""Offline browser viewport, visible-text contrast, and pixel parity audit.

Requires a locally installed browser automation module and browser binary.
The pages are rendered from in-memory HTML/CSS/images because some sandboxed
browsers reject both file URLs and loopback navigation. Any attempted remote
request fails the audit.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
from pathlib import Path
import re
import sys

from validate_site import safe_path

VIEWPORTS = ((320, 800), (375, 812), (768, 1024), (1280, 900))
PAGES = ("index.html", "showcase.html", "privacy-policy.html")
TEXT_AUDIT_JS = r"""() => {
  function rgb(s){const m=s.match(/rgba?\(([^)]+)\)/);if(!m)return null;
    const v=m[1].split(',').map(x=>Number.parseFloat(x.trim()));
    return {r:v[0],g:v[1],b:v[2],a:v.length>3?v[3]:1};}
  function lum(v){const x=[v.r,v.g,v.b].map(n=>{const c=n/255;return c<=.04045?c/12.92:Math.pow((c+.055)/1.055,2.4)});
    return .2126*x[0]+.7152*x[1]+.0722*x[2];}
  function background(el){for(let p=el;p;p=p.parentElement){const c=rgb(getComputedStyle(p).backgroundColor);
    if(c&&c.a===1)return c;}return {r:255,g:255,b:255,a:1};}
  const bad=[],scores=[];
  for(const el of document.body.querySelectorAll('*')){
    if(['SCRIPT','STYLE','SVG','NOSCRIPT'].includes(el.tagName))continue;
    if(!Array.from(el.childNodes).some(n=>n.nodeType===3&&n.nodeValue.trim()))continue;
    const s=getComputedStyle(el);if(s.display==='none'||s.visibility==='hidden'||Number(s.opacity)===0||!el.getClientRects().length)continue;
    const fg=rgb(s.color),bg=background(el);if(!fg||fg.a!==1)continue;
    const a=lum(fg),b=lum(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
    const large=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&Number(s.fontWeight)>=700);
    const threshold=large?3:4.5;
    scores.push(ratio);
    if(ratio+1e-6<threshold)bad.push({tag:el.tagName,text:el.textContent.trim().slice(0,75),ratio:Number(ratio.toFixed(2)),threshold});
  }
  const overflow=[];
  for(const el of document.body.querySelectorAll('*')){
    const s=getComputedStyle(el);if(s.position==='fixed'||s.display==='none')continue;
    const r=el.getBoundingClientRect();
    if(r.width>0&&(r.right>innerWidth+2||r.left < -2))overflow.push({tag:el.tagName,cls:el.className?.toString().slice(0,65),left:Math.round(r.left),right:Math.round(r.right)});
  }
  return {viewport_width:innerWidth,document_width:document.documentElement.scrollWidth,
    min_text_contrast:scores.length?Number(Math.min(...scores).toFixed(2)):null,
    text_nodes_sampled:scores.length,low_contrast:bad.slice(0,20),offscreen_elements:overflow.slice(0,20)};
}"""


STYLE_LINK = re.compile(r'<link\b(?=[^>]*\brel=["\']stylesheet["\'])[^>]*>', re.IGNORECASE)
IMG_TAG = re.compile(r'<img\b[^>]*>', re.IGNORECASE)
HREF = re.compile(r'\bhref=["\']([^"\']+)["\']', re.IGNORECASE)
SRC = re.compile(r'\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)


def _inline_local_resources(site: Path, name: str) -> str:
    """Read bytes strictly from a local site root; never navigate to an URL."""
    page_path = safe_path(site, name)
    source = page_path.read_text(encoding="utf-8")

    def style_sub(match):
        m = HREF.search(match.group(0))
        if not m:
            return match.group(0)
        css_path = safe_path(site, str((page_path.parent / m.group(1).split('?', 1)[0]).relative_to(site)))
        css = css_path.read_text(encoding="utf-8")
        if '</style' in css.lower():
            raise ValueError("CSS cannot contain a closing style element")
        return '<style>' + css + '</style>'

    def img_sub(match):
        m = SRC.search(match.group(0))
        if not m:
            return match.group(0)
        url = m.group(1)
        if url.startswith(('http:', 'https:', '//', 'data:')):
            return match.group(0)  # Remote resources are independently rejected.
        image_path = safe_path(site, str((page_path.parent / url.split('?', 1)[0]).relative_to(site)))
        if not image_path.is_file() or image_path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError(f"image missing or too large for offline audit: {url}")
        mime = mimetypes.guess_type(image_path.name)[0] or 'application/octet-stream'
        encoded = base64.b64encode(image_path.read_bytes()).decode('ascii')
        src = f'data:{mime};base64,{encoded}'
        return match.group(0)[:m.start(1)] + src + match.group(0)[m.end(1):]

    source = STYLE_LINK.sub(style_sub, source)
    source = IMG_TAG.sub(img_sub, source)
    return source


def _load_virtual(page, root: Path, name: str) -> None:
    page.set_content(_inline_local_resources(root, name), wait_until="load")
    page.evaluate('document.fonts.ready')


def run(site: Path, *, baseline: Path | None = None, off: Path | None = None,
        shots: Path | None = None, browser_path: str | None = None) -> dict:
    try:
        from playwright.sync_api import sync_playwright  # optional for browser audit only
    except ImportError as exc:
        return {"passed": False, "error": f"local automation module unavailable: {exc}"}
    site = site.resolve()
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    report: dict = {"passed": True, "site": str(site), "checks": [], "violations": [],
                    "pixel_parity": [], "minimum_contrast": None}
    with sync_playwright() as p:
        options = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if browser_path:
            options["executable_path"] = browser_path
        browser = p.chromium.launch(**options)
        context = browser.new_context(service_workers="block")
        page = context.new_page()
        remote: list[str] = []
        page.on("request", lambda request: remote.append(request.url) if request.url.startswith(("http://", "https://")) else None)
        page.route("http://**/*", lambda route: route.abort())
        page.route("https://**/*", lambda route: route.abort())
        for name in PAGES:
            if not (site / name).is_file():
                if name == "showcase.html":
                    continue
                report["violations"].append(f"missing audit page: {name}")
                continue
            for width, height in VIEWPORTS:
                for scheme in ("light", "dark"):
                    page.set_viewport_size({"width": width, "height": height})
                    page.emulate_media(color_scheme=scheme, reduced_motion="reduce")
                    _load_virtual(page, site, name)
                    result = page.evaluate(TEXT_AUDIT_JS)
                    record = {"page": name, "viewport": f"{width}x{height}", "scheme": scheme,
                              "document_width": result["document_width"],
                              "minimum_contrast": result["min_text_contrast"],
                              "text_samples": result["text_nodes_sampled"]}
                    report["checks"].append(record)
                    if result["document_width"] > result["viewport_width"] + 1:
                        report["violations"].append(f"{name} {width} {scheme}: horizontal scrolling")
                    if result["offscreen_elements"]:
                        report["violations"].append(f"{name} {width} {scheme}: offscreen {result['offscreen_elements']}")
                    if result["low_contrast"]:
                        report["violations"].append(f"{name} {width} {scheme}: contrast {result['low_contrast']}")
                    if result["min_text_contrast"] is not None:
                        current = report["minimum_contrast"]
                        report["minimum_contrast"] = min(current, result["min_text_contrast"]) if current is not None else result["min_text_contrast"]
                    if shots and name == "showcase.html" and (width, scheme) in ((375, "light"), (375, "dark"), (1280, "light")):
                        page.screenshot(path=str(shots / f"showcase_{width}_{scheme}.png"), full_page=True)
        if baseline is not None and off is not None:
            for name in ("index.html", "privacy-policy.html"):
                for width, height in ((375, 812), (1280, 900)):
                    for scheme in ("light", "dark"):
                        a, b = baseline.resolve() / name, off.resolve() / name
                        if not a.is_file() or not b.is_file():
                            report["violations"].append(f"parity input missing: {name}")
                            continue
                        page.set_viewport_size({"width": width, "height": height})
                        page.emulate_media(color_scheme=scheme, reduced_motion="reduce")
                        _load_virtual(page, baseline.resolve(), name)
                        before = page.screenshot(full_page=True)
                        _load_virtual(page, off.resolve(), name)
                        after = page.screenshot(full_page=True)
                        equal = before == after
                        report["pixel_parity"].append({"page": name, "viewport": width, "scheme": scheme, "equal": equal})
                        if not equal:
                            report["violations"].append(f"pixel parity failed: {name} {width} {scheme}")
        if remote:
            report["violations"].append(f"unexpected network requests: {remote}")
        browser.close()
    report["passed"] = not report["violations"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--off", type=Path)
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--browser-path", default=None)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.site, baseline=args.baseline, off=args.off,
                     shots=args.screenshots, browser_path=args.browser_path)
    except Exception as exc:
        result = {"passed": False, "error": f"browser audit failure: {exc}"}
    print(json.dumps({"passed": result["passed"], "checks": len(result.get("checks", [])),
                      "pixel_parity": len(result.get("pixel_parity", [])),
                      "minimum_contrast": result.get("minimum_contrast"),
                      "violations": result.get("violations", []), "error": result.get("error")}, indent=2))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
