#!/bin/sh

set -e

HERE=$(realpath "$(dirname "$0")")

PYTHONPATH=$HERE/../:$PYTHONPATH
PATH=$HERE/../bin:$PATH
export PYTHONPATH PATH

mkdir -p _composes

pungi-koji \
--target-dir="$HERE/_composes" \
--old-composes="$HERE/_composes" \
--config="$HERE/data/dummy-pungi.conf" \
--test "$@"

# Run this to create unified ISOs for the just created compose
#pungi-create-unified-isos _composes/latest-DP-1/
