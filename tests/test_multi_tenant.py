from fastapi.testclient import TestClient

from agentiva.api import server
from agentiva.auth.tenancy import TenantManager


def test_tenant_manager_register_and_lookup() -> None:
    manager = TenantManager()
    manager.register_tenant("t1", "Tenant One", "key-1")
    tenant = manager.tenant_from_key("key-1")
    assert tenant.tenant_id == "t1"


def test_tenant_manager_invalid_key() -> None:
    manager = TenantManager()
    manager.register_tenant("t1", "Tenant One", "key-1")
    try:
        manager.tenant_from_key("bad")
        assert False, "Expected KeyError for invalid API key"
    except KeyError:
        assert True


def test_api_key_auth_enforced_when_tenancy_enabled() -> None:
    # Enable tenancy at runtime for this test.
    server._tenant_manager.register_tenant("test-tenant", "Test Tenant", "tenant-key")
    try:
        with TestClient(server.app) as client:
            no_key = client.get("/api/v1/metrics")
            assert no_key.status_code == 401
            with_key = client.get("/api/v1/metrics", headers={"X-Agentiva-Key": "tenant-key"})
            assert with_key.status_code == 200
    finally:
        server._tenant_manager._tenants_by_key.clear()
        server._tenant_manager._tenants_by_id.clear()


def test_tenant_isolation_smoke() -> None:
    manager = TenantManager()
    manager.register_tenant("a", "A", "key-a")
    manager.register_tenant("b", "B", "key-b")
    assert manager.tenant_from_key("key-a").tenant_id != manager.tenant_from_key("key-b").tenant_id
