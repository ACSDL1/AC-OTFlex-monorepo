from matterlab_pumps import RunzePump
pump = RunzePump(com_port="/dev/ttyUSB0", address=0, syringe_volume=1e-3, num_valve_port=12) #note only here volume is in L, all others are in mL
pump.draw(volume=0.5, valve_port=1, speed=0.5)
# pump.draw(volume=1.0, speed=0.5)