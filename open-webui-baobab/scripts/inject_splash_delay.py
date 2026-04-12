#!/usr/bin/env python3
"""Вставляет baobab-splash-delay.js, gena-openwebui.css и gena-openwebui.js в index.html сборки Open WebUI."""
from pathlib import Path


def main() -> None:
    splash = '<script src="/static/baobab-splash-delay.js"></script>'
    css = '<link rel="stylesheet" href="/static/gena-openwebui.css" />'
    gena = '<script defer src="/static/gena-openwebui.js"></script>'
    for p in Path("/app/build").rglob("index.html"):
        t = p.read_text(encoding="utf-8")
        orig = t
        if splash not in t and "<head>" in t:
            t = t.replace("<head>", "<head>" + splash, 1)
        if css not in t and "<head>" in t:
            t = t.replace("<head>", "<head>" + css, 1)
        if gena not in t and "<head>" in t:
            t = t.replace("<head>", "<head>" + gena, 1)
        if t != orig:
            p.write_text(t, encoding="utf-8")
    if not any(Path("/app/build").rglob("index.html")):
        raise SystemExit("baobab: no index.html under /app/build")


if __name__ == "__main__":
    main()
