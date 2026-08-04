#!/usr/bin/env sh
set -eu

flutter pub get
flutter analyze lib test
flutter test
