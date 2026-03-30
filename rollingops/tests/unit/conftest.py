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

"""Fixtures for unit tests, typically mocking out parts of the external system."""

import types
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import ops
import pytest
from ops.testing import Context

import charmlibs.rollingops._certificates as certificates
import charmlibs.rollingops._etcdctl as etcdctl
from charmlibs import rollingops
from charmlibs.pathops import LocalPath
from charmlibs.rollingops._models import SharedCertificate


@pytest.fixture
def temp_certificates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    base_dir = LocalPath(str(tmp_path)) / 'tls'
    ca_cert = base_dir / 'client-ca.pem'
    client_key = base_dir / 'client.key'
    client_cert = base_dir / 'client.pem'

    monkeypatch.setattr(certificates, 'BASE_DIR', base_dir)
    monkeypatch.setattr(certificates, 'CA_CERT_PATH', ca_cert)
    monkeypatch.setattr(certificates, 'CLIENT_KEY_PATH', client_key)
    monkeypatch.setattr(certificates, 'CLIENT_CERT_PATH', client_cert)

    base_dir.mkdir(parents=True, exist_ok=True)
    return certificates


@pytest.fixture
def temp_etcdctl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    base_dir = LocalPath(str(tmp_path)) / 'etcd'
    server_ca = base_dir / 'server-ca.pem'
    env_file = base_dir / 'etcdctl.json'

    monkeypatch.setattr(etcdctl, 'BASE_DIR', base_dir)
    monkeypatch.setattr(etcdctl, 'SERVER_CA_PATH', server_ca)
    monkeypatch.setattr(etcdctl, 'CONFIG_FILE_PATH', env_file)

    base_dir.mkdir(parents=True, exist_ok=True)
    return etcdctl


@pytest.fixture
def etcdctl_patch() -> Generator[MagicMock, None, None]:
    with patch('charmlibs.rollingops._certificates') as mock_etcdctl:
        yield mock_etcdctl


@pytest.fixture
def certificates_manager_patches() -> Generator[dict[str, MagicMock], None, None]:
    with (
        patch(
            'charmlibs.rollingops._certificates._exists',
            return_value=False,
        ),
        patch(
            'charmlibs.rollingops._certificates.generate',
            return_value=SharedCertificate('CERT_PEM', 'KEY_PEM', 'CA_PEM'),
        ) as mock_generate,
        patch(
            'charmlibs.rollingops._certificates.persist_client_cert_key_and_ca',
            return_value=None,
        ) as mock_persit,
    ):
        yield {
            'generate': mock_generate,
            'persist': mock_persit,
        }


class RollingOpsCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)

        callback_targets = {
            '_restart': self.restart,
        }

        self.restart_manager = rollingops.EtcdRollingOpsManager(
            charm=self,
            peer_relation_name='restart',
            etcd_relation_name='etcd',
            cluster_id='cluster-12345',
            callback_targets=callback_targets,
        )

    def restart(self) -> None:
        pass


@pytest.fixture
def charm_test() -> type[RollingOpsCharm]:
    return RollingOpsCharm


meta: dict[str, Any] = {
    'name': 'charm',
    'peers': {
        'restart': {
            'interface': 'rolling_op',
        },
    },
    'requires': {
        'etcd': {
            'interface': 'etcd_client',
        },
    },
}


@pytest.fixture
def ctx(charm_test: type[RollingOpsCharm]) -> Context[RollingOpsCharm]:
    return Context(charm_test, meta=meta)
