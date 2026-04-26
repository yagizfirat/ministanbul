"""ASGI wiring smoke — Faz 3 Adım 6b. Verifies ProtocolTypeRouter is built
with both http and websocket protocols. Echo + VehicleAll consumers come later."""


def test_application_imports():
    from config.asgi import application

    assert application is not None


def test_application_mapping_has_http_and_websocket():
    from config.asgi import application

    assert "http" in application.application_mapping
    assert "websocket" in application.application_mapping
