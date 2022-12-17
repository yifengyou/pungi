#!/bin/bash

cat Dockerfile

docker build -t fedora36-pungi .

echo "All done![$?]"
