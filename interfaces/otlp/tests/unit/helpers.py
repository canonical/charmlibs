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
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

import yaml

logger = logging.getLogger(__name__)
COS_TOOL_URL = 'https://github.com/canonical/cos-tool/releases/latest/download/cos-tool-amd64'

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent


P = ParamSpec('P')
R = TypeVar('R')


def add_alerts(alerts: dict[str, dict[str, Any]], dest_path: Path) -> None:
    """Save the alerts to files in the specified destination folder.

    For K8s charms, alerts are saved in the charm container.

    Args:
        alerts: Dictionary of alerts to save to disk
        dest_path: Path to the folder where alerts will be saved
    """
    dest_path.mkdir(parents=True, exist_ok=True)
    for topology_identifier, rule in alerts.items():
        rule_file = dest_path.joinpath(f'juju_{topology_identifier}.rules')
        rule_file.write_text(yaml.safe_dump(rule))
        logger.debug('updated alert rules file: %s', rule_file.as_posix())
