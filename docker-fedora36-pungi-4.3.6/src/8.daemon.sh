#!/bin/bash

set -e

docker container prune -f

[ ! -d pungi-data ] && mkdir pungi-data

docker run \
	--privileged -d \
	-v `pwd`/pungi-data:/data \
	--name fedora36-pungi \
	fedora36-pungi \
	/usr/sbin/init

echo "All done!"
