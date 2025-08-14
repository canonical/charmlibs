# This Makefile was adapted from the documentation starter pack. We've kept it for
# consistency with other Canonical projects, so that contributors can use familiar
# `make` commands to build the docs.

# To modify the doc build process, edit `docs.just` in the repo root.

help:
	@echo "\n" \
        "------------------------------------------------------------- \n" \
        "* watch, build and serve the documentation:  make run \n" \
        "* only build:                                make html \n" \
        "* clean full environment:                    make clean \n" \
        "* check links:                               make linkcheck \n" \
        "* check spelling:                            make spelling \n" \
        "------------------------------------------------------------- \n"

.PHONY: html run clean install linkcheck

run:
	uvx --from=rust-just just docs run

html:
	uvx --from=rust-just just docs html

clean:
	uvx --from=rust-just just docs clean

linkcheck:
	uvx --from=rust-just just docs linkcheck

spelling:
	uvx --from=rust-just just docs spelling
