#!/usr/bin/env bash
# This script is executed in this directory via `just pack-k8s` or `just pack-machine`.
# Extra args are passed to this script, e.g. `just pack-k8s foo` -> $1 is 'foo'.
# In CI, the `just pack-<substrate>` commands are invoked:
#     - If this file exists and `just integration-<substrate>` would execute any tests
#     - Before running integration tests
#     - With no additional arguments
#
# Environment variables:
# $CHARMLIBS_SUBSTRATE will have the value 'k8s' or 'machine' (set by pack-k8s or pack-machine)
# In CI, $CHARMLIBS_TAG is set based on pyproject.toml:tool.charmlibs.integration.tags
# For local testing, set $CHARMLIBS_TAG directly or use the tag variable. For example:
# just tag=24.04 pack-k8s some extra args
set -xueo pipefail

TMP_DIR=".tmp"  # clean temporary directory where charms will be packed
PACKED_DIR=".packed"  # where packed charms will be placed with name expected in conftest.py

: copy charm files to temporary directory for packing, dereferencing symlinks
rm -rf "$TMP_DIR"
cp --recursive --dereference "charms/$CHARMLIBS_SUBSTRATE/" "$TMP_DIR"

: pack charm
cd "$TMP_DIR"
cd provider
uv lock  # required by uv charm plugin
charmcraft pack
cd ..
cd requirer
uv lock  # required by uv charm plugin
charmcraft pack
cd -

: place packed charm in expected location
mkdir -p "$PACKED_DIR"
mkdir -p "$PACKED_DIR/provider/"
mkdir -p "$PACKED_DIR/requirer/"
mv "$TMP_DIR"/provider/*.charm "$PACKED_DIR/provider/$CHARMLIBS_SUBSTRATE.charm"  # read by conftest.py
mv "$TMP_DIR"/requirer/*.charm "$PACKED_DIR/requirer/$CHARMLIBS_SUBSTRATE.charm"  # read by conftest.py
