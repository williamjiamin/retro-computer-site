# Offline showcase and asset verifier

This directory is an additive, private-draft toolset for an existing static site.
It does not deploy, publish, create an application installer, or change source files.
The generated showcase deliberately has a `noindex,nofollow` meta directive.

## Build (flag ON by default)

From the site repository root:

```sh
python3 site_tools/build_showcase.py --site . --out ../retro-preview
python3 site_tools/validate_site.py ../retro-preview
python3 -m unittest discover -s site_tools/tests -v
```

A safety check rejects an output directory within the source repository.
The builder copies the known static entry pages and the existing `press/`
folder, then adds the new showcase, original vector downloads, and hashes.
It never edits the input repository or contacts a network service.

## Emergency kill switch (reversion)

```sh
RETRO_SHOWCASE_KILL_SWITCH=1 python3 site_tools/build_showcase.py --site . --out ../retro-preview-off
```

When enabled, the kill switch omits the showcase, restores the exact source
HTML bytes, and preserves the existing static entry files. It is tested via
both byte comparison and browser screenshot equality on a local fixture.
The enabled default is equivalent to `RETRO_SHOWCASE_KILL_SWITCH=0`.

## Browser audit

```sh
python3 site_tools/audit_browser.py --site ../retro-preview --json ../viewport-audit.json
```

Requires a locally installed Python browser-automation module and browser
binary. The audit is entirely offline and verifies overflow, visible text
contrast (WCAG AA for normal body text), page links, and selected viewports in
light/dark modes. The basic builder and asset verifier need only the standard
Python library.

## Schema and downloaded content

`metadata.schema.json` is the machine-readable v1 JSON Schema for
`metadata.json`. `validate_site.py` performs equivalent core checks without
additional packages. Downloaded files are original schematic illustrations and
project summary text, not binaries, promotional screenshots, or app releases.
No external fonts, scripts, analytics, or image references are used.
