#!/usr/bin/env bash
set -euo pipefail

# The source bind mount can be newer than the image. Refresh dependency metadata
# before commands that consume the project, while keeping simple diagnostics fast.
if [[ -f pubspec.yaml && "${1:-}" == "flutter" ]]; then
  case "${2:-}" in
    pub|--version|-h|help|doctor|config)
      ;;
    *)
      flutter pub get
      ;;
  esac
fi

exec "$@"
