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

# mkdir -p means create parents and don't complain if dir already exists
mkdir -p "$TMP_DIR"
mkdir -p "$PACKED_DIR"

for charm in 'provider' 'requirer'; do
    for variant in 'local' 'published'; do
        charm_tmp_dir="$TMP_DIR/$charm-$variant"

        : copy charm files to temporary directory for packing, dereferencing symlinks
        rm -rf "$charm_tmp_dir"
        cp --recursive --dereference "charms/$charm/$variant" "$charm_tmp_dir"

        : pack charm
        cd "$charm_tmp_dir"
        uv lock  # required by uv charm plugin
        charmcraft pack
        cd -

        : place packed charm in expected location
        mv "$charm_tmp_dir"/*.charm "$PACKED_DIR/$charm-$variant.charm"  # read by integration tests
    done
done

: pack requirer variants built on the Charmhub-hosted v4 lib, used by the upgrade tests
: 'fetch-lib-latest' uses the newest v4 libpatch, 'fetch-lib-pre-fix' is pinned to
: libpatch 26, from before APP mode private keys were stored as app-owned secrets
for variant_and_lib in 'fetch-lib-latest=4' 'fetch-lib-pre-fix=4.26'; do
    variant="${variant_and_lib%%=*}"
    lib_version="${variant_and_lib##*=}"
    charm_tmp_dir="$TMP_DIR/requirer-$variant"

    rm -rf "$charm_tmp_dir"
    cp --recursive --dereference "charms/requirer/$variant" "$charm_tmp_dir"

    : declare the Charmhub lib at the pinned version, then fetch and pack
    printf '\ncharm-libs:\n  - lib: tls_certificates_interface.tls_certificates\n    version: "%s"\n' \
        "$lib_version" >> "$charm_tmp_dir/charmcraft.yaml"
    cd "$charm_tmp_dir"
    charmcraft fetch-libs
    uv lock
    charmcraft pack
    cd -

    mv "$charm_tmp_dir"/*.charm "$PACKED_DIR/requirer-$variant.charm"  # read by integration tests
done

ls "$PACKED_DIR"
