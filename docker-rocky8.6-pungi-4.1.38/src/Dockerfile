FROM rockylinux:8.6
LABEL maintainers="yifengyou <nicyou@tencent.com>"

RUN dnf install -y epel-release && cat /etc/yum.repos.d/*.repo && dnf makecache && \
    dnf -y install systemd findutils git \
                   which passwd openssh-server vim

RUN dnf install -y \
        createrepo \
	pungi \
	python3-pungi

RUN dnf install -y \
    net-tools \
    tmux \
    && dnf clean all

RUN useradd pungi && passwd -d pungi
