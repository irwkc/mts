#!/usr/bin/env python3
"""Вставляет baobab-splash-delay.js в index.html сборки Open WebUI."""
from pathlib import Path

def main() -> None:
    inj = '<script src="/static/baobab-splash-delay.js"></script>'
    patched = 0
    for p in Path("/app/build").rglob("index.html"):
        t = p.read_text(encoding="utf-8")
        if inj in t:
            continue
        if "<head>" in t:
            p.write_text(t.replace("<head>", "<head>" + inj, 1), encoding="utf-8")
            patched += 1
    if patched == 0:
        raise SystemExit("baobab: index.html not found or already contains inject")


if __name__ == "__main__":
    main()
