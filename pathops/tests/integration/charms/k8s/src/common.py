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

"""Common code for the kubernetes and machine test charms.

The contents of kubernetes/src/common.py and machine/src/common.py should be identical.
"""

from __future__ import annotations

import logging
import traceback
import typing

import ops

# TODO: switch to recommended form `from charmlibs import pathops`
#       after next pyright release fixes:
#       https://github.com/microsoft/pyright/issues/10203
import charmlibs.pathops as pathops

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class Charm(ops.CharmBase):
    """Substrate agnostic charm base class.

    Subclasses must provide the following substrate aware attributes/methods:
        - root
        - remove_path
        - exec
    """

    root: pathops.PathProtocol

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        framework.observe(self.on['ensure-contents'].action, self._on_ensure_contents)
        framework.observe(self.on['iterdir'].action, self._on_iterdir)
        framework.observe(self.on['chown'].action, self._on_chown)

    def exec(self, cmd: Sequence[str]) -> int:
        """Run a command and return the exit code."""
        raise NotImplementedError()

    def _on_ensure_contents(self, event: ops.ActionEvent) -> None:
        path = self.root / typing.cast('str', event.params['path'])
        pathops.ensure_contents(path=path, source=event.params['contents'])
        contents = path.read_text()
        path.unlink()
        event.set_results({'contents': contents})

    def _on_iterdir(self, event: ops.ActionEvent) -> None:
        n: int = event.params['n-temp-files']
        path = self.root / 'unique-temp-dir-name'
        if path.exists():
            event.fail("Couldn't create a unique temporary directory.")
            return
        path.mkdir()
        for i in range(n):
            (path / str(i)).write_bytes(b'')
        result = [str(p) for p in path.iterdir()]
        for p in path.iterdir():
            p.unlink()
        path.rmdir()
        event.set_results({'files': str(result)})

    def _on_chown(self, event: ops.ActionEvent) -> None:
        path = self.root / 'unique-temp-name'
        if path.exists():
            event.fail('File already exists.')
            return
        temp_user = 'temp-user'
        try:
            method: str = event.params['method']
            user: str | None = event.params['user'] or None
            group: str | None = event.params['group'] or None
            already_exists: bool = event.params['already-exists']
            self.add_user(temp_user)
            if already_exists:
                if method == 'mkdir':
                    path.mkdir(user=temp_user)
                else:
                    path.write_bytes(b'', user=temp_user, mode=0o777)
                assert path.owner() == temp_user
                assert path.owner() == temp_user
            if method == 'mkdir':
                path.mkdir(user=user, group=group, exist_ok=True)
            elif method == 'write_bytes':
                path.write_bytes(b'', user=user, group=group)
            elif method == 'write_text':
                path.write_text('', user=user, group=group)
            else:
                raise ValueError(f'Unknown method: {method!r}')
            event.set_results({'user': path.owner(), 'group': path.group()})
        except Exception as e:
            tb = traceback.format_exc()
            msg = f'Exception: {e!r}\n{tb}'
            event.fail(msg)
        finally:
            if path.is_dir() and not path.is_symlink():
                path.rmdir()
            elif path.exists():
                path.unlink()
            self.remove_user(temp_user)

    def add_user(self, user: str) -> None:
        retcode = self.exec(['useradd', user])
        assert retcode in (
            0,  # success
            9,  # already exists
        )

    def remove_user(self, user: str) -> None:
        retcode = self.exec(['userdel', '--remove', user])
        assert retcode in (
            0,  # success
            6,  # doesn't exist
        )
