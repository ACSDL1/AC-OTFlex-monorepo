import serial
import csv
from datetime import datetime

PORT = "COM11"   # Change to your Arduino port
BAUD = 115200
CSV_FILE = "sensor_log.csv"

ser = serial.Serial(PORT, BAUD)
print(f"Logging data from {PORT} into {CSV_FILE} ...")

# Create CSV file with header if it doesn't exist yet
with open(CSV_FILE, "a", newline="") as f:
    writer = csv.writer(f)
    if f.tell() == 0:
        writer.writerow([
            "Timestamp",
            "Temp(C)",
            "Humidity(%)",
            "Pressure(hPa)",
            "Light(lx)",
            "O2(%)",
            "CO2(ppm)"
        ])

    while True:
        try:
            line = ser.readline().decode().strip()
            if not line:
                continue
            values = line.split(",")

            if len(values) == 6:  # valid row
                writer.writerow([datetime.now().isoformat()] + values)
                print(f"{datetime.now()} | {values}")
        except KeyboardInterrupt:
            print("\nLogging stopped.")
            break
