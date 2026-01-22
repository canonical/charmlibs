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

"""Functional tests for the `passwd` charm library."""

from charmlibs import passwd


def test_add_remove_user() -> None:
    """Verify we can add and remove a user."""
    assert passwd.add_user(username='bob')
    assert passwd.remove_user(user='bob')


def test_add_remove_group() -> None:
    """Verify we can add and remove a group."""
    assert passwd.add_group(group_name='testgroup')
    assert passwd.remove_group(group='testgroup')


def test_user_exists() -> None:
    """Verify we can check for user existence."""
    passwd.add_user(username='bob')
    assert passwd.user_exists(user='bob') is not None
    passwd.remove_user(user='bob')


def test_group_exists() -> None:
    """Verify we can check for group existence."""
    passwd.add_group(group_name='testgroup')
    assert passwd.group_exists(group='testgroup') is not None
    passwd.remove_group(group='testgroup')


def test_add_user_to_group() -> None:
    """Verify we can add a user to a group."""
    passwd.add_group(group_name='testgroup')
    passwd.add_user(username='bob')
    assert passwd.add_user_to_group(username='bob', group='testgroup')
    passwd.remove_user(user='bob')
    passwd.remove_group(group='testgroup')


def test_add_user_to_nonexistent_group() -> None:
    """Verify adding a user to a non-existent group raises ValueError."""
    passwd.add_user(username='bob')
    try:
        passwd.add_user_to_group(username='bob', group='nonexistentgroup')
    except ValueError as e:
        assert str(e) == "group 'nonexistentgroup' does not exist"
    finally:
        passwd.remove_user(user='bob')


def test_remove_nonexistent_group() -> None:
    """Verify removing a non-existent group returns True."""
    assert passwd.remove_group(group='nonexistentgroup') is True


def test_remove_nonexistent_user() -> None:
    """Verify removing a non-existent user returns True."""
    assert passwd.remove_user(user='nonexistentuser') is True


def test_add_user_with_shell() -> None:
    """Verify we can add a user with a specific shell."""
    assert passwd.add_user(username='bob', shell='/bin/sh')  # noqa: S604
    user_info = passwd.user_exists(user='bob')
    assert user_info is not None
    assert user_info.pw_shell == '/bin/sh'
    assert passwd.remove_user(user='bob')


def test_user_not_exists() -> None:
    """Verify user_exists returns None for non-existent user."""
    assert passwd.user_exists(user='nonexistentuser') is None


def test_group_not_exists() -> None:
    """Verify group_exists returns None for non-existent group."""
    assert passwd.group_exists(group='nonexistentgroup') is None


def test_user_exist_by_uid() -> None:
    """Verify we can check for user existence by uid."""
    user = passwd.add_user(username='bob')
    assert passwd.user_exists(user=user.pw_uid) is not None
    passwd.remove_user(user='bob')
