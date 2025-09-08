#!/usr/bin/env bash
# usage: CHARMLIBS_SUBSTRATE=k8s CHARMLIBS_BASE=24.04 ./pack.sh
set -xueo pipefail
cd charms

CHARMDIR="$CHARMLIBS_SUBSTRATE"  # k8s or machine
BASE="$CHARMLIBS_TAG"  # 20.04, 24.04, etc


TMPDIR=".$CHARMDIR"
rm -rf "$TMPDIR"
cp --recursive "$CHARMDIR" "$TMPDIR"
mv "$TMPDIR"/"$BASE"-charmcraft.yaml "$TMPDIR"/charmcraft.yaml

mkdir "$TMPDIR/nginx"
cp -r ../../../pyproject.toml "$TMPDIR/nginx/"
cp -r ../../../src "$TMPDIR/nginx/"

cd "$TMPDIR"
uv lock  # required by uv charm plugin
charmcraft pack
cd -

mkdir -p .packed
mv "$TMPDIR"/*.charm ".packed/$CHARMDIR.charm"
rm -rf "$TMPDIR"
echo "juju deploy ./.packed/$CHARMDIR.charm"
