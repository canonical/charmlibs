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

import json
from typing import Any
from unittest.mock import patch

import pytest

from charmlibs.pathops import LocalPath
from charmlibs.rollingops import RollingOpsEtcdNotConfiguredError


def test_etcdctl_write_env(temp_etcdctl: Any) -> None:
    temp_etcdctl.write_config_file(
        endpoints='https://10.0.0.1:2379,https://10.0.0.2:2379',
        client_cert_path=LocalPath('PATH1'),
        client_key_path=LocalPath('PATH2'),
    )

    assert temp_etcdctl.BASE_DIR.exists()

    config = json.loads(temp_etcdctl.CONFIG_FILE_PATH.read_text())
    assert config == {
        'endpoints': 'https://10.0.0.1:2379,https://10.0.0.2:2379',
        'cacert_path': str(temp_etcdctl.SERVER_CA_PATH),
        'cert_path': 'PATH1',
        'key_path': 'PATH2',
    }


def test_etcdctl_ensure_initialized_raises_when_env_missing(temp_etcdctl: Any) -> None:
    with pytest.raises(RollingOpsEtcdNotConfiguredError):
        temp_etcdctl.ensure_initialized()


def test_etcdctl_cleanup_removes_env_file_and_server_ca(temp_etcdctl: Any) -> None:
    temp_etcdctl.BASE_DIR.mkdir(parents=True, exist_ok=True)
    temp_etcdctl.CONFIG_FILE_PATH.write_text('env')
    temp_etcdctl.SERVER_CA_PATH.write_text('ca')

    assert temp_etcdctl.CONFIG_FILE_PATH.exists()
    assert temp_etcdctl.SERVER_CA_PATH.exists()

    temp_etcdctl.cleanup()

    assert not temp_etcdctl.CONFIG_FILE_PATH.exists()
    assert not temp_etcdctl.SERVER_CA_PATH.exists()


def test_etcdctl_cleanup_is_noop_when_files_do_not_exist(temp_etcdctl: Any) -> None:
    assert not temp_etcdctl.CONFIG_FILE_PATH.exists()
    assert not temp_etcdctl.SERVER_CA_PATH.exists()

    temp_etcdctl.cleanup()

    assert not temp_etcdctl.CONFIG_FILE_PATH.exists()
    assert not temp_etcdctl.SERVER_CA_PATH.exists()


def test_etcdctl_load_env_parses_exported_vars(temp_etcdctl: Any) -> None:
    temp_etcdctl.BASE_DIR.mkdir(parents=True, exist_ok=True)
    temp_etcdctl.SERVER_CA_PATH.write_text('SERVER CA')
    temp_etcdctl.CONFIG_FILE_PATH.write_text(
        json.dumps({
            'endpoints': 'https://10.0.0.1:2379',
            'cacert_path': '/a-path/server-ca.pem',
            'cert_path': '/a-path/client.pem',
            'key_path': '/a-path/client.key',
        })
    )

    with patch.dict('os.environ', {'EXISTING_VAR': 'present'}, clear=True):
        env = temp_etcdctl.load_env()

    assert env['EXISTING_VAR'] == 'present'
    assert env['ETCDCTL_API'] == '3'
    assert env['ETCDCTL_ENDPOINTS'] == 'https://10.0.0.1:2379'
    assert env['ETCDCTL_CERT'] == '/a-path/client.pem'
    assert env['ETCDCTL_KEY'] == '/a-path/client.key'
    assert env['ETCDCTL_CACERT'] == '/a-path/server-ca.pem'
