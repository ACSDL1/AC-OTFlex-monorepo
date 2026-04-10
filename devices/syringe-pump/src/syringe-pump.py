from matterlab_pumps import RunzePump
import csv
from pathlib import Path
import serial
import serial.tools.list_ports
from typing import Dict, List, Optional

FTDI_FT232R_VID = 0x0403
FTDI_FT232R_PID = 0x6001
PUMP_CHANNEL_COUNT = 12
DEFAULT_SYRINGE_VOLUME_L = 5e-3
MAIN_HEADER = "MAIN"
OUT_HEADER = "OUT"


def find_pump_com_port():
    ports = serial.tools.list_ports.comports()

    # Prefer stable USB VID/PID matching across OSes.
    for port in ports:
        if port.vid == FTDI_FT232R_VID and port.pid == FTDI_FT232R_PID:
            return port.device

    # Fallback for systems/drivers that do not expose VID/PID.
    for port in ports:
        description = (port.description or "").lower()
        if "ft232r usb uart" in description:
            return port.device
    return None


def parse_pump_csv(csv_path: str, channel_count: int = PUMP_CHANNEL_COUNT) -> Dict[str, object]:
    """Parse a CSV recipe and infer MAIN/OUT valve ports from header names.

    CSV expectations:
    - Exactly 12 columns (one per channel/valve port).
    - Header row contains channel labels (for example chemical names).
    - Exactly one header is MAIN and exactly one header is OUT.
    - Each non-empty cell contains a volume in mL.
    - Empty cells are ignored.
    """
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    with csv_file.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV file is empty: {csv_file}") from exc

        if len(header) != channel_count:
            raise ValueError(
                f"CSV must have exactly {channel_count} header columns; found {len(header)}."
            )

        channel_labels = [
            label.strip() if label.strip() else f"channel_{index + 1}"
            for index, label in enumerate(header)
        ]
        normalized_labels = [label.upper() for label in channel_labels]

        main_indices = [index for index, label in enumerate(normalized_labels) if label == MAIN_HEADER]
        out_indices = [index for index, label in enumerate(normalized_labels) if label == OUT_HEADER]

        if len(main_indices) != 1:
            raise ValueError(
                f"CSV header must include exactly one '{MAIN_HEADER}' column; found {len(main_indices)}."
            )

        if len(out_indices) != 1:
            raise ValueError(
                f"CSV header must include exactly one '{OUT_HEADER}' column; found {len(out_indices)}."
            )

        main_port = main_indices[0] + 1
        out_port = out_indices[0] + 1

        operations: List[Dict[str, object]] = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) > channel_count:
                raise ValueError(
                    f"Row {row_number} has {len(row)} columns; expected at most {channel_count}."
                )

            for channel_index in range(channel_count):
                # MAIN and OUT define destination lines; they are not reagent source channels.
                if channel_index in (main_indices[0], out_indices[0]):
                    continue

                raw_value = row[channel_index].strip() if channel_index < len(row) else ""
                if not raw_value:
                    continue

                try:
                    volume_ml = float(raw_value)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid volume '{raw_value}' at row {row_number}, "
                        f"column {channel_index + 1} ({channel_labels[channel_index]})."
                    ) from exc

                if volume_ml <= 0:
                    continue

                operations.append(
                    {
                        "row": row_number,
                        "channel_label": channel_labels[channel_index],
                        "draw_valve_port": channel_index + 1,
                        "volume_ml": volume_ml,
                    }
                )

    return {
        "main_port": main_port,
        "out_port": out_port,
        "operations": operations,
    }


def connect_pump(
    com_port: Optional[str] = None,
    address: int = 0,
    syringe_volume_l: float = DEFAULT_SYRINGE_VOLUME_L,
    num_valve_port: int = PUMP_CHANNEL_COUNT,
) -> RunzePump:
    """Create a RunzePump instance, auto-detecting COM port when needed."""
    if com_port is None:
        com_port = find_pump_com_port()

    if com_port is None:
        raise RuntimeError("Could not find syringe pump COM port.")

    return RunzePump(
        com_port=com_port,
        address=address,
        syringe_volume=syringe_volume_l,
        num_valve_port=num_valve_port,
    )


def run_csv_protocol(
    csv_path: str,
    speed: float,
    pump: Optional[RunzePump] = None,
) -> Dict[str, object]:
    """Execute CSV-defined transfers and dispense all volumes to MAIN.

    MAIN and OUT ports are inferred from CSV header labels.
    OUT is returned for downstream functions that handle end-of-line output.
    """
    recipe = parse_pump_csv(csv_path, channel_count=PUMP_CHANNEL_COUNT)
    main_port = recipe["main_port"]
    out_port = recipe["out_port"]
    operations = recipe["operations"]

    if pump is None:
        pump = connect_pump()

    for operation in operations:
        pump.draw_and_dispense(
            volume=operation["volume_ml"],
            draw_valve_port=operation["draw_valve_port"],
            dispense_valve_port=main_port,
            speed=speed,
        )

    return {
        "main_port": main_port,
        "out_port": out_port,
        "operations": operations,
    }

if __name__ == "__main__":
    com_port = find_pump_com_port()