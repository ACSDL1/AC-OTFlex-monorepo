# RASPI Camera

## Purpose
Raspberry Pi 5 camera module used for imaging in the AC-OTFlex system.

## Setup Notes
- Uses `picamera2` on the Pi 5
- The Pi does not have Wi-Fi access in normal operation
- Initial setup was done using a mobile hotspot
- Remote control and command execution are handled from host using Paramiko

## Structure
- `notebooks/` - Camera demo and control notebooks

## Notebooks
Use the notebooks in this folder to inspect and run camera-side workflows:
- `notebooks/SSH_Pi_Cam_Demo.ipynb`
- `notebooks/SSH_Pi_Cam_Demo_VERBOSE.ipynb`

## Adapter Link
Host integration is through:
- `src/adapters/pi_cam.py`
