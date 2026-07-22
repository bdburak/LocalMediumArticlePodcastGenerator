import socket


def find_free_port(preferred: int = 0, max_tries: int = 100) -> int:
    """Find a free TCP port, preferring a specific port and scanning upward.

    Args:
        preferred: Port to try first. If 0, the OS picks any free port.
        max_tries: Number of additional ports to try (scanning upward from
            preferred+1) if `preferred` is busy. Ignored if preferred == 0.

    Returns:
        A port number that was bindable at the moment of the call.

    Raises:
        RuntimeError: If no port could be bound within the try range.
    """
    if preferred == 0:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
        finally:
            s.close()

    for offset in range(max_tries + 1):
        candidate = preferred + offset
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", candidate))
            return candidate
        except OSError:
            continue
        finally:
            s.close()

    raise RuntimeError(
        f"No free port found in range {preferred}-{preferred + max_tries}"
    )