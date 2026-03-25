from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class Tenant:
    tenant_id: str
    name: str
    api_key: str


class TenantManager:
    """Support multiple organizations using the same Agentiva instance."""

    def __init__(self):
        self._tenants_by_key: Dict[str, Tenant] = {}
        self._tenants_by_id: Dict[str, Tenant] = {}

    def register_tenant(self, tenant_id: str, name: str, api_key: str) -> Tenant:
        tenant = Tenant(tenant_id=tenant_id, name=name, api_key=api_key)
        self._tenants_by_key[api_key] = tenant
        self._tenants_by_id[tenant_id] = tenant
        return tenant

    def tenant_from_key(self, api_key: str) -> Tenant:
        if api_key not in self._tenants_by_key:
            raise KeyError("Invalid API key")
        return self._tenants_by_key[api_key]

    def is_enabled(self) -> bool:
        return bool(self._tenants_by_key)
