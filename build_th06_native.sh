#!/usr/bin/env bash
set -euo pipefail

TH06_REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TH06_BUILD_DIR="$TH06_REPO_DIR/build"
mkdir -p "$TH06_BUILD_DIR"

x86_64-w64-mingw32-g++ \
  -std=c++17 -O3 -Wall -Wextra -Werror \
  -shared -static -static-libgcc -static-libstdc++ \
  "$TH06_REPO_DIR/scripts/th06/kernels/safety.cpp" \
  -o "$TH06_BUILD_DIR/th06_safety.dll"

sha256sum "$TH06_BUILD_DIR/th06_safety.dll"
