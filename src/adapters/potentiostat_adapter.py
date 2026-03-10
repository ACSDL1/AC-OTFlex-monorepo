from __future__ import annotations

import asyncio
import glob
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import serial
    import serial.tools.list_ports
except Exception as exc:  # pragma: no cover
    serial = None
    _SERIAL_IMPORT_ERROR = exc
else:
    _SERIAL_IMPORT_ERROR = None


class PotentiostatAdapter:
    """Adapter for STM32 serial potentiostats used by SDL1 workflow nodes.

    The current implementation focuses on robust connectivity/protocol verification
    and a minimal measurement handshake. It can be used as a drop-in backend for
    sdl1ElectrochemicalMeasurement nodes while full chemistry routines are built.
    """

    CMD_READ_ADC = 1
    CMD_READ_GAIN = 16
    CMD_READ_SWITCH = 17

    ADC_WE_OUT = 0
    ADC_RE_OUT = 1
    ADC_VREF = 2
    ADC_TEMP = 3
    ADC_HUMID = 4

    GAIN_LABELS = {0: "100 Ω", 1: "1 kΩ", 2: "10 kΩ", 3: "100 kΩ", 4: "1 MΩ"}

    def __init__(self, device_cfg: Dict[str, Any] | None, root_dir: Path):
        self.device_cfg = device_cfg or {}
        self.root_dir = root_dir

        self.baudrate = int(self.device_cfg.get("baudrate", 115200))
        self.timeout_s = float(self.device_cfg.get("timeout_s", 2.0))
        self.device_id = int(self.device_cfg.get("device_id", 1))
        self.strict = bool(self.device_cfg.get("strict", False))

        self.expected_ports = self._resolve_expected_ports(self.device_cfg)

    async def connect(self):
        if serial is None:
            msg = f"[Potentiostat] pyserial unavailable: {_SERIAL_IMPORT_ERROR}"
            if self.strict:
                raise RuntimeError(msg)
            print(msg)
            return
        print(
            f"[Potentiostat] Ready (baud={self.baudrate}, timeout={self.timeout_s}s, "
            f"device_id={self.device_id}, expected_ports={self.expected_ports})"
        )

    async def disconnect(self):
        return

    async def echem_measure(self, p: Dict[str, Any]):
        result = await asyncio.to_thread(self.run_measurement_probe, p)
        if self.strict and not result.get("ok", False):
            raise RuntimeError(f"Potentiostat probe failed: {result}")
        return result

    def run_measurement_probe(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if serial is None:
            return {
                "ok": False,
                "error": f"pyserial unavailable: {_SERIAL_IMPORT_ERROR}",
                "ports": [],
            }

        ports = self._ports_from_params(params)
        checks = []
        for port in ports:
            open_res = self._open_close_test(port)
            ping_res = self._firmware_ping(port) if open_res["opened"] else None
            adc_res = self._read_adc_channels(port, [self.ADC_VREF, self.ADC_RE_OUT]) if (ping_res and ping_res.get("alive")) else None
            checks.append({
                "port": port,
                "open": open_res,
                "ping": ping_res,
                "adc": adc_res,
            })

        ok = all(c["open"].get("opened") and c.get("ping", {}).get("alive") for c in checks)

        uo_name = params.get("uo_name") or params.get("measurement_type") or "ElectrochemicalMeasurement"
        print(f"[Potentiostat] {uo_name}: probing {len(ports)} port(s)")
        for c in checks:
            ping = c.get("ping") or {}
            status = "OK" if c["open"].get("opened") and ping.get("alive") else "FAIL"
            print(
                f"  - {c['port']}: {status}; "
                f"open_err={c['open'].get('error')} "
                f"ping_err={ping.get('error')}"
            )

        return {
            "ok": ok,
            "ports": ports,
            "checks": checks,
            "params_echo": {
                "uo_name": params.get("uo_name"),
                "measurement_type": params.get("measurement_type"),
                "com_port": params.get("com_port"),
                "channel": params.get("channel"),
                "sequence_enabled": params.get("sequence_enabled"),
            },
        }

    def smoke_test(self) -> Dict[str, Any]:
        detected_acm = sorted(glob.glob("/dev/ttyACM*"))
        detected_usb = sorted(glob.glob("/dev/ttyUSB*"))
        missing = [p for p in self.expected_ports if p not in detected_acm]
        open_results = [self._open_close_test(p) for p in self.expected_ports]
        return {
            "expected_ports": self.expected_ports,
            "detected_acm": detected_acm,
            "detected_usb": detected_usb,
            "missing": missing,
            "open_results": open_results,
        }

    def list_serial_devices(self) -> List[Dict[str, Any]]:
        if serial is None:
            return []
        rows: List[Dict[str, Any]] = []
        for p in serial.tools.list_ports.comports():
            rows.append(
                {
                    "device": p.device,
                    "description": p.description,
                    "hwid": p.hwid,
                    "vid": p.vid,
                    "pid": p.pid,
                    "manufacturer": p.manufacturer,
                    "product": p.product,
                    "serial_number": p.serial_number,
                    "location": p.location,
                }
            )
        return rows

    def _resolve_expected_ports(self, cfg: Dict[str, Any]) -> List[str]:
        ports = cfg.get("ports")
        if isinstance(ports, list) and ports:
            return [str(p) for p in ports]

        if Path("/dev").exists():
            count = int(cfg.get("count", 4))
            prefix = str(cfg.get("port_prefix", "/dev/ttyACM"))
            return [f"{prefix}{i}" for i in range(count)]

        return [str(cfg.get("com_port", "COM10"))]

    def _ports_from_params(self, params: Dict[str, Any]) -> List[str]:
        configs = params.get("potentiostat_configs")
        if isinstance(configs, list) and configs:
            ports = [str(c.get("com_port")) for c in configs if c.get("com_port")]
            if ports:
                return ports

        if params.get("com_port"):
            return [str(params["com_port"])]

        return self.expected_ports

    def _open_close_test(self, port: str) -> Dict[str, Any]:
        result = {"port": port, "opened": False, "error": None}
        if serial is None:
            result["error"] = f"pyserial unavailable: {_SERIAL_IMPORT_ERROR}"
            return result

        try:
            with serial.Serial(port, baudrate=self.baudrate, timeout=self.timeout_s) as ser:
                result["opened"] = bool(ser.is_open)
        except Exception as exc:
            result["error"] = repr(exc)
        return result

    def _firmware_ping(self, port: str) -> Dict[str, Any]:
        result = {
            "port": port,
            "alive": False,
            "switch_on": None,
            "gain": None,
            "gain_label": None,
            "error": None,
        }
        if serial is None:
            result["error"] = f"pyserial unavailable: {_SERIAL_IMPORT_ERROR}"
            return result

        try:
            with serial.Serial(port, baudrate=self.baudrate, timeout=self.timeout_s) as ser:
                ser.reset_input_buffer()

                ser.write(bytes([self.device_id, self.CMD_READ_SWITCH]))
                resp = ser.read(1)
                if len(resp) != 1:
                    result["error"] = f"READ_SWITCH timeout: {len(resp)} bytes"
                    return result
                result["switch_on"] = bool(resp[0])

                ser.write(bytes([self.device_id, self.CMD_READ_GAIN, 0]))
                resp = ser.read(1)
                if len(resp) != 1:
                    result["error"] = f"READ_GAIN timeout: {len(resp)} bytes"
                    return result

                gain = int(resp[0])
                result["gain"] = gain
                result["gain_label"] = self.GAIN_LABELS.get(gain, f"unknown({gain})")
                result["alive"] = True
        except Exception as exc:
            result["error"] = repr(exc)
        return result

    def _read_adc_channels(self, port: str, channels: List[int]) -> Dict[str, Any]:
        out = {"port": port, "readings": {}, "error": None}
        if serial is None:
            out["error"] = f"pyserial unavailable: {_SERIAL_IMPORT_ERROR}"
            return out

        ch_names = {
            self.ADC_WE_OUT: "WE_OUT",
            self.ADC_RE_OUT: "RE_OUT",
            self.ADC_VREF: "VREF",
            self.ADC_TEMP: "TEMP",
            self.ADC_HUMID: "HUMID",
        }

        try:
            with serial.Serial(port, baudrate=self.baudrate, timeout=self.timeout_s) as ser:
                ser.reset_input_buffer()
                for ch in channels:
                    ser.write(bytes([self.device_id, self.CMD_READ_ADC, ch]))
                    payload = ser.read(4)
                    key = ch_names.get(ch, str(ch))
                    if len(payload) != 4:
                        out["readings"][key] = "TIMEOUT"
                        continue
                    raw_v = float(struct.unpack("<f", payload)[0])
                    scaled_v = self._scale_adc(raw_v) if ch not in (self.ADC_TEMP, self.ADC_HUMID) else raw_v
                    out["readings"][key] = {
                        "raw_V": round(raw_v, 4),
                        "scaled_V": round(scaled_v, 4),
                    }
        except Exception as exc:
            out["error"] = repr(exc)
        return out

    @staticmethod
    def _scale_adc(raw_v: float) -> float:
        # 0..3.3V maps to -5..+5V on this firmware family
        return ((raw_v / 3.3) * 10.0) - 5.0
