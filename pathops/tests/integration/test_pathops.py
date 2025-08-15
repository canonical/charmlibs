# Copyright 2025 Canonical Ltd.
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

"""Integration tests using a real Juju and charm to test ContainerPath."""

from __future__ import annotations

import ast

import jubilant
import pytest


def test_deploy(juju: jubilant.Juju, charm: str):
    """The deployment takes place in the module scoped `juju` fixture."""
    assert charm in juju.status().apps


def test_ensure_contents(juju: jubilant.Juju, charm: str):
    contents = 'Hello world!'
    result = juju.run(
        f'{charm}/0', 'ensure-contents', params={'path': 'file.txt', 'contents': contents}
    )
    assert result.results['contents'] == contents


def test_iterdir(juju: jubilant.Juju, charm: str):
    n = 2
    result = juju.run(f'{charm}/0', 'iterdir', params={'n-temp-files': n})
    files = ast.literal_eval(result.results['files'])
    assert len(files) == n


@pytest.mark.parametrize(
    ('user', 'group'),
    (
        (None, None),
        ('root', None),
        ('temp-user', None),
        (None, 'root'),
        (None, 'temp-user'),
        ('root', 'root'),
        ('root', 'temp-user'),
        ('temp-user', 'root'),
        ('temp-user', 'temp-user'),
    ),
)
@pytest.mark.parametrize('method', ['mkdir', 'write_bytes', 'write_text'])
@pytest.mark.parametrize('already_exists', [True, False])
def test_chown(
    juju: jubilant.Juju,
    charm: str,
    method: str,
    user: str | None,
    group: str | None,
    already_exists: bool,
):
    params = {
        'method': method,
        'user': user or '',
        'group': group or '',
        'already-exists': already_exists,
    }
    try:
        result = juju.run(f'{charm}/0', 'chown', params=params)
    except jubilant.TaskError as e:
        print(e)
        print(e.task.message)
        if (
            charm == 'kubernetes'
            and user is None
            and group is not None
            and (method == 'mkdir' or not already_exists)
        ):
            # we expect the group-only case to fail (unless Pebble is updated to handle it)
            # although if the file already exists and the method is write_{bytes,text} then
            # it succeeds because we look up the user to avoid clobbering the file ownership
            prefix = 'Exception: '
            assert e.task.message.startswith(prefix)
            msg = e.task.message[len(prefix) :]
            assert msg.startswith('LookupError')
            return
        raise
    user_result = result.results['user']
    group_result = result.results['group']
    if already_exists:
        if method == 'mkdir':
            expected_user = 'temp-user'
            expected_group = 'temp-user'
            assert (user_result, group_result) == (expected_user, expected_group)
        else:  # write_{bytes,text}
            expected_user = user if user is not None else 'temp-user'
            expected_group = group if group is not None else expected_user
            assert (user_result, group_result) == (expected_user, expected_group)
    else:  # not already_exists
        expected_user = user if user is not None else 'root'
        expected_group = group if group is not None else expected_user
        assert (result.results['user'], result.results['group']) == (expected_user, expected_group)
