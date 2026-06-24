# Headless-browser meeting bot worker.
# Playwright's official image ships Chromium + all its system deps; we add the
# PulseAudio virtual-audio stack + ffmpeg so the bot can capture and speak audio.
FROM mcr.microsoft.com/playwright:v1.49.1-jammy

RUN apt-get update && apt-get install -y --no-install-recommends \
    pulseaudio pulseaudio-utils ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev --no-audit --no-fund

COPY src ./src
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV AUDIO_CAPTURE=pulse \
    HEADLESS=true \
    PORT=4500
EXPOSE 4500

ENTRYPOINT ["/entrypoint.sh"]
