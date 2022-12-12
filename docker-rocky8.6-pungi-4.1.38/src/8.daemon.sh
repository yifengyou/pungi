#!/bin/bash

set -e

docker container prune -f

[ ! -d pungi-data ] && mkdir pungi-data

docker run \
	--privileged -d \
	-v `pwd`/pungi-data:/data \
	--name rocky8.6-pungi \
	rockylinux8.6-pungi \
	/usr/sbin/init

echo "All done!"
