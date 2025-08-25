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

"""Ensure that the test charms aren't out of sync."""

from __future__ import annotations

import pathlib

BASES = ['20.04', '24.04']


def test_bases():
    k = pathlib.Path(__file__).parent / 'charms' / 'k8s'
    kb = sorted(p.name for p in k.glob('*-charmcraft.yaml'))
    bases = [b.split('-')[0] for b in kb]
    assert bases == BASES
