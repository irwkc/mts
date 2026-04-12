# Тёмно-фиолетовая оболочка BAOBAB + custom.css поверх Open WebUI
FROM ghcr.io/open-webui/open-webui:main

COPY custom.css /app/build/static/custom.css
# Некоторые пути отдают статику из backend (см. open-webui issues про custom.css)
RUN if [ -d /app/backend/open_webui/static ]; then \
      cp /app/build/static/custom.css /app/backend/open_webui/static/custom.css; \
    fi
