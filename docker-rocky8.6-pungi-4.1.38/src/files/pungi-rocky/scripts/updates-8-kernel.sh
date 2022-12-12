#!/bin/bash

source "$(dirname "$0")/common-8"
TARGET_DIR="/mnt/compose/8"
SHORT=kernel
CONFIG=/etc/pungi-prod/kernel.conf
# Unused for now
OLDCOMPOSE_ID=$(cat $TARGET_DIR/latest-$SHORT-8/COMPOSE_ID)
SKIP="--skip-phase buildinstall --skip-phase createiso --skip-phase extra_isos --skip-phase productimg"
LABEL="--production --no-label"
CMD="pungi-koji --config=$CONFIG --old-composes=$TARGET_DIR $OLD_COMPOSES_DIR $SKIP $LABEL"

if [ -z "$COMPOSE_ID" ]; then
  CMD="$CMD --target-dir=$TARGET_DIR"
else
  CMD="$CMD --debug-mode --compose-dir=$TARGET_DIR/$COMPOSE_ID"
fi

time $CMD
