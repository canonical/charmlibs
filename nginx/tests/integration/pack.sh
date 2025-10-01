#!/usr/bin/env bash
set -xueo pipefail
cd charms

cd ./k8s
uv lock  # required by uv charm plugin
charmcraft pack
mv *.charm k8s.charm  # rename to a predictable name
cd ..
