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
from ops import ActionEvent
from ops.testing import Context

import charmlibs.rollingops._certificates as certificates
import charmlibs.rollingops._etcdctl as etcdctl
from charmlibs import rollingops
from charmlibs.pathops import LocalPath
from charmlibs.rollingops._models import SharedCertificate
from charmlibs.rollingops.peer_manager import PeerRollingOpsManager
from charmlibs.rollingops.peer_models import OperationResult


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


class PeerRollingOpsCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)

        callback_targets = {
            '_restart': self._restart,
            '_failed_restart': self._failed_restart,
            '_deferred_restart': self._deferred_restart,
        }

        self.restart_manager = PeerRollingOpsManager(
            charm=self,
            relation_name='restart',
            callback_targets=callback_targets,
        )
        self.framework.observe(self.on.restart_action, self._on_restart_action)
        self.framework.observe(self.on.failed_restart_action, self._on_failed_restart_action)
        self.framework.observe(self.on.deferred_restart_action, self._on_deferred_restart_action)

    def _on_restart_action(self, event: ActionEvent) -> None:
        delay = event.params.get('delay')
        self.restart_manager.request_async_lock(callback_id='_restart', kwargs={'delay': delay})

    def _on_failed_restart_action(self, event: ActionEvent) -> None:
        delay = event.params.get('delay')
        max_retry = event.params.get('max-retry', None)
        self.restart_manager.request_async_lock(
            callback_id='_failed_restart',
            kwargs={'delay': delay},
            max_retry=max_retry,
        )

    def _on_deferred_restart_action(self, event: ActionEvent) -> None:
        delay = event.params.get('delay')
        max_retry = event.params.get('max-retry', None)
        self.restart_manager.request_async_lock(
            callback_id='_deferred_restart',
            kwargs={'delay': delay},
            max_retry=max_retry,
        )

    def _restart(self) -> None:
        pass

    def _failed_restart(self, delay: int = 0) -> OperationResult:
        return OperationResult.RETRY_RELEASE

    def _deferred_restart(self, delay: int = 0) -> OperationResult:
        return OperationResult.RETRY_HOLD


@pytest.fixture
def charm_test() -> type[RollingOpsCharm]:
    return RollingOpsCharm


@pytest.fixture
def peer_charm_test() -> type[PeerRollingOpsCharm]:
    return PeerRollingOpsCharm


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

actions: dict[str, Any] = {
    'restart': {
        'description': 'Restarts the example service',
        'params': {
            'delay': {
                'description': 'Introduce an artificial delay (for testing).',
                'type': 'integer',
                'default': 0,
            },
        },
    },
    'failed-restart': {
        'description': 'Example restart with a custom callback function. Used in testing',
        'params': {
            'delay': {
                'description': 'Introduce an artificial delay (for testing).',
                'type': 'integer',
                'default': 0,
            },
            'max-retry': {
                'description': 'Number of times the operation should be retried.',
                'type': 'integer',
            },
        },
    },
    'deferred-restart': {
        'description': 'Example restart with a custom callback function. Used in testing',
        'params': {
            'delay': {
                'description': 'Introduce an artificial delay (for testing).',
                'type': 'integer',
                'default': 0,
            },
            'max-retry': {
                'description': 'Number of times the operation should be retried.',
                'type': 'integer',
            },
        },
    },
}


@pytest.fixture
def ctx(charm_test: type[RollingOpsCharm]) -> Context[RollingOpsCharm]:
    return Context(charm_test, meta=meta, actions=actions)


@pytest.fixture
def peer_ctx(peer_charm_test: type[PeerRollingOpsCharm]) -> Context[PeerRollingOpsCharm]:
    return Context(peer_charm_test, meta=meta, actions=actions)
