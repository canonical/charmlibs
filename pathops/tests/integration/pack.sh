#!/usr/bin/env bash
# usage: pack.sh <substrate> <base>
# e.g. pack.sh machine 24.04
set -xueo pipefail
cd charms

CHARMDIR="$CHARMLIBS_SUBSTRATE"  # k8s or machine
BASE="$CHARMLIBS_TAG"  # 20.04, 24.04, etc


TMPDIR=".$CHARMDIR"
rm -rf "$TMPDIR"
cp --recursive "$CHARMDIR" "$TMPDIR"
mv "$TMPDIR"/"$BASE"-charmcraft.yaml "$TMPDIR"/charmcraft.yaml

mkdir "$TMPDIR/pathops"
cp -r ../../../pyproject.toml "$TMPDIR/pathops/"
cp -r ../../../src "$TMPDIR/pathops/"

cd "$TMPDIR"
uv lock  # required by uv charm plugin
charmcraft pack
cd -

mkdir -p .packed
mv "$TMPDIR"/*.charm ".packed/$CHARMDIR.charm"
rm -rf "$TMPDIR"
