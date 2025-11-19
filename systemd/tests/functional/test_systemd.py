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

"""Functional tests for the `systemd` charm library."""

import logging
from subprocess import check_output

from charmlibs import systemd

logger = logging.getLogger(__name__)


def test_service() -> None:
    def create_service(name: str, start_command: str):
        """Create a custom service."""
        content = f"""[Unit]
        Description=Test Service
        After=multi-user.target

        [Service]
        ExecStart=/usr/bin/bash -c "{start_command}"
        Type=simple

        [Install]
        WantedBy=multi-user.target
        """

        with open(f'/etc/systemd/system/{name}', 'w+') as f:
            f.writelines([f'{line.strip()}\n' for line in content.split('\n')])

        systemd.service_restart(name)

    # Cron is pre-installed in the lxc images we are using.
    assert systemd.service_running('cron')
    # Foo is made up, and should not be running.
    assert not systemd.service_running('foo')

    # test custom service with correct command
    create_service('test.service', 'while true; do echo; sleep 1; done')
    assert systemd.service_running('test.service')
    systemd.service_stop('test.service')

    # test failed status
    create_service('test.service', 'bad command')
    assert systemd.service_failed('test.service')


def test_pause_and_resume() -> None:
    # Verify that we can disable and re-enable a service.
    assert systemd.service_pause('cron')
    assert not systemd.service_running('cron')
    assert systemd.service_resume('cron')
    assert systemd.service_running('cron')


def test_restart():
    # Verify that we seem to be able to restart a service.
    assert systemd.service_restart('cron')


def test_stop_and_start() -> None:
    # Verify that we can stop and start a service.
    assert systemd.service_stop('cron')
    assert not systemd.service_running('cron')
    assert systemd.service_start('cron')
    assert systemd.service_running('cron')


def test_reload() -> None:
    # Verify that we can reload services that support reload.
    try:
        systemd.service_reload('cron')
    except systemd.SystemdError:
        pass
    else:
        raise AssertionError("cron does not support reload, but we didn't raise and error.")
    assert systemd.service_reload('apparmor')

    # The following is observed behavior. Not sure how happy I am about it.
    assert systemd.service_reload('cron', restart_on_failure=True)


def test_daemon_reload() -> None:
    # Verify that we can reload the systemd manager configuration.

    def needs_reload(svc: str):
        """Check if a given service has changed, and requires a daemon-reload."""
        output = check_output(['systemctl', 'show', svc, '--property=NeedDaemonReload'])
        return output.decode().strip() == 'NeedDaemonReload=yes'

    # Edit a unit file such that a reload would be required
    with open('/lib/systemd/system/cron.service', 'r+') as f:
        content = f.read()
        content.replace('Restart=on-failure', 'Restart=never')
        f.write(content)

    assert needs_reload('cron')
    assert systemd.daemon_reload()
    assert not needs_reload('cron')
