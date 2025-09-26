#!/usr/bin/env bash
set -xueo pipefail
cd charms

uv lock  # required by uv charm plugin
cd ./k8s
charmcraft pack
mv *.charm k8s.charm  # rename to a predictable name
cd ..
