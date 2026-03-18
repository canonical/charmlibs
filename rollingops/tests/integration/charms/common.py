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

"""Common charm code for integration test charms.

This file is symlinked alongside src/charm.py by these charms.
"""

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ops import ActionEvent, CharmBase, Framework, InstallEvent
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus

from charmlibs.rollingops import (
    EtcdRollingOpsManager,
    OperationResult,
)

logger = logging.getLogger(__name__)

TRACE_FILE = Path('/var/lib/charm-rolling-ops/transitions.log')


def _now_timestamp_str() -> str:
    """UTC timestamp as a string using ISO 8601 format."""
    return datetime.now(UTC).isoformat()


class Charm(CharmBase):
    """Charm the service."""

    def __init__(self, framework: Framework):
        super().__init__(framework)
        callback_targets = {
            '_restart': self._restart,
            '_failed_restart': self._failed_restart,
            '_deferred_restart': self._deferred_restart,
        }

        self.restart_manager = EtcdRollingOpsManager(
            charm=self,
            peer_relation_name='restart',
            etcd_relation_name='etcd',
            cluster_id='cluster-12345',
            callback_targets=callback_targets,
        )

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.restart_action, self._on_restart_action)
        self.framework.observe(self.on.failed_restart_action, self._on_failed_restart_action)
        self.framework.observe(self.on.deferred_restart_action, self._on_deferred_restart_action)

    def _restart(self, delay: int = 0) -> None:
        self._record_transition('_restart:start', delay=delay)
        logger.info('Starting restart operation')
        self.model.unit.status = MaintenanceStatus('Executing _restart operation')
        time.sleep(int(delay))
        self.model.unit.status = ActiveStatus()
        self._record_transition('_restart:done')

    def _failed_restart(self, delay: int = 0) -> OperationResult:
        self._record_transition('_failed_restart:start', delay=delay)
        logger.info('Starting failed restart operation')
        self.model.unit.status = MaintenanceStatus('Executing _failed_restart operation')
        time.sleep(int(delay))
        self.model.unit.status = MaintenanceStatus('Rolling _failed_restart operation failed')
        self._record_transition('_failed_restart:retry_release')
        return OperationResult.RETRY_RELEASE

    def _deferred_restart(self, delay: int = 0) -> OperationResult:
        self._record_transition('_deferred_restart:start', delay=delay)
        logger.info('Starting deferred restart operation')
        self.model.unit.status = MaintenanceStatus('Executing _deferred_restart operation')
        time.sleep(int(delay))
        self.model.unit.status = MaintenanceStatus('Rolling _deferred_restart operation failed')
        self._record_transition('_deferred_restart:retry_hold', delay=delay)
        return OperationResult.RETRY_HOLD

    def _on_install(self, event: InstallEvent) -> None:
        self.unit.status = ActiveStatus()

    def _on_restart_action(self, event: ActionEvent) -> None:
        delay = event.params.get('delay')
        self._record_transition('action:restart', delay=delay)
        self.model.unit.status = WaitingStatus('Awaiting _restart operation')
        self.restart_manager.request_async_lock(callback_id='_restart', kwargs={'delay': delay})

    def _on_failed_restart_action(self, event: ActionEvent) -> None:
        delay = event.params.get('delay')
        max_retry = event.params.get('max-retry', None)
        self._record_transition('action:failed-restart', delay=delay, max_retry=max_retry)
        self.model.unit.status = WaitingStatus('Awaiting _failed_restart operation')
        self.restart_manager.request_async_lock(
            callback_id='_failed_restart',
            kwargs={'delay': delay},
            max_retry=max_retry,
        )

    def _on_deferred_restart_action(self, event: ActionEvent) -> None:
        delay = event.params.get('delay')
        max_retry = event.params.get('max-retry', None)
        self._record_transition('action:deferred-restart', delay=delay, max_retry=max_retry)
        self.model.unit.status = WaitingStatus('Awaiting _deferred_restart operation')
        self.restart_manager.request_async_lock(
            callback_id='_deferred_restart',
            kwargs={'delay': delay},
            max_retry=max_retry,
        )

    def _record_transition(self, name: str, **data: Any) -> None:
        TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'ts': _now_timestamp_str(),
            'unit': self.model.unit.name,
            'event': name,
            **data,
        }
        with TRACE_FILE.open('a', encoding='utf-8') as f:
            f.write(json.dumps(payload) + '\n')
