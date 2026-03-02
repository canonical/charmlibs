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
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import ParamSpec, TypeVar
from unittest.mock import patch

import requests
from cosl import CosTool as _CosTool

logger = logging.getLogger(__name__)
COS_TOOL_URL = 'https://github.com/canonical/cos-tool/releases/latest/download/cos-tool-amd64'

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent


P = ParamSpec('P')
R = TypeVar('R')


def patch_cos_tool_path(func: Callable[P, R]) -> Callable[P, R]:
    """Patch cos tool path.

    Downloads from GitHub, if it does not exist locally.
    Updates CosTool class internal `_path`, otherwise it will always look in CWD
    (execution directory).

    Returns:
        Patch object for CosTool class in both prometheus_scrape and prometheus_remote_write
    """
    cos_path = PROJECT_DIR / 'cos-tool-amd64'
    if not cos_path.exists():
        logging.debug('cos-tool was not found, download it')
        with requests.get(COS_TOOL_URL, stream=True, timeout=10) as r:
            r.raise_for_status()
            with open(cos_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024):
                    f.write(chunk)

    cos_path.chmod(0o777)

    # Patch the installed cosl.CosTool implementation so tests use the
    # downloaded binary instead of looking for it in CWD.
    path = patch.object(target=_CosTool, attribute='_path', new=str(cos_path))

    @wraps(func)
    def wrapper_decorator(*args: P.args, **kwargs: P.kwargs) -> R:
        with path:
            value = func(*args, **kwargs)
        return value

    return wrapper_decorator
