#!/usr/bin/env bash
set -e

# Virtual audio so the headless browser can (a) output meeting audio to a sink we
# can capture, and (b) read a virtual microphone we play TTS into.
export XDG_RUNTIME_DIR=/tmp/runtime
mkdir -p "$XDG_RUNTIME_DIR"

pulseaudio --start --exit-idle-time=-1 --disallow-exit -n \
  --load="module-native-protocol-unix" || true

# Sink the browser plays meeting audio into (capture its monitor for STT).
pactl load-module module-null-sink sink_name=vspeaker sink_properties=device.description=vspeaker || true
# Sink whose monitor becomes the bot's microphone; we paplay TTS into this sink.
pactl load-module module-null-sink sink_name=virtmic_sink sink_properties=device.description=virtmic_sink || true
pactl load-module module-remap-source master=virtmic_sink.monitor source_name=virtmic source_properties=device.description=virtmic || true
pactl set-default-sink vspeaker || true
pactl set-default-source virtmic || true

echo "[entrypoint] PulseAudio virtual devices ready (vspeaker, virtmic)"
exec node src/server.js
