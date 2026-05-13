#!/usr/bin/env python3
"""
Real Biologic host server.

Listens for client requests, runs techniques on specified Biologic channels,
and streams data back to clients in real time.
"""

import socket
import threading
import pickle
import struct
import traceback
import logging
import os
from logging.handlers import RotatingFileHandler

from biologic import connect, BANDWIDTH, I_RANGE, E_RANGE
from biologic.techniques.ocv import OCVTechnique, OCVParams, OCVData
from biologic.techniques.peis import PEISTechnique, PEISParams, SweepMode, PEISData
from biologic.techniques.ca import CATechnique, CAParams, CAStep, CAData
from biologic.techniques.cpp import CPPTechnique, CPPParams, CPPData
from biologic.techniques.pzir import PZIRTechnique, PZIRParams, PZIRData
from biologic.techniques.cv import CVTechnique, CVParams, CVStep, CVData
from biologic.techniques.lp import LPTechnique, LPParams, LPStep, LPData
from biologic.techniques.cp import CPTechnique, CPParams, CPStep, CPData

import datetime

HOST = "127.0.0.1"
PORT = 6001
MAX_CHANNELS = 4
LOG_FILE = "biologic_host.log"


# Per-channel locks so different threads don't share the same channel at once
channel_locks = {ch: threading.Lock() for ch in range(1, MAX_CHANNELS + 1)}

# Global Biologic connection and USB port info
biologic = None
current_usb_port = None
biologic_lock = threading.Lock()  # protects (biologic, current_usb_port)

# Setup logging to append to file only for [HOST] logs
def setup_logging():
    """Configure logging to write [HOST] logs to file only, keeping library logs on console."""
    # Create a custom logger for [HOST] messages only
    host_logger = logging.getLogger('biologic_host')
    host_logger.setLevel(logging.DEBUG)
    host_logger.propagate = False  # Don't propagate to root logger
    
    # File handler - appends to file without overwriting
    file_handler = logging.FileHandler(LOG_FILE, mode='a')
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler - for displaying [HOST] messages
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add both handlers to host logger
    host_logger.addHandler(file_handler)
    host_logger.addHandler(console_handler)
    
    # Keep root logger for biologic library logs (they'll go to console via their own handlers)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)


def send_msg(sock, obj):
    """Serialize `obj` and send it with a 4-byte length prefix."""
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    header = struct.pack("!I", len(data))
    sock.sendall(header + data)


def recv_exact(sock, n):
    """Receive exactly n bytes or return None if the connection closes prematurely."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def recv_msg(sock):
    """Receive one length-prefixed pickled object."""
    header = recv_exact(sock, 4)
    if header is None:
        return None
    (length,) = struct.unpack("!I", header)
    payload = recv_exact(sock, length)
    if payload is None:
        return None
    return pickle.loads(payload)


def handle_client_job(client_sock: socket.socket):
    """
    Handle a single client connection:
      - receive job (usb_port, channel, techniques)
      - ensure Biologic is connected on correct USB port
      - run techniques on given channel
      - stream data back as 'type': 'data'
      - send final 'type': 'done'
      - send 'type': 'error' on exceptions
    """
    global biologic, current_usb_port
    host_logger = logging.getLogger('biologic_host')

    try:
        job = recv_msg(client_sock)
        if job is None:
            # Client disconnected before sending a job
            return

        usb_port = job.get("usb_port", "USB0")
        channel_id = int(job["channel"])
        techniques = job["techniques"]

        # Validate channel
        if channel_id not in channel_locks:
            raise ValueError(f"Invalid channel {channel_id}")

        host_logger.info(
            f"[HOST] Job received: usb_port={usb_port}, "
            f"channel={channel_id}, techniques={len(techniques)}"
        )

        # Ensure Biologic connection is open and on the correct USB port
        with biologic_lock:
            if biologic is None or usb_port != current_usb_port:
                # Close any previous connection if present
                if biologic is not None:
                    try:
                        host_logger.info(f"[HOST] Closing Biologic on {current_usb_port}...")
                        biologic.close()
                    except Exception:
                        pass

                host_logger.info(f"[HOST] Connecting Biologic on {usb_port}...")

                biologic = connect(usb_port)
                current_usb_port = usb_port

                host_logger.info(f"[HOST] Connected to Biologic on {usb_port}.")

        # Run techniques on chosen channel, one job at a time per channel
        chan_lock = channel_locks[channel_id]
        with chan_lock:
            channel = biologic.get_channel(channel_id)
            runner = channel.run_techniques(techniques)

            # Stream each data_temp back to the client
            for data_temp in runner:
                try:
                    send_msg(
                        client_sock,
                        {
                            "type": "data",
                            "channel": channel_id,
                            "payload": data_temp,
                        },
                    )
                except Exception:
                    # Client disconnected mid-job
                    host_logger.info(
                        f"[HOST] Client disconnected during job on channel {channel_id}"
                    )
                    return

        # If we exit the loop normally, signal completion
        try:
            send_msg(client_sock, {"type": "done", "channel": channel_id})
        except Exception:
            # If we can't send 'done', client is gone; nothing more to do
            pass

        host_logger.info(f"[HOST] Finished streaming job on channel {channel_id}.")

    except Exception as e:
        # Any error in this worker: log to console and notify client
        tb = traceback.format_exc()
        host_logger.error("[HOST] Error in job handler:", exc_info=True)
        host_logger.info(tb)
        try:
            send_msg(
                client_sock,
                {"type": "error", "error": str(e), "traceback": tb},
            )
        except Exception:
            # If the client is gone, we just swallow this
            pass

    finally:
        try:
            client_sock.close()
        except Exception:
            pass


def main():
    """Main server loop: accept clients and spawn worker threads."""
    global biologic

    # Setup logging first
    setup_logging()
    host_logger = logging.getLogger('biologic_host')
    host_logger.info("-"*70)
    host_logger.info("[HOST] Biologic host starting...")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(10)

    host_logger.info(f"[HOST] Listening on {HOST}:{PORT}")

    try:
        while True:
            client_sock, addr = server.accept()
            host_logger.info(f"[HOST] Client from {addr}")
            t = threading.Thread(
                target=handle_client_job, args=(client_sock,), daemon=True
            )
            t.start()
    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C in the host terminal
        host_logger.info("\n[HOST] KeyboardInterrupt received. Shutting down...")
    finally:
        # Close listening socket
        try:
            server.close()
        except Exception:
            pass

        # Close Biologic connection if open
        if biologic is not None:
            try:
                host_logger.info(f"[HOST] Closing Biologic on {current_usb_port}...")
                biologic.close()
            except Exception:
                pass
            biologic = None

        host_logger.info("[HOST] Biologic host stopped.")


if __name__ == "__main__":
    main()
