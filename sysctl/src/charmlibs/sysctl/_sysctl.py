# Copyright 2023 Canonical Ltd.
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

"""Source code of operator_libs_linux.v0.sysctl.

Snapshot of version 0.4. Charmhub-hosted lib specific metadata has been removed, and the docstring
has been moved to the package docstring.
"""

import logging
import re
from pathlib import Path
from subprocess import STDOUT, CalledProcessError, check_output

from ._version import __version__

logger = logging.getLogger(__name__)

CHARM_FILENAME_PREFIX = '90-juju-'
SYSCTL_DIRECTORY = Path('/etc/sysctl.d')
SYSCTL_FILENAME = SYSCTL_DIRECTORY / '95-juju-sysctl.conf'
SYSCTL_HEADER = f"""# This config file was produced by sysctl lib v{__version__}
#
# This file represents the output of the sysctl lib, which can combine multiple
# configurations into a single file like.
"""


class Error(Exception):
    """Base class of most errors raised by this library."""

    @property
    def message(self):
        """Return the message passed as an argument."""
        return self.args[0]


class CommandError(Error):
    """Raised when there's an error running sysctl command."""


class ApplyError(Error):
    """Raised when there's an error applying values in sysctl."""


class ValidationError(Error):
    """Exception representing value validation error."""


class Config(dict[str, str]):
    """Represents the state of the config that a charm wants to enforce."""

    _apply_re = re.compile(r'sysctl: permission denied on key \"([a-z_\.]+)\", ignoring$')

    def __init__(self, name: str) -> None:
        self.name = name
        self._data = self._load_data()

    def __contains__(self, key: object) -> bool:
        """Check if key is in config."""
        return key in self._data

    def __len__(self):
        """Get size of config."""
        return len(self._data)

    def __iter__(self):
        """Iterate over config."""
        return iter(self._data)

    def __getitem__(self, key: str) -> str:
        """Get value for key form config."""
        return self._data[key]

    @property
    def charm_filepath(self) -> Path:
        """Name for resulting charm config file."""
        return SYSCTL_DIRECTORY / f'{CHARM_FILENAME_PREFIX}{self.name}'

    def configure(self, config: dict[str, str]) -> None:
        """Configure sysctl options with a desired set of params.

        Args:
            config: dictionary with keys to configure: ``{"vm.swappiness": "10", ...}``
        """
        self._parse_config(config)

        # NOTE: case where own charm calls configure() more than once.
        if self.charm_filepath.exists():
            self._merge(add_own_charm=False)

        conflict = self._validate()
        if conflict:
            raise ValidationError(f'Validation error for keys: {conflict}')

        snapshot = self._create_snapshot()
        logger.debug('Created snapshot for keys: %s', snapshot)
        try:
            self._apply()
        except ApplyError:
            self._restore_snapshot(snapshot)
            raise

        self._create_charm_file()
        self._merge()

    def remove(self) -> None:
        """Remove config for charm.

        The removal process won't apply any sysctl configuration. It will only merge files from
        remaining charms.
        """
        self.charm_filepath.unlink(missing_ok=True)
        logger.info('Charm config file %s was removed', self.charm_filepath)
        self._merge()

    def _validate(self) -> list[str]:
        """Validate the desired config params against merged ones."""
        common_keys = set(self._data.keys()) & set(self._desired_config.keys())
        conflict_keys: list[str] = []
        for key in common_keys:
            if self._data[key] != self._desired_config[key]:
                logger.warning(
                    "Values for key '%s' are different: %s != %s",
                    key,
                    self._data[key],
                    self._desired_config[key],
                )
                conflict_keys.append(key)

        return conflict_keys

    def _create_charm_file(self) -> None:
        """Write the charm file."""
        with open(self.charm_filepath, 'w') as f:
            f.write(f'# {self.name}\n')
            for key, value in self._desired_config.items():
                f.write(f'{key}={value}\n')

    def _merge(self, add_own_charm: bool = True) -> None:
        """Create the merged sysctl file.

        Args:
            add_own_charm : bool, if false it will skip the charm file from the merge.
        """
        # get all files that start by 90-juju-
        data = [SYSCTL_HEADER]
        paths = set(SYSCTL_DIRECTORY.glob(f'{CHARM_FILENAME_PREFIX}*'))
        if not add_own_charm:
            paths.discard(self.charm_filepath)

        for path in paths:
            with open(path) as f:
                data += f.readlines()
        with open(SYSCTL_FILENAME, 'w') as f:
            f.writelines(data)

        # Reload data with newly created file.
        self._data = self._load_data()

    def _apply(self) -> None:
        """Apply values to machine."""
        cmd = [f'{key}={value}' for key, value in self._desired_config.items()]
        result = self._sysctl(cmd)
        failed_values = [m for line in result if (m := self._apply_re.match(line))]
        logger.debug('Failed values: %s', failed_values)

        if failed_values:
            msg = f'Unable to set params: {[f.group(1) for f in failed_values]}'
            logger.error(msg)
            raise ApplyError(msg)

    def _create_snapshot(self) -> dict[str, str]:
        """Create a snapshot of config options that are going to be set."""
        cmd = ['-n', *list(self._desired_config.keys())]
        values = self._sysctl(cmd)
        return dict(zip(list(self._desired_config.keys()), values, strict=False))

    def _restore_snapshot(self, snapshot: dict[str, str]) -> None:
        """Restore a snapshot to the machine."""
        values = [f'{key}={value}' for key, value in snapshot.items()]
        self._sysctl(values)

    def _sysctl(self, cmd: list[str]) -> list[str]:
        """Execute a sysctl command."""
        cmd = ['sysctl', *cmd]
        logger.debug('Executing sysctl command: %s', cmd)
        try:
            return check_output(cmd, stderr=STDOUT, universal_newlines=True).splitlines()
        except CalledProcessError as e:
            msg = f"Error executing '{cmd}': {e.stdout}"
            logger.error(msg)
            raise CommandError(msg) from e

    def _parse_config(self, config: dict[str, str]) -> None:
        """Parse a config passed to the lib."""
        self._desired_config = {k: str(v) for k, v in config.items()}

    def _load_data(self) -> dict[str, str]:
        """Get merged config."""
        config: dict[str, str] = {}
        if not SYSCTL_FILENAME.exists():
            return config

        with open(SYSCTL_FILENAME) as f:
            for line in f:
                if line.startswith(('#', ';')) or not line.strip() or '=' not in line:
                    continue

                key, _, value = line.partition('=')
                config[key.strip()] = value.strip()

        return config
