# Copyright 2025 Canonical
# See LICENSE file for licensing details.
"""Tracer for the nginx package."""

from opentelemetry import trace

tracer = trace.get_tracer('nginx_k8s')
