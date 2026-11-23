"""Offline unit tests; no network, installation or publishing actions."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_showcase import build
from validate_site import audit, sha256, validate_metadata


class ShowcaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.site = self.base / "input_site"
        self.site.mkdir()
        self.html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                     '<meta name="viewport" content="width=device-width,initial-scale=1">'
                     '<meta name="description" content="An offline sample page.">'
                     '<title>Sample</title></head><body><nav><a href="./">Home</a></nav>'
                     '<main><h1>Sample</h1><a href="./#support">Support</a>'
                     '<a href="./privacy-policy.html">Privacy</a>'
                     '<section id="support"><h2>Support</h2></section>'
                     '<section id="apps"><h2>Other tools</h2></section></main></body></html>')
        (self.site / "index.html").write_text(self.html, encoding="utf-8")
        (self.site / "privacy-policy.html").write_text(
            '<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="description" content="Test privacy page"><title>Privacy</title></head>'
            '<body><nav><a href="./">Home</a></nav><main><h1>Privacy</h1></main></body></html>', encoding="utf-8")
        (self.site / ".nojekyll").write_bytes(b"")
        (self.site / "press").mkdir()
        (self.site / "press" / "caption.txt").write_bytes(b"Original caption\n")

    def output(self, name="enabled", disabled=None):
        dest = self.base / name
        return dest, build(self.site, dest, disabled=disabled)

    def test_enabled_by_default_and_validator(self):
        with patch.dict(os.environ, {"RETRO_SHOWCASE_KILL_SWITCH": "0"}):
            path, result = self.output()
        self.assertTrue(result["flag_enabled"])
        self.assertIn('href="./showcase.html"', (path / "index.html").read_text(encoding="utf-8"))
        self.assertIn('name="robots" content="noindex,nofollow"', (path / "showcase.html").read_text())
        report = audit(path)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["counts"]["verified_downloads"], 3)
        self.assertEqual((path / "press" / "caption.txt").read_bytes(), b"Original caption\n")

    def test_kill_switch_restores_byte_identity(self):
        with patch.dict(os.environ, {"RETRO_SHOWCASE_KILL_SWITCH": "1"}):
            path, result = self.output("disabled")
        self.assertFalse(result["flag_enabled"])
        self.assertEqual(result["index_sha256"], result["baseline_index_sha256"])
        for name in ("index.html", "privacy-policy.html", ".nojekyll", "press/caption.txt"):
            self.assertEqual((self.site / name).read_bytes(), (path / name).read_bytes())
        self.assertFalse((path / "showcase.html").exists())
        self.assertFalse((path / "downloads").exists())
        self.assertTrue(audit(path)["ok"])

    def test_checksum_detects_mutated_download(self):
        path, _ = self.output()
        target = path / "downloads" / "product-facts.txt"
        target.write_bytes(target.read_bytes() + b"extra")
        issues = audit(path)["errors"]
        self.assertTrue(any("checksum mismatch" in issue for issue in issues), issues)
        self.assertTrue(any("size mismatch" in issue for issue in issues), issues)

    def test_relative_asset_missing_and_bad_anchor(self):
        path, _ = self.output()
        (path / "showcase.css").unlink()
        text = (path / "showcase.html").read_text(encoding="utf-8")
        (path / "showcase.html").write_text(text.replace('href="#rooms"', 'href="#not-found"'), encoding="utf-8")
        issues = audit(path)["errors"]
        self.assertTrue(any("missing local asset" in issue for issue in issues), issues)
        self.assertTrue(any("missing local anchor" in issue for issue in issues), issues)

    def test_remote_resource_and_path_traversal_rejected(self):
        path, _ = self.output()
        text = (path / "showcase.html").read_text(encoding="utf-8")
        text = text.replace("</head>", '<script src="https://example.invalid/x.js"></script></head>')
        text = text.replace("</body>", '<a href="../../outside.bin">Invalid</a></body>')
        (path / "showcase.html").write_text(text, encoding="utf-8")
        issues = audit(path)["errors"]
        self.assertTrue(any("remote dependency" in issue for issue in issues), issues)
        self.assertTrue(any("traversal outside" in issue for issue in issues), issues)

    def test_invalid_metadata_contract(self):
        obj = json.loads((Path(__file__).resolve().parents[1] / "metadata.json").read_text())
        self.assertEqual(validate_metadata(obj), [])
        obj["downloads"][0]["path"] = "../escape.svg"
        obj["rooms"][1]["id"] = obj["rooms"][0]["id"]
        issues = validate_metadata(obj)
        self.assertTrue(any("path malformed" in s for s in issues))
        self.assertTrue(any("id malformed" in s for s in issues))

    def test_schema_version_mismatch(self):
        path, _ = self.output()
        meta_file = path / "site-metadata.json"
        meta = json.loads(meta_file.read_text())
        meta["schema_version"] = 2
        meta_file.write_text(json.dumps(meta))
        self.assertTrue(any("schema_version" in s for s in audit(path)["errors"]))

    def test_reproducible_default_build(self):
        path1, _ = self.output("a", disabled=False)
        path2, _ = self.output("b", disabled=False)
        files1 = sorted(p.relative_to(path1) for p in path1.rglob("*") if p.is_file())
        files2 = sorted(p.relative_to(path2) for p in path2.rglob("*") if p.is_file())
        self.assertEqual(files1, files2)
        self.assertEqual({p: sha256(path1 / p) for p in files1}, {p: sha256(path2 / p) for p in files2})

    def test_out_inside_site_fails_safely(self):
        with self.assertRaisesRegex(ValueError, "separate"):
            build(self.site, self.site / "generated", disabled=False)
        self.assertFalse((self.site / "generated").exists())

    def test_default_flag_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            path, result = self.output("unset")
        self.assertTrue(result["flag_enabled"])
        self.assertTrue((path / "showcase.html").exists())

    def test_linked_vector_asset_remote_reference_detected(self):
        path, _ = self.output("svg")
        svg = path / "showcase_assets" / "mark.svg"
        content = svg.read_text(encoding="utf-8")
        content = content.replace("</svg>", '<image href="https://example.invalid/remote.svg"/></svg>')
        svg.write_text(content, encoding="utf-8")
        self.assertTrue(any("remote dependency" in s for s in audit(path)["errors"]))

    def test_relative_css_resource_detected(self):
        path, _ = self.output("css")
        css = path / "showcase.css"
        css.write_text(css.read_text(encoding="utf-8") + "\n.hidden{background:url('./gone.png')}\n", encoding="utf-8")
        self.assertTrue(any("missing local asset" in s for s in audit(path)["errors"]))

    def test_checksum_list_corruption_detected(self):
        path, _ = self.output("sums")
        checksum_file = path / "downloads" / "SHA256SUMS.txt"
        checksum_file.write_text("0" * 64 + "  downloads/five-room-map.svg\n", encoding="utf-8")
        self.assertTrue(any("SHA256SUMS.txt" in s for s in audit(path)["errors"]))

    def test_no_unexpected_schema_file_fallback(self):
        path, _ = self.output()
        (path / "site-metadata.schema.json").unlink()
        self.assertTrue(any("must all be present" in s for s in audit(path)["errors"]))


if __name__ == "__main__":
    unittest.main()
