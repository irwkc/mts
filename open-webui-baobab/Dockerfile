# Тёмно-фиолетовая оболочка BAOBAB + custom.css, favicon и splash-изображение
FROM ghcr.io/open-webui/open-webui:main

COPY custom.css /app/build/static/custom.css
COPY baobab-splash-delay.js /app/build/static/baobab-splash-delay.js
COPY scripts/inject_splash_delay.py /tmp/inject_splash_delay.py

# Splash ещё +3 с: скрипт в <head> до основного бандла
RUN python3 /tmp/inject_splash_delay.py && rm -f /tmp/inject_splash_delay.py

# Брендинг: assets/splash-logo.png, assets/favicon.ico
COPY assets/splash-logo.png /app/build/static/baobab-splash.png
COPY assets/favicon.ico /app/build/static/favicon.ico
COPY assets/splash-logo.png /app/build/static/favicon.png

# Подмена штатных splash-картинок (inline-скрипт в app.html тоже тянет splash*.png)
COPY assets/splash-logo.png /app/build/static/splash-dark.png
COPY assets/splash-logo.png /app/build/static/splash.png

RUN if [ -d /app/backend/open_webui/static ]; then \
      cp /app/build/static/custom.css /app/backend/open_webui/static/custom.css; \
      cp /app/build/static/baobab-splash-delay.js /app/backend/open_webui/static/baobab-splash-delay.js; \
      cp /app/build/static/favicon.ico /app/backend/open_webui/static/favicon.ico; \
      cp /app/build/static/favicon.png /app/backend/open_webui/static/favicon.png; \
      cp /app/build/static/baobab-splash.png /app/backend/open_webui/static/baobab-splash.png; \
      cp /app/build/static/splash-dark.png /app/backend/open_webui/static/splash-dark.png; \
      cp /app/build/static/splash.png /app/backend/open_webui/static/splash.png; \
    fi
