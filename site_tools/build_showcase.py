#!/usr/bin/env python3
"""Deterministic, private/offline showcase generator, ON by default.

RETRO_SHOWCASE_KILL_SWITCH=1 copies the original site files unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
import os
from pathlib import Path
import shutil
from string import Template
import sys

from validate_site import sha256, safe_path, validate_metadata

TOOL_ROOT = Path(__file__).resolve().parent
KILL_SWITCH = "RETRO_SHOWCASE_KILL_SWITCH"
ROOT_FILES = ("index.html", "privacy-policy.html", ".nojekyll", "README.md", "PRIVACY.md", "SUPPORT.md")


def _copy_press(site: Path, out: Path) -> None:
    src = site / "press"
    if not src.exists():
        return
    if src.is_symlink() or not src.is_dir():
        raise ValueError("press directory must be a normal directory")
    for entry in sorted(src.rglob("*")):
        if entry.is_symlink():
            raise ValueError("press directory cannot contain symlinks")
        destination = out / entry.relative_to(site)
        if entry.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif entry.is_file():
            if entry.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("press file exceeds the offline build limit")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(entry, destination)


def _plain(value: object) -> str:
    return escape(str(value), quote=True)


def _render_page(metadata: dict, entries: list[dict]) -> str:
    rooms = []
    for n, room in enumerate(metadata["rooms"], start=1):
        rooms.append(
            '<li class="room"><span class="num">ROOM ' + f'{n:02d}' + '</span>'
            + '<div><span class="era">' + _plain(room["era"]) + '</span></div>'
            + '<h3>' + _plain(room["name"]) + '</h3>'
            + '<p>' + _plain(room["summary"]) + '</p></li>'
        )
    downloads = []
    for item in entries:
        display_type = "Vector artwork" if item["media_type"] == "image/svg+xml" else "Plain text"
        downloads.append(
            '<article class="download"><span class="type">' + display_type + '</span>'
            + '<h3>' + _plain(item["label"]) + '</h3>'
            + '<p>' + _plain(item["summary"]) + '</p>'
            + '<span class="file">SHA-256 · ' + str(item["size_bytes"]) + ' bytes</span>'
            + '<code class="hash">' + item["sha256"] + '</code>'
            + '<a href="./' + _plain(item["path"]) + '" download>Download asset</a></article>'
        )
    product = metadata["product"]
    values = dict(
        meta_title=_plain(product["name"]),
        meta_description=_plain(product["summary"]),
        tagline=_plain(product["tagline"]),
        summary=_plain(product["summary"]),
        room_count=str(product["room_count"]),
        desktop_count=str(product["desktop_count"]),
        game_count=str(product["game_count"]),
        room_cards="\n".join(rooms),
        download_cards="\n".join(downloads),
    )
    template = (TOOL_ROOT / "templates" / "showcase.html.tmpl").read_text(encoding="utf-8")
    return Template(template).substitute(values)


def build(site: Path, out: Path, *, disabled: bool | None = None) -> dict[str, object]:
    site = site.resolve()
    out = out.resolve()
    if not site.is_dir() or not (site / "index.html").is_file() or not (site / "privacy-policy.html").is_file():
        raise ValueError("site must contain index.html and privacy-policy.html")
    if site == out or site in out.parents or out in site.parents:
        raise ValueError("output and source must be separate directory trees")
    if out.exists() and any(out.iterdir()):
        raise ValueError("output directory must not already contain files")
    out.mkdir(parents=True, exist_ok=True)
    for name in ROOT_FILES:
        src = site / name
        if src.exists():
            if src.is_symlink() or not src.is_file():
                raise ValueError("input entry must be a regular file")
            shutil.copyfile(src, out / name)
    _copy_press(site, out)
    if disabled is None:
        disabled = os.environ.get(KILL_SWITCH, "0").strip().lower() in ("1", "true", "yes", "on")
    if disabled:
        return {"flag_enabled": False, "kill_switch": True, "new_files": 0,
                "index_sha256": sha256(out / "index.html"), "baseline_index_sha256": sha256(site / "index.html")}

    metadata = json.loads((TOOL_ROOT / "metadata.json").read_text(encoding="utf-8"))
    errors = validate_metadata(metadata)
    if errors:
        raise ValueError("invalid metadata: " + "; ".join(errors))
    # Only one original root navigation tag is changed in the generated copy.
    index_file = out / "index.html"
    before = index_file.read_text(encoding="utf-8")
    if before.count("</nav>") != 1 or "<nav" not in before:
        raise ValueError("source index must have exactly one navigation element")
    if 'href="./showcase.html"' in before:
        after = before
    else:
        after = before.replace("</nav>", '<a href="./showcase.html">Showcase</a></nav>', 1)
    index_file.write_text(after, encoding="utf-8", newline="")

    shutil.copyfile(TOOL_ROOT / "showcase.css", out / "showcase.css")
    shutil.copyfile(TOOL_ROOT / "metadata.json", out / "site-metadata.json")
    shutil.copyfile(TOOL_ROOT / "metadata.schema.json", out / "site-metadata.schema.json")
    (out / "showcase_assets").mkdir()
    shutil.copyfile(TOOL_ROOT / "assets" / "mark.svg", out / "showcase_assets" / "mark.svg")
    downloads_dir = out / "downloads"
    downloads_dir.mkdir()
    catalog_entries = []
    rendered_entries = []
    for item in metadata["downloads"]:
        rel = item["path"]
        target = safe_path(out, rel)
        source = TOOL_ROOT / "assets" / Path(rel).name
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"missing original asset {rel}")
        shutil.copyfile(source, target)
        entry = {"path": rel, "sha256": sha256(target), "size_bytes": target.stat().st_size,
                 "media_type": item["media_type"], "label": item["label"]}
        catalog_entries.append(entry)
        rendered_entries.append({**item, **entry})
    catalog = {"schema_version": 1, "license": "CC0-1.0", "files": catalog_entries}
    (downloads_dir / "catalog.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    checksum_lines = [f'{e["sha256"]}  {e["path"]}' for e in sorted(catalog_entries, key=lambda e: e["path"])]
    (downloads_dir / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    (out / "showcase.html").write_text(_render_page(metadata, rendered_entries), encoding="utf-8", newline="")
    return {"flag_enabled": True, "kill_switch": False, "new_files": 3 + len(catalog_entries) + 4,
            "index_sha256": sha256(index_file), "baseline_index_sha256": sha256(site / "index.html"),
            "downloads": len(catalog_entries)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True, help="existing static-site repo root")
    parser.add_argument("--out", type=Path, required=True, help="new, separate output directory")
    args = parser.parse_args()
    try:
        result = build(args.site, args.out)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
