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


class SyringePump:
    """Object-oriented interface for the syringe pump.
    
    Encapsulates pump configuration including valve port mappings,
    draw speed, and dispense speed.
    """

    def __init__(
        self,
        solutions: Dict[str, int],
        draw_speed: float,
        dispense_speed: float,
        com_port: Optional[str] = None,
        address: int = 0,
        syringe_volume_l: float = DEFAULT_SYRINGE_VOLUME_L,
        num_valve_port: int = PUMP_CHANNEL_COUNT,
    ):
        """Initialize a SyringePump instance.
        
        Args:
            solutions: Dict mapping solution names (e.g., "MAIN", "H2O") to port numbers (1-indexed).
            draw_speed: Speed for draw operations.
            dispense_speed: Speed for dispense operations.
            com_port: COM port for the pump. Auto-detected if None.
            address: Pump address.
            syringe_volume_l: Syringe volume in liters.
            num_valve_port: Number of valve ports on the pump.
        """
        self.solutions = solutions
        self.draw_speed = draw_speed
        self.dispense_speed = dispense_speed
        
        if com_port is None:
            com_port = find_pump_com_port()
        
        if com_port is None:
            raise RuntimeError("Could not find syringe pump COM port.")
        
        self.pump = RunzePump(
            com_port=com_port,
            address=address,
            syringe_volume=syringe_volume_l,
            num_valve_port=num_valve_port,
        )

    def _validate_solution(self, solution: str) -> int:
        """Validate and retrieve port number for a solution.
        
        Args:
            solution: Solution name.
            
        Returns:
            Port number (1-indexed).
            
        Raises:
            ValueError: If solution is not configured.
        """
        if solution not in self.solutions:
            raise ValueError(
                f"Solution '{solution}' not found. Available: {list(self.solutions.keys())}"
            )
        port = self.solutions[solution]
        if port < 1 or port > PUMP_CHANNEL_COUNT:
            raise ValueError(f"Port for '{solution}' must be between 1 and {PUMP_CHANNEL_COUNT}; got {port}.")
        return port

    def draw_and_dispense(
        self,
        volume_ml: float,
        from_solution: str,
        to_solution: str,
        speed: Optional[float] = None,
    ) -> Dict[str, object]:
        """Draw from one solution and dispense to another.
        
        Args:
            volume_ml: Volume to transfer in mL.
            from_solution: Source solution name.
            to_solution: Destination solution name.
            speed: Optional override for pump speed. Uses dispense_speed if None.
            
        Returns:
            Dict with step details.
        """
        if volume_ml <= 0:
            raise ValueError("volume_ml must be > 0.")
        
        draw_port = self._validate_solution(from_solution)
        dispense_port = self._validate_solution(to_solution)
        
        op_speed = speed if speed is not None else self.dispense_speed
        if op_speed <= 0:
            raise ValueError("speed must be > 0.")
        
        self.pump.draw_and_dispense(
            volume=volume_ml,
            draw_valve_port=draw_port,
            dispense_valve_port=dispense_port,
            speed=op_speed,
        )
        
        return {
            "volume_ml": volume_ml,
            "from_solution": from_solution,
            "to_solution": to_solution,
            "draw_valve_port": draw_port,
            "dispense_valve_port": dispense_port,
        }

    def dispense_to_solution(
        self,
        volume_ml: float,
        to_solution: str,
        speed: Optional[float] = None,
    ) -> Dict[str, object]:
        """Dispense to a solution (convenience method).
        
        Args:
            volume_ml: Volume to dispense in mL.
            to_solution: Destination solution name.
            speed: Optional override for pump speed.
            
        Returns:
            Dict with step details.
        """
        # Uses the last configured source
        raise NotImplementedError("Use draw_and_dispense instead.")

    def run_csv_protocol(
        self,
        csv_path: str,
        target_solution: str = "MAIN",
    ) -> Dict[str, object]:
        """Execute CSV-defined transfers to a target solution.
        
        Args:
            csv_path: Path to CSV recipe file.
            target_solution: Solution to dispense all volumes to.
            
        Returns:
            Dict with parsed operations and results.
        """
        recipe = parse_pump_csv(csv_path, channel_count=PUMP_CHANNEL_COUNT)
        operations = recipe["operations"]
        
        target_port = self._validate_solution(target_solution)
        executed_operations = []
        
        for operation in operations:
            self.pump.draw_and_dispense(
                volume=operation["volume_ml"],
                draw_valve_port=operation["draw_valve_port"],
                dispense_valve_port=target_port,
                speed=self.dispense_speed,
            )
            executed_operations.append(operation)
        
        return {
            "target_solution": target_solution,
            "target_port": target_port,
            "operations": executed_operations,
        }

    def flush_with_solution(
        self,
        flush_solution: str,
        target_solution: str,
        flush2intermediary_volume_ml: float,
        flush_solution_volume_ml: float,
        speed: Optional[float] = None,
    ) -> Dict[str, object]:
        """Add a flush solution to intermediary, then dispense to target.
        
        Sequence:
        1) Draw from flush_solution and dispense to an intermediary.
        2) Draw from intermediary and dispense to target_solution.
        
        Args:
            flush_solution: Solution name for flushing (e.g., "H2O").
            target_solution: Final destination solution name (e.g., "OUT").
            flush2intermediary_volume_ml: Volume to flush into intermediary.
            flush_solution_volume_ml: Volume of flush solution to draw.
            speed: Optional override for pump speed.
            
        Returns:
            Dict with executed steps.
        """
        if flush2intermediary_volume_ml <= 0:
            raise ValueError("flush2intermediary_volume_ml must be > 0.")
        if flush_solution_volume_ml <= 0:
            raise ValueError("flush_solution_volume_ml must be > 0.")
        
        flush_port = self._validate_solution(flush_solution)
        target_port = self._validate_solution(target_solution)
        
        # Use MAIN as intermediary for flush operations
        intermediary_port = self._validate_solution("MAIN")
        
        op_speed = speed if speed is not None else self.dispense_speed
        if op_speed <= 0:
            raise ValueError("speed must be > 0.")
        
        raw_steps = [
            ("flush_add", flush_solution_volume_ml, flush_port, intermediary_port),
            ("flush_out", flush2intermediary_volume_ml, intermediary_port, target_port),
        ]
        
        executed_steps: List[Dict[str, object]] = []
        for step_name, volume_ml, draw_port, dispense_port in raw_steps:
            self.pump.draw_and_dispense(
                volume=volume_ml,
                draw_valve_port=draw_port,
                dispense_valve_port=dispense_port,
                speed=op_speed,
            )
            executed_steps.append(
                {
                    "step": step_name,
                    "volume_ml": volume_ml,
                    "draw_valve_port": draw_port,
                    "dispense_valve_port": dispense_port,
                }
            )
        
        return {
            "flush_solution": flush_solution,
            "target_solution": target_solution,
            "steps": executed_steps,
        }


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


def dispense_main2out(
    main_port: int,
    out_port: int,
    volume_ml: float,
    speed: float,
    pump: Optional[RunzePump] = None,
) -> Dict[str, object]:
    """Draw from MAIN and dispense to OUT."""
    for name, value in (("main_port", main_port), ("out_port", out_port)):
        if value < 1 or value > PUMP_CHANNEL_COUNT:
            raise ValueError(f"{name} must be between 1 and {PUMP_CHANNEL_COUNT}; got {value}.")

    if volume_ml <= 0:
        raise ValueError("volume_ml must be > 0.")

    if speed <= 0:
        raise ValueError("speed must be > 0.")

    if pump is None:
        pump = connect_pump()

    pump.draw_and_dispense(
        volume=volume_ml,
        draw_valve_port=main_port,
        dispense_valve_port=out_port,
        speed=speed,
    )

    return {
        "step": "out",
        "volume_ml": volume_ml,
        "draw_valve_port": main_port,
        "dispense_valve_port": out_port,
    }


def flush_water2out(
    main_port: int,
    out_port: int,
    water_draw_port: int,
    main2out_volume_ml: float,
    water_draw_volume_ml: float,
    speed: float,
    pump: Optional[RunzePump] = None,
) -> Dict[str, object]:
    """Add water to MAIN, then dispense from MAIN to OUT.

    Sequence:
    1) Draw from water port and dispense to MAIN.
    2) Draw from MAIN and dispense to OUT.
    """
    for name, value in (
        ("main_port", main_port),
        ("out_port", out_port),
        ("water_draw_port", water_draw_port),
    ):
        if value < 1 or value > PUMP_CHANNEL_COUNT:
            raise ValueError(f"{name} must be between 1 and {PUMP_CHANNEL_COUNT}; got {value}.")

    if main2out_volume_ml <= 0:
        raise ValueError("main2out_volume_ml must be > 0.")

    if water_draw_volume_ml <= 0:
        raise ValueError("water_draw_volume_ml must be > 0.")

    if speed <= 0:
        raise ValueError("speed must be > 0.")

    if pump is None:
        pump = connect_pump()

    raw_steps = [
        ("water", water_draw_volume_ml, water_draw_port, main_port),
        ("out", main2out_volume_ml, main_port, out_port),
    ]

    executed_steps: List[Dict[str, object]] = []
    for step_name, volume_ml, draw_port, dispense_port in raw_steps:
        pump.draw_and_dispense(
            volume=volume_ml,
            draw_valve_port=draw_port,
            dispense_valve_port=dispense_port,
            speed=speed,
        )
        executed_steps.append(
            {
                "step": step_name,
                "volume_ml": volume_ml,
                "draw_valve_port": draw_port,
                "dispense_valve_port": dispense_port,
            }
        )

    return {
        "main_port": main_port,
        "out_port": out_port,
        "water_draw_port": water_draw_port,
        "steps": executed_steps,
    }


def flush_out_water_out(
    main_port: int,
    out_port: int,
    water_draw_port: int,
    main2out_volume_ml: float,
    water_draw_volume_ml: float,
    speed: float,
    pump: Optional[RunzePump] = None,
) -> Dict[str, object]:
    """Backward-compatible alias for flush_water2out."""
    return flush_water2out(
        main_port=main_port,
        out_port=out_port,
        water_draw_port=water_draw_port,
        main2out_volume_ml=main2out_volume_ml,
        water_draw_volume_ml=water_draw_volume_ml,
        speed=speed,
        pump=pump,
    )

if __name__ == "__main__":
    # Example usage:
    # pump = SyringePump(
    #     solutions={"MAIN": 1, "OUT": 2, "H2O": 3},
    #     draw_speed=2.0,
    #     dispense_speed=2.0,
    # )
    # pump.draw_and_dispense(volume_ml=5, from_solution="H2O", to_solution="MAIN")
    # pump.draw_and_dispense(volume_ml=15, from_solution="MAIN", to_solution="OUT")
    # pump.flush_with_solution(
    #     flush_solution="H2O",
    #     target_solution="OUT",
    #     flush_to_intermediary_volume_ml=15,
    #     flush_solution_volume_ml=5,
    # )
    
    com_port = find_pump_com_port()