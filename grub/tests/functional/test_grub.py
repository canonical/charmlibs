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

import logging

import pytest

from charmlibs import grub
from charmlibs.grub import _grub

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def clean_configs():
    """Clean main and charms configs after each test."""
    yield  # run test
    grub.GRUB_CONFIG.unlink(missing_ok=True)
    for charm_config in grub.GRUB_DIRECTORY.glob(f'{grub.CHARM_CONFIG_PREFIX}-*'):
        charm_config.unlink(missing_ok=True)


@pytest.mark.parametrize(
    'config',
    [
        {'GRUB_CMDLINE_LINUX_DEFAULT': '$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G'},
        {
            'GRUB_CMDLINE_LINUX_DEFAULT': '$GRUB_CMDLINE_LINUX_DEFAULT hugepages=64 hugepagesz=1G',
            'GRUB_DEFAULT': '0',
        },
        {'GRUB_TIMEOUT': '0'},
    ],
)
def test_single_charm_valid_update(config: dict[str, str]):
    """Test single charm update GRUB configuration."""
    grub_conf = grub.Config('test-charm')
    grub_conf.update(config)
    # check that config was set for charm config file
    assert config == grub_conf
    assert config == _grub._load_config(grub_conf.path)
    # check the main config
    assert config == _grub._load_config(grub.GRUB_CONFIG)


@pytest.mark.parametrize('config', [{'TEST_WRONG_KEY:test': '1'}])
def test_single_charm_update_apply_failure(config: dict[str, str]):
    """Test single charm update GRUB configuration with ApplyError."""
    # create empty grub config
    grub.GRUB_CONFIG.touch()
    grub_conf = grub.Config('test-charm')

    with pytest.raises(grub.ApplyError):
        grub_conf.update(config)

    # check that charm file was not configured
    assert not grub_conf.path.exists()
    # check the main config
    main_config = _grub._load_config(grub.GRUB_CONFIG)
    for key in config:
        assert key not in main_config


def test_single_charm_multiple_update():
    """Test that charm can do multiple updates and update it's own configuration."""
    # charms using this config to make update
    configs = [
        {'GRUB_TIMEOUT': '0'},
        {
            'GRUB_TIMEOUT': '0',
            'GRUB_CMDLINE_LINUX_DEFAULT': '$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G',
        },
        {'GRUB_TIMEOUT': '1'},
    ]
    # charms configs in time
    exp_charms_configs = [
        {'GRUB_TIMEOUT': '0'},
        {
            'GRUB_TIMEOUT': '0',
            'GRUB_CMDLINE_LINUX_DEFAULT': '$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G',
        },
        {
            'GRUB_TIMEOUT': '1',
            'GRUB_CMDLINE_LINUX_DEFAULT': '$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G',
        },
    ]
    exp_main_config = {
        'GRUB_TIMEOUT': '1',
        'GRUB_CMDLINE_LINUX_DEFAULT': '$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G',
    }
    grub_conf = grub.Config('test-charm')

    for config, exp_conf in zip(configs, exp_charms_configs, strict=False):
        grub_conf.update(config)
        assert exp_conf == grub_conf
        assert exp_conf == _grub._load_config(grub_conf.path)

    # check the main config
    assert exp_main_config == _grub._load_config(grub.GRUB_CONFIG)


@pytest.mark.parametrize(
    'config_1, config_2',
    [
        ({'GRUB_TIMEOUT': '0'}, {'GRUB_TIMEOUT': '0'}),
        (
            {'GRUB_TIMEOUT': '0'},
            {'GRUB_CMDLINE_LINUX_DEFAULT': '$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G'},
        ),
        (
            {'GRUB_CMDLINE_LINUX_DEFAULT': '$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G'},
            {'GRUB_TIMEOUT': '0'},
        ),
    ],
)
def test_two_charms_no_conflict(config_1: dict[str, str], config_2: dict[str, str]):
    """Test two charms update GRUB configuration without any conflict."""
    for name, config in [('test-charm-1', config_1), ('test-charm-2', config_2)]:
        grub_conf = grub.Config(name)
        grub_conf.update(config)
        assert config == _grub._load_config(grub_conf.path)

    # check the main config
    assert {**config_1, **config_2} == _grub._load_config(grub.GRUB_CONFIG)


@pytest.mark.parametrize(
    'config_1, config_2',
    [
        ({'GRUB_TIMEOUT': '0'}, {'GRUB_TIMEOUT': '1'}),
        (
            {'GRUB_TIMEOUT': '0'},
            {
                'GRUB_TIMEOUT': '1',
                'GRUB_CMDLINE_LINUX_DEFAULT': '$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G',
            },
        ),
    ],
)
def test_two_charms_with_conflict(config_1: dict[str, str], config_2: dict[str, str]):
    """Test two charms update GRUB configuration with conflict."""
    # configure charm 1
    grub_conf_1 = grub.Config('test-charm-1')
    grub_conf_1.update(config_1)
    assert config_1 == _grub._load_config(grub_conf_1.path)

    # configure charm 2
    grub_conf_2 = grub.Config('test-charm-2')
    with pytest.raises(grub.ValidationError):
        grub_conf_2.update(config_2)

    assert not grub_conf_2.path.exists()
    # check the main config
    assert config_1 == _grub._load_config(grub.GRUB_CONFIG)


def test_charm_remove_configuration():
    """Test removing charm configuration."""
    config = {'GRUB_TIMEOUT': '0'}
    grub_conf = grub.Config('test-charm')
    grub_conf.update(config)

    assert grub_conf.path.exists(), 'Config file is missing, check test_single_charm_valid_update'
    assert config == _grub._load_config(grub_conf.path)
    assert config == _grub._load_config(grub.GRUB_CONFIG)

    grub_conf.remove()
    assert not grub_conf.path.exists()
    assert _grub._load_config(grub.GRUB_CONFIG) == {}


@pytest.mark.parametrize(
    'config_1, config_2',
    [
        (
            {'GRUB_TIMEOUT': '0'},
            {
                'GRUB_TIMEOUT': '0',
                'GRUB_CMDLINE_LINUX_DEFAULT': '$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G',
            },
        ),
        (
            {
                'GRUB_TIMEOUT': '0',
                'GRUB_CMDLINE_LINUX_DEFAULT': '$GRUB_CMDLINE_LINUX_DEFAULT hugepagesz=1G',
            },
            {'GRUB_TIMEOUT': '0'},
        ),
    ],
)
def test_charm_remove_configuration_without_changing_others(
    config_1: dict[str, str], config_2: dict[str, str]
):
    """Test removing charm configuration and do not touch other."""
    grub_conf_1 = grub.Config('test-charm-1')
    grub_conf_1.update(config_1)
    grub_conf_2 = grub.Config('test-charm-2')
    grub_conf_2.update(config_2)

    assert grub_conf_1.path.exists()
    assert grub_conf_2.path.exists()

    grub_conf_1.remove()
    assert not grub_conf_1.path.exists()
    assert config_2 == _grub._load_config(grub.GRUB_CONFIG)
