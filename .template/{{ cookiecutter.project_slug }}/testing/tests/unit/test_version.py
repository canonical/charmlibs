# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.


from charmlibs.interfaces import {{ cookiecutter.__pkg }} as {{ cookiecutter.__pkg }}
from charmlibs.interfaces import {{ cookiecutter.__pkg }}_testing as {{ cookiecutter.__pkg }}_testing


def test_versions_match():
    assert {{ cookiecutter.__pkg }}_testing.__version__ == {{ cookiecutter.__pkg }}.__version__
