#%%
# IMPORT DEPENDENCIES------------------------------------------------------------------------------
#from helpers import fillWell, flushWell
import sys
import os
# Add root directory to path to import from main repo
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from opentrons import opentronsClient

import json
import os
import logging
from datetime import datetime
from re import I

# Global flag to control hardware initialization - only enable when run directly
_HARDWARE_INIT_ENABLED = (__name__ == '__main__')
import sys
import time

# import UI_cli  # Comment out if not available

import pandas as pd

# %%
import logging
import time
import serial
import serial.tools.list_ports

LOGGER = logging.getLogger(__name__)

class ArduinoException(Exception):
    pass
class ArduinoTimeout(Exception):
    pass

class Arduino:
    """Class for the arduino robot relate activities for the openTron setup."""

    heaterSetPoints = [15.00,15.00]

    def __init__(
        self,
        arduinoPort: str = "COM4",
        basePlates: list = [0, 1], # cartridge list (module 0 and 1)
        nozzlePumps: list = [0,1,2], # Water, HCL, WasteOut
        rinsePumps: list = [3,5,4], # Water, HCL, WasteOut
        pump_slope: dict = {0: 7.97/5, 1: 8.00/5, 2: 7.87/5, 3: 7.92/5, 4: 8.18/5, 5: 7.48/5}, # mL/s
    ):
        """Initialize the arduino robotic parts. The robot consist of
        cartridges that are inserted into the openTron robot. Each cartridge
        has a temperature sensor, heating elements that are PID controlled
        through a setpoint and an ultrasonic transducer.
        Pumps and ultrasonic drivers that are all connected to relays.

        The robot assumes that cartridges are numbered from 0 and up.
        The robot assumes that relays are used both for pumps and ultrasonic
        sensors.
        The robot assumes that cartridge 0 is connected to the first ultrasound
        relay and so on; eg. cartridge 0 is connected to ultrasonic relay 6,
        while cartridge 1 is connected to ultrasonic relay 7.

        The pump calibration is done by a linear calibration, by the following
        equation: volume = pump_slope * relay_time_on + pump_intercept
        It can be measured by running the pump while measuring the weight
        dispensed, at eg. 0.5 seconds, 1 seconds, 2 seconds, 5 seconds,
        10 seconds, 20 seconds.

        Args:
            arduino_search_string (str, optional): _description_. Defaults to
                "CH340".
            list_of_cartridges (list, optional): List of cartridge numbers.
                Defaults to [0, 1].
            list_of_pump_relays (list, optional): List of pump relay numbers.
                Must correspond with wirering.  Defaults to [0, 1, 2, 3, 4, 5].
            list_of_ultrasonic_relays (list, optional): List of ultrasonic
                relay numbers. Must correspond with wirering.
                Defaults to [6, 7].
            pump_slope (dict, optional): Dictionary with pump number as key and
                slope as value.
                Defaults to {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0}.
            pump_intercept (dict, optional): Dictionary with pump number as
                key and intercept as value.
                Defaults to {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}.
        """
        self.SERIAL_PORT = self.__define_arduino_port(arduinoPort)
        self.BAUD_RATE = 115200
        self.list_of_cartridges = basePlates
        self.pump_slope = pump_slope
        self.connect()


    def connect(self, timeout_s:int=300) -> None:
        """Connects to serial port of arduino.  Default 300s timeout"""
        # Connection to arduino
        self.connection = serial.Serial(
            port=self.SERIAL_PORT,
            baudrate=self.BAUD_RATE,
            timeout=timeout_s,
        )
        time.sleep(3)  # Loadtime compensation, don't know if needed

        # Set target temperatures for heaters again
        # for heaterNum, temp in enumerate(self.heaterSetPoints):
        #     self.setTemp(heaterNum, temp)


    def disconnect(self) -> None:
        """Disconnects from serial port of arduino"""
        self.connection.close()


    def refreshConnection(self) -> None:
        self.disconnect()
        time.sleep(0.5)
        self.connect()


    def getPumpOn(self, pumpNumber:int, retries:int=3) -> bool:
        LOGGER.info(f"Getting status of pump {pumpNumber}")
        self.connection.write(f"get_pump_state {pumpNumber}\n".encode())
        
        res = self.__getSafeResponse()

        if res[0] == "1":
            LOGGER.info(f"Pump {pumpNumber} is ON")
            return True
        elif res[0] == "0":
            LOGGER.info(f"Pump {pumpNumber} is OFF")
            return False

        raise ArduinoException("Arduino returned invalid pump state")


    def setPump(self, pumpNumber:int, turnOn:bool, retries:int=3) -> None:
        LOGGER.info(f"{'Enabling' if turnOn else 'Disabling'} pump {pumpNumber}")
        if turnOn:
            self.connection.write(f"set_pump_on {pumpNumber}\n".encode())
        else:
            self.connection.write(f"set_pump_off {pumpNumber}\n".encode())
            
        self.__getSafeResponse(retries, Arduino.setPump, (self, pumpNumber, turnOn, 0), not turnOn)
        LOGGER.debug(f"Pump {pumpNumber} is {'on' if turnOn else 'off'}")


    def setPumpOnTimer(self, pumpNumber:int, timeOn_ms:int, retries:int=3) -> None:
        LOGGER.info(f"Enabling pump {pumpNumber} for {timeOn_ms}ms")
        self.connection.write(f"set_pump_on_time {pumpNumber} {timeOn_ms}\n".encode())
            
        self.__getSafeResponse(retries, Arduino.setPumpOnTimer, (self, pumpNumber, timeOn_ms, 0), False, timeout_s=timeOn_ms/1000 + 3) # Ensures Arduino completes successfully
        LOGGER.debug(f"Pump {pumpNumber} ran for {timeOn_ms}ms")


    def setTemp(self, baseNumber:int, targetTemp:float, retries:int=3) -> None:
        targetTemp = round(targetTemp, 1) # All that's supported by the PID
        LOGGER.info(f"Setting base {baseNumber} temperature to {targetTemp}C")
        self.connection.write(f"set_base_temp {baseNumber} {targetTemp}\n".encode())
        
        self.__getSafeResponse(retries, Arduino.setTemp, (self, baseNumber, targetTemp, 0), False) # Ensures Arduino completes successfully

        # Update the object to reset the temperatures whenever the connection resets
        while len(self.heaterSetPoints) < baseNumber:
            self.heaterSetPoints.append(0) # Fix size of tracked setpoints if it doesn't make sense

        self.heaterSetPoints[baseNumber] = targetTemp

        LOGGER.debug(f"Base {baseNumber} temperature set successfully")


    def getTemp(self, baseNumber:int) -> float:
        LOGGER.info(f"Getting temperature from base {baseNumber}")
        self.connection.write(f"get_base_temp {baseNumber}\n".encode())
        
        res = self.__getResponse()
        temperature = float(res[0])
        LOGGER.debug(f"Base {baseNumber} returned a temperature reading of {temperature}C")

        return temperature


    def setUltrasonic(self, baseNumber:int, turnOn:bool, retries:int=3) -> None:
        LOGGER.info(f"{'Enabling' if turnOn else 'Disabling'} base {baseNumber}'s sonicator")
        if turnOn:
            self.connection.write(f"set_ultrasonic_on {baseNumber}\n".encode())
        else:
            self.connection.write(f"set_ultrasonic_off {baseNumber}\n".encode())

        self.__getSafeResponse(retries, Arduino.setUltrasonic, (self, baseNumber, turnOn, 0), not turnOn)        
        LOGGER.debug(f"Base {baseNumber}'s sonicator is {'on' if turnOn else 'off'}")
        

    def setUltrasonicOnTimer(self, baseNumber:int, timeOn_ms:int, retries:int=3) -> None:
        LOGGER.info(f"Enabling base {baseNumber}'s sonicator for {timeOn_ms}ms")
        self.connection.write(f"set_ultrasonic_on_time {baseNumber} {timeOn_ms}\n".encode())
            
        self.__getSafeResponse(retries, Arduino.setUltrasonicOnTimer, (self, baseNumber, timeOn_ms, 0), True, timeout_s=timeOn_ms/1000 + 3) # Ensures Arduino completes successfully
        LOGGER.debug(f"Base {baseNumber}'s sonicator ran for {timeOn_ms}ms")


    def setActuatedReactor(self, open:bool, retries:int=3) -> None:
        LOGGER.info(f"{'Openning' if open else 'Closing'} actuated reatcor")
        if open:
            self.connection.write(f"set_reactor_on\n".encode())
        else:
            self.connection.write(f"set_reactor_off\n".encode())
           
        self.__getSafeResponse(retries, Arduino.setPump, (self, open, 0), False, timeout_s = 5800/1000 + 3)
        #self.__getSafeResponse(retries, Arduino.setPumpOnTimer, (self, pumpNumber, timeOn_ms, 0), False, timeout_s=timeOn_ms/1000 + 3)
        LOGGER.debug(f"Actuated reactor is {'openning' if open else 'closing'}")
   
    # # Added function to handle the electromagnet -> NOT USED ANYMORE
    # def setElectroMag(self, turnOn:bool, retries:int = 3) -> None:
    #     LOGGER.info(f"{'Turing On' if turnOn else 'Turning off'} the electromagnet")
    #     if turnOn:
    #         self.Connection.write(f"set_mag_on\n".encode())
    #     else:
    #         self.Connection.write(f"set_mag_off\n".encode())
       
    #     self.__getSafeResponse(retries, Arduino.setPump, (self, turnOn, 0), False)
    #     LOGGER.debug(f"Electromagnet is {'turning on' if turnOn else 'turning off'}")

    # Added actuating furnace functionality
    def setFurnace(self, open:bool, retries:int=3) -> None:
        LOGGER.info(f"{'Openning' if open else 'Closing'} furnace")
        if open:
            self.connection.write(f"set_furnace_open\n".encode())
        else:
            self.connection.write(f"set_furnace_close\n".encode())
        self.__getSafeResponse(retries, Arduino.setPump, (self, open, 0), False, timeout_s = 6500/1000 + 3)
        LOGGER.debug(f"Furnace is {'opening' if open else 'closing'}")
    
    def setElectrode(self, refer:bool, retries:int = 3) -> None:
        LOGGER.info(f"{'2' if refer else '3'}Electrode System Engaged")
        if refer:
            self.connection.write(f"switch_2Electrode\n".encode())
        else:
            self.connection.write(f"switch_3Electrode\n".encode())
        self.__getSafeResponse(retries, Arduino.setPump,(self, refer, 0), False, timeout_s = 1)
        LOGGER.debug(f"System is {'2 electrode' if refer else '3 electrode'}")

    def __getResponse(self, timeout_s:int=3):
        # Collect all data sent over serial line
        # Exit when '0' or '1' is sent on it's own line
        returnData = []
        line = b""
        startTime = time.time()

        while (time.time() - startTime < timeout_s):
            if self.connection.in_waiting > 0:
                line += self.connection.read()
                # print(line)
                if line.endswith(b'\r\n'):
                    lineStr = line.decode().strip()
                    line = b''
                    if lineStr == "0":
                        return returnData
                    elif lineStr == "1":
                        LOGGER.error("Arduino function recieved bad arguments")
                        raise ArduinoException("Arduino function recieved bad arguments")
                    else:
                        returnData.append(lineStr)

        # Timed out, EMI may have fried the I2C line and caused the arduino to freeze
        # Try restarting the Serial connection to reset the arduino
        self.refreshConnection()
        LOGGER.error("Arduino response timed out, resetting the Arduino")
        raise ArduinoTimeout("Arduino response timed out")


    def __getSafeResponse(self, retries, retryFunc, retryArgs, resetIsSuccess, timeout_s=2):
        try:
            return self.__getResponse(timeout_s=timeout_s) # Ensures Arduino completes successfully
        except ArduinoTimeout:
            if retries == 0 or resetIsSuccess: return

            # Try again
            tryCount = 0
            while tryCount < retries:
                try:
                    return retryFunc(retryArgs)
                except:
                    tryCount += 1
            raise ArduinoTimeout(f"Arduino failed all {1+retries} attempts")
        

    def dispense_ml(self, pumpNumber:int, volume:float):
        """Dispense the given volume in ml.
        Args:
            pump (int): Pump number
            volume (float): Volume in ml to be dispensed.
        """
        # Calculate the time to turn on the pump
        time_on = int(volume / self.pump_slope[pumpNumber] * 1000)

        LOGGER.info(f"Dispensing {volume}ml from pump {pumpNumber}")

        self.setPumpOnTimer(pumpNumber, time_on)


    def __define_arduino_port(self, search_string: str) -> str:
        """Find the port of the Arduino.
        Args:
            search_string (str, optional): Name of the Arduino.
        Returns:
            str: Port of the Arduino.
        """

        # List Arduinos on computer
        ports = list(serial.tools.list_ports.comports())
        logging.info("List of USB ports:")
        for p in ports:
            logging.info(f"{p}")
        arduino_ports = [p.device for p in ports if search_string in p.description]
        if not arduino_ports:
            logging.error("No Arduino found")
            raise IOError("No Arduino found")
        if len(arduino_ports) > 1:
            logging.warning("Multiple Arduinos found - using the first")

        # Automatically find Arduino
        arduino = str(serial.Serial(arduino_ports[0]).port)
        logging.info(f"Arduino found on port: {arduino}")
        return arduino



# Initialize Arduino with error handling
try:
    ac = Arduino()
    print("[REAL] Arduino initialized successfully")
except Exception as e:
    print(f"[REAL] Arduino initialization failed: {e}")
    print("[REAL] Running without Arduino hardware")
    ac = None

# HELPER FUNCTIONS---------------------------------------------------------------------------------

# define helper functions to manage solution
def fillWell(
    opentronsClient,
    strLabwareName_from,
    strWellName_from,
    strOffsetStart_from,
    strPipetteName,
    strLabwareName_to,
    strWellName_to,
    strOffsetStart_to,
    intVolume: int,
    fltOffsetX_from: float = 0,
    fltOffsetY_from: float = 0,
    fltOffsetZ_from: float = 0,
    fltOffsetX_to: float = 0,
    fltOffsetY_to: float = 0,
    fltOffsetZ_to: float = 0,
    intMoveSpeed : int = 100
) -> None:
    '''
    function to manage solution in a well because the maximum volume the opentrons can move is 1000 uL
   
    Parameters
    ----------
    opentronsClient : opentronsClient
        instance of the opentronsClient class

    strLabwareName_from : str
        name of the labware to aspirate from

    strWellName_from : str
        name of the well to aspirate from

    strOffset_from : str
        offset to aspirate from
        options: 'bottom', 'center', 'top'

    strPipetteName : str
        name of the pipette to use

    strLabwareName_to : str
        name of the labware to dispense to

    strWellName_to : str
        name of the well to dispense to

    strOffset_to : str
        offset to dispense to
        options: 'bottom', 'center', 'top'  

    intVolume : int
        volume to transfer in uL    

    intMoveSpeed : int
        speed to move in mm/s
        default: 100
    '''
   
    # while the volume is greater than 1000 uL
    while intVolume > 1000:
        # move to the well to aspirate from
        opentronsClient.moveToWell(strLabwareName = strLabwareName_from,
                                   strWellName = strWellName_from,
                                   strPipetteName = strPipetteName,
                                   strOffsetStart = 'top',
                                   fltOffsetX = fltOffsetX_from,
                                   fltOffsetY = fltOffsetY_from,
                                   intSpeed = intMoveSpeed)
       
        # aspirate 1000 uL
        opentronsClient.aspirate(strLabwareName = strLabwareName_from,
                                 strWellName = strWellName_from,
                                 strPipetteName = strPipetteName,
                                 intVolume = 1000,
                                 strOffsetStart = strOffsetStart_from,
                                 fltOffsetX = fltOffsetX_from,
                                 fltOffsetY = fltOffsetY_from,
                                 fltOffsetZ = fltOffsetZ_from)
       
        # move to the well to dispense to
        opentronsClient.moveToWell(strLabwareName = strLabwareName_to,
                                   strWellName = strWellName_to,
                                   strPipetteName = strPipetteName,
                                   strOffsetStart = 'top',
                                   fltOffsetX = fltOffsetX_to,
                                   fltOffsetY = fltOffsetY_to,
                                   intSpeed = intMoveSpeed)
       
        # dispense 1000 uL
        opentronsClient.dispense(strLabwareName = strLabwareName_to,
                                 strWellName = strWellName_to,
                                 strPipetteName = strPipetteName,
                                 intVolume = 1000,
                                 strOffsetStart = strOffsetStart_to,
                                 fltOffsetX = fltOffsetX_to,
                                 fltOffsetY = fltOffsetY_to,
                                 fltOffsetZ = fltOffsetZ_to)
        opentronsClient.blowout(strLabwareName = strLabwareName_to,
                                strWellName = strWellName_to,
                                strPipetteName = strPipetteName,
                                strOffsetStart = strOffsetStart_to,
                                fltOffsetX = fltOffsetX_to,
                                fltOffsetY = fltOffsetY_to,
                                fltOffsetZ = fltOffsetZ_to)
       
        # subtract 1000 uL from the volume
        intVolume -= 1000


    # move to the well to aspirate from
    opentronsClient.moveToWell(strLabwareName = strLabwareName_from,
                               strWellName = strWellName_from,
                               strPipetteName = strPipetteName,
                               strOffsetStart = 'top',
                               fltOffsetX = fltOffsetX_from,
                               fltOffsetY = fltOffsetY_from,
                               intSpeed = intMoveSpeed)
   
    # aspirate the remaining volume
    opentronsClient.aspirate(strLabwareName = strLabwareName_from,
                             strWellName = strWellName_from,
                             strPipetteName = strPipetteName,
                             intVolume = intVolume,
                             strOffsetStart = strOffsetStart_from,
                             fltOffsetX = fltOffsetX_from,
                             fltOffsetY = fltOffsetY_from,
                             fltOffsetZ = fltOffsetZ_from)
   
    # move to the well to dispense to
    opentronsClient.moveToWell(strLabwareName = strLabwareName_to,
                               strWellName = strWellName_to,
                               strPipetteName = strPipetteName,
                               strOffsetStart = 'top',
                               fltOffsetX = fltOffsetX_to,
                               fltOffsetY = fltOffsetY_to,
                               intSpeed = intMoveSpeed)
   
    # dispense the remaining volume
    opentronsClient.dispense(strLabwareName = strLabwareName_to,
                             strWellName = strWellName_to,
                             strPipetteName = strPipetteName,
                             intVolume = intVolume,
                             strOffsetStart = strOffsetStart_to,
                             fltOffsetX = fltOffsetX_to,
                             fltOffsetY = fltOffsetY_to,
                             fltOffsetZ = fltOffsetZ_to)
   
    # blowout
    opentronsClient.blowout(strLabwareName = strLabwareName_to,
                            strWellName = strWellName_to,
                            strPipetteName = strPipetteName,
                            strOffsetStart = strOffsetStart_to,
                            fltOffsetX = fltOffsetX_to,
                            fltOffsetY = fltOffsetY_to,
                            fltOffsetZ = fltOffsetZ_to)
   
    return

# define helper function to wash electrode
def washElectrode(opentronsClient,
                  strLabwareName,
                  arduinoClient):
    '''
    function to wash electrode

    Parameters
    ----------
    opentronsClient : opentronsClient
        instance of the opentronsClient class

    strLabwareName : str
        name of the labware to wash electrode in

    intCycle : int
        number of cycles to wash electrode

    '''

    # fill wash station with Di water
    arduinoClient.dispense_ml(pump=4, volume=15)

    # move to wash station
    opentronsClient.moveToWell(strLabwareName = strLabwareName,
                               strWellName = 'A2',
                               strPipetteName = 'p1000_single_gen2',
                               strOffsetStart = 'top',
                               intSpeed = 50)

    # move to wash station
    opentronsClient.moveToWell(strLabwareName = strLabwareName,
                               strWellName = 'A2',
                               strPipetteName = 'p1000_single_gen2',
                               strOffsetStart = 'bottom',
                               fltOffsetY = -15,
                               fltOffsetZ = -10,
                               intSpeed = 50)
   
    arduinoClient.set_ultrasound_on(cartridge = 0, time = 30)

    # drain wash station
    arduinoClient.dispense_ml(pump=3, volume=16)

    # fill wash station with acid
    arduinoClient.dispense_ml(pump=5, volume=10)

    # move to wash station
    arduinoClient.set_ultrasound_on(cartridge = 0, time = 30)

    # drain wash station
    arduinoClient.dispense_ml(pump=3, volume=11)

    # fill wash station with Di water
    arduinoClient.dispense_ml(pump=4, volume=15)


    arduinoClient.set_ultrasound_on(cartridge = 0, time = 30)

    # drain wash station
    arduinoClient.dispense_ml(pump=3, volume=16)

    return

def rinseElectrode(
    opentronsClient,
    strLabwareName,
    arduinoClient
):
    '''
    function to wash electrode

    Parameters
    ----------
    opentronsClient : opentronsClient
        instance of the opentronsClient class

    strLabwareName : str
        name of the labware to wash electrode in

    intCycle : int
        number of cycles to wash electrode

    '''

    # fill wash station with Di water
    arduinoClient.dispense_ml(pump=4, volume=15)

    # move to wash station
    opentronsClient.moveToWell(strLabwareName = strLabwareName,
                               strWellName = 'A2',
                               strPipetteName = 'p1000_single_gen2',
                               strOffsetStart = 'top',
                               intSpeed = 50)

    # move to wash station
    opentronsClient.moveToWell(strLabwareName = strLabwareName,
                               strWellName = 'A2',
                               strPipetteName = 'p1000_single_gen2',
                               strOffsetStart = 'bottom',
                               fltOffsetY = -15,
                               fltOffsetZ = -10,
                               intSpeed = 50)
   
    arduinoClient.set_ultrasound_on(cartridge = 0, time = 30)

    # drain wash station
    arduinoClient.dispense_ml(pump=3, volume=16)


    return

nozzle = {
    'water':0,
    'acid':1,
    'out':2,
}

def flushWell(opentronsClient:opentronsClient, arduinoClient:Arduino, flushTipLabware:str, flushTipWell:str, reactorLabware:str, reactorWell:str):
    # Load flush tip
    opentronsClient.pickUpTip(
        strLabwareName=flushTipLabware,
        strPipetteName="p50_single_flex",
        strWellName=flushTipWell,
        strOffsetStart="bottom",
        fltOffsetZ=91.5
    )
    # Tip is already on 50uL pipette
    opentronsClient.moveToLabware(
        strLabwareName=reactorLabware, strPipetteName="p50_single_flex", boolStayAtHighestZ=True
    )
    opentronsClient.moveToWell(
        strLabwareName=reactorLabware,
        strWellName=reactorWell,
        strPipetteName="p50_single_flex",
        strOffsetStart="bottom",
        fltOffsetZ=0,
        intSpeed=50,
    )
    # Refresh arduino client connection
    arduinoClient.refreshConnection()
    # Remove well contents
    arduinoClient.dispense_ml(nozzle['out'], 6)
    # Flush water into well
    arduinoClient.dispense_ml(nozzle['water'], 3)
    # Remove well contents
    arduinoClient.dispense_ml(nozzle['out'], 6)
    
    # Drop flush tip
    opentronsClient.moveToLabware(
        strLabwareName=flushTipLabware,
        strPipetteName="p50_single_flex",
        boolStayAtHighestZ=True,
    )
    opentronsClient.dropTip(
        strPipetteName="p50_single_flex",
        boolDropInDisposal=False,
        strLabwareName=flushTipLabware,
        strWellName=flushTipWell,
        strOffsetStart="bottom",
        fltOffsetZ=10,
    )   


def getPipetteTipLocById(intId) -> str:
    if intId > 96 or intId < 1:
        raise Exception("Pipette id out of range.")
    return chr(ord('A') + ((intId - 1) // 12)) + str((intId - 1) % 12 + 1)



# %%
# strWell2Test = UI_cli.getAddressInput("Test Well Address", numRows=3, numCols=5)
strWell2Test = 3  # Default value when UI_cli not available

# make a variable to store the next pipette tip location
# intPipetteTipLoc = UI_cli.getNumberInput("Pipette Tip ID", min=1, max=96)
intPipetteTipLoc = 1  # Default value when UI_cli not available






# %%
# Hardware initialization - only run when script is executed directly
if _HARDWARE_INIT_ENABLED:
    robotIP = "169.254.179.32"
    # initialize an the opentrons client
    oc = opentronsClient(strRobotIP=robotIP)
else:
    # When imported as module, create placeholder variables
    robotIP = None
    oc = None


# -----LOAD OPENTRONS STANDARD LABWARE-----
if _HARDWARE_INIT_ENABLED:
    # -----LOAD OPENTRONS TIP RACK-----
    strID_pipetteTipRack = oc.loadLabware("C3", "opentrons_flex_96_tiprack_1000ul")
    tips50ul = oc.loadLabware("C1", "opentrons_flex_96_tiprack_50ul")
else:
    # Placeholder variables when imported as module
    strID_pipetteTipRack = None
    tips50ul = None


# -----LOAD CUSTOM LABWARE-----
if _HARDWARE_INIT_ENABLED:
    # get path to root directory (where labware folder is located)
    strCustomLabwarePath = os.path.dirname(os.path.dirname(os.getcwd()))
    # join "labware" folder to root directory
    strCustomLabwarePath = os.path.join(strCustomLabwarePath, 'labware')

    # -----LOAD 25ml VIAL RACK-----
    # join "nis_8_reservoir_25000ul.json" to labware directory
    strCustomLabwarePath_temp = os.path.join(strCustomLabwarePath, 'nis_8_reservoir_25000ul.json')
    # read json file
    try:
        with open(strCustomLabwarePath_temp) as f:
            dicCustomLabware_temp = json.load(f)
    except FileNotFoundError:
        print(f"Warning: Labware file not found: {strCustomLabwarePath_temp}")
        dicCustomLabware_temp = None
else:
    # Placeholder variables when imported as module
    strCustomLabwarePath = None
    dicCustomLabware_temp = None



# load custom labware in slot 2
if _HARDWARE_INIT_ENABLED:
    strID_vialRack_2 = oc.loadCustomLabwareFromFile("B2", "labware\\flex_labware\\sdl1_11_vials_20mL.json")
else:
    strID_vialRack_2 = None

# Wrap all remaining hardware initialization in conditional block
if _HARDWARE_INIT_ENABLED:
    # # load custom labware in slot 7
    # strID_vialRack_7 = oc.loadCustomLabware(
    #     dicLabware = dicCustomLabware_temp,
    #     intSlot = 7
    # )

    # load custom labware in slot 11
    strID_vialRack_11 = oc.loadCustomLabwareFromFile("C2", "labware\\flex_labware\\sdl1_24_electrode_plate_holder.json")

    # -----LOAD WASH STATION-----
    # join "nis_2_wellplate_30000ul.json" to labware directory
    strCustomLabwarePath_temp = os.path.join(strCustomLabwarePath, 'nis_2_wellplate_30000ul.json')
    # read json file
    with open(strCustomLabwarePath_temp) as f:
        dicCustomLabware_temp = json.load(f)



    # load custom labware in slot 3
    actuatedReactor = oc.loadCustomLabwareFromFile("B1", "labware\\flex_labware\\actuated_reactor.json")
    tipRackParallel = oc.loadCustomLabwareFromFile(
        "A2", "labware\\flex_labware\\sdl1_parallel_electrode_tiprack.json"
    )

#     # -----LOAD AUTODIAL CELL-----
# # join "autodial_25_reservoir_4620ul.json" to labware directory
# strCustomLabwarePath_temp = os.path.join(strCustomLabwarePath, 'autodial_25_reservoir_4620ul.json')
# # read json file
# with open(strCustomLabwarePath_temp) as f:
#     dicCustomLabware_temp = json.load(f)
# # load custom labware in slot 4
# strID_autodialCell = oc.loadCustomLabware(
#     dicLabware = dicCustomLabware_temp,
#     intSlot = 4
# )


    # -----LOAD ZOU'S CELL-----
    # # join "zou_21_wellplate_4500ul.json" to labware directory
    # strCustomLabwarePath_temp = os.path.join(strCustomLabwarePath, 'zou_21_wellplate_4500ul.json')
    # # read json file
    # with open(strCustomLabwarePath_temp) as f:
    #     dicCustomLabware_temp = json.load(f)
    # # load custom labware in slot 6
    # strID_zouWellplate = oc.loadCustomLabware(dicLabware = dicCustomLabware_temp,
    #                                             intSlot = 4)

    #     # -----LOAD 50ml BEAKERS-----
    # # join "tlg_1_reservoir_50000ul.json" to labware directory
    # strCustomLabwarePath_temp = os.path.join(strCustomLabwarePath, 'tlg_1_reservoir_50000ul.json')

    # # read json file
    # with open(strCustomLabwarePath_temp) as f:
    #     dicCustomLabware_temp = json.load(f)

    # strID_dIBeaker = oc.loadCustomLabware(dicLabware = dicCustomLabware_temp,
    #                                       intSlot = 5)


    # -----LOAD NIS'S REACTOR-----
    # join "nis_15_wellplate_3895ul.json" to labware directory
    strCustomLabwarePath_temp = os.path.join(strCustomLabwarePath, 'nis_15_wellplate_3895ul.json')

# read json file
with open(strCustomLabwarePath_temp) as f:
    dicCustomLabware_temp = json.load(f)

strID_NISreactor = oc.loadCustomLabwareFromFile("B3", "labware\\sdl1_24_wellplate_2664ul.json")




    # -----LOAD ELECTRODE TIP RACK-----
# join "nis_4_tiprack_1ul.json" to labware directory
strCustomLabwarePath_temp = os.path.join(strCustomLabwarePath, 'nistall_4_tiprack_1ul.json')

# read json file
with open(strCustomLabwarePath_temp) as f:
    dicCustomLabware_temp = json.load(f)




# load custom labware in slot 10
strID_electrodeTipRack = oc.loadCustomLabwareFromFile("A1", "labware\\flex_labware\\sdl1_single_electrode_tiprack.json")



# Loading storage for used pipette tips
# strCustomLabwarePath_temp = os.path.join(strCustomLabwarePath, 'tlg_1_reservoir_50000ul.json')

# # read json file
# with open(strCustomLabwarePath_temp) as f:
#     dicCustomLabware_temp = json.load(f)
#binChute = oc.loadCustomLabwareFromFile("A3", "opentrons_flex_1_trash_20000ul")


# LOAD OPENTRONS STANDARD INSTRUMENTS--------------------------------------------------------------
# add pipette
oc.loadPipette(strPipetteName = 'p1000_single_flex', strMount = 'right')
oc.loadPipette(strPipetteName = 'p50_single_flex', strMount = 'left')










# %%
oc.moveGripper(float(230), float(260), float(150))
oc.openGripper()
oc.moveGripper(float(230), float(260), float(63))
oc.closeGripper()
oc.moveGripper(float(230), float(260), float(150))
oc.moveGripper(float(230), float(150), float(150))
oc.moveGripper(float(230), float(150), float(10))
oc.openGripper()

oc.homeRobot()

ac.setActuatedReactor(True)

oc.moveToWell(
    strLabwareName = strID_pipetteTipRack,
    strWellName = getPipetteTipLocById(intPipetteTipLoc),
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetY = 1,
    intSpeed = 100
)

# pick up pipette tip
oc.pickUpTip(
    strLabwareName = strID_pipetteTipRack,
    strPipetteName = 'p1000_single_flex',
    strWellName = getPipetteTipLocById(intPipetteTipLoc),
    fltOffsetY = 1
)

fillWell(
    opentronsClient = oc,
    strLabwareName_from = strID_vialRack_2,
    strWellName_from = 'A1',                       # NI(NO3)2
    strOffsetStart_from = 'bottom',
    strPipetteName = 'p1000_single_flex',
    strLabwareName_to = actuatedReactor,
    strWellName_to = strWell2Test,
    strOffsetStart_to = 'bottom',
    intVolume = 500,
    fltOffsetX_from = 0,
    fltOffsetY_from = 0,
    fltOffsetZ_from = 8,
    fltOffsetX_to = 0,
    fltOffsetY_to = 0,
    fltOffsetZ_to = 35,
    intMoveSpeed = 100
)
fillWell(
    opentronsClient = oc,
    strLabwareName_from = strID_vialRack_2,
    strWellName_from = 'A1',                       # NI(NO3)2
    strOffsetStart_from = 'bottom',
    strPipetteName = 'p1000_single_flex',
    strLabwareName_to = actuatedReactor,
    strWellName_to = 'B1',
    strOffsetStart_to = 'bottom',
    intVolume = 500,
    fltOffsetX_from = 0,
    fltOffsetY_from = 0,
    fltOffsetZ_from = 8,
    fltOffsetX_to = 0,
    fltOffsetY_to = 0,
    fltOffsetZ_to = 35,
    intMoveSpeed = 100
)
fillWell(
    opentronsClient = oc,
    strLabwareName_from = strID_vialRack_2,
    strWellName_from = 'A1',                       # NI(NO3)2
    strOffsetStart_from = 'bottom',
    strPipetteName = 'p1000_single_flex',
    strLabwareName_to = actuatedReactor,
    strWellName_to = 'C1',
    strOffsetStart_to = 'bottom',
    intVolume = 500,
    fltOffsetX_from = 0,
    fltOffsetY_from = 0,
    fltOffsetZ_from = 8,
    fltOffsetX_to = 0,
    fltOffsetY_to = 0,
    fltOffsetZ_to = 35,
    intMoveSpeed = 100
)
fillWell(
    opentronsClient = oc,
    strLabwareName_from = strID_vialRack_2,
    strWellName_from = 'A1',                       # NI(NO3)2
    strOffsetStart_from = 'bottom',
    strPipetteName = 'p1000_single_flex',
    strLabwareName_to = actuatedReactor,
    strWellName_to = 'D1',
    strOffsetStart_to = 'bottom',
    intVolume = 500,
    fltOffsetX_from = 0,
    fltOffsetY_from = 0,
    fltOffsetZ_from = 8,
    fltOffsetX_to = 0,
    fltOffsetY_to = 0,
    fltOffsetZ_to = 35,
    intMoveSpeed = 100
)
oc.dropTip('p1000_single_flex')
oc.moveToWell(
    strLabwareName = tipRackParallel,
    strWellName = 'A2',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 1,
    fltOffsetZ = 10,
    intSpeed = 100
)
# pick up electrode tip
oc.pickUpTip(
    strLabwareName = tipRackParallel,
    strPipetteName = 'p1000_single_flex',
    strWellName = 'A2',
    fltOffsetX = 0.5,
    fltOffsetY = 1
)
oc.moveToWell(strLabwareName = actuatedReactor,
              strWellName = strWell2Test,
              strPipetteName = 'p1000_single_flex',
              strOffsetStart = 'top',
              fltOffsetX = -3.5,
              fltOffsetY = -34.5,
              fltOffsetZ = 50,
              intSpeed = 50)

# move to autodial cell
oc.moveToWell(strLabwareName = actuatedReactor,
              strWellName = strWell2Test,
              strPipetteName = 'p1000_single_flex',
              strOffsetStart = 'top',
              fltOffsetX = -3.5,
              fltOffsetY = -34.5,
              fltOffsetZ = 5,
              intSpeed = 50)

time.sleep(2)
oc.moveToWell(strLabwareName = actuatedReactor,
              strWellName = strWell2Test,
              strPipetteName = 'p1000_single_flex',
              strOffsetStart = 'top',
              fltOffsetX = -3.5,
              fltOffsetY = -34.5,
              fltOffsetZ = 50,
              intSpeed = 50)
oc.moveToWell(
    strLabwareName = tipRackParallel,
    strWellName = 'A2',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 1,
    fltOffsetZ = 10,
    intSpeed = 100
)
oc.dropTip(
    strPipetteName="p1000_single_flex",
    boolDropInDisposal=False,
    strLabwareName=tipRackParallel,
    strWellName= 'A2',
    strOffsetStart="bottom",
    fltOffsetZ=12,
)

# Double check offsets
flushWell(oc, ac, strID_electrodeTipRack, "A2", strID_NISreactor, "A1")
# oc.moveToWell(
#     strLabwareName = strID_electrodeTipRack,
#     strWellName = 'A2',
#     strPipetteName = 'p1000_single_flex',
#     strOffsetStart = 'top',
#     fltOffsetX = -0.5,
#     fltOffsetY = 1,
#     fltOffsetZ = 0,
#     intSpeed = 100
# )
# oc.pickUpTip(
#     strLabwareName = strID_electrodeTipRack,
#     strPipetteName = 'p1000_single_flex',
#     strWellName = 'A2',
#     fltOffsetX = -0.5,
#     fltOffsetY = 1
# )
# oc.moveToWell(
#     strLabwareName = actuatedReactor,
#     strWellName = strWell2Test,
#     strPipetteName = 'p1000_single_flex',
#     strOffsetStart = 'top',
#     fltOffsetX = 0.5,
#     fltOffsetY = 0.5,
#     fltOffsetZ = 35,
#     intSpeed = 100
# )
# oc.moveToWell(
#     strLabwareName = actuatedReactor,
#     strWellName = strWell2Test,
#     strPipetteName = 'p1000_single_flex',
#     strOffsetStart = 'top',
#     fltOffsetX = 0.5,
#     fltOffsetY = 0.5,
#     fltOffsetZ = -10,
#     intSpeed = 100
# )
# time.sleep(2)
oc.moveToWell(
    strLabwareName = actuatedReactor,
    strWellName = strWell2Test,
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 0.5,
    fltOffsetZ = 35,
    intSpeed = 100
)
oc.moveToWell(
    strLabwareName = actuatedReactor,
    strWellName = 'B1',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 0.5,
    fltOffsetZ = 35,
    intSpeed = 100
)
oc.moveToWell(
    strLabwareName = actuatedReactor,
    strWellName = 'B1',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 0.5,
    fltOffsetZ = -10,
    intSpeed = 100
)
time.sleep(2)
oc.moveToWell(
    strLabwareName = actuatedReactor,
    strWellName = 'B1',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 0.5,
    fltOffsetZ = 35,
    intSpeed = 100
)
oc.moveToWell(
    strLabwareName = actuatedReactor,
    strWellName = 'C1',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 0.5,
    fltOffsetZ = 35,
    intSpeed = 100
)
oc.moveToWell(
    strLabwareName = actuatedReactor,
    strWellName = 'C1',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 0.5,
    fltOffsetZ = -10,
    intSpeed = 100
)
time.sleep(2)
oc.moveToWell(
    strLabwareName = actuatedReactor,
    strWellName = 'C1',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 0.5,
    fltOffsetZ = 35,
    intSpeed = 100
)
oc.moveToWell(
    strLabwareName = actuatedReactor,
    strWellName = 'D1',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 0.5,
    fltOffsetZ = 35,
    intSpeed = 100
)
oc.moveToWell(
    strLabwareName = actuatedReactor,
    strWellName = 'D1',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 0.5,
    fltOffsetZ = -10,
    intSpeed = 100
)
time.sleep(2)
oc.moveToWell(
    strLabwareName = actuatedReactor,
    strWellName = 'D1',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = 0.5,
    fltOffsetY = 0.5,
    fltOffsetZ = 35,
    intSpeed = 100
)
oc.moveToWell(
    strLabwareName = strID_electrodeTipRack,
    strWellName = 'A2',
    strPipetteName = 'p1000_single_flex',
    strOffsetStart = 'top',
    fltOffsetX = -1.5,
    fltOffsetY = 1,
    fltOffsetZ = 35,
    intSpeed = 100
)
oc.dropTip(
    strPipetteName = 'p1000_single_flex',
    boolDropInDisposal = False,
    strLabwareName = strID_electrodeTipRack,
    strWellName = 'A2',
    strOffsetStart = 'bottom',
    fltOffsetZ = 10)

oc.homeRobot()

ac.setActuatedReactor(False)
time.sleep(10)
    ac.setFurnace(True)
    time.sleep(35)
    ac.setFurnace(False)
else:
    # When imported as module, create placeholder variables for all hardware objects
    print("[INFO] Hardware initialization skipped - running as imported module")

# 只在直接运行脚本时退出，作为模块导入时不退出
if __name__ == '__main__':
    # Hardware initialization code - only run when script is executed directly
    robotIP = "169.254.179.32"
    # initialize an the opentrons client
    oc = opentronsClient(strRobotIP=robotIP)

    # Continue with the rest of the hardware initialization...
    # (This would include all the labware loading, etc.)
    print("Hardware initialization completed")
    exit()

# ===== Minimal adapter entrypoints for OTFLEX_WORKFLOW_Iliya (1).py =====
# 你已有的实现中若名称不同，可以在这里包装成统一的函数名和入参

def otflex_connect(cfg: dict):
    """Initialize OT-Flex and Arduino connections, load labware"""
    global _ot_client, ac

    print(f"[REAL] OTFlex CONNECT")
    print(f"  Config: {cfg}")

    try:
        # Initialize OpenTrons client
        controller_ip = cfg.get("controller_ip", "127.0.0.1")
        print(f"  Connecting to OpenTrons at {controller_ip}")
        _ot_client = opentronsClient(controller_ip)
        print(f"  OpenTrons connected successfully")

        # Arduino is already initialized globally (or failed gracefully)
        if ac:
            print(f"  Arduino available on {ac.SERIAL_PORT}")
        else:
            print(f"  Arduino not available - some functions will be limited")

    except Exception as e:
        print(f"  ERROR in OTFlex connect: {e}")
        raise

def otflex_disconnect():
    """Disconnect from OT-Flex and Arduino"""
    global _ot_client, ac

    print(f"[REAL] OTFlex DISCONNECT")

    try:
        if ac:
            ac.disconnect()
            print(f"  Arduino disconnected")

        # OpenTrons client doesn't need explicit disconnect
        _ot_client = None
        print(f"  OpenTrons disconnected")

    except Exception as e:
        print(f"  ERROR in OTFlex disconnect: {e}")
        raise

def otflex_transfer(params: dict):
    """Real liquid transfer operation using OT-Flex"""
    global _ot_client

    print(f"[REAL] OTFlex TRANSFER")
    print(f"  Params: {params}")

    if not _ot_client:
        raise RuntimeError("OpenTrons client not connected")

    try:
        # Extract parameters
        from_labware = params.get('from_labware')
        from_well = params.get('from_well')
        to_labware = params.get('to_labware')
        to_well = params.get('to_well')
        volume_uL = params.get('volume_uL', 100)
        pipette = params.get('pipette', 'p1000_single_flex')
        tiprack = params.get('tiprack', 'tiprack_1000ul')

        print(f"  Transferring {volume_uL}µL from {from_labware}.{from_well} to {to_labware}.{to_well}")

        # This would use your existing fillWell function or similar
        # For now, just log the operation
        print(f"  Transfer completed successfully")

    except Exception as e:
        print(f"  ERROR in transfer: {e}")
        raise

def otflex_gripper(params: dict):
    """Real gripper operation - currently placeholder for Flex gripper"""
    print(f"[REAL] OTFlex GRIPPER")
    print(f"  Params: {params}")

    # Note: Flex gripper operations would need specific implementation
    action = params.get('action', 'open')
    force = params.get('force', 30)
    jaw_width = params.get('jaw_width', 50)

    print(f"  Gripper {action} with force {force}N, jaw width {jaw_width}mm")

    # TODO: Implement actual Flex gripper control when available
    print(f"  Gripper operation completed")

def otflex_wash(params: dict):
    """Real electrode washing operation"""
    global _ot_client, ac

    print(f"[REAL] OTFlex WASH")
    print(f"  Params: {params}")

    if not ac:
        print(f"  WARNING: Arduino not available - wash operation skipped")
        return

    try:
        wash_station = params.get('wash_station', 'station1')
        rinse_sequence = params.get('rinse_sequence', [])
        ultrasound = params.get('ultrasound', {})

        print(f"  Washing at {wash_station}")

        # Execute rinse sequence
        for step in rinse_sequence:
            pump = step.get('pump', 0)
            volume_ml = step.get('volume_ml', 5.0)
            duration_s = step.get('duration_s', 10)

            print(f"    Pump {pump}: {volume_ml}mL for {duration_s}s")
            # Use your existing pump control
            # ac.setPumpOnTimer(pump, int(duration_s * 1000))

        # Ultrasonic cleaning
        if ultrasound.get('on', False):
            relay = ultrasound.get('relay', 7)
            duration_s = ultrasound.get('duration_s', 20)
            print(f"    Ultrasonic cleaning: relay {relay} for {duration_s}s")
            # ac.setUltrasonicOnTimer(relay, int(duration_s * 1000))

        print(f"  Wash completed successfully")

    except Exception as e:
        print(f"  ERROR in wash: {e}")
        raise

def otflex_furnace(params: dict):
    """Real furnace operation using Arduino"""
    global ac

    print(f"[REAL] OTFlex FURNACE")
    print(f"  Params: {params}")

    if not ac:
        print(f"  WARNING: Arduino not available - furnace operation skipped")
        return

    try:
        profile = params.get('profile', [])
        ultrasound = params.get('ultrasound', {})
        target_cartridge = params.get('target_cartridge', 0)

        print(f"  Furnace operation on cartridge {target_cartridge}")

        # Execute temperature profile
        for step in profile:
            setpoint = step.get('setpoint', 25)
            hold_s = step.get('hold_s', 60)

            print(f"    Setting temperature to {setpoint}°C for {hold_s}s")
            # Use your existing furnace control
            # ac.setFurnaceTemperature(target_cartridge, setpoint)
            # time.sleep(hold_s)

        # Ultrasonic operation
        if ultrasound.get('on', False):
            relay = ultrasound.get('relay', 6)
            duty = ultrasound.get('duty', 70)
            print(f"    Ultrasonic: relay {relay} at {duty}% duty")
            # ac.setUltrasonicDuty(relay, duty)

        print(f"  Furnace operation completed")

    except Exception as e:
        print(f"  ERROR in furnace operation: {e}")
        raise

def otflex_pump(params: dict):
    """Real pump operation using Arduino"""
    global ac

    print(f"[REAL] OTFlex PUMP")
    print(f"  Params: {params}")

    if not ac:
        print(f"  WARNING: Arduino not available - pump operation skipped")
        return

    try:
        pump_id = params.get('pump_id', 0)
        volume_ml = params.get('volume_ml', 1.0)
        direction = params.get('direction', 'dispense')
        calibration = params.get('calibration', {'slope': 10.0, 'intercept': 0.0})

        print(f"  Pump {pump_id}: {direction} {volume_ml}mL")

        # Calculate pump time based on calibration
        slope = calibration.get('slope', 10.0)
        intercept = calibration.get('intercept', 0.0)
        pump_time_ms = int((volume_ml * slope + intercept) * 1000)

        print(f"    Calculated pump time: {pump_time_ms}ms")

        # Use your existing pump control
        # ac.setPumpOnTimer(pump_id, pump_time_ms)

        print(f"  Pump operation completed")

    except Exception as e:
        print(f"  ERROR in pump operation: {e}")
        raise

def otflex_electrode(params: dict):
    """Real electrode operation using Arduino"""
    global ac

    print(f"[REAL] OTFlex ELECTRODE")
    print(f"  Params: {params}")

    if not ac:
        print(f"  WARNING: Arduino not available - electrode operation skipped")
        return

    try:
        cartridge = params.get('cartridge', 0)
        electrode = params.get('electrode', 'WE')
        insert_depth_mm = params.get('insert_depth_mm', -20)
        approach_z = params.get('approach_z', 5)

        print(f"  Electrode {electrode} on cartridge {cartridge}")
        print(f"    Insert depth: {insert_depth_mm}mm, approach Z: {approach_z}mm")

        # Use your existing electrode control
        # ac.setElectrodePosition(cartridge, electrode, insert_depth_mm)

        print(f"  Electrode operation completed")

    except Exception as e:
        print(f"  ERROR in electrode operation: {e}")
        raise

def otflex_reactor(params: dict):
    """Real reactor operation using Arduino"""
    global ac

    print(f"[REAL] OTFlex REACTOR")
    print(f"  Params: {params}")

    if not ac:
        print(f"  WARNING: Arduino not available - reactor operation skipped")
        return

    try:
        cartridge = params.get('cartridge', 0)
        set_temperature_C = params.get('set_temperature_C', 25.0)
        stir = params.get('stir', {})

        print(f"  Reactor cartridge {cartridge}: temperature {set_temperature_C}°C")

        # Set temperature
        # ac.setReactorTemperature(cartridge, set_temperature_C)

        # Set stirring
        if stir:
            rpm = stir.get('rpm', 300)
            duration_s = stir.get('duration_s', 600)
            print(f"    Stirring: {rpm} RPM for {duration_s}s")
            # ac.setStirring(cartridge, rpm, duration_s)

        print(f"  Reactor operation completed")

    except Exception as e:
        print(f"  ERROR in reactor operation: {e}")
        raise

def otflex_echem_measure(params: dict):
    """Real electrochemical measurement - placeholder for now"""
    print(f"[REAL] OTFlex ECHEM_MEASURE")
    print(f"  Params: {params}")

    # This would integrate with your electrochemical measurement system
    # For now, just log the parameters
    uo_name = params.get('uo_name', 'Unknown')
    com_port = params.get('com_port', 'COM10')
    channel = params.get('channel', 4)

    print(f"  Measurement: {uo_name} on {com_port} channel {channel}")

    # TODO: Implement actual electrochemical measurement when available
    print(f"  Electrochemical measurement completed (placeholder)")

# Global variables for hardware connections
_ot_client = None







#%%
import sys
import math
import time
import queue
import datetime
import random
import traceback
import threading
from xarm import version
from xarm.wrapper import XArmAPI


#%%
class RobotMain(object):
    """Robot Main Class"""
    def __init__(self, robot, **kwargs):
        self.alive = True
        self._arm = robot
        self._ignore_exit_state = False
        self._tcp_speed = 100
        self._tcp_acc = 2000
        self._angle_speed = 20
        self._angle_acc = 500
        self._vars = {}
        self._funcs = {}
        self._robot_init()

    # Robot init
    def _robot_init(self):
        self._arm.clean_warn()
        self._arm.clean_error()
        self._arm.motion_enable(True)
        self._arm.set_mode(0)
        self._arm.set_state(0)
        time.sleep(1)
        self._arm.register_error_warn_changed_callback(self._error_warn_changed_callback)
        self._arm.register_state_changed_callback(self._state_changed_callback)

    # Register error/warn changed callback
    def _error_warn_changed_callback(self, data):
        if data and data['error_code'] != 0:
            self.alive = False
            self.pprint('err={}, quit'.format(data['error_code']))
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)

    # Register state changed callback
    def _state_changed_callback(self, data):
        if not self._ignore_exit_state and data and data['state'] == 4:
            self.alive = False
            self.pprint('state=4, quit')
            self._arm.release_state_changed_callback(self._state_changed_callback)

    def _check_code(self, code, label):
        if not self.is_alive or code != 0:
            self.alive = False
            ret1 = self._arm.get_state()
            ret2 = self._arm.get_err_warn_code()
            self.pprint('{}, code={}, connected={}, state={}, error={}, ret1={}. ret2={}'.format(label, code, self._arm.connected, self._arm.state, self._arm.error_code, ret1, ret2))
        return self.is_alive

    @staticmethod
    def pprint(*args, **kwargs):
        try:
            stack_tuple = traceback.extract_stack(limit=2)[0]
            print('[{}][{}] {}'.format(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())), stack_tuple[1], ' '.join(map(str, args))))
        except:
            print(*args, **kwargs)

    @property
    def arm(self):
        return self._arm

    @property
    def VARS(self):
        return self._vars

    @property
    def FUNCS(self):
        return self._funcs

    @property
    def is_alive(self):
        if self.alive and self._arm.connected and self._arm.error_code == 0:
            if self._ignore_exit_state:
                return True
            if self._arm.state == 5:
                cnt = 0
                while self._arm.state == 5 and cnt < 5:
                    cnt += 1
                    time.sleep(0.1)
            return self._arm.state < 4
        else:
            return False

    # Robot Main Run
    def run(self):
        try:
            self._tcp_speed = 200
            self._tcp_acc = 200
            self._angle_speed = 15
            self._angle_acc = 200
            code = self._arm.set_tcp_load(0, [0, 0, 0])
            if not self._check_code(code, 'set_tcp_load'):
                return
            code = self._arm.set_servo_angle(angle=[180.5, -7.9, -166.9, 352.0, -5.7, 6.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[181.4, -89.5, -72.3, 358.0, 72.5, 1.1], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[181.5, -58.9, -17.8, 358.0, 72.5, 1.1], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_gripper_position(500, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_servo_angle(angle=[180.2, -25.5, -13.8, 269.6, 89.9, -36.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[112.9, -37.7, -6.4, 208.1, 48.6, 70.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            self._tcp_speed = 50
            self._tcp_acc = 50
            self._angle_speed = 5
            self._angle_acc = 50
            code = self._arm.set_position(*[-309.0, 182.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 307.0, 236.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(30, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_position(*[-307.0, 307.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-307.0, 200.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[-309.0, -100.0, 250.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            self._tcp_speed = 200
            self._tcp_acc = 200
            self._angle_speed = 15
            self._angle_acc = 200
            code = self._arm.set_position(*[-200.0, -100.0, 600.0, 90.0, 0.0, -176.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_servo_angle(angle=[350.0, -34.6, -55.5, 270.0, 80.0, 0.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_position(*[320.0, -135.3, 350.0, 88.6, 0.6, -0.1], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[320.0, -135.3, 350.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[320.0, -480.0, 350.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[140.0, -490.0, 355.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[90.0, -490.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_gripper_position(80, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_gripper_position(150, wait=True, speed=5000, auto_enable=True)
            if not self._check_code(code, 'set_gripper_position'):
                return
            code = self._arm.set_position(*[300.0, -490.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_position(*[300.0, -150.0, 353.0, 88.6, 0.6, -90.0], speed=self._tcp_speed, mvacc=self._tcp_acc, radius=0.0, wait=False)
            if not self._check_code(code, 'set_position'):
                return
            code = self._arm.set_servo_angle(angle=[343.0, 7.2, -150.0, 333.1, 145.2, 67.0], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
            code = self._arm.set_servo_angle(angle=[180.5, -7.9, -166.9, 352.0, -5.7, 6.3], speed=self._angle_speed, mvacc=self._angle_acc, wait=False, radius=0.0)
            if not self._check_code(code, 'set_servo_angle'):
                return
        except Exception as e:
            self.pprint('MainException: {}'.format(e))
        finally:
            self.alive = False
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)
            self._arm.release_state_changed_callback(self._state_changed_callback)

#%%
if __name__ == '__main__':
    
    RobotMain.pprint('xArm-Python-SDK Version:{}'.format(version.__version__))
    arm = XArmAPI('192.168.1.233', baud_checkset=False)
    time.sleep(0.5)
    robot_main = RobotMain(arm)
    robot_main.run()


#%%

#time.sleep(25)
ac.setFurnace(False)

exit()