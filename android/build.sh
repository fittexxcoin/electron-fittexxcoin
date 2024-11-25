#!/bin/bash
set -eu

cd $(dirname $0)/..

git submodule update --init contrib/electrum-locale

docker build -t ec-android -f android/Dockerfile .
container_name=$(docker create ec-android)
docker cp $container_name:/root/android/app/build/outputs/apk/MainNet/release android
docker rm $container_name
