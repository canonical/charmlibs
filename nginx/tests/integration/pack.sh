#!/usr/bin/env bash
set -xueo pipefail
cd charms

uv lock  # required by uv charm plugin
charmcraft pack
