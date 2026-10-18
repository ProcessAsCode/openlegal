"""UAPF-IP integration.

Host side (engine -> host):
  * manifest.py   - capability registry (single source of truth)
  * dispatcher.py - engine -> host capability dispatch with invocation logging
  * dmn.py        - minimal DMN decision-table evaluator
  * handlers/     - one module per capability family

Client side (host -> engine):
  * client.py     - UapfClient async wrapper over UAPF-IP v0.1 REST
  * bridge.py     - start_uapf_run + engine_reachable + build_host_manifest
"""

from openlegal.uapf.bridge import (
    build_host_manifest,
    engine_reachable,
    start_uapf_run,
)
from openlegal.uapf.client import UapfClient, UapfEngineError
from openlegal.uapf.dispatcher import UnknownCapabilityError, dispatch
from openlegal.uapf.manifest import (
    CapabilityDescriptor,
    CapabilityHandler,
    get_handler,
    get_registry,
    manifest_dict,
)


__all__ = [
    # Host side
    "CapabilityDescriptor",
    "CapabilityHandler",
    "UnknownCapabilityError",
    "dispatch",
    "get_handler",
    "get_registry",
    "manifest_dict",
    # Client side
    "UapfClient",
    "UapfEngineError",
    "build_host_manifest",
    "engine_reachable",
    "start_uapf_run",
]
