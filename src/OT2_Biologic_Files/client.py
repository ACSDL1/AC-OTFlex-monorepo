# client.py
import socket
import pickle
import struct

HOST = "127.0.0.1"
PORT = 6001


def send_msg(sock, obj):
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    header = struct.pack("!I", len(data))
    sock.sendall(header + data)


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def recv_msg(sock):
    header = recv_exact(sock, 4)
    if header is None:
        return None
    (length,) = struct.unpack("!I", header)
    payload = recv_exact(sock, length)
    if payload is None:
        return None
    return pickle.loads(payload)


def biologic_stream(channel: int, techniques: list, usb_port: str = "USB0"):
    """
    Generator that:
      - connects to dummy host
      - sends a job (channel, usb_port, techniques)
      - yields one 'payload' per data message (here, a dict)
      - stops on 'done' or 'error'
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))

    job = {
        "usb_port": usb_port,
        "channel": int(channel),
        "techniques": techniques,
    }
    send_msg(sock, job)

    try:
        while True:
            msg = recv_msg(sock)
            if msg is None:
                break

            msg_type = msg.get("type")

            if msg_type == "data":
                # In the dummy host, payload is a dict:
                #   {"channel": ..., "t": ..., "value": ..., "step": ...}
                yield msg["payload"]
            elif msg_type == "done":
                break
            elif msg_type == "error":
                err = msg.get("error", "Unknown error")
                tb = msg.get("traceback", "")
                raise RuntimeError(f"Dummy host error: {err}\n{tb}")
            else:
                break
    finally:
        try:
            sock.close()
        except Exception:
            pass
