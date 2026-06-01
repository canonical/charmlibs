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

"""Tests for the example-interface testing library from a provider charm perspective."""

import ops.testing

import provider_charm
from charmlibs.interfaces import example_interface as example_interface
from charmlibs.interfaces import example_interface_testing as example_interface_testing


def test_provider_no_relation():
    """Test provider charm without any relation as a sanity check."""
    ctx = ops.testing.Context(provider_charm.ProviderCharm, meta=provider_charm.META)
    with ctx(ctx.on.update_status(), ops.testing.State()) as manager:
        manager.run()
    # FIXME: Assert something about the charm.


def test_provider_relation_default():
    """Test provider charm when the relation is populated with defaults."""
    ctx = ops.testing.Context(provider_charm.ProviderCharm, meta=provider_charm.META)
    relation = example_interface_testing.relation_for_provider('endpoint')
    state = ops.testing.State(relations=[relation])
    with ctx(ctx.on.update_status(), state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.


def test_provider_relation_variant():
    """Test provider charm when the relation is populated with some non-default argument."""
    ctx = ops.testing.Context(provider_charm.ProviderCharm, meta=provider_charm.META)
    relation = example_interface_testing.relation_for_provider(
        'endpoint',  # FIXME: Test a variant by providing some non-default arguments.
    )
    state_in = ops.testing.State(relations=[relation])
    with ctx(ctx.on.update_status(), state_in) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.
