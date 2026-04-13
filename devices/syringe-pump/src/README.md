# Runze Pump Test

## About

This project is part of the **Acceleration Consortium** and focuses on testing the **RunzePump 12-Channel SY01** pumps. The RunzePump SY01 is a precision peristaltic pump system designed for automated fluid handling and dispensing in laboratory and research environments.

## Acid Flush Test

This workflow validates the pump's ability to perform automated fluid management tasks, including dispensing protocols and system flushing operations.

**Key Components:**

- **recipe.csv** — Defines the dispensing protocol with channel mappings:
  - MAIN: Primary dispensing destination (reactor)
  - AIR: Flush medium for tube conditioning
  - OUT: Waste collection and disposal destination
- **acid-flush-test.ipynb** — Interactive notebook implementing the test workflow
- **syringe-pump.py** — Core pump control module, with primary execution logic in the `run_csv_protocol()` method
- **requirements.txt** — Project dependencies and version specifications