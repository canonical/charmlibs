#!/usr/bin/env python3
# This script is executed in this directory via `just pack-k8s` or `just pack-machine`.
# Extra args are passed to this script, e.g. `just pack-k8s foo` -> `sys.argv[1] == 'foo'`.
# These commands are invoked in CI:
#     - if this file exists ad `just integration-<substrate>` would execute any tests
#     - before running integration tests
#     - with no additional arguments
#
# Environment variables:
# $CHARMLIBS_SUBSTRATE will have the value 'k8s' or 'machine' (set by pack-k8s or pack-machine)
# in CI, $CHARMLIBS_TAG is set based on pyproject.toml:tools.charmlibs.integration.tags
#     set $CHARMLIBS_TAG locally for testing, or use the tag variable
#     e.g. just tag=24.04 pack-k8s some extra args

import argparse
import os
import pathlib
import shutil
import subprocess

LIBRARY_DIR = pathlib.Path(__file__).parent.parent.parent
PACKED_DIR = pathlib.Path('.packed')
TEMPLATE_DIR = pathlib.Path('charm')


def _get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep', action='store_true')
    # add arguments here, e.g. parser.add_argument('foo', nargs='?')
    return parser


def _main(substrate: str, tag: str | None, keep: bool = False) -> None:
    charm_name = f'{substrate}-{tag}' if tag else substrate
    # temporary directory for packing
    tmp_dir = pathlib.Path('.tmp')
    shutil.rmtree(tmp_dir, ignore_errors=True)  # remove temp dir if it already exists
    tmp_dir.mkdir()
    # write templated file
    charmcraft_yaml = (TEMPLATE_DIR / 'charmcraft.yaml.template').read_text().format(
        charm_name=charm_name,
        suffix=path.read_text() if (path := TEMPLATE_DIR / f'{substrate}.yaml').exists() else '',
        # template other fields based on substrate or tag
    )
    (tmp_dir / 'charmcraft.yaml').write_text(charmcraft_yaml)
    # copy static files
    (tmp_dir / 'src').mkdir()
    shutil.copy(TEMPLATE_DIR / 'pyproject.toml', tmp_dir)
    shutil.copy(TEMPLATE_DIR / 'common.py', tmp_dir / 'src')
    shutil.copy(TEMPLATE_DIR / f'{substrate}.py', tmp_dir / 'src' / 'charm.py')
    # copy library src and pyproject.toml
    package_dir = tmp_dir / 'package'
    package_dir.mkdir()
    shutil.copy(LIBRARY_DIR / 'pyproject.toml', package_dir)
    shutil.copy(LIBRARY_DIR / 'README.md', package_dir)  # needed for build
    shutil.copytree(LIBRARY_DIR / 'src', package_dir / 'src')
    # pack charm
    subprocess.check_call(['uv', 'lock'], cwd=tmp_dir)  # required by uv plugin
    subprocess.check_call(['charmcraft', 'pack', '--verbosity', 'trace'], cwd=tmp_dir)
    # move packed charm to PACKED_DIR before temp dir is cleaned up
    PACKED_DIR.mkdir(exist_ok=True)
    next(tmp_dir.glob('*.charm')).rename(PACKED_DIR / f'{charm_name}.charm')
    if not keep:
        shutil.rmtree(tmp_dir)


if __name__ ==  '__main__':
    _args = _get_parser().parse_args()
    _main(os.environ['CHARMLIBS_SUBSTRATE'], tag=os.environ.get('CHARMLIBS_TAG'), keep=_args.keep)
