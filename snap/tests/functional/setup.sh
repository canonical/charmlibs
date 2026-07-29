# sourced by just functional snap
SNAPS_DIR="tests/functional/snaps"
# Every subdirectory is a snap source tree named <snap-name>-<version>, built to
# <snap-name>_<version>.snap. Adding a snap needs no change here: drop in the directory.
# -all-root forces the squashfs payload to be owned by root:root. Without it, mksquashfs records
# the uid/gid of the source files as checked out, and snapd's unsquashfs fails to sideload the snap
# ("set_attributes ... Invalid argument") when that uid is unmapped in the container (e.g. a large
# LDAP uid on a developer machine). Snap payloads are root-owned in any case.
for src in "$SNAPS_DIR"/*/; do
    dir="$(basename "${src%/}")"
    mksquashfs "$SNAPS_DIR/$dir" "$SNAPS_DIR/${dir%-*}_${dir##*-}.snap" \
        -noappend -comp xz -all-root -quiet
done
