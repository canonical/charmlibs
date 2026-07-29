# sourced by just functional snap
SNAPS_DIR="tests/functional/snaps"
# -all-root forces the squashfs payload to be owned by root:root. Without it, mksquashfs records
# the uid/gid of the source files as checked out, and snapd's unsquashfs fails to sideload the snap
# ("set_attributes ... Invalid argument") when that uid is unmapped in the container (e.g. a large
# LDAP uid on a developer machine). Snap payloads are root-owned in any case.
mksquashfs "$SNAPS_DIR/test-snap-1.0" "$SNAPS_DIR/test-snap_1.0.snap" -noappend -comp xz -all-root -quiet
mksquashfs "$SNAPS_DIR/test-snap-2.0" "$SNAPS_DIR/test-snap_2.0.snap" -noappend -comp xz -all-root -quiet
mksquashfs "$SNAPS_DIR/test-classic-snap-1.0" "$SNAPS_DIR/test-classic-snap_1.0.snap" -noappend -comp xz -all-root -quiet
mksquashfs "$SNAPS_DIR/test-configure-snap-1.0" "$SNAPS_DIR/test-configure-snap_1.0.snap" -noappend -comp xz -all-root -quiet
mksquashfs "$SNAPS_DIR/test-interfaces-snap-1.0" "$SNAPS_DIR/test-interfaces-snap_1.0.snap" -noappend -comp xz -all-root -quiet
mksquashfs "$SNAPS_DIR/test-service-snap-1.0" "$SNAPS_DIR/test-service-snap_1.0.snap" -noappend -comp xz -all-root -quiet
mksquashfs "$SNAPS_DIR/test-other-service-snap-1.0" "$SNAPS_DIR/test-other-service-snap_1.0.snap" -noappend -comp xz -all-root -quiet
