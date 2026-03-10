from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional
import glob
import time

try:
    import serial
    import serial.tools.list_ports
except Exception as exc:  # pragma: no cover
    serial = None
    _SERIAL_IMPORT_ERROR = exc
else:
    _SERIAL_IMPORT_ERROR = None


@dataclass
class SerialPortInfo:
    device: str
    name: Optional[str] = None
    description: Optional[str] = None
    hwid: Optional[str] = None
    vid: Optional[int] = None
    pid: Optional[int] = None
    manufacturer: Optional[str] = None
    product: Optional[str] = None
    serial_number: Optional[str] = None
    location: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def pyserial_available() -> bool:
    return serial is not None


def require_pyserial() -> None:
    if serial is None:
        raise RuntimeError(f"pyserial is required but unavailable: {_SERIAL_IMPORT_ERROR}")


def list_candidate_device_paths() -> list[str]:
    return sorted(set(glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')))


def list_serial_devices() -> list[SerialPortInfo]:
    if serial is None:
        return [SerialPortInfo(device=path) for path in list_candidate_device_paths()]

    ports = []
    for port in serial.tools.list_ports.comports():
        ports.append(
            SerialPortInfo(
                device=port.device,
                name=port.name,
                description=port.description,
                hwid=port.hwid,
                vid=port.vid,
                pid=port.pid,
                manufacturer=port.manufacturer,
                product=port.product,
                serial_number=port.serial_number,
                location=port.location,
            )
        )
    return ports


class SerialPotentiostat:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[Any] = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def connect(self) -> None:
        require_pyserial()
        if self.is_connected:
            return
        self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)

    def disconnect(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def reset_input_buffer(self) -> None:
        if not self.is_connected:
            raise RuntimeError('Device is not connected')
        self._serial.reset_input_buffer()

    def write_raw(self, payload: bytes) -> int:
        if not self.is_connected:
            raise RuntimeError('Device is not connected')
        return self._serial.write(payload)

    def read_raw(self, size: int = 256) -> bytes:
        if not self.is_connected:
            raise RuntimeError('Device is not connected')
        return self._serial.read(size)

    def read_available(self, wait_seconds: float = 0.0, max_bytes: int = 4096) -> bytes:
        if not self.is_connected:
            raise RuntimeError('Device is not connected')
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        waiting = self._serial.in_waiting
        return self._serial.read(min(waiting if waiting > 0 else max_bytes, max_bytes))

    def query(self, payload: bytes, wait_seconds: float = 0.2, max_bytes: int = 4096) -> bytes:
        if not self.is_connected:
            raise RuntimeError('Device is not connected')
        self.reset_input_buffer()
        self.write_raw(payload)
        return self.read_available(wait_seconds=wait_seconds, max_bytes=max_bytes)

    def __enter__(self) -> 'SerialPotentiostat':
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()
