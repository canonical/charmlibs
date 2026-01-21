# Copyright 2026 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from charmlibs import passwd


@patch('charmlibs.passwd._passwd.pwd.getpwnam')
def test_user_exists(getpwnam_mock: MagicMock) -> None:
    mock_passwd = SimpleNamespace(pw_name='bob')
    getpwnam_mock.return_value = mock_passwd
    assert passwd.user_exists('bob') == mock_passwd


@patch('charmlibs.passwd._passwd.pwd.getpwuid')
def test_user_exists_by_uid_true(getpwuid_mock: MagicMock) -> None:
    mock_passwd = SimpleNamespace(pw_name='bob')
    getpwuid_mock.return_value = mock_passwd
    assert passwd.user_exists(1000) == mock_passwd


def test_user_exists_invalid_input() -> None:
    with pytest.raises(TypeError):
        passwd.user_exists(True)


@patch('charmlibs.passwd._passwd.pwd.getpwnam')
def test_user_exists_false(getpwnam_mock: MagicMock) -> None:
    getpwnam_mock.side_effect = KeyError('user not found')
    assert passwd.user_exists('alice') is None


@patch('charmlibs.passwd._passwd.grp.getgrnam')
def test_group_exists_true(getgrnam_mock: MagicMock) -> None:
    mock_group = SimpleNamespace(gr_name='testgroup')
    getgrnam_mock.return_value = mock_group
    assert passwd.group_exists('testgroup') == mock_group


@patch('charmlibs.passwd._passwd.grp.getgrgid')
def test_group_exists_by_gid_true(getgrgid_mock: MagicMock) -> None:
    mock_group = SimpleNamespace(gr_name='testgroup')
    getgrgid_mock.return_value = mock_group
    assert passwd.group_exists(1000) == mock_group


def test_group_exists_invalid_input() -> None:
    with pytest.raises(TypeError):
        passwd.group_exists(True)


@patch('charmlibs.passwd._passwd.grp.getgrnam')
def test_group_exists_false(getgrnam_mock: MagicMock) -> None:
    getgrnam_mock.side_effect = KeyError('group not found')
    assert passwd.group_exists('testgroup') is None


@patch('charmlibs.passwd._passwd.grp.getgrnam')
@patch('charmlibs.passwd._passwd.pwd.getpwnam')
@patch('charmlibs.passwd._passwd.check_output')
def test_adds_a_user_if_it_doesnt_exist(
    check_output_mock: MagicMock, getpwnam_mock: MagicMock, getgrnam_mock: MagicMock
) -> None:
    username = 'johndoe'
    password = 'eodnhoj'
    shell = '/bin/bash'
    existing_user_pwnam = KeyError('user not found')
    new_user_pwnam = SimpleNamespace(pw_name=username)

    getpwnam_mock.side_effect = [existing_user_pwnam, new_user_pwnam]

    result = passwd.add_user(username, password=password)

    assert result == new_user_pwnam
    check_output_mock.assert_called_with(
        [
            'useradd',
            '--shell',
            shell,
            '--password',
            password,
            '--create-home',
            '-g',
            username,
            username,
        ],
        stderr=-2,
    )
    getpwnam_mock.assert_called_with(username)


@patch('charmlibs.passwd._passwd.pwd.getpwnam')
@patch('charmlibs.passwd._passwd.check_output')
def test_doesnt_add_user_if_it_already_exists(
    check_output_mock: MagicMock, getpwnam_mock: MagicMock
) -> None:
    username = 'johndoe'
    password = 'eodnhoj'
    existing_user_pwnam = SimpleNamespace(pw_name=username)

    getpwnam_mock.return_value = existing_user_pwnam

    result = passwd.add_user(username, password=password)

    assert result == existing_user_pwnam
    check_output_mock.assert_not_called()
    getpwnam_mock.assert_called_with(username)


@patch('charmlibs.passwd._passwd.grp.getgrnam')
@patch('charmlibs.passwd._passwd.pwd.getpwnam')
@patch('charmlibs.passwd._passwd.check_output')
def test_adds_a_user_with_different_shell(
    check_output_mock: MagicMock, getpwnam_mock: MagicMock, getgrnam_mock: MagicMock
) -> None:
    username = 'johndoe'
    password = 'eodnhoj'
    shell = '/bin/zsh'
    existing_user_pwnam = KeyError('user not found')
    new_user_pwnam = SimpleNamespace(pw_name=username)

    getpwnam_mock.side_effect = [existing_user_pwnam, new_user_pwnam]
    getgrnam_mock.side_effect = KeyError('group not found')

    result = passwd.add_user(username, password=password, shell=shell)

    assert result == new_user_pwnam
    check_output_mock.assert_called_with(
        ['useradd', '--shell', shell, '--password', password, '--create-home', username],
        stderr=-2,
    )
    getpwnam_mock.assert_called_with(username)


@patch('charmlibs.passwd._passwd.grp.getgrnam')
@patch('charmlibs.passwd._passwd.pwd.getpwnam')
@patch('charmlibs.passwd._passwd.check_output')
def test_add_user_with_groups(
    check_output_mock: MagicMock, getpwnam_mock: MagicMock, getgrnam_mock: MagicMock
) -> None:
    username = 'johndoe'
    password = 'eodnhoj'
    shell = '/bin/bash'
    existing_user_pwnam = KeyError('user not found')
    new_user_pwnam = SimpleNamespace(pw_name=username)

    getpwnam_mock.side_effect = [existing_user_pwnam, new_user_pwnam]

    result = passwd.add_user(
        username,
        password=password,
        primary_group='foo',
        secondary_groups=[
            'bar',
            'qux',
        ],
    )

    assert result == new_user_pwnam
    check_output_mock.assert_called_with(
        [
            'useradd',
            '--shell',
            shell,
            '--password',
            password,
            '--create-home',
            '-g',
            'foo',
            '-G',
            'bar,qux',
            username,
        ],
        stderr=-2,
    )
    getpwnam_mock.assert_called_with(username)
    assert getgrnam_mock.call_count == 0


@patch('charmlibs.passwd._passwd.pwd.getpwnam')
@patch('charmlibs.passwd._passwd.check_output')
def test_adds_a_systemuser(check_output_mock: MagicMock, getpwnam_mock: MagicMock) -> None:
    username = 'johndoe'
    shell = '/bin/bash'
    existing_user_pwnam = KeyError('user not found')
    new_user_pwnam = SimpleNamespace(pw_name=username)

    getpwnam_mock.side_effect = [existing_user_pwnam, new_user_pwnam]

    result = passwd.add_user(username, system_user=True)

    assert result == new_user_pwnam
    check_output_mock.assert_called_with(
        ['useradd', '--shell', shell, '--create-home', '--system', username],
        stderr=-2,
    )
    getpwnam_mock.assert_called_with(username)


@patch('charmlibs.passwd._passwd.pwd.getpwnam')
@patch('charmlibs.passwd._passwd.check_output')
def test_adds_a_systemuser_with_home_dir(
    check_output_mock: MagicMock, getpwnam_mock: MagicMock
) -> None:
    username = 'johndoe'
    shell = '/bin/bash'
    home_dir = '/var/lib/johndoe'
    existing_user_pwnam = KeyError('user not found')
    new_user_pwnam = SimpleNamespace(pw_name=username)

    getpwnam_mock.side_effect = [existing_user_pwnam, new_user_pwnam]

    result = passwd.add_user(username, system_user=True, home_dir=home_dir)

    assert result == new_user_pwnam
    check_output_mock.assert_called_with(
        ['useradd', '--shell', shell, '--home', home_dir, '--create-home', '--system', username],
        stderr=-2,
    )
    getpwnam_mock.assert_called_with(username)


@patch('charmlibs.passwd._passwd.pwd.getpwnam')
@patch('charmlibs.passwd._passwd.pwd.getpwuid')
@patch('charmlibs.passwd._passwd.grp.getgrnam')
@patch('charmlibs.passwd._passwd.check_output')
def test_add_user_uid(
    check_output_mock: MagicMock,
    getgrnam_mock: MagicMock,
    getpwuid_mock: MagicMock,
    getpwnam_mock: MagicMock,
) -> None:
    username = 'johndoe'
    user_id = 1111
    shell = '/bin/bash'
    uuid_key_error = KeyError('user not found')
    getpwuid_mock.side_effect = [uuid_key_error, uuid_key_error]
    passwd.add_user(username, uid=user_id)

    check_output_mock.assert_called_with(
        [
            'useradd',
            '--shell',
            shell,
            '--uid',
            str(user_id),
            '--create-home',
            '--system',
            '-g',
            username,
            username,
        ],
        stderr=-2,
    )

    getpwnam_mock.assert_called_with(username)
    getpwuid_mock.assert_called_with(user_id)


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.user_exists')
def test_remove_user_that_does_not_exist(
    user_exists_mock: MagicMock, check_output_mock: MagicMock
) -> None:
    user_exists_mock.return_value = None
    result = passwd.remove_user('bob')

    assert result is True
    check_output_mock.assert_not_called()


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.user_exists')
def test_remove_user_that_exists(
    user_exists_mock: MagicMock, check_output_mock: MagicMock
) -> None:
    username = 'bob'
    user_exists_mock.return_value = SimpleNamespace(pw_name=username)
    result = passwd.remove_user(username)

    assert result is True
    check_output_mock.assert_called_with(['userdel', username], stderr=-2)


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.user_exists')
def test_remove_user_that_exists_remove_homedir(
    user_exists_mock: MagicMock, check_output_mock: MagicMock
) -> None:
    username = 'bob'
    user_exists_mock.return_value = SimpleNamespace(pw_name=username)
    result = passwd.remove_user(username, remove_home=True)

    assert result is True
    check_output_mock.assert_called_with(['userdel', '-f', username], stderr=-2)


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.grp.getgrnam')
def test_add_a_group_if_it_doesnt_exist(
    getgrnam_mock: MagicMock, check_output_mock: MagicMock
) -> None:
    groupname = 'testgroup'
    new_group = SimpleNamespace(gr_name=groupname)

    getgrnam_mock.side_effect = [KeyError('group not found'), new_group]

    result = passwd.add_group(groupname)

    assert result == new_group
    check_output_mock.assert_called_with(['addgroup', '--group', groupname], stderr=-2)


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.grp.getgrnam')
def test_doesnt_add_group_if_it_already_exists(
    getgrnam_mock: MagicMock, check_output_mock: MagicMock
) -> None:
    groupname = 'testgroup'
    existing_group = SimpleNamespace(gr_name=groupname)

    getgrnam_mock.return_value = existing_group

    result = passwd.add_group(groupname)

    assert result == existing_group
    check_output_mock.assert_not_called()


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.grp.getgrnam')
def test_add_a_system_group(getgrnam_mock: MagicMock, check_output_mock: MagicMock) -> None:
    groupname = 'testgroup'
    new_group = SimpleNamespace(gr_name=groupname)

    getgrnam_mock.side_effect = [KeyError('group not found'), new_group]

    result = passwd.add_group(groupname, system_group=True)

    assert result == new_group
    check_output_mock.assert_called_with(['addgroup', '--system', groupname], stderr=-2)


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.grp.getgrgid')
@patch('charmlibs.passwd._passwd.grp.getgrnam')
def test_add_group_gid(
    getgrnam_mock: MagicMock, getgrgid_mock: MagicMock, check_output_mock: MagicMock
) -> None:
    groupname = 'testgroup'
    group_id = 1111
    new_group = SimpleNamespace(gr_name=groupname)

    getgrnam_mock.side_effect = [KeyError('group not found'), new_group]

    result = passwd.add_group(groupname, gid=group_id)

    assert result == new_group
    check_output_mock.assert_called_with(
        ['addgroup', '--gid', str(group_id), '--group', groupname], stderr=-2
    )


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.grp.getgrnam')
@patch('charmlibs.passwd._passwd.group_exists')
@patch('charmlibs.passwd._passwd.user_exists')
def test_adds_a_user_to_a_group(
    user_exists_mock: MagicMock,
    group_exists_mock: MagicMock,
    getgrnam_mock: MagicMock,
    check_output_mock: MagicMock,
) -> None:
    username = 'bob'
    groupname = 'testgroup'
    mock_group = SimpleNamespace(gr_name=groupname)

    user_exists_mock.return_value = True
    group_exists_mock.return_value = True
    getgrnam_mock.return_value = mock_group

    result = passwd.add_user_to_group(username, groupname)

    assert result == mock_group
    check_output_mock.assert_called_with(['gpasswd', '-a', username, groupname], stderr=-2)


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.group_exists')
@patch('charmlibs.passwd._passwd.user_exists')
def test_adds_a_user_to_a_group_user_missing(
    user_exists_mock: MagicMock, group_exists_mock: MagicMock, check_output_mock: MagicMock
) -> None:
    username = 'bob'
    groupname = 'testgroup'

    user_exists_mock.return_value = None
    group_exists_mock.return_value = True

    with pytest.raises(ValueError, match=f"user '{username}' does not exist"):
        passwd.add_user_to_group(username, groupname)

    check_output_mock.assert_not_called()


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.group_exists')
@patch('charmlibs.passwd._passwd.user_exists')
def test_adds_a_user_to_a_group_group_missing(
    user_exists_mock: MagicMock, group_exists_mock: MagicMock, check_output_mock: MagicMock
) -> None:
    username = 'bob'
    groupname = 'testgroup'

    user_exists_mock.return_value = True
    group_exists_mock.return_value = None

    with pytest.raises(ValueError, match=f"group '{groupname}' does not exist"):
        passwd.add_user_to_group(username, groupname)

    check_output_mock.assert_not_called()


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.group_exists')
def test_remove_group_that_does_not_exist(
    group_exists_mock: MagicMock, check_output_mock: MagicMock
) -> None:
    group_exists_mock.return_value = None
    result = passwd.remove_group('testgroup')

    assert result is True
    check_output_mock.assert_not_called()


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.group_exists')
def test_remove_group_that_exists(
    group_exists_mock: MagicMock, check_output_mock: MagicMock
) -> None:
    groupname = 'testgroup'
    group_exists_mock.return_value = SimpleNamespace(gr_name=groupname)
    result = passwd.remove_group(groupname)

    assert result is True
    check_output_mock.assert_called_with(['groupdel', groupname], stderr=-2)


@patch('charmlibs.passwd._passwd.check_output')
@patch('charmlibs.passwd._passwd.group_exists')
def test_remove_group_that_exists_force(
    group_exists_mock: MagicMock, check_output_mock: MagicMock
) -> None:
    groupname = 'testgroup'
    group_exists_mock.return_value = SimpleNamespace(gr_name=groupname)
    result = passwd.remove_group(groupname, force=True)

    assert result is True
    check_output_mock.assert_called_with(['groupdel', '-f', groupname], stderr=-2)
