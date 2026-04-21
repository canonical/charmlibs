# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from ops import testing

from charmlibs.interfaces import {{ cookiecutter.__pkg }} as {{ cookiecutter.__pkg }}
from charmlibs.interfaces import {{ cookiecutter.__pkg }}_testing as {{ cookiecutter.__pkg }}_testing


def test_local_provider():
    rel = {{ cookiecutter.__pkg }}_testing.relation_for_provider('foo')
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == 'foo'
    assert rel.interface == '{{ cookiecutter.project_slug }}'


def test_local_requirer():
    rel = {{ cookiecutter.__pkg }}_testing.relation_for_requirer('bar')
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == 'bar'
    assert rel.interface == '{{ cookiecutter.project_slug }}'
