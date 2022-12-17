#!/bin/bash

# Copyright (C) 2015 Red Hat, Inc.
# SPDX-License-Identifier:      GPL-2.0

trap cleanup EXIT

function cleanup() {
    printf "Run cleanup\\n"
    rm -rf  "$dir_pungi" "$dir_pungi_doc"
}

if [ -z "$1" ]; then
    printf "Usage:\\n"
    printf "\\t%s release_version\\n" "$0"
    exit 1
fi

set -e
dir_pungi=$(mktemp -d /tmp/pungi.XXX) || { echo "Failed to create temp directory"; exit 1; }
git clone https://pagure.io/pungi.git "$dir_pungi"
pushd "$dir_pungi"/doc
make html
popd

dir_pungi_doc=$(mktemp -d /tmp/pungi-doc.XXX) || { echo "Failed to create temp directory"; exit 1; }
git clone ssh://git@pagure.io/docs/pungi.git "$dir_pungi_doc"
pushd "$dir_pungi_doc"
git rm -fr ./*
cp -r "$dir_pungi"/doc/_build/html/* ./
pushd "$dir_pungi"/doc
git checkout 4.0.x
make html
popd
mkdir 4.0
cp -r "$dir_pungi"/doc/_build/html/* ./4.0/
git add .
git commit -s -m "update rendered pungi docs for release $1"
git push origin master
popd
