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

"""The charmlibs.passwd package."""

from ._passwd import (
    add_group,
    add_user,
    add_user_to_group,
    group_exists,
    remove_group,
    remove_user,
    user_exists,
)
from ._version import __version__ as __version__

__all__ = [
    'add_group',
    'add_user',
    'add_user_to_group',
    'group_exists',
    'remove_group',
    'remove_user',
    'user_exists',
]
