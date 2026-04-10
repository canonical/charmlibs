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

import charmlibs.rollingops.etcd._certificates as certificates
import charmlibs.rollingops.etcd._etcdctl as etcdctl
from charmlibs.interfaces.tls_certificates import (
    Certificate,
    PrivateKey,
)
from charmlibs.pathops import LocalPath
from charmlibs.rollingops import RollingOpsManager
from charmlibs.rollingops.common._models import OperationResult
from charmlibs.rollingops.etcd._models import SharedCertificate
from charmlibs.rollingops.peer._manager import PeerRollingOpsManager

VALID_CA_CERT_PEM = """-----BEGIN CERTIFICATE-----
      MIIC6DCCAdCgAwIBAgIUW42TU9LSjEZLMCclWrvSwAsgRtcwDQYJKoZIhvcNAQEL
      BQAwIDELMAkGA1UEBhMCVVMxETAPBgNVBAMMCHdoYXRldmVyMB4XDTIzMDMyNDE4
      NDMxOVoXDTI0MDMyMzE4NDMxOVowPDELMAkGA1UEAwwCb2sxLTArBgNVBC0MJGUw
      NjVmMWI3LTE2OWEtNDE5YS1iNmQyLTc3OWJkOGM4NzIwNjCCASIwDQYJKoZIhvcN
      AQEBBQADggEPADCCAQoCggEBAK42ixoklDH5K5i1NxXo/AFACDa956pE5RA57wlC
      BfgUYaIDRmv7TUVJh6zoMZSD6wjSZl3QgP7UTTZeHbvs3QE9HUwEkH1Lo3a8vD3z
      eqsE2vSnOkpWWnPbfxiQyrTm77/LAWBt7lRLRLdfL6WcucD3wsGqm58sWXM3HG0f
      SN7PHCZUFqU6MpkHw8DiKmht5hBgWG+Vq3Zw8MNaqpwb/NgST3yYdcZwb58G2FTS
      ZvDSdUfRmD/mY7TpciYV8EFylXNNFkth8oGNLunR9adgZ+9IunfRKj1a7S5GSwXU
      AZDaojw+8k5i3ikztsWH11wAVCiLj/3euIqq95z8xGycnKcCAwEAATANBgkqhkiG
      9w0BAQsFAAOCAQEAWMvcaozgBrZ/MAxzTJmp5gZyLxmMNV6iT9dcqbwzDtDtBvA/
      46ux6ytAQ+A7Bd3AubvozwCr1Id6g66ae0blWYRRZmF8fDdX/SBjIUkv7u9A3NVQ
      XN9gsEvK9pdpfN4ZiflfGSLdhM1STHycLmhG6H5s7HklbukMRhQi+ejbSzm/wiw1
      ipcxuKhSUIVNkTLusN5b+HE2gwF1fn0K0z5jWABy08huLgbaEKXJEx5/FKLZGJga
      fpIzAdf25kMTu3gggseaAmzyX3AtT1i8A8nqYfe8fnnVMkvud89kq5jErv/hlMC9
      49g5yWQR2jilYYM3j9BHDuB+Rs+YS5BCep1JnQ==
      -----END CERTIFICATE-----"""

VALID_CLIENT_CERT_PEM = """-----BEGIN CERTIFICATE-----
      MIIC6DCCAdCgAwIBAgIUdiBwE/CtaBXJl3MArjZen6Y8kigwDQYJKoZIhvcNAQEL
      BQAwIDELMAkGA1UEBhMCVVMxETAPBgNVBAMMCHdoYXRldmVyMB4XDTIzMDMyNDE4
      NDg1OVoXDTI0MDMyMzE4NDg1OVowPDELMAkGA1UEAwwCb2sxLTArBgNVBC0MJDEw
      MDdjNDBhLWUwYzMtNDVlOS05YTAxLTVlYjY0NWQ0ZmEyZDCCASIwDQYJKoZIhvcN
      AQEBBQADggEPADCCAQoCggEBANOnUl6JDlXpLMRr/PxgtfE/E5Yk6E/TkPkPL/Kk
      tUGjEi42XZDg9zn3U6cjTDYu+rfKY2jiitfsduW6DQIkEpz3AvbuCMbbgnFpcjsB
      YysLSMTmuz/AVPrfnea/tQTALcONCSy1VhAjGSr81ZRSMB4khl9StSauZrbkpJ1P
      shqkFSUyAi31mKrnXz0Es/v0Yi0FzAlgWrZ4u1Ld+Bo2Xz7oK4mHf7/93Jc+tEaM
      IqG6ocD0q8bjPp0tlSxftVADNUzWlZfM6fue5EXzOsKqyDrxYOSchfU9dNzKsaBX
      kxbHEeSUPJeYYj7aVPEfAs/tlUGsoXQvwWfRie8grp2BoLECAwEAATANBgkqhkiG
      9w0BAQsFAAOCAQEACZARBpHYH6Gr2a1ka0mCWfBmOZqfDVan9rsI5TCThoylmaXW
      quEiZ2LObI+5faPzxSBhr9TjJlQamsd4ywout7pHKN8ZGqrCMRJ1jJbUfobu1n2k
      UOsY4+jzV1IRBXJzj64fLal4QhUNv341lAer6Vz3cAyRk7CK89b/DEY0x+jVpyZT
      1osx9JtsOmkDTgvdStGzq5kPKWOfjwHkmKQaZXliCgqbhzcCERppp1s/sX6K7nIh
      4lWiEmzUSD3Hngk51KGWlpZszO5KQ4cSZ3HUt/prg+tt0ROC3pY61k+m5dDUa9M8
      RtMI6iTjzSj/UV8DiAx0yeM+bKoy4jGeXmaL3g==
      -----END CERTIFICATE-----"""

VALID_CLIENT_KEY_PEM = """-----BEGIN RSA PRIVATE KEY-----
      MIIEpAIBAAKCAQEAqk3eP5GA+m9xeAaP8TzcPVQPXdkDYWFENB2P3qPv+nSF/KGK
      BxmADFR43tCT69rv44BQvYt38MB8cvyMSPBfQqJmE2ff3UnBISfhebS0A3WC7qWy
      yPLjpHcznHxcxYLmqVjcCBO40TVvWTbcjmKNtQbDc5lnEeWyv1Vv5ceXGQD/dId7
      tfbGgeG1kqB02ysAYLxeoMuHGoL77+8DEuQY7PlFCCQMNTLwB4isft9OkhTpCQad
      xJNzc5mGYc9nMofLl/tZIi7Kn3mw4LmwNoyuxeoP1eklK+g8FvPyWYYaLug08wCR
      Sf/YKpmZgj6LfRFnXvxYiw1tGQLZ4uqiuQpBLwIDAQABAoIBACWfr1Zu4EYzgadp
      F7rNXcCkxgJPM7p7QRScZVDj+dvki0dNLs+zuADBVrSu8sb75txlWDEP008aT0Qd
      /CYPCJSRiSiHXcMnDKY1B9CZ9dz/xI3RiIZxdo46kWnkZaBy8199VJrqNH3vpqpY
      fvBr4G+aT2rF/KnNC6jOiLqEViK9I1CDIEBM+Hc9VfNlSd1yKCMH5FCge95GqALP
      rbjA2YxQNql20fZqs3QRbwUZ7LCvb7DIKr4puxOFyxfe5tgHtDnHc/mdzt0BhLXb
      2ZwioPtqfgolFoAwSQ1rpTjK9fiSCrvIb0CaVUnNyO1wJ/i90uztYVXswEeWMket
      cwRj0BkCgYEA6ozA07DY4q6XmQPUZZS9H7qk2TwD7cuGoNpYCYtTrMFkajLT5F4E
      C82Sfd94+hqNBix11h2FPY8ng/De6O37k6jHNnep/N80/90cyvwwdHInGwIAbWF7
      wpRZEk6/ftlYji/zbAK0Dz9AncQVBGVjqu/rlOUeEbrqBprMBFdMBFcCgYEAueEB
      TQPiTIfkBlHBuGS505Q05sPGyR1KsmwQ6fHRtu7gaqsQUXnd4vLXGwNsoNJyPxDw
      uj6GCrpEyY6nMPUEGALM4WTd5EoNej1FVDJWaJk9s4uv6fTu/pFdjbf4ezcmH54I
      SpyyFRsjm6Y84a9V5pu9rv/wyRVdcLgS+Ne3YukCgYEAs5pkbbWV3r7ixwDvu3lR
      +OHrKY2TVJvs029eyrAturO8OLYDG3QClSctbcWZ1apPItMYyISCaskb8SSZDLRv
      WHp9UXAAcupYozSlv6mtUP24hC3cNeXX5v/B1QsICBJWhUqik6reRm6hBC4KCfu5
      fkOJmdJ4XAtM+RG/9/MA+rECgYEApo2Bn+OiC1ccL7lkLng6teWvvTKhVSWk/9ir
      EyS1+Ad1GL8tAQSEmE1mBvN7i2LmMbJZMVjCvKwI5N2o28o/n9Aqiq/Zzyu3hdeO
      3pG4MUNWMSIyPx1UZNAWFt1IjgdtZpkw7sIXI6hMsLQ1CzgTbW4RedQlidhWAKE/
      hq+rx7kCgYAS7uXayl5+8+QAHlTCt7FJInFIHE3yy1g5pxK0zp0rNE7T4SmGzZv9
      QccUFun5Tk0AgoeKEQQpvDHv3ACODl3PUyiuoFDYOeEB57dIEmM9FW85MIBGK5RI
      5Zv3x7N0WSyCf6w51sT2UsaI5Ybqnfo7zCThvUkmVM1yfxyfjcKKnQ==
      -----END RSA PRIVATE KEY-----"""


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
    with patch('charmlibs.rollingops.etcd._certificates') as mock_etcdctl:
        yield mock_etcdctl


@pytest.fixture
def certificates_manager_patches() -> Generator[dict[str, MagicMock], None, None]:
    with (
        patch(
            'charmlibs.rollingops.etcd._certificates._exists',
            return_value=False,
        ),
        patch(
            'charmlibs.rollingops.etcd._certificates.generate',
            return_value=SharedCertificate(
                certificate=Certificate.from_string(VALID_CLIENT_CERT_PEM),
                key=PrivateKey.from_string(VALID_CLIENT_KEY_PEM),
                ca=Certificate.from_string(VALID_CA_CERT_PEM),
            ),
        ) as mock_generate,
        patch(
            'charmlibs.rollingops.etcd._certificates.persist_client_cert_key_and_ca',
            return_value=None,
        ) as mock_persit,
    ):
        yield {
            'generate': mock_generate,
            'persist': mock_persit,
        }


class BaseRollingOpsTestCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)

        callback_targets = {
            '_restart': self._restart,
            '_failed_restart': self._failed_restart,
            '_deferred_restart': self._deferred_restart,
        }

        self.restart_manager = self._make_restart_manager(callback_targets)
        self.framework.observe(self.on.restart_action, self._on_restart_action)
        self.framework.observe(self.on.failed_restart_action, self._on_failed_restart_action)
        self.framework.observe(self.on.deferred_restart_action, self._on_deferred_restart_action)

    def _make_restart_manager(
        self, callback_targets: dict[str, Any]
    ) -> PeerRollingOpsManager | RollingOpsManager:
        raise NotImplementedError

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


class PeerRollingOpsCharm(BaseRollingOpsTestCharm):
    def _make_restart_manager(self, callback_targets: dict[str, Any]) -> PeerRollingOpsManager:
        return PeerRollingOpsManager(
            charm=self,
            relation_name='restart',
            callback_targets=callback_targets,
        )


class RollingOpsCharm(BaseRollingOpsTestCharm):
    def _make_restart_manager(self, callback_targets: dict[str, Any]) -> RollingOpsManager:
        return RollingOpsManager(
            charm=self,
            peer_relation_name='restart',
            etcd_relation_name='etcd',
            cluster_id='cluster-12345',
            callback_targets=callback_targets,
        )


@pytest.fixture
def peer_charm_test() -> type[PeerRollingOpsCharm]:
    return PeerRollingOpsCharm


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
