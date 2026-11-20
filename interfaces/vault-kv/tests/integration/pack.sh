#!/usr/bin/env bash
# This script is executed in this directory via `just pack-k8s` or `just pack-machine`.
# Extra args are passed to this script, e.g. `just pack-k8s <package> foo` -> $1 is 'foo'.
# In CI, the `just pack-<substrate>` commands are invoked:
#     - If this file exists and `just integration-<substrate>` would execute any tests
#     - Before running integration tests
#     - With no additional arguments
#
# Environment variables:
# $CHARMLIBS_SUBSTRATE is ignored: the provider and requirer charms have no containers
# or resources, so the same charms are packed for both the K8s and machine substrates.
set -xueo pipefail

TMP_DIR=".tmp"  # clean temporary directory where charms will be packed
PACKED_DIR=".packed"  # where packed charms will be placed with name expected by the tests

# mkdir -p means create parents and don't complain if dir already exists
mkdir -p "$TMP_DIR"
mkdir -p "$PACKED_DIR"

for charm in 'provider' 'requirer'; do
    charm_tmp_dir="$TMP_DIR/$charm"

    : copy charm files to temporary directory for packing, dereferencing symlinks
    rm -rf "$charm_tmp_dir"
    cp --recursive --dereference "charms/$charm-charm" "$charm_tmp_dir"

    : pack charm
    cd "$charm_tmp_dir"
    uv lock  # required by uv charm plugin
    charmcraft pack
    cd -

    : place packed charm in expected location
    mv "$charm_tmp_dir"/*.charm "$PACKED_DIR/$charm.charm"  # read by integration tests
done

ls "$PACKED_DIR"
