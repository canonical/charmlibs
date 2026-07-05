# sourced by just functional snap
SNAPS_DIR="tests/functional/snaps"
mksquashfs "$SNAPS_DIR/test-snap-1.0" "$SNAPS_DIR/test-snap_1.0.snap" -noappend -comp xz -quiet
mksquashfs "$SNAPS_DIR/test-snap-2.0" "$SNAPS_DIR/test-snap_2.0.snap" -noappend -comp xz -quiet
mksquashfs "$SNAPS_DIR/test-classic-snap-1.0" "$SNAPS_DIR/test-classic-snap_1.0.snap" -noappend -comp xz -quiet
