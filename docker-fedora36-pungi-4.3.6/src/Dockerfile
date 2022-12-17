FROM fedora:36
LABEL maintainers="yifengyou 13518106436@163.com"

RUN cat /etc/yum.repos.d/*.repo && dnf makecache && \
    dnf -y install systemd findutils which passwd

RUN dnf install -y \
        createrepo \
        git \
        openssh-server \
        vim \
        net-tools \
        iproute \
        tmux

RUN dnf install -y \
    pungi \
    python3-pungi \
    pungi-utils && dnf clean all

COPY files/pungi-init /usr/bin/pungi-init
