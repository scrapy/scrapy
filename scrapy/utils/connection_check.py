import socket

def is_port_open(host: str = "127.0.0.1", port: int = 80, timeout: float = 1.0) -> bool:
    """
    Check if a network port is open.
    Returns True if connection succeeds, otherwise False.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    print(is_port_open("example.com", 80))  # Expected: True
