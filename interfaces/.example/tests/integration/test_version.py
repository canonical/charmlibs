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

"""Integration tests using real Juju and pre-packed charm(s)."""

import jubilant

from charmlibs.interfaces import example_interface


def test_deploy(juju: jubilant.Juju, provider: str, requirer: str):
    """The deployment takes place in the module scoped `juju` fixture."""
    assert provider in juju.status().apps
    assert requirer in juju.status().apps


def test_relate(juju: jubilant.Juju, provider: str, requirer: str):
    juju.integrate(f'{provider}:endpoint', f'{requirer}:endpoint')
    juju.wait(jubilant.all_active)
    relations = juju.status().apps[provider].relations['endpoint']
    assert any(relation.related_app == requirer for relation in relations)


def test_lib_version(juju: jubilant.Juju, provider: str, requirer: str):
    for app in (provider, requirer):
        result = juju.run(f'{app}/0', 'lib-version')
        assert result.results['version'] == example_interface.__version__
