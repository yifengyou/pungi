#!/bin/bash

source "$(dirname "$0")/common-8"
export PATH=/usr/sbin:/usr/bin:/root/bin
TARGET_DIR="/mnt/compose/8"
SHORT=Rocky
CONFIG=/etc/pungi-prod/r8.conf
# Unused for now
OLDCOMPOSE_ID=$(cat $TARGET_DIR/latest-$SHORT-8/COMPOSE_ID)
SKIP=""
LABEL="--production --label RC-${REVISION}"

CMD="pungi-koji --config=$CONFIG $SKIP $LABEL"
#COMPOSE_ID="Rocky-8-20210625.n.0"

if [ -z "$COMPOSE_ID" ]; then
  CMD="$CMD --target-dir=$TARGET_DIR"
else
  CMD="$CMD --debug-mode --compose-dir=$TARGET_DIR/$COMPOSE_ID"
fi

time $CMD
