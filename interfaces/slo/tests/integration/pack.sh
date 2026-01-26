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

mkdir -p "$PACKED_DIR"  # -p means create parents and don't complain if dir already exists

# Pack SLO test provider charm
: pack slo-test-provider charm
rm -rf "$TMP_DIR"
cp --recursive --dereference "charms/slo-provider/" "$TMP_DIR"
cd "$TMP_DIR"
uv lock  # required by uv charm plugin
charmcraft pack
cd -
mv "$TMP_DIR"/*.charm "$PACKED_DIR/slo-test-provider_ubuntu-24.04-amd64.charm"

# Pack SLO test requirer charm
: pack slo-test-requirer charm
rm -rf "$TMP_DIR"
cp --recursive --dereference "charms/slo-requirer/" "$TMP_DIR"
cd "$TMP_DIR"
uv lock  # required by uv charm plugin
charmcraft pack
cd -
mv "$TMP_DIR"/*.charm "$PACKED_DIR/slo-test-requirer_ubuntu-24.04-amd64.charm"
