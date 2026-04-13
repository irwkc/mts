#!/usr/bin/env python3
"""Вставляет в собранный index.html только BAOBAB: splash-delay и custom.css (без gena-inject)."""
from pathlib import Path


def main() -> None:
    splash = '<script src="/static/baobab-splash-delay.js"></script>'
    css = '<link rel="stylesheet" href="/static/custom.css" />'
    found = False
    for p in Path("/app/build").rglob("index.html"):
        found = True
        t = p.read_text(encoding="utf-8")
        orig = t
        if splash not in t and "<head>" in t:
            t = t.replace("<head>", "<head>" + splash, 1)
        if css not in t and "<head>" in t:
            t = t.replace("<head>", "<head>" + css, 1)
        if t != orig:
            p.write_text(t, encoding="utf-8")
    if not found:
        raise SystemExit("baobab: no index.html under /app/build")


if __name__ == "__main__":
    main()
