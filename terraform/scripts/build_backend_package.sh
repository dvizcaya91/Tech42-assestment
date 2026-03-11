#!/usr/bin/env bash

set -euo pipefail

BACKEND_SOURCE_DIR="${BACKEND_SOURCE_DIR:?BACKEND_SOURCE_DIR is required}"
BACKEND_BUILD_DIR="${BACKEND_BUILD_DIR:?BACKEND_BUILD_DIR is required}"
BACKEND_RUNTIME_REQUIREMENTS="${BACKEND_RUNTIME_REQUIREMENTS:?BACKEND_RUNTIME_REQUIREMENTS is required}"
BACKEND_BUILD_PYTHON="${BACKEND_BUILD_PYTHON:-}"

resolve_build_python() {
  if [[ -n "$BACKEND_BUILD_PYTHON" ]]; then
    echo "$BACKEND_BUILD_PYTHON"
    return 0
  fi

  for candidate in python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
sys.exit(0 if sys.version_info >= (3, 11) else 1)
PY
      then
        echo "$candidate"
        return 0
      fi
    fi
  done

  if command -v pyenv >/dev/null 2>&1; then
    PYENV_ROOT="$(pyenv root)"
    while IFS= read -r version_name; do
      for candidate in \
        "$PYENV_ROOT/versions/$version_name/bin/python3.11" \
        "$PYENV_ROOT/versions/$version_name/bin/python" \
        "$PYENV_ROOT/versions/$version_name/bin/python3"; do
        if [[ -x "$candidate" ]]; then
          if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
sys.exit(0 if sys.version_info >= (3, 11) else 1)
PY
          then
            echo "$candidate"
            return 0
          fi
        fi
      done
    done < <(pyenv versions --bare)
  fi

  echo "Unable to find a Python interpreter for Lambda packaging." >&2
  return 1
}

BUILD_PYTHON="$(resolve_build_python)"

if ! "$BUILD_PYTHON" - <<'PY'
import sys
sys.exit(0 if sys.version_info >= (3, 11) else 1)
PY
then
  echo "Lambda packaging requires Python 3.11+ but '$BUILD_PYTHON' is $("$BUILD_PYTHON" --version 2>&1)." >&2
  echo "Set BACKEND_BUILD_PYTHON to a Python 3.11 interpreter before running terraform apply." >&2
  exit 1
fi

rm -rf "$BACKEND_BUILD_DIR"
mkdir -p "$BACKEND_BUILD_DIR"

"$BUILD_PYTHON" -m pip install \
  --disable-pip-version-check \
  --no-compile \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.11 \
  --requirement "$BACKEND_RUNTIME_REQUIREMENTS" \
  --target "$BACKEND_BUILD_DIR"
cp -R "$BACKEND_SOURCE_DIR/app" "$BACKEND_BUILD_DIR/app"
