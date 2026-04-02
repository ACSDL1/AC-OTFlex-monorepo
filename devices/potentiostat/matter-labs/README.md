# Matter Labs Potentiostat

This folder is intended for the matter labs potenstiostat.

## Code Archive
The following code is derived from the archived codebase in the [archived_potentiostat](archived_potentiostat/) folder, which was a barebones placeholder for future integration. The code in this folder is intended to be the basis for the future integration of the matter labs potentiostat system for electrochemistry experiments.

The archived folder contains code to run 4 in parallel. However, it was discovered that the Working electrodes are shorted together once all connected to the same USB hub (March 2026). This is likely a hardware issue with the potentiostat system, and not a software issue. Therefore, the code in this folder is intended to run 1 potentiostat with single working electrode and is not intended to run 4 in parallel. Future integration may involve running 4 in parallel if the hardware issue is resolved. 