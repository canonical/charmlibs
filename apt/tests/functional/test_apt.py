#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from urllib.request import urlopen

import charmlibs.apt as apt

logger = logging.getLogger(__name__)

KEY_DIR = Path(__file__).parent / 'keys'


def test_install_packages():
    apt.update()
    apt.add_package('zsh')
    assert shutil.which('zsh') == '/usr/bin/zsh'
    apt.add_package(['golang-cfssl', 'jq'])
    assert shutil.which('cfssl') == '/usr/bin/cfssl'
    assert shutil.which('jq') == '/usr/bin/jq'


def test_install_package_error():
    package = apt.DebianPackage(
        name="ceci-n'est-pas-un-paquet",
        version='1.0',
        epoch='',
        arch='amd64',
        state=apt.PackageState.Available,
    )
    try:
        package.ensure(apt.PackageState.Present)
    except apt.PackageError as e:
        assert 'Unable to locate package' in str(e)


def test_remove_package():
    # First ensure the package is present
    cfssl = apt.DebianPackage.from_apt_cache('golang-cfssl')
    assert not cfssl.present
    # Add package
    apt.add_package('golang-cfssl')
    assert shutil.which('cfssl')
    subprocess.run(['cfssl', 'version'], check=True)
    # Now remove the package and check its bins disappear too
    apt.remove_package('golang-cfssl')
    assert not shutil.which('cfssl')


def test_install_package_from_external_repository():
    repo_id = 'deb-https://repo.mongodb.org/apt/ubuntu-jammy/mongodb-org/8.0'
    repos = apt.RepositoryMapping()
    assert repo_id not in repos
    assert not shutil.which('mongod')
    # steps
    key = urlopen('https://www.mongodb.org/static/pgp/server-8.0.asc').read().decode()
    key_file = apt.import_key(key)
    line = (
        f'deb [ arch=amd64,arm64 signed-by={key_file} ]'
        ' https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/8.0 multiverse'
    )
    # if: use implicit write_file
    repo = apt.DebianRepository.from_repo_line(line)  # write_file=True by default
    assert repo_id not in repos
    # if: don't use implicit write_file
    # repo = apt.DebianRepository.from_repo_line(line, write_file=False)
    # repos.add(repo)
    # assert repo_id in repos
    # fi
    assert repo_id in apt.RepositoryMapping()
    apt.update()
    apt.add_package('mongodb-org')
    assert shutil.which('mongod')
    subprocess.run(['mongod', '--version'], check=True)
    # cleanup
    os.remove(key_file)
    apt._add_repository(repo, remove=True)
    assert repo_id not in apt.RepositoryMapping()
    apt.update()
    apt.remove_package('mongodb-org')
    assert shutil.which('mongod')  # mongodb-org is a metapackage
    subprocess.run(['apt', 'autoremove'], check=True)
    assert not shutil.which('mongod')


def test_install_higher_version_package_from_external_repository():
    # The release-4 PPA publishes a newer fish than the Ubuntu archive for each supported series.
    codename = platform.freedesktop_os_release()['VERSION_CODENAME']
    ppa_uri = 'https://ppa.launchpadcontent.net/fish-shell/release-4/ubuntu/'
    repo_id = f'deb-{ppa_uri}-{codename}'
    repos = apt.RepositoryMapping()
    assert repo_id not in repos
    # version before
    if not shutil.which('fish'):
        apt.add_package('fish')
    assert shutil.which('fish')
    version_before = apt.DebianPackage.from_installed_package('fish').version
    apt.remove_package('fish')
    assert not shutil.which('fish')
    # The PPA only builds for base architectures, so on systems using an architecture variant
    # (such as amd64v3 on GitHub's ubuntu-26.04 runners) apt would read the PPA's empty variant
    # index and never see the newer fish. add-apt-repository drops [arch=...] options (#790),
    # so disable variants for the duration of the test instead.
    no_variants_conf = Path('/etc/apt/apt.conf.d/zzz-charmlibs-test-no-variants')
    repo = apt.DebianRepository(
        enabled=True,
        repotype='deb',
        uri=ppa_uri,
        release=codename,
        groups=['main'],
    )
    key_file = None
    # The variants setting, key, and repository are machine-wide, so undo them even if the test
    # fails, or the apt tests that run after this one see a different system.
    try:
        no_variants_conf.write_text('#clear APT::Architecture-Variants;\n')
        # steps
        repos.add(repo)  # update_cache=False by default
        assert repo_id in repos
        assert repo_id in apt.RepositoryMapping()
        key_file = apt.import_key((KEY_DIR / 'FISH_KEY.asc').read_text())
        apt.update()
        policy = subprocess.run(
            ['apt-cache', 'policy', 'fish'], capture_output=True, check=True, text=True
        ).stdout
        apt.add_package('fish')
        assert shutil.which('fish')
        version_after = apt.DebianPackage.from_installed_package('fish').version
        assert version_after > version_before, policy
    finally:
        # cleanup
        if key_file is not None:
            os.remove(key_file)
        no_variants_conf.unlink(missing_ok=True)
        if repo_id in apt.RepositoryMapping():
            apt._add_repository(repo, remove=True)
    assert repo_id not in apt.RepositoryMapping()
    apt.update()
    apt.remove_package('fish')
    assert not shutil.which('fish')


def test_install_hardware_observer_ssacli():
    """Test the ability to install a package used by the hardware-observer charm.

    Here we follow the order of operations and arguments used in the charm:
        for key in HP_KEYS:
            apt.import_key(key)

        repositories = apt.RepositoryMapping()
        repo = apt.DebianRepository.from_repo_line(...)
        repositories.add(repo)

        apt.add_package(self.pkg, update_cache=True)
    """
    line = 'deb https://downloads.linux.hpe.com/SDR/repo/mcp stretch/current non-free'
    repo_id = apt._repo_to_identifier(apt.DebianRepository.from_repo_line(line, write_file=False))
    assert repo_id not in apt.RepositoryMapping()
    assert not shutil.which('ssacli')
    key_files: list[str] = []  # just for cleanup
    # steps
    # Keys enumerated per HPE's current guidance at
    # https://downloads.linux.hpe.com/SDR/keys.html: KEY1 verifies packages
    # published after 2015, KEY2 verifies packages published after 2024, and
    # the legacy HP keys cover pre-2015 packages that may still be pinned.
    for path in (
        KEY_DIR / 'HPEPUBLICKEY2048_KEY1.asc',
        KEY_DIR / 'HPEPUBLICKEY2048_KEY2.asc',
        KEY_DIR / 'HPPUBLICKEY2048_KEY1.asc',
        KEY_DIR / 'HPPUBLICKEY2048.asc',
        KEY_DIR / 'HPPUBLICKEY1024.asc',
    ):
        key_file = apt.import_key(path.read_text())
        key_files.append(key_file)
    repos = apt.RepositoryMapping()
    repo = apt.DebianRepository.from_repo_line(line)  # write_file=True by default
    assert repo_id in apt.RepositoryMapping()
    # repo added to system but repos doesn't know about it yet
    assert repo_id not in repos
    repos.add(repo)
    assert repo_id in repos
    # `add` call is redundant with `from_repo_line` from system pov
    # but adds an entry to the RepositoryMapping
    apt.add_package('ssacli', update_cache=True)
    # apt.update not required since update_cache=True
    assert shutil.which('ssacli')
    # cleanup
    for key_file in key_files:
        os.remove(key_file)
    apt._add_repository(repo, remove=True)
    assert repo_id not in apt.RepositoryMapping()
    apt.update()
    apt.remove_package('ssacli')
    assert not shutil.which('ssacli')


def test_from_apt_cache_error():
    try:
        apt.DebianPackage.from_apt_cache("ceci-n'est-pas-un-paquet")
    except apt.PackageError as e:
        assert 'No packages found' in str(e)
