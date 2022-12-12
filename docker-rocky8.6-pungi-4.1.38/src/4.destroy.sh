#!/bin/bash

set -e

docker container prune -f
docker container rm --force rocky8.6-pungi

[ -d pungi-data ] && rm -rf pungi-data

echo "All done!"
