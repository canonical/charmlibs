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
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

from pathlib import Path
from unittest.mock import patch

import pytest

from charmlibs.advanced_rollingops import EtcdCtl, RollingOpsEtcdNotConfiguredError


def test_etcdctl_write_env(temp_etcdctl: EtcdCtl) -> None:
    temp_etcdctl.write_env_file(
        endpoints='https://10.0.0.1:2379,https://10.0.0.2:2379',
        client_cert_path=Path('PATH1'),
        client_key_path=Path('PATH2'),
    )

    assert temp_etcdctl.BASE_DIR.exists()

    env_text = temp_etcdctl.ENV_FILE.read_text()
    assert 'export ETCDCTL_API="3"' in env_text
    assert 'export ETCDCTL_ENDPOINTS="https://10.0.0.1:2379,https://10.0.0.2:2379"' in env_text
    assert f'export ETCDCTL_CACERT="{temp_etcdctl.SERVER_CA}"' in env_text
    assert 'export ETCDCTL_CERT="PATH1"' in env_text
    assert 'export ETCDCTL_KEY="PATH2"' in env_text


def test_etcdctl_ensure_initialized_raises_when_env_missing(temp_etcdctl: EtcdCtl) -> None:
    with pytest.raises(RollingOpsEtcdNotConfiguredError):
        temp_etcdctl.ensure_initialized()


def test_etcdctl_cleanup_removes_env_file_and_server_ca(temp_etcdctl: EtcdCtl) -> None:
    temp_etcdctl.BASE_DIR.mkdir(parents=True, exist_ok=True)
    temp_etcdctl.ENV_FILE.write_text('env')
    temp_etcdctl.SERVER_CA.write_text('ca')

    assert temp_etcdctl.ENV_FILE.exists()
    assert temp_etcdctl.SERVER_CA.exists()

    temp_etcdctl.cleanup()

    assert not temp_etcdctl.ENV_FILE.exists()
    assert not temp_etcdctl.SERVER_CA.exists()


def test_etcdctl_cleanup_is_noop_when_files_do_not_exist(temp_etcdctl: EtcdCtl) -> None:
    assert not temp_etcdctl.ENV_FILE.exists()
    assert not temp_etcdctl.SERVER_CA.exists()

    temp_etcdctl.cleanup()

    assert not temp_etcdctl.ENV_FILE.exists()
    assert not temp_etcdctl.SERVER_CA.exists()


def test_etcdctl_load_env_parses_exported_vars(temp_etcdctl: EtcdCtl) -> None:
    temp_etcdctl.BASE_DIR.mkdir(parents=True, exist_ok=True)
    temp_etcdctl.SERVER_CA.write_text('SERVER CA')
    temp_etcdctl.ENV_FILE.write_text(
        '\n'.join([
            '# comment',
            'export ETCDCTL_API="3"',
            'export ETCDCTL_ENDPOINTS="https://10.0.0.1:2379"',
            "export ETCDCTL_CERT='/a-path/client.pem'",
            'export ETCDCTL_KEY="/a-path/client.key"',
            'export ETCDCTL_CACERT="/a-path/server-ca.pem"',
            '',
        ])
    )

    with patch.dict('os.environ', {'EXISTING_VAR': 'present'}, clear=True):
        env = temp_etcdctl.load_env()

    assert env['EXISTING_VAR'] == 'present'
    assert env['ETCDCTL_API'] == '3'
    assert env['ETCDCTL_ENDPOINTS'] == 'https://10.0.0.1:2379'
    assert env['ETCDCTL_CERT'] == '/a-path/client.pem'
    assert env['ETCDCTL_KEY'] == '/a-path/client.key'
    assert env['ETCDCTL_CACERT'] == '/a-path/server-ca.pem'
