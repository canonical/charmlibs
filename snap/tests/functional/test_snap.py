#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


import datetime
import logging
import subprocess

import pytest

from charmlibs import snap

# enable debug logging from snap library during tests
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
snap_logger = logging.getLogger(snap.__name__)
snap_logger.setLevel(logging.DEBUG)
snap_logger.addHandler(handler)


def get_command_path(command: str) -> str:
    try:
        return subprocess.check_output(['which', command]).decode().strip()
    except subprocess.CalledProcessError:
        return ''


def ensure_removed(*snaps: str):
    for snap_name in snaps:
        if snap.info(snap_name, missing_ok=True) is not None:
            snap.remove(snap_name)


def test_snap_install():
    ensure_removed('juju')
    assert not get_command_path('juju')
    snap.install('juju')
    assert get_command_path('juju') == '/snap/bin/juju'


def test_snap_remove():
    snap.ensure('charmcraft', classic=True)
    assert get_command_path('charmcraft') == '/snap/bin/charmcraft'
    snap.remove('charmcraft')
    assert get_command_path('charmcraft') == ''


def test_snap_refresh():
    snap.ensure('hello-world', channel='latest/stable')
    assert snap.info('hello-world').channel == 'latest/stable'
    snap.refresh('hello-world', channel='latest/candidate')
    assert snap.info('hello-world').channel == 'latest/candidate'


def test_snap_set_and_get():
    simple_types = {
        'true': True,
        'false': False,
        'null': None,
        'integer': 1,
        'float': 2.0,
        'string': 'true',
    }
    list_value = list(simple_types.values())
    dict_value = {**simple_types, 'list': list_value, 'dict': {'hello': 'world'}}
    config_to_set = {**simple_types, 'list': list_value, 'dict': dict_value}

    snap_name = 'lxd'
    snap.ensure(snap_name)
    snap.set(snap_name, config_to_set)

    # Test the full config retrieval.
    snap_config = snap.get(snap_name)
    assert snap_config
    assert snap_config.get('true') is True
    assert snap_config.get('false') is False
    assert 'null' not in snap_config
    assert snap_config['integer'] == 1
    assert snap_config['float'] == 2.0
    assert snap_config['string'] == 'true'
    assert snap_config['list'] == list_value
    assert {**snap_config['dict'], 'null': None} == dict_value

    # Null values in containers will be preserved, but a top-level null means unset.
    with pytest.raises(snap.SnapOptionNotFoundError):
        snap.get(snap_name, 'dict.null')
    # Test retrieval of specific keys.
    snap_config_subset = snap.get(snap_name, 'true', 'integer', 'dict.dict')
    assert snap_config_subset['true'] is True
    assert snap_config_subset['integer'] == 1
    assert snap_config_subset['dict.dict'] == {'hello': 'world'}
    # Test retrieval of individual nested keys.
    assert snap._snapd_conf._get_one(snap_name, 'dict.true') is True
    assert snap._snapd_conf._get_one(snap_name, 'dict.false') is False
    assert snap._snapd_conf._get_one(snap_name, 'dict.integer') == 1
    assert snap._snapd_conf._get_one(snap_name, 'dict.float') == 2.0
    assert snap._snapd_conf._get_one(snap_name, 'dict.list') == list_value
    assert snap._snapd_conf._get_one(snap_name, 'dict.dict') == {'hello': 'world'}
    assert snap._snapd_conf._get_one(snap_name, 'dict.dict.hello') == 'world'


def test_unset_key_raises_snap_error():
    snap.ensure('lxd')
    # Verify that the correct exception gets raised in the case of an unset key.
    key = 'keythatshouldntexist01'
    snap.unset('lxd', key)  # Succeeds regardless of whether the key exists or not.
    with pytest.raises(snap.SnapOptionNotFoundError) as ctx:
        snap.get('lxd', key)
    assert key in ctx.value.message
    snap.set('lxd', {key: 'true'})
    assert snap._snapd_conf._get_one('lxd', key) == 'true'


def test_snap_ensure():
    ensure_removed('charmcraft')
    did_something = snap.ensure('charmcraft', classic=True)
    assert did_something
    assert snap.info('charmcraft').channel == 'latest/stable'
    with pytest.raises(ValueError):
        # No changes because classic confinement was wrong.
        snap.ensure('charmcraft')  # classic=False by default
    # We're still installed as requested.
    did_something = snap.ensure('charmcraft', classic=True)
    assert not did_something
    # We installed latest/stable by default.
    did_something = snap.ensure('charmcraft', classic=True, channel='latest/stable')
    assert not did_something
    assert snap.info('charmcraft').channel == 'latest/stable'
    did_something = snap.ensure('charmcraft', classic=True, channel='latest')
    assert not did_something
    assert snap.info('charmcraft').channel == 'latest/stable'
    did_something = snap.ensure('charmcraft', classic=True, channel='stable')
    assert not did_something
    assert snap.info('charmcraft').channel == 'latest/stable'
    did_something = snap.ensure('charmcraft', classic=True, channel='beta')
    assert did_something
    assert snap.info('charmcraft').channel == 'beta'


def test_new_snap_ensure():
    snap.ensure('vlc', channel='edge')


def test_snap_ensure_revision():
    if snap.info('juju', missing_ok=True) is not None:
        snap.remove('juju')

    channels = snap._snapd._list_channels('juju')
    info = channels['3/stable']
    snap.install('juju', revision=info.revision)

    assert get_command_path('juju') == '/snap/bin/juju'

    info = snap.info('juju')
    assert info.revision == info.revision


def test_snap_start():
    ensure_removed('kube-proxy')
    snap.ensure('kube-proxy', classic=True, channel='latest/stable')
    services = snap._snapd_apps._list_services('kube-proxy')
    assert services
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert daemon.get('active')

    snap.stop('kube-proxy', 'daemon')
    services = snap._snapd_apps._list_services('kube-proxy')
    assert services
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert not daemon.get('active')

    snap.start('kube-proxy', 'daemon')
    services = snap._snapd_apps._list_services('kube-proxy')
    assert services
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert daemon['active']

    with pytest.raises(snap.SnapError):
        snap.start('kube-proxy', 'foobar')


def test_snap_stop():
    snap.ensure('kube-proxy', classic=True, channel='latest/stable')
    snap.stop('kube-proxy', 'daemon', disable=True)
    services = snap._snapd_apps._list_services('kube-proxy')
    daemon = next(s for s in services if s['name'] == 'daemon')
    assert not daemon.get('active')
    assert not daemon.get('enabled')


def test_snap_logs():
    snap.ensure('kube-proxy', classic=True, channel='latest/stable')

    before = snap.logs('kube-proxy', num_lines=10)

    # Terrible means of populating logs
    snap.start('kube-proxy')
    snap.stop('kube-proxy')
    snap.start('kube-proxy')
    snap.stop('kube-proxy')

    after = snap.logs('kube-proxy', num_lines=10)
    assert len(before) == 10 or len(after) > len(before)


def test_snap_logs_no_services():
    snap.ensure('vlc')
    with pytest.raises(snap.SnapError) as ctx:
        snap.logs('vlc')
    assert ctx.value.kind == 'app-not-found'


def test_snap_restart():
    snap.ensure('kube-proxy', classic=True, channel='latest/stable')
    snap.restart('kube-proxy')


def test_snap_hold_refresh():
    snap.ensure('hello-world', channel='latest/stable')

    snap.hold('hello-world', duration=datetime.timedelta(days=2))
    info = snap.info('hello-world')
    assert info.hold is not None
    hold = snap._snapd_logs._parse_timestamp(info.hold)
    assert hold - datetime.datetime.now().astimezone() > datetime.timedelta(days=1)


def test_snap_unhold_refresh():
    # cache = snap.SnapCache()
    # hw = cache['hello-world']
    # hw.ensure(snap.SnapState.Latest, channel='latest/stable')

    snap.ensure('hello-world', channel='latest/stable')

    # hw.unhold()
    # assert not hw.held

    snap.unhold('hello-world')
    info = snap.info('hello-world')
    assert info.hold is None


def test_snap_connect_and_disconnect():
    snap.ensure('vlc')
    # plugs = snap._snap.list_plugs('vlc')
    # assert [p for p in plugs if p.plug == 'mount-observe']

    snap.connect('vlc', 'mount-observe')
    # plugs = snap._snap.list_plugs('vlc')
    # assert [p for p in plugs if p.plug == 'mount-observe']

    snap._snapd_interfaces.disconnect('vlc', 'mount-observe')
    # plugs = snap._snap.list_plugs('vlc')
    # assert not [p for p in plugs if p.plug == 'mount-observe']


def test_alias():
    snap.ensure('lxd')
    snap.alias('lxd', 'lxc', 'testlxc')
    result = subprocess.check_output(['snap', 'aliases'], text=True)
    found = any(line.split() == ['lxd.lxc', 'testlxc', 'manual'] for line in result.splitlines())
    assert found, result
