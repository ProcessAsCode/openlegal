#!/bin/sh
set -e
mkdir -p /data/db /data/agreements
if [ ! -d /data/uas ] || [ -z "$(ls -A /data/uas 2>/dev/null)" ]; then
  mkdir -p /data/uas && cp -r /uas-data/. /data/uas/
fi
exec "$@"
