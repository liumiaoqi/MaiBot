"""WebSocket 域注册表单元测试"""

from src.webui.routers.websocket.domains import WSDomain, WSDomainRegistry


def test_register_and_get():
    registry = WSDomainRegistry()

    async def handler(cid, rid):
        pass

    domain = WSDomain(name="test", event_types={"a", "b"}, subscribe_handler=handler)
    registry.register(domain)

    assert registry.get("test") is domain
    assert registry.get("nonexistent") is None


def test_list_domains():
    registry = WSDomainRegistry()

    async def handler(cid, rid):
        pass

    registry.register(WSDomain(name="logs", event_types={"entry"}, subscribe_handler=handler))
    registry.register(WSDomain(name="chat", event_types={"message"}, subscribe_handler=handler))

    domains = registry.list_domains()
    assert set(domains) == {"logs", "chat"}


def test_overwrite_domain():
    registry = WSDomainRegistry()

    async def handler_v1(cid, rid):
        pass

    async def handler_v2(cid, rid):
        pass

    registry.register(WSDomain(name="test", event_types={"a"}, subscribe_handler=handler_v1))
    registry.register(WSDomain(name="test", event_types={"b"}, subscribe_handler=handler_v2))

    domain = registry.get("test")
    assert domain.event_types == {"b"}