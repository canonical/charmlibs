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

"""Fixtures for unit tests, typically mocking out parts of the external system."""

from unittest.mock import patch

import ops
import pytest

from charmlibs import advanced_rollingops


@pytest.fixture
def temp_cert_manager(tmp_path):
    class TestCertificatesManager(advanced_rollingops.CertificatesManager):
        BASE_DIR = tmp_path / 'tls'
        CA_CERT = BASE_DIR / 'client-ca.pem'
        CLIENT_KEY = BASE_DIR / 'client.key'
        CLIENT_CERT = BASE_DIR / 'client.pem'

    TestCertificatesManager.BASE_DIR.mkdir(parents=True, exist_ok=True)
    return TestCertificatesManager


@pytest.fixture
def temp_etcdctl(tmp_path):
    class TestEtcdCtl(advanced_rollingops.EtcdCtl):
        BASE_DIR = tmp_path / 'etcd'
        SERVER_CA = BASE_DIR / 'server-ca.pem'
        ENV_FILE = BASE_DIR / 'etcdctl.env'

    return TestEtcdCtl


@pytest.fixture
def etcdctl_patch():
    with patch('charmlibs.advanced_rollingops.EtcdCtl') as mock_etcdctl:
        yield mock_etcdctl


@pytest.fixture
def certificates_manager_patches():
    with (
        patch(
            'charmlibs.advanced_rollingops.CertificatesManager._exists',
            return_value=False,
        ),
        patch(
            'charmlibs.advanced_rollingops.CertificatesManager.generate',
            return_value=('CERT_PEM', 'KEY_PEM', 'CA_PEM'),
        ) as mock_generate,
        patch(
            'charmlibs.advanced_rollingops.CertificatesManager.persist_client_cert_key_and_ca',
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

        self.restart_manager = advanced_rollingops.EtcdRollingOpsManager(
            charm=self,
            peer_relation_name='restart',
            etcd_relation_name='etcd',
            cluster_id='cluster-12345',
            callback_targets=callback_targets,
        )

    def restart(self):
        pass


@pytest.fixture
def charm_test():
    return RollingOpsCharm


meta = {
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
def ctx(charm_test):
    return ops.testing.Context(charm_test, meta=meta)
