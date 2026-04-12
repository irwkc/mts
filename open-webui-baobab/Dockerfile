# Open WebUI + BAOBAB: лого → favicon.ico, PNG, splash, PWA-иконки; splash +3 с
FROM ghcr.io/open-webui/open-webui:main

COPY custom.css /app/build/static/custom.css
COPY baobab-splash-delay.js /app/build/static/baobab-splash-delay.js
COPY gena-openwebui.css /app/build/static/gena-openwebui.css
COPY gena-openwebui.js /app/build/static/gena-openwebui.js
COPY scripts/inject_splash_delay.py /tmp/inject_splash_delay.py

RUN python3 /tmp/inject_splash_delay.py && rm -f /tmp/inject_splash_delay.py

COPY assets/baobab-logo.png /tmp/baobab-logo.png

USER root
RUN apt-get update && apt-get install -y --no-install-recommends imagemagick \
  && convert /tmp/baobab-logo.png -define icon:auto-resize=64,48,32,16 /app/build/static/favicon.ico \
  && cp /tmp/baobab-logo.png /app/build/static/favicon.png \
  && convert /tmp/baobab-logo.png -resize 96x96 /app/build/static/favicon-96x96.png \
  && convert /tmp/baobab-logo.png -resize 180x180 /app/build/static/apple-touch-icon.png \
  && cp /tmp/baobab-logo.png /app/build/static/splash.png \
  && cp /tmp/baobab-logo.png /app/build/static/splash-dark.png \
  && convert /tmp/baobab-logo.png -resize 192x192 /app/build/static/web-app-manifest-192x192.png \
  && convert /tmp/baobab-logo.png -resize 512x512 /app/build/static/web-app-manifest-512x512.png \
  && cp /app/build/static/favicon.png /app/build/static/logo.png \
  && cp /app/build/static/favicon.png /app/build/static/favicon-dark.png \
  && rm -f /tmp/baobab-logo.png \
  && rm -rf /var/lib/apt/lists/*

RUN if [ -d /app/backend/open_webui/static ]; then \
      for f in custom.css baobab-splash-delay.js gena-openwebui.css gena-openwebui.js favicon.ico favicon.png favicon-dark.png logo.png favicon-96x96.png \
               apple-touch-icon.png splash.png splash-dark.png \
               web-app-manifest-192x192.png web-app-manifest-512x512.png; do \
        [ -f "/app/build/static/$f" ] && cp "/app/build/static/$f" "/app/backend/open_webui/static/$f"; \
      done; \
    fi
