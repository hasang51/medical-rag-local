import socket

import pytest


@pytest.fixture(autouse=True)
def block_outbound_sockets(request, monkeypatch):
    """İşaretsiz testler ağa çıkamaz. Canlı Ollama testleri ayrı çalışır."""
    if request.node.get_closest_marker("ollama"):
        return

    def blocked(*args, **kwargs):
        raise AssertionError("birim testi ağ açmamalı")

    monkeypatch.setattr(socket, "create_connection", blocked)
