# Workaround for building whisper.cpp (via whisper-rs-sys) with GCC on arm64
# hosts (e.g. this DGX Spark / Grace box).
#
# ggml's GGML_NATIVE probing constructs "-mcpu=native+nodotprod+noi8mm+nosve",
# a spelling GCC (<= 13 at least) rejects outright, killing the build. Turning
# native probing off makes ggml use the explicit -march below instead
# (armv8.2-a+dotprod+fp16 is safe on any recent arm64 server/laptop core and
# keeps whisper's hot loops vectorized).
#
# This file is injected through the CMAKE_TOOLCHAIN_FILE env var set in
# ../.cargo/config.toml — the cmake crate forwards it to every cmake build in
# this crate's dependency graph (only whisper-rs-sys uses cmake here). It sets
# no CMAKE_SYSTEM_NAME, so it does NOT put CMake into cross-compile mode.

set(GGML_NATIVE OFF CACHE BOOL "ggml: skip broken -mcpu=native probing (see header)" FORCE)
set(GGML_CPU_ARM_ARCH "armv8.2-a+dotprod+fp16" CACHE STRING "ggml: explicit ARM arch" FORCE)
