import socket
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from port_utils import find_free_port


def test_returns_a_bindable_port():
    port = find_free_port(preferred=0)
    assert 1024 <= port <= 65535
    # Verify the port is actually free right now (find_free_port closed its socket)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
    finally:
        s.close()


def test_falls_back_when_preferred_is_busy():
    # Occupy a port, then ask find_free_port for the same preferred port.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    busy_port = s.getsockname()[1]
    s.listen(1)
    try:
        free = find_free_port(preferred=busy_port)
        assert free != busy_port
        # The fallback should itself be bindable
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s2.bind(("127.0.0.1", free))
        finally:
            s2.close()
    finally:
        s.close()


def test_raises_runtime_error_if_all_ports_busy():
    # Occupy the preferred port, then ask with max_tries=0 (zero additional tries).
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 60000))
    blocker.listen(1)
    try:
        try:
            find_free_port(preferred=60000, max_tries=0)
            assert False, "Should have raised RuntimeError"
        except RuntimeError:
            pass
    finally:
        blocker.close()