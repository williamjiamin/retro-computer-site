#!/usr/bin/env python3
"""Dependency-free offline HTML/CSS link, metadata and SHA-256 verifier.

No network requests or writes are made by validation. Exits nonzero on errors.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
DL_RE = re.compile(r"^downloads/[a-z0-9][a-z0-9._-]{0,100}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
CSS_IMPORT_RE = re.compile(r"@import\s+(['\"])(.*?)\1", re.IGNORECASE)
MAX_DOCUMENT_BYTES = 12 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(131072), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"invalid relative path: {relative!r}")
    parsed = urlsplit(relative)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or relative.startswith("/"):
        raise ValueError(f"not a plain site-local path: {relative!r}")
    candidate = (root / unquote(parsed.path)).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes site root: {relative!r}")
    if candidate.is_symlink():
        raise ValueError(f"site symlink forbidden: {relative!r}")
    return candidate


def validate_metadata(data: object) -> list[str]:
    """Portable counterpart of metadata.schema.json plus cross-field rules."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["metadata root must be an object"]
    if set(data) != {"schema_version", "product", "rooms", "downloads"}:
        errors.append("metadata fields differ from v1 contract")
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        errors.append("unsupported schema_version")
    prod = data.get("product")
    if not isinstance(prod, dict):
        return errors + ["product must be an object"]
    if set(prod) != {"name", "tagline", "summary", "room_count", "desktop_count", "game_count"}:
        errors.append("product fields differ from v1 contract")
    for key, maximum in (("name", 90), ("tagline", 160), ("summary", 400)):
        val = prod.get(key)
        if not isinstance(val, str) or not 1 <= len(val.strip()) <= maximum:
            errors.append(f"product.{key} invalid")
    for key, minimum, maximum in (("room_count", 1, 50), ("desktop_count", 1, 200), ("game_count", 0, 10000)):
        val = prod.get(key)
        if type(val) is not int or not minimum <= val <= maximum:
            errors.append(f"product.{key} invalid")
    rooms = data.get("rooms")
    if not isinstance(rooms, list) or not 1 <= len(rooms) <= 50:
        errors.append("rooms array missing or out of range")
        rooms = []
    if rooms and len(rooms) != prod.get("room_count"):
        errors.append("room_count does not match rooms length")
    for list_key, items, fields, lengths in (
        ("rooms", rooms, {"id", "era", "name", "summary"}, {"era": 24, "name": 80, "summary": 240}),
        ("downloads", data.get("downloads"), {"id", "path", "label", "summary", "media_type"}, {"label": 100, "summary": 240}),
    ):
        if not isinstance(items, list) or not 1 <= len(items) <= 50:
            errors.append(f"{list_key} must have 1..50 entries")
            continue
        ids: set[str] = set()
        paths: set[str] = set()
        for index, item in enumerate(items):
            prefix = f"{list_key}[{index}]"
            if not isinstance(item, dict) or set(item) != fields:
                errors.append(f"{prefix} fields invalid")
                continue
            item_id = item["id"]
            if not isinstance(item_id, str) or not ID_RE.fullmatch(item_id) or item_id in ids:
                errors.append(f"{prefix}.id malformed or duplicate")
            else:
                ids.add(item_id)
            for key, mx in lengths.items():
                value = item[key]
                if not isinstance(value, str) or not 1 <= len(value.strip()) <= mx:
                    errors.append(f"{prefix}.{key} invalid")
            if list_key == "downloads":
                path = item["path"]
                if not isinstance(path, str) or not DL_RE.fullmatch(path) or path in paths:
                    errors.append(f"{prefix}.path malformed or duplicate")
                else:
                    paths.add(path)
                mime = item["media_type"]
                if mime not in ("image/svg+xml", "text/plain"):
                    errors.append(f"{prefix}.media_type invalid")
                elif isinstance(path, str) and not path.endswith(".svg" if mime == "image/svg+xml" else ".txt"):
                    errors.append(f"{prefix}.media_type and path mismatch")
    return errors


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[tuple[str, str]] = []
        self.inline_styles: list[str] = []
        self.duplicates: list[str] = []
        self._style_depth = 0
        self.heading_one_count = 0
        self.language: str | None = None
        self.viewport = False
        self.description = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "html":
            self.language = a.get("lang")
        if tag == "h1":
            self.heading_one_count += 1
        if tag == "style":
            self._style_depth += 1
        if tag == "meta":
            if a.get("name", "").lower() == "viewport" and a.get("content"):
                self.viewport = True
            if a.get("name", "").lower() == "description" and a.get("content"):
                self.description = True
        ident = a.get("id")
        if ident:
            if ident in self.ids:
                self.duplicates.append(ident)
            self.ids.add(ident)
        if a.get("style"):
            self.inline_styles.append(a["style"] or "")
        for key in ("href", "src", "poster", "data", "action", "formaction"):
            if a.get(key):
                # The link tag can also provide an external stylesheet.
                role = "resource" if key in ("src", "poster", "data") or tag in ("link", "script", "source", "iframe") else "nav"
                self.links.append((a[key] or "", role))
        if a.get("srcset"):
            for part in (a["srcset"] or "").split(","):
                if part.strip():
                    self.links.append((part.strip().split()[0], "resource"))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self._style_depth:
            self._style_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._style_depth:
            self.inline_styles.append(data)


def parse_page(path: Path) -> Page:
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"oversized HTML: {path}")
    page = Page()
    page.feed(path.read_text(encoding="utf-8"))
    page.close()
    return page


def css_urls(css_text: str) -> list[str]:
    urls = [match.group(2).strip() for match in CSS_URL_RE.finditer(css_text)]
    urls.extend(match.group(2).strip() for match in CSS_IMPORT_RE.finditer(css_text))
    return urls


def verify_links(root: Path) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    htmls = sorted(root.rglob("*.html"))
    stylesheets = sorted(root.rglob("*.css"))
    counts = {"html_pages": len(htmls), "stylesheets": len(stylesheets), "svg_images": 0, "local_references": 0, "external_navigation": 0}
    parsed: dict[Path, Page] = {}
    for file in htmls:
        try:
            parsed[file.resolve()] = parse_page(file)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{file.relative_to(root)}: {exc}")
    for file, page in parsed.items():
        rel = str(file.relative_to(root))
        if page.duplicates:
            errors.append(f"{rel}: duplicate IDs {page.duplicates}")
        if not page.language:
            errors.append(f"{rel}: missing html language")
        if not page.viewport:
            errors.append(f"{rel}: missing viewport metadata")
        if not page.description:
            errors.append(f"{rel}: missing description metadata")
        if page.heading_one_count != 1:
            errors.append(f"{rel}: expected exactly one h1")
        links = page.links[:]
        for css in page.inline_styles:
            links.extend((u, "resource") for u in css_urls(css))
        for url, role in links:
            _check_url(root, file, url, role, parsed, errors, counts)
    for css_file in stylesheets:
        try:
            urls = css_urls(css_file.read_text(encoding="utf-8"))
            for url in urls:
                _check_url(root, css_file, url, "resource", parsed, errors, counts)
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{css_file.relative_to(root)}: {exc}")
    # Vector art is also an asset: reject remote images, fonts, scripts,
    # linked styles and unsafe relative file paths inside SVG documents.
    for svg_file in sorted(root.rglob("*.svg")):
        counts["svg_images"] += 1
        try:
            if svg_file.stat().st_size > MAX_DOCUMENT_BYTES:
                raise ValueError("SVG exceeds offline file-size limit")
            raw = svg_file.read_text(encoding="utf-8")
            if "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
                raise ValueError("SVG document type and entities forbidden")
            svg_tree = ET.fromstring(raw)
            for elem in svg_tree.iter():
                if elem.tag.split("}")[-1].lower() in ("script", "foreignobject"):
                    errors.append(f"{svg_file.relative_to(root)}: script/foreignObject in vector art")
                for key, value in elem.attrib.items():
                    short = key.split("}")[-1].lower()
                    if short in ("href", "src"):
                        _check_url(root, svg_file, value, "resource", parsed, errors, counts)
                    if short == "style" or "url(" in value.lower():
                        for url in css_urls(value):
                            _check_url(root, svg_file, url, "resource", parsed, errors, counts)
                if elem.tag.split("}")[-1].lower() == "style" and elem.text:
                    for url in css_urls(elem.text):
                        _check_url(root, svg_file, url, "resource", parsed, errors, counts)
        except (ET.ParseError, OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{svg_file.relative_to(root)}: invalid SVG: {exc}")
    return errors, counts


def _check_url(root: Path, from_file: Path, url: str, role: str,
               parsed: dict[Path, Page], errors: list[str], counts: dict[str, int]) -> None:
    where = str(from_file.relative_to(root))
    raw = url.strip()
    if not raw:
        return
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme in ("https", "http", "mailto", "tel") or raw.startswith("//"):
        if role == "resource" or raw.startswith("//"):
            errors.append(f"{where}: remote dependency is not offline: {raw}")
        else:
            counts["external_navigation"] += 1
        return
    if scheme or parts.netloc:
        errors.append(f"{where}: disallowed URI scheme in {raw}")
        return
    if raw.startswith("/"):
        errors.append(f"{where}: root-absolute URL breaks subpath hosting: {raw}")
        return
    raw_path = unquote(parts.path)
    if "\\" in raw_path or "\x00" in raw_path:
        errors.append(f"{where}: invalid URL path: {raw}")
        return
    target = (from_file.parent / raw_path).resolve() if raw_path else from_file
    if not target.is_relative_to(root.resolve()):
        errors.append(f"{where}: traversal outside site root: {raw}")
        return
    if target.is_dir():
        target /= "index.html"
    if not target.is_file() or target.is_symlink():
        errors.append(f"{where}: missing local asset: {raw}")
        return
    counts["local_references"] += 1
    if parts.fragment and target.suffix.lower() in (".html", ".htm"):
        page = parsed.get(target.resolve())
        if page is None or unquote(parts.fragment) not in page.ids:
            errors.append(f"{where}: missing local anchor: {raw}")


def verify_downloads(root: Path) -> tuple[list[str], int]:
    errors: list[str] = []
    metadata_file = root / "site-metadata.json"
    catalog_file = root / "downloads" / "catalog.json"
    sums_file = root / "downloads" / "SHA256SUMS.txt"
    if not metadata_file.exists() and not catalog_file.exists() and not sums_file.exists():
        return [], 0  # Kill-switch OFF may preserve a site without any showcase files.
    if not all(p.is_file() for p in (metadata_file, catalog_file, sums_file, root / "site-metadata.schema.json")):
        return ["showcase metadata, schema, catalog and checksum list must all be present"], 0
    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
        schema = json.loads((root / "site-metadata.schema.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"malformed metadata/catalog/schema: {exc}"], 0
    errors.extend(validate_metadata(metadata))
    if not isinstance(schema, dict) or schema.get("properties", {}).get("schema_version", {}).get("const") != 1:
        errors.append("metadata schema file is not schema v1")
    expected = {item["path"]: item for item in metadata.get("downloads", []) if isinstance(item, dict) and isinstance(item.get("path"), str)}
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1 or not isinstance(catalog.get("files"), list):
        return errors + ["catalog structure invalid"], 0
    if set(catalog) != {"schema_version", "files", "license"} or catalog.get("license") != "CC0-1.0":
        errors.append("catalog license/field contract invalid")
    observed: set[str] = set()
    expected_sums: set[str] = set()
    for item in catalog["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size_bytes", "media_type", "label"}:
            errors.append("catalog entry shape invalid")
            continue
        rel = item.get("path")
        if not isinstance(rel, str) or not DL_RE.fullmatch(rel) or rel in observed:
            errors.append(f"catalog path invalid/duplicate: {rel!r}")
            continue
        observed.add(rel)
        match = expected.get(rel)
        if match is None or item.get("label") != match["label"] or item.get("media_type") != match["media_type"]:
            errors.append(f"catalog and metadata disagree: {rel}")
        try:
            file = safe_path(root, rel)
            if not file.is_file():
                errors.append(f"missing downloaded file: {rel}")
                continue
            digest = sha256(file)
            if not isinstance(item.get("sha256"), str) or not HEX_RE.fullmatch(item["sha256"]):
                errors.append(f"invalid SHA-256 syntax: {rel}")
            if item.get("sha256") != digest:
                errors.append(f"checksum mismatch: {rel}")
            if type(item.get("size_bytes")) is not int or item.get("size_bytes") != file.stat().st_size:
                errors.append(f"size mismatch: {rel}")
            expected_sums.add(f"{digest}  {rel}")
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    if observed != set(expected):
        errors.append("catalog downloads differ from metadata downloads")
    try:
        lines = set(sums_file.read_text(encoding="utf-8").splitlines())
        if lines != expected_sums:
            errors.append("download SHA256SUMS.txt differs from computed digests")
    except (OSError, UnicodeError) as exc:
        errors.append(f"invalid checksum list: {exc}")
    page = root / "showcase.html"
    if not page.is_file():
        errors.append("showcase missing while download metadata is present")
    else:
        source = page.read_text(encoding="utf-8")
        for item in catalog["files"]:
            if isinstance(item, dict) and isinstance(item.get("sha256"), str) and item["sha256"] not in source:
                errors.append(f"checksum not displayed in HTML: {item.get('path')}")
    return errors, len(observed)


def audit(root: Path) -> dict[str, object]:
    root = root.resolve()
    errors: list[str] = []
    if not root.is_dir() or not (root / "index.html").is_file():
        return {"ok": False, "errors": ["site root or index.html does not exist"], "counts": {}}
    link_errors, counts = verify_links(root)
    checksum_errors, counts_download = verify_downloads(root)
    errors.extend(link_errors)
    errors.extend(checksum_errors)
    counts["verified_downloads"] = counts_download
    return {"ok": not errors, "errors": errors, "counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    parser.add_argument("--json", type=Path, help="write an audit record locally")
    args = parser.parse_args()
    report = audit(args.site)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
