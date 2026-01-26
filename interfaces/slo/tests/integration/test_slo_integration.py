#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for SLO provider/requirer functionality."""

import logging

import jubilant
import pytest
from jubilant import Juju

logger = logging.getLogger(__name__)

TIMEOUT = 600
PROVIDER = 'slo-test-provider'
REQUIRER = 'slo-test-requirer'


@pytest.mark.setup
def test_setup_provider(juju: Juju, slo_provider_charm: str) -> None:
    """Deploy the SLO provider test charm."""
    juju.deploy(
        slo_provider_charm,
        PROVIDER,
        resources={'workload': 'ubuntu:latest'},
        config={
            'slo-service-name': 'test-service',
            'slo-objective': '99.9',
        },
    )

    juju.wait(
        lambda status: PROVIDER in status.apps and status.apps[PROVIDER].is_active,
        error=jubilant.any_error,
        delay=10,
        successes=1,
        timeout=TIMEOUT,
    )


@pytest.mark.setup
def test_setup_requirer(juju: Juju, slo_requirer_charm: str) -> None:
    """Deploy the SLO requirer test charm."""
    juju.deploy(
        slo_requirer_charm,
        REQUIRER,
        resources={'workload': 'ubuntu:latest'},
    )

    juju.wait(
        lambda status: REQUIRER in status.apps and status.apps[REQUIRER].is_active,
        error=jubilant.any_error,
        delay=10,
        successes=1,
        timeout=TIMEOUT,
    )


def test_provider_can_provide_slos(juju: Juju) -> None:
    """Test that provider charm can provide SLOs without errors."""
    # Provider should be active after setup
    status = juju.status()
    assert PROVIDER in status.apps
    assert status.apps[PROVIDER].is_active
    logger.info('Provider status: %s', status.apps[PROVIDER].app_status)


def test_requirer_can_be_related(juju: Juju) -> None:
    """Test that provider and requirer can be related."""
    # Relate the provider to the requirer
    juju.integrate(f'{PROVIDER}:slos', f'{REQUIRER}:slos')

    juju.wait(
        lambda status: (status.apps[PROVIDER].is_active and status.apps[REQUIRER].is_active),
        delay=10,
        successes=2,
        timeout=TIMEOUT,
    )

    status = juju.status()
    logger.info('Provider status after relation: %s', status.apps[PROVIDER].app_status)
    logger.info('Requirer status after relation: %s', status.apps[REQUIRER].app_status)


def test_requirer_receives_slos(juju: Juju) -> None:
    """Test that requirer receives SLOs from provider."""
    # Use the get-slos action to verify SLOs were received
    result = juju.run(f'{REQUIRER}/0', 'get-slos')

    # Action results are in result.results dict
    count = int(result.results.get('count', '0'))
    assert count > 0, f'No SLOs received from provider. Results: {result.results}'

    # Verify the service name
    services = result.results.get('services', '')
    assert 'test-service' in services, f"Expected 'test-service' in services, got: {services}"

    logger.info('Received %s SLO(s) for services: %s', count, services)


def test_provider_config_update(juju: Juju) -> None:
    """Test that updating provider config updates the SLO."""
    # Update the provider configuration
    juju.config(
        PROVIDER,
        {
            'slo-service-name': 'updated-service',
            'slo-objective': '99.5',
        },
    )

    juju.wait(
        lambda status: status.apps[PROVIDER].is_active,
        delay=10,
        successes=2,
        timeout=TIMEOUT,
    )

    # Verify the requirer received the updated SLO
    result = juju.run(f'{REQUIRER}/0', 'get-slos')

    # Action results are in result.results dict
    services = result.results.get('services', '')
    assert 'updated-service' in services, (
        f"Expected 'updated-service' in services, got: {services}"
    )

    logger.info('Updated SLO services: %s', services)


def test_multiple_providers(juju: Juju, slo_provider_charm: str) -> None:
    """Test that requirer can handle multiple providers."""
    # Deploy a second provider with different config
    provider2 = 'slo-provider-second'  # Changed to avoid -2 suffix which Juju doesn't allow
    juju.deploy(
        slo_provider_charm,
        provider2,
        resources={'workload': 'ubuntu:latest'},
        config={
            'slo-service-name': 'second-service',
            'slo-objective': '99.0',
        },
    )

    juju.wait(
        lambda status: provider2 in status.apps and status.apps[provider2].is_active,
        error=jubilant.any_error,
        delay=10,
        successes=1,
        timeout=TIMEOUT,
    )

    # Relate the second provider
    juju.integrate(f'{provider2}:slos', f'{REQUIRER}:slos')

    juju.wait(
        lambda status: status.apps[REQUIRER].is_active,
        delay=10,
        successes=2,
        timeout=TIMEOUT,
    )

    # Verify requirer received SLOs from both providers
    result = juju.run(f'{REQUIRER}/0', 'get-slos')

    # Action results are in result.results dict
    count = int(result.results.get('count', '0'))
    assert count >= 2, f'Expected at least 2 SLOs, got {count}'

    services = result.results.get('services', '')
    assert 'second-service' in services, f"Expected 'second-service' in services, got: {services}"

    logger.info('Received %s SLO(s) from multiple providers: %s', count, services)


def test_relation_removal(juju: Juju) -> None:
    """Test that removing relation stops SLO exchange."""
    import time
    
    # Remove the relation between provider and requirer
    juju.remove_relation(f'{PROVIDER}:slos', f'{REQUIRER}:slos')

    juju.wait(
        lambda status: (status.apps[PROVIDER].is_active and status.apps[REQUIRER].is_active),
        delay=10,
        successes=2,  # Wait for 2 consecutive successes to ensure relation cleanup
        timeout=TIMEOUT,
    )
    
    # Give Juju time to fully clean up relation data after relation-broken completes
    time.sleep(5)

    # Verify requirer no longer has SLOs from the first provider
    result = juju.run(f'{REQUIRER}/0', 'get-slos')

    # Action results are in result.results dict
    services = result.results.get('services', '')
    assert 'updated-service' not in services, (
        f"Should not have 'updated-service' after relation removal, got: {services}"
    )

    logger.info('After relation removal, services: %s', services)


@pytest.mark.teardown
def test_teardown(juju: Juju) -> None:
    """Clean up deployed charms."""
    status = juju.status()

    for app_name in [PROVIDER, 'slo-provider-second', REQUIRER]:
        if app_name in status.apps:
            juju.remove_application(app_name)
