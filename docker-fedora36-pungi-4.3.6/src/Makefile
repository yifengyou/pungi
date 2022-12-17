.PHONY: build attach destroy daemon reenter help default

APP=pungi
DOCKER_IMAGE=fedora36-$(APP)
CONTAINER_NAME=fedora36-$(APP)

default:
	@echo ""
	@echo "Makefile for $(APP) using docker image $(DOCKER_IMAGE)"
	@echo "maintainers: yifengyou 13518106436@163.com"
	@echo ""
	@echo "help        show help info(default)"
	@echo "status      show docker status"
	@echo "build       build docker image"
	@echo "attach      attach container"
	@echo "destroy     destroy container"
	@echo "daemon      start an container with daemon"
	@echo "reenter     restart container"

help: default

build:
	cat Dockerfile
	docker build -t $(DOCKER_IMAGE) .

attach:
	docker exec -it $(CONTAINER_NAME) /bin/bash -c "cd /data && /bin/bash"

destroy:
	docker container rm --force $(CONTAINER_NAME) || :

daemon:
	docker run \
		--privileged -d \
		-v `pwd`/$(APP)-data:/data \
		--name $(CONTAINER_NAME) \
		$(DOCKER_IMAGE) \
		/usr/sbin/init

reenter: build destroy daemon
	docker exec -it $(CONTAINER_NAME) /bin/bash -c "$(APP)-init"
	docker exec -it $(CONTAINER_NAME) /bin/bash -c "cd /data && /bin/bash"

status:
	systemctl status docker --no-pager
	docker image ls $(DOCKER_IMAGE)
	docker container ls --filter name=$(CONTAINER_NAME)
	@echo "All ok!"