# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

# ruff: noqa: E501

import subprocess
from unittest.mock import MagicMock, patch

import pytest

import charmlibs.apt as apt

dpkg_output_zsh = """Desired=Unknown/Install/Remove/Purge/Hold
| Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend
|/ Err?=(none)/Reinst-required (Status,Err: uppercase=bad)
||/ Name                                 Version                                                                   Architecture Description
+++-====================================-=========================================================================-============-===============================================================================
ii  zsh                                  5.8-3ubuntu1                                                              amd64        shell with lots of features
"""

dpkg_output_vim = """Desired=Unknown/Install/Remove/Purge/Hold
| Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend
|/ Err?=(none)/Reinst-required (Status,Err: uppercase=bad)
||/ Name                                 Version                                                                   Architecture Description
+++-====================================-=========================================================================-============-===============================================================================
ii  vim                           2:8.1.2269-1ubuntu5                                                       amd64          Vi IMproved - Common files
"""

dpkg_output_all_arch = """Desired=Unknown/Install/Remove/Purge/Hold
| Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend
|/ Err?=(none)/Reinst-required (Status,Err: uppercase=bad)
||/ Name                                 Version                                                                   Architecture Description
+++-====================================-=========================================================================-============-===============================================================================
ii  postgresql                           12+214ubuntu0.1                                                           all         object-relational SQL database (supported version)
"""

dpkg_output_multi_arch = """Desired=Unknown/Install/Remove/Purge/Hold
| Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend
|/ Err?=(none)/Reinst-required (Status,Err: uppercase=bad)
||/ Name                                 Version                                                                   Architecture Description
+++-====================================-=========================================================================-============-===============================================================================
ii  vim                           2:8.1.2269-1ubuntu5                                                       amd64          Vi IMproved - Common files
ii  vim                           2:8.1.2269-1ubuntu5                                                       i386          Vi IMproved - Common files
"""

dpkg_output_not_installed = """Desired=Unknown/Install/Remove/Purge/Hold
| Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend
|/ Err?=(none)/Reinst-required (Status,Err: uppercase=bad)
||/ Name                              Version               Architecture          Description
+++-=================================-=====================-=====================-========================================================================
rc  ubuntu-advantage-tools            27.2.2~16.04.1        amd64                 management tools for Ubuntu Advantage
"""

apt_cache_mocktester = """
Package: mocktester
Architecture: amd64
Version: 1:1.2.3-4
Priority: optional
Section: test
Origin: Ubuntu
Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>
Original-Maintainer: Debian GNOME Maintainers <pkg-gnome-maintainers@lists.alioth.debian.org>
Bugs: https://bugs.launchpad.net/ubuntu/+filebug
Installed-Size: 1234
Depends: vim-common
Recommends: zsh
Suggests: foobar
Filename: pool/main/m/mocktester/mocktester_1:1.2.3-4_amd64.deb
Size: 65536
MD5sum: a87e414ad5aede7c820ce4c4e6bc7fa9
SHA1: b21d6ce47cb471c73fb4ec07a24c6f4e56fd19fc
SHA256: 89e7d5f61a0e3d32ef9aebd4b16e61840cd97e10196dfa186b06b6cde2f900a2
Homepage: https://wiki.gnome.org/Apps/MockTester
Description: Testing Package
Task: ubuntu-desktop
Description-md5: e7f99df3aa92cf870d335784e155ec33
"""

apt_cache_mocktester_all_arch = """
Package: mocktester
Architecture: all
Version: 1:1.2.3-4
Priority: optional
Section: test
Origin: Ubuntu
Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>
Original-Maintainer: Debian GNOME Maintainers <pkg-gnome-maintainers@lists.alioth.debian.org>
Bugs: https://bugs.launchpad.net/ubuntu/+filebug
Installed-Size: 1234
Depends: vim-common
Recommends: zsh
Suggests: foobar
Filename: pool/main/m/mocktester/mocktester_1:1.2.3-4_amd64.deb
Size: 65536
MD5sum: a87e414ad5aede7c820ce4c4e6bc7fa9
SHA1: b21d6ce47cb471c73fb4ec07a24c6f4e56fd19fc
SHA256: 89e7d5f61a0e3d32ef9aebd4b16e61840cd97e10196dfa186b06b6cde2f900a2
Homepage: https://wiki.gnome.org/Apps/MockTester
Description: Testing Package
Task: ubuntu-desktop
Description-md5: e7f99df3aa92cf870d335784e155ec33
"""

apt_cache_mocktester_multi = """
Package: mocktester
Architecture: amd64
Version: 1:1.2.3-4
Priority: optional
Section: test
Origin: Ubuntu
Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>
Original-Maintainer: Debian GNOME Maintainers <pkg-gnome-maintainers@lists.alioth.debian.org>
Bugs: https://bugs.launchpad.net/ubuntu/+filebug
Installed-Size: 1234
Depends: vim-common
Recommends: zsh
Suggests: foobar
Filename: pool/main/m/mocktester/mocktester_1:1.2.3-4_amd64.deb
Size: 65536
MD5sum: a87e414ad5aede7c820ce4c4e6bc7fa9
SHA1: b21d6ce47cb471c73fb4ec07a24c6f4e56fd19fc
SHA256: 89e7d5f61a0e3d32ef9aebd4b16e61840cd97e10196dfa186b06b6cde2f900a2
Homepage: https://wiki.gnome.org/Apps/MockTester
Description: Testing Package
Task: ubuntu-desktop
Description-md5: e7f99df3aa92cf870d335784e155ec33

Package: mocktester
Architecture: i386
Version: 1:1.2.3-4
Priority: optional
Section: test
Origin: Ubuntu
Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>
Original-Maintainer: Debian GNOME Maintainers <pkg-gnome-maintainers@lists.alioth.debian.org>
Bugs: https://bugs.launchpad.net/ubuntu/+filebug
Installed-Size: 1234
Depends: vim-common
Recommends: zsh
Suggests: foobar
Filename: pool/main/m/mocktester/mocktester_1:1.2.3-4_amd64.deb
Size: 65536
MD5sum: a87e414ad5aede7c820ce4c4e6bc7fa9
SHA1: b21d6ce47cb471c73fb4ec07a24c6f4e56fd19fc
SHA256: 89e7d5f61a0e3d32ef9aebd4b16e61840cd97e10196dfa186b06b6cde2f900a2
Homepage: https://wiki.gnome.org/Apps/MockTester
Description: Testing Package
Task: ubuntu-desktop
Description-md5: e7f99df3aa92cf870d335784e155ec33
"""

apt_cache_aisleriot = """
Package: aisleriot
Architecture: amd64
Version: 1:3.22.9-1
Priority: optional
Section: games
Origin: Ubuntu
Maintainer: Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>
Original-Maintainer: Debian GNOME Maintainers <pkg-gnome-maintainers@lists.alioth.debian.org>
Bugs: https://bugs.launchpad.net/ubuntu/+filebug
Installed-Size: 8800
Depends: dconf-gsettings-backend | gsettings-backend, guile-2.2-libs, libatk1.0-0 (>= 1.12.4), libc6 (>= 2.14), libcairo2 (>= 1.10.0), libcanberra-gtk3-0 (>= 0.25), libcanberra0 (>= 0.2), libgdk-pixbuf2.0-0 (>= 2.22.0), libglib2.0-0 (>= 2
.37.3), libgtk-3-0 (>= 3.19.12), librsvg2-2 (>= 2.32.0)
Recommends: yelp
Suggests: gnome-cards-data
Filename: pool/main/a/aisleriot/aisleriot_3.22.9-1_amd64.deb
Size: 843864
MD5sum: a87e414ad5aede7c820ce4c4e6bc7fa9
SHA1: b21d6ce47cb471c73fb4ec07a24c6f4e56fd19fc
SHA256: 89e7d5f61a0e3d32ef9aebd4b16e61840cd97e10196dfa186b06b6cde2f900a2
Homepage: https://wiki.gnome.org/Apps/Aisleriot
Description: GNOME solitaire card game collection
Task: ubuntu-desktop, ubuntukylin-desktop, ubuntu-budgie-desktop
Description-md5: e7f99df3aa92cf870d335784e155ec33
"""


class TestApt:
    @patch.object(apt, 'check_output')
    def test_can_load_from_dpkg(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = ['amd64', dpkg_output_vim]

        vim = apt.DebianPackage.from_installed_package('vim')
        assert vim.epoch == '2'
        assert vim.arch == 'amd64'
        assert vim.fullversion == '2:8.1.2269-1ubuntu5.amd64'
        assert str(vim.version) == '2:8.1.2269-1ubuntu5'

    @patch.object(apt, 'check_output')
    def test_can_load_from_dpkg_with_version(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = ['amd64', dpkg_output_zsh]

        zsh = apt.DebianPackage.from_installed_package('zsh', version='5.8-3ubuntu1')
        assert zsh.epoch == ''
        assert zsh.arch == 'amd64'
        assert zsh.fullversion == '5.8-3ubuntu1.amd64'
        assert str(zsh.version) == '5.8-3ubuntu1'

    @patch.object(apt, 'check_output')
    def test_will_not_load_from_system_with_bad_version(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = ['amd64', dpkg_output_zsh]

        with pytest.raises(apt.PackageNotFoundError):
            apt.DebianPackage.from_installed_package('zsh', version='1.2-3')

    @patch.object(apt, 'check_output')
    def test_can_load_from_dpkg_with_arch(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = ['amd64', dpkg_output_zsh]

        zsh = apt.DebianPackage.from_installed_package('zsh', arch='amd64')
        assert zsh.epoch == ''
        assert zsh.arch == 'amd64'
        assert zsh.fullversion == '5.8-3ubuntu1.amd64'
        assert str(zsh.version) == '5.8-3ubuntu1'

    @patch.object(apt, 'check_output')
    def test_can_load_from_dpkg_with_all_arch(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = ['amd64', dpkg_output_all_arch]

        postgresql = apt.DebianPackage.from_installed_package('postgresql')
        assert postgresql.epoch == ''
        assert postgresql.arch == 'all'
        assert postgresql.fullversion == '12+214ubuntu0.1.all'
        assert str(postgresql.version) == '12+214ubuntu0.1'

    @patch.object(apt, 'check_output')
    def test_can_load_from_dpkg_multi_arch(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = ['amd64', dpkg_output_multi_arch]

        vim = apt.DebianPackage.from_installed_package('vim', arch='i386')
        assert vim.epoch == '2'
        assert vim.arch == 'i386'
        assert vim.fullversion == '2:8.1.2269-1ubuntu5.i386'
        assert str(vim.version) == '2:8.1.2269-1ubuntu5'

    @patch.object(apt, 'check_output')
    def test_can_load_from_dpkg_not_installed(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = ['amd64', dpkg_output_not_installed]

        with pytest.raises(apt.PackageNotFoundError) as exc_info:
            apt.DebianPackage.from_installed_package('ubuntu-advantage-tools')

        assert exc_info.type == apt.PackageNotFoundError
        assert 'Package ubuntu-advantage-tools.amd64 is not installed!' in exc_info.value.message

    @patch.object(apt, 'check_output')
    def test_can_load_from_apt_cache(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = ['amd64', apt_cache_mocktester]

        tester = apt.DebianPackage.from_apt_cache('mocktester')
        assert tester.epoch == '1'
        assert tester.arch == 'amd64'
        assert tester.fullversion == '1:1.2.3-4.amd64'
        assert str(tester.version) == '1:1.2.3-4'

    @patch.object(apt, 'check_output')
    def test_can_load_from_apt_cache_all_arch(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = ['amd64', apt_cache_mocktester_all_arch]

        tester = apt.DebianPackage.from_apt_cache('mocktester')
        assert tester.epoch == '1'
        assert tester.arch == 'all'
        assert tester.fullversion == '1:1.2.3-4.all'
        assert str(tester.version) == '1:1.2.3-4'

    @patch.object(apt, 'check_output')
    def test_can_load_from_apt_cache_multi_arch(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = ['amd64', apt_cache_mocktester_multi]

        tester = apt.DebianPackage.from_apt_cache('mocktester', arch='i386')
        assert tester.epoch == '1'
        assert tester.arch == 'i386'
        assert tester.fullversion == '1:1.2.3-4.i386'
        assert str(tester.version) == '1:1.2.3-4'

    @patch.object(apt, 'check_output')
    def test_will_throw_apt_cache_errors(self, mock_subprocess: MagicMock):
        mock_subprocess.side_effect = [
            'amd64',
            subprocess.CalledProcessError(
                returncode=100,
                cmd=['apt-cache', 'show', 'mocktester'],
                stderr='N: Unable to locate package mocktester',
            ),
        ]

        with pytest.raises(apt.PackageError) as exc_info:
            apt.DebianPackage.from_apt_cache('mocktester', arch='i386')

        assert exc_info.type == apt.PackageError
        assert 'Could not list packages in apt-cache' in exc_info.value.message
        assert 'Unable to locate package' in exc_info.value.message

    @patch.object(apt, 'check_output')
    @patch.object(apt.subprocess, 'run')
    @patch('os.environ.copy')
    def test_can_run_apt_commands(
        self,
        mock_environ: MagicMock,
        mock_subprocess_call: MagicMock,
        mock_subprocess_output: MagicMock,
    ):
        mock_subprocess_call.return_value = 0
        mock_subprocess_output.side_effect = [
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['dpkg', '-l', 'mocktester']),
            'amd64',
            apt_cache_mocktester,
        ]
        mock_environ.return_value = {'PING': 'PONG'}

        pkg = apt.DebianPackage.from_system('mocktester')
        assert not pkg.present
        assert pkg.version.epoch == '1'
        assert pkg.version.number == '1.2.3-4'

        pkg.ensure(apt.PackageState.Latest)
        mock_subprocess_call.assert_called_with(
            [
                'apt-get',
                '-y',
                '--option=Dpkg::Options::=--force-confold',
                'install',
                'mocktester=1:1.2.3-4',
            ],
            capture_output=True,
            check=True,
            text=True,
            env={'DEBIAN_FRONTEND': 'noninteractive', 'PING': 'PONG'},
        )
        assert pkg.state == apt.PackageState.Latest

        pkg.state = apt.PackageState.Absent
        mock_subprocess_call.assert_called_with(
            ['apt-get', '-y', 'remove', 'mocktester=1:1.2.3-4'],
            capture_output=True,
            check=True,
            text=True,
            env={'DEBIAN_FRONTEND': 'noninteractive', 'PING': 'PONG'},
        )

    @patch.object(apt, 'check_output')
    @patch.object(apt.subprocess, 'run')
    def test_will_throw_apt_errors(
        self,
        mock_subprocess_call: MagicMock,
        mock_subprocess_output: MagicMock,
    ):
        mock_subprocess_call.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=['apt-get', '-y', 'install'],
            stderr='E: Unable to locate package mocktester',
        )
        mock_subprocess_output.side_effect = [
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['dpkg', '-l', 'mocktester']),
            'amd64',
            apt_cache_mocktester,
        ]

        pkg = apt.DebianPackage.from_system('mocktester')
        assert not pkg.present

        with pytest.raises(apt.PackageError) as exc_info:
            pkg.ensure(apt.PackageState.Latest)

        assert exc_info.type == apt.PackageError
        assert 'Could not install package' in exc_info.value.message
        assert 'Unable to locate package' in exc_info.value.message

    def test_can_compare_versions(self):
        old_version = apt.Version('1.0.0', '')
        old_dupe = apt.Version('1.0.0', '')
        new_version = apt.Version('1.0.1', '')
        new_epoch = apt.Version('1.0.1', '1')

        assert old_version == old_dupe
        assert new_version > old_version
        assert new_epoch > new_version
        assert old_version < new_version
        assert new_version <= new_epoch
        assert new_version >= old_version
        assert new_version != old_version

    def test_can_parse_epoch_and_version(self):
        assert apt.DebianPackage._get_epoch_from_version('1.0.0') == (None, '1.0.0')
        assert apt.DebianPackage._get_epoch_from_version('2:9.8-7ubuntu6') == ('2', '9.8-7ubuntu6')


class TestAptBareMethods:
    @patch.object(apt, 'check_output')
    @patch.object(apt.subprocess, 'run')
    @patch('os.environ.copy')
    def test_can_run_bare_changes_on_single_package(
        self,
        mock_environ: MagicMock,
        mock_subprocess: MagicMock,
        mock_subprocess_output: MagicMock,
    ):
        mock_subprocess.return_value = 0
        mock_subprocess_output.side_effect = [
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['dpkg', '-l', 'aisleriot']),
            'amd64',
            apt_cache_aisleriot,
        ]
        mock_environ.return_value = {}

        foo = apt.add_package('aisleriot')
        mock_subprocess.assert_called_with(
            [
                'apt-get',
                '-y',
                '--option=Dpkg::Options::=--force-confold',
                'install',
                'aisleriot=1:3.22.9-1',
            ],
            capture_output=True,
            check=True,
            text=True,
            env={'DEBIAN_FRONTEND': 'noninteractive'},
        )
        assert foo.present

        mock_subprocess_output.side_effect = ['amd64', dpkg_output_zsh]
        bar = apt.remove_package('zsh')
        bar.ensure(apt.PackageState.Absent)
        mock_subprocess.assert_called_with(
            ['apt-get', '-y', 'remove', 'zsh=5.8-3ubuntu1'],
            capture_output=True,
            check=True,
            text=True,
            env={'DEBIAN_FRONTEND': 'noninteractive'},
        )
        assert not bar.present

    @patch.object(apt, 'check_output')
    @patch.object(apt.subprocess, 'run')
    @patch('os.environ.copy')
    def test_can_run_bare_changes_on_multiple_packages(
        self,
        mock_environ: MagicMock,
        mock_subprocess: MagicMock,
        mock_subprocess_output: MagicMock,
    ):
        mock_subprocess.return_value = 0
        mock_subprocess_output.side_effect = [
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['dpkg', '-l', 'aisleriot']),
            'amd64',
            apt_cache_aisleriot,
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['dpkg', '-l', 'mocktester']),
            'amd64',
            apt_cache_mocktester,
        ]
        mock_environ.return_value = {}

        foo = apt.add_package(['aisleriot', 'mocktester'])
        assert isinstance(foo, list)
        mock_subprocess.assert_any_call(
            [
                'apt-get',
                '-y',
                '--option=Dpkg::Options::=--force-confold',
                'install',
                'aisleriot=1:3.22.9-1',
            ],
            capture_output=True,
            check=True,
            text=True,
            env={'DEBIAN_FRONTEND': 'noninteractive'},
        )
        mock_subprocess.assert_any_call(
            [
                'apt-get',
                '-y',
                '--option=Dpkg::Options::=--force-confold',
                'install',
                'mocktester=1:1.2.3-4',
            ],
            capture_output=True,
            check=True,
            text=True,
            env={'DEBIAN_FRONTEND': 'noninteractive'},
        )
        assert foo[0].present
        assert foo[1].present

        mock_subprocess_output.side_effect = ['amd64', dpkg_output_vim, 'amd64', dpkg_output_zsh]
        bar = apt.remove_package(['vim', 'zsh'])
        assert isinstance(bar, list)
        mock_subprocess.assert_any_call(
            ['apt-get', '-y', 'remove', 'vim=2:8.1.2269-1ubuntu5'],
            capture_output=True,
            check=True,
            text=True,
            env={'DEBIAN_FRONTEND': 'noninteractive'},
        )
        mock_subprocess.assert_any_call(
            ['apt-get', '-y', 'remove', 'zsh=5.8-3ubuntu1'],
            capture_output=True,
            check=True,
            text=True,
            env={'DEBIAN_FRONTEND': 'noninteractive'},
        )
        assert not bar[0].present
        assert not bar[1].present

    @patch.object(apt, 'check_output')
    @patch.object(apt.subprocess, 'run')
    def test_refreshes_apt_cache_if_not_found(
        self,
        mock_subprocess: MagicMock,
        mock_subprocess_output: MagicMock,
    ):
        mock_subprocess.return_value = 0
        mock_subprocess_output.side_effect = [
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['dpkg', '-l', 'nothere']),
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['apt-cache', 'show', 'nothere']),
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['dpkg', '-l', 'nothere']),
            'amd64',
            apt_cache_aisleriot,
        ]
        pkg = apt.add_package('aisleriot')
        mock_subprocess.assert_any_call(
            ['apt-get', 'update', '--error-on=any'], capture_output=True, check=True
        )
        assert pkg.name == 'aisleriot'
        assert pkg.present

    @patch.object(apt, 'check_output')
    @patch.object(apt.subprocess, 'run')
    def test_refreshes_apt_cache_before_apt_install(
        self,
        mock_subprocess: MagicMock,
        mock_subprocess_output: MagicMock,
    ):
        mock_subprocess.return_value = 0
        mock_subprocess_output.side_effect = [
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['dpkg', '-l', 'nothere']),
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['apt-cache', 'show', 'nothere']),
        ] * 2  # Double up for the retry before update
        with pytest.raises(apt.PackageError) as exc_info:
            apt.add_package('nothere', update_cache=True)
        mock_subprocess.assert_any_call(
            ['apt-get', 'update', '--error-on=any'], capture_output=True, check=True
        )
        assert exc_info.type == apt.PackageError
        assert 'Failed to install packages: nothere' in exc_info.value.message

    @patch.object(apt, 'check_output')
    @patch.object(apt.subprocess, 'run')
    def test_raises_package_not_found_error(
        self,
        mock_subprocess: MagicMock,
        mock_subprocess_output: MagicMock,
    ):
        mock_subprocess.return_value = 0
        mock_subprocess_output.side_effect = [
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['dpkg', '-l', 'nothere']),
            'amd64',
            subprocess.CalledProcessError(returncode=100, cmd=['apt-cache', 'show', 'nothere']),
        ] * 2  # Double up for the retry after update
        with pytest.raises(apt.PackageError) as exc_info:
            apt.add_package('nothere')
        mock_subprocess.assert_any_call(
            ['apt-get', 'update', '--error-on=any'], capture_output=True, check=True
        )
        assert exc_info.type == apt.PackageError
        assert 'Failed to install packages: nothere' in exc_info.value.message

    @patch.object(apt, 'check_output')
    @patch.object(apt.subprocess, 'run')
    def test_remove_package_not_installed(
        self,
        mock_subprocess: MagicMock,
        mock_subprocess_output: MagicMock,
    ):
        mock_subprocess_output.side_effect = ['amd64', dpkg_output_not_installed]

        packages = apt.remove_package('ubuntu-advantage-tools')
        mock_subprocess.assert_not_called()
        assert packages == []
