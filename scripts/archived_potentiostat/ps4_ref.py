#!/usr/bin/env python3
"""
2023-08-30
deniz
"""
import serial
import time
import numpy as np
from enum import IntEnum
from pathlib import Path
# import tomllib
import sys
from typing import Union
from .proc_echem import *

class Commands(IntEnum):
    """Contains index for each serial command

    """
    READ_ADC = 1 # access ADC (analog-to-digital converter)'s measurement (V/I)
    WRITE_DAC = 2  # use to add a voltage to DAC (digital-to-analog converter)
    READ_DAC = 3
    WRITE_SWITCH = 4
    WRITE_GAIN = 5
    EXECUTE_VOLTAGE_BATCH = 7
    _WRITE_BUFFER = 8
    _READ_BUFFER = 9
    WRITE_CURRENT_HOLD = 10 # hold current
    _RESET_BUFFER = 11
    WRITE_SAMPLE_COUNT = 12
    WRITE_AUTO_GAIN = 13
    READ_ANALOG_GAIN = 14
    READ_AUTO_GAIN = 15
    READ_GAIN = 16
    READ_SWITCH = 17
    STOP_CURRENT_HOLD = 18

    
class Resistors(): # used to convert V between WE&CE to I
    """Contains index information of resistor values along with the resistance values for gain.
    This information is then used for V to I conversion (simple V=IR)
    """
    R_100 = 0
    R_1K = 1
    R_10K = 2
    R_100K = 3
    R_1M = 4
    #R_10M = 5

class ADC():
    WE_OUT = 0 #WE-CE potential for conversion to current with resistor multiplier.
    RE_OUT = 1 #WE-RE potential, for controling V
    VREF = 2
    TEMP = 3 #Temperature
    HUMID = 4 #Humidity

class DAC():
    CE_IN = 0 #RE-WE
    A_REF = 1
    V_AN = 2


class SwitchState(IntEnum):
    On = 1 #CE and WE connected
    Off = 0 #CE and WE disconnected

class Potentiostat():
    serial = None
    serial_port = None
    device_ID = 0
    baudrate = 115200
    _chunk_size = 254 #number of bytes that can be communicated at once minus 2 (for ID and command bytes) !!!CONFIG
    _vin_lims = [-5,5]
    _vout_lims = [0,3.3]
    _auto_gain = False
    _switch_state = False
    _rx_buffer_size = 24000 #rx buffer size of the pstat
    _tx_buffer_size = 64000 #tx buffer size of the pstat

    res_vals    = {Resistors.R_100: 1e2,
                Resistors.R_1K: 1e3,
                Resistors.R_10K: 1e4,
                Resistors.R_100K: 1e5,
                Resistors.R_1M: 1e6,
                #R_10M: 1e7,
    }
    
    def _select_resistor(self, current):
        """_summary_

        Args:
            current (float): Target Ampere

        Returns:
            Resistors: Best resistance for highest gain without saturation of the ADC
        """
        max_currents = [0.05, 0.005, 0.0005, 0.00005, 0.000005, 0.0000005] #in Amps
        #max_currents = [0.05, 0.005, 0.0005, 0.00005, 0.000005, 0.0000005, 0.00000005] #in Amps (with 10M resistor)
        for i in range(len(max_currents)):
            if abs(current) > (max_currents[i] * 0.9):
                if i < 1: return 0
                return i-1
        return Resistors.R_1M


    class Errors(IntEnum):
        NO_ERROR = 0
        ERROR = 1

    def __init__(self,serial_port='/dev/ttyACM1',baudrate=115200,device_ID = 1):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.device_ID = device_ID
    
    def connect(self):
        self.serial = serial.Serial(self.serial_port,self.baudrate)
        time.sleep(0.1)
        print("serial dev created")
        self.write_switch(False)
        self.write_gain(4)
        self.write_auto_gain(False)
        #Sync current status of the pstat to the class by read commands
        print(f'switch is {self.read_switch()}\n'
              f'gain is {self.read_gain()}\n'
              f'auto_gain is {self.read_auto_gain()}\n'
              )
        self.write_dac(channels=[DAC.A_REF,DAC.V_AN], voltages=[-5,0])
    
    def disconnect(self):
        self.serial.close()

    def _scale_input_voltages(self,voltages):
        """Map (and limit) to be inputted actual potential(V) values to pstat operation range
        """
        return np.interp(voltages,self._vin_lims,self._vout_lims)
    
    def _scale_output_voltages(self,voltages):
        """Map (and limit) outputted potential(V) values to actual values
        """
        return np.interp(voltages,self._vout_lims,self._vin_lims)
    
    def _current_to_voltage(self,currents):
        """Converts target current value(s) to DAC voltage value to be written.

        Args:
            currents (np.float32): current(I) value(s)

        Returns:
            np.float32: DAC voltage value
        """
        voltages = currents * -1
        voltages *= self.res_vals[self.Resistor]
        voltages = self._scale_input_voltages(voltages)
        return voltages

    def _check_response(self,timeout_s=10):
        """Check whether the response to a command is an OK line.
        If not, then there is an error.
        """
        resp = self.serial.readline()
        resp = resp.strip()
        if resp == "OK":
            return True
        else:
            Exception(resp)
        
    def _write_cmd(self,cmd,data,check_response=True):
        """Write command by its date. Adds device ID to the beginning of the data package

        Args:
            cmd (Commands): command index
            data (any): command data
            check_response (bool, optional): Whether to check for OK. Defaults to True.
        """
        msg = bytearray()
        msg.extend(np.uint8(self.device_ID).tobytes()) #device ID
        msg.extend(np.uint8(cmd).tobytes()) #Command
        if not (data is None):
            if str(type(data)) == "<class 'bytes'>" or str(type(data)) == "<class 'bytearray'>":
                msg.extend(data)
            else:
                msg.extend(data.tobytes())
        
        self.serial.write(msg)
        if check_response: 
            return(self._check_response())

    def _reset_buffer(self, pos=0):
        self._write_cmd(Commands._RESET_BUFFER,np.uint32(pos))

    def _write_to_buffer(self, data):
        ind = 0
        remainder = len(data) % self._chunk_size
        n_chunk = int((len(data) - remainder) / self._chunk_size)
        if len(data) < self._chunk_size:
            self._write_cmd(Commands._WRITE_BUFFER,data,False)
            return True
            
        for i in range(n_chunk):
            self._write_cmd(Commands._WRITE_BUFFER,data[ind:ind+self._chunk_size],False)
            ind = ind + self._chunk_size
            
        if remainder > 0:
            self._write_cmd(Commands._WRITE_BUFFER,data[ind:ind+remainder],False)
            
        return True

    def _read_from_buffer(self, data_len):
        return self.serial.read(data_len)
                    
    def write_voltage_batch(self, voltages: float, delay: np.uint32):
        """Write a list of set voltage values to pstat's buffer. Then this buffer is executed.
        Each set V (WE-RE) will be set and immediately the CE-WE current (A) will be read along with RE-WE potential.
        If auto-gain mode is active, it will automatically return the gain corrected current values.

        Args:
            voltages (float): list of voltages to set
            delay (np.uint32): delay between setting voltages (and reading the current and potential)

        Returns:
            list: 2D array with rows as many as voltages | column 0: CE-WE current (A) | column 1: RE-WE V
        """
        v_per_chunk = 6 #number of potentials (V) written to pstat each time
        bytes_per_v = 4 #number of bytes used for each V
        tx_len = v_per_chunk * bytes_per_v #number of bytes to write at a time
        new_voltages = self._scale_input_voltages(voltages) #scale potentials for pstat
        v_count = int(len(new_voltages)) #number of data points (# of target V's)

        #ensure multiple of v_per_chunk per data point
        remainder = (v_count % v_per_chunk)
        pad_count = 0
        if remainder > 0:
            pad_count = v_per_chunk - remainder
            for i in range(pad_count):
                new_voltages = np.append(new_voltages,new_voltages[-1]) #pad by the last potential
            v_count += pad_count


        v_bytes = np.float32(new_voltages).tobytes() #entire array of target Vs in bytes
        v_byte_count = len(v_bytes)

        first_tx_bytes = tx_len * 4 #number of bytes to start the read-write stream protocol
        tx_ind = 0 #index to iterate on v_bytes

        self._reset_buffer(0) #set the rx buffer of pstat to zero
        self._write_to_buffer(v_bytes[0:first_tx_bytes]) #write the first chunk
        time.sleep(0.01) #wait for pstat to receive the message (1ms delay is end of msg for USB)
        tx_ind = first_tx_bytes #move the ind accordingly

        if self._auto_gain:
            rx_len = 9 #1 float32 current(A) + 1 float32 potential(V) + 1 uint8 resistor index (per target V)
        else:
            rx_len = 8 #1 float32 current(A) + 1 float32 potential(V) (per target V)
        
        temp_adc = np.zeros((v_count,2),np.float32) #array to hold ADC readings
        temp_res_val = np.zeros((v_count),np.float32) #array to hold resistor multipliers

        self._write_cmd(Commands.EXECUTE_VOLTAGE_BATCH,np.uint32([delay,v_count]),True) #start the protocol
        for i in range(0,v_count,v_per_chunk): #for each target V
            data = self._read_from_buffer(rx_len * v_per_chunk) #read
            if (tx_ind + tx_len) <= v_byte_count: #write if the target V list is not exhausted
                self._write_to_buffer(v_bytes[tx_ind:tx_ind+tx_len])
                tx_ind += tx_len

            temp_ind = 0 #temp index in data
            for j in range(v_per_chunk):
                temp_adc[i+j,:] = np.frombuffer(data,np.float32,2,temp_ind) #read 2 float32s
                temp_ind += 8
                if self._auto_gain:
                    temp_gain= np.frombuffer(data,np.uint8,1,temp_ind) #read resistor index if autogain is on
                    temp_gain = temp_gain[0]
                    temp_res_val[i+j] = self.res_vals[temp_gain]
                    temp_ind += 1

        #Process the data
        temp_adc = self._scale_output_voltages(temp_adc)
        if self._auto_gain:
            temp_adc[:,0] = np.divide(temp_adc[:,0],temp_res_val)
            self.Resistor = temp_gain
            self.ResistorVal = temp_res_val[-1]
        else:
            temp_adc[:,0] /= self.ResistorVal
        temp_adc[:,0] *= -1

        if pad_count == 0:
            return temp_adc
        
        return temp_adc[:-pad_count,:] #get rid of the results of padding

    def write_dac(self, channels, voltages):
        """Write Digital to Analog Converter values to potentiostat.
        Consult "DAC" class for channel information.
        Channels and voltages must refer to same index.
        i.e., channel[1]'s target value should be given in voltages[1]

        Args:
            channels (list): list of channel(s)
            voltages (list): list of voltages(s)

        """
        new_voltages = self._scale_input_voltages(voltages)
        data = bytearray()
        data.extend(np.uint8(channels).tobytes())
        data.extend(np.float32(new_voltages).tobytes())
        self._write_cmd(Commands.WRITE_DAC,data)

    def write_switch(self, state:bool):
        """Change the switch state between CE and WE. True for connected, False for disconnected.

        Args:
            state (bool): Whether the switch is on

        """
        self._write_cmd(Commands.WRITE_SWITCH,np.uint8(state))
        self._switch_state = state

    def read_switch(self)-> bool:
        """Returns the switch state between CE and WE. True for connected, False for disconnected.

        Returns:
            bool: Whether the switch is on
        """
        self._write_cmd(Commands.READ_SWITCH,None,False)
        result = self.serial.read(1)
        result = np.frombuffer(result,np.uint8)
        if result == 0:
            self._switch_state = False
        else:
            self._switch_state = True
        return result
    
    def write_gain(self, resistor: Resistors = Resistors.R_100):
        """Change gain by switching resistor between CE and WE

        Args:
            resistor (Resistors, optional): Target resistor (gain) index. Defaults to Resistors.R_100.
        """
    
        self._write_cmd(Commands.WRITE_GAIN,np.uint8(resistor))
        self.Resistor = resistor
        self.ResistorVal = self.res_vals[self.Resistor]
    
    def read_gain(self):
        """Returns currently active resistor index (gain) between CE and WE

        Returns:
            Resistor: Current resistor index
        """
        self._write_cmd(Commands.READ_GAIN,np.uint8(0),False)
        result = self.serial.read(1)
        result = np.frombuffer(result,np.uint8)
        self.Resistor = result[0]
        self.ResistorVal = self.res_vals[self.Resistor]
        return self.Resistor
    
    def write_current_hold(self, target_current_mA=0.0001, initial_step_V = 0.00015, learning_rate = 0.05, force_gain = False):
        target_A = target_current_mA / 1000
        if force_gain == False:
            self.write_gain(self._select_resistor(target_A)) #guess the best resistor for highest gain without saturation
        dac_val = self._current_to_voltage(target_A)
        #ADD "LEARNING RATE" AND REPEAT COUNT PARAMS
        msg = bytearray()
        msg.extend(np.float32([dac_val,initial_step_V,learning_rate]).tobytes())
        self._write_cmd(Commands.WRITE_CURRENT_HOLD,msg)

    def write_sample_count(self, sample_count=10):
        """Sets the number of samples to be averaged per channel

        Args:
            sample_count (int, optional): Number of samples to be averaged per channel. Defaults to 10.
        """
        self._write_cmd(Commands.WRITE_SAMPLE_COUNT,np.uint32(sample_count))

    def write_current_hold_stop(self):
        """Stop current hold tasl
        """
        self._write_cmd(Commands.STOP_CURRENT_HOLD,None)

    def read_DAC(self,channels):
        """Read Digital to Analog Converter values from potentiostat.
        Consult "DAC" class for channel information

        Args:
            channels (list): list of channel(s)

        Returns:
            list: List of float32 DAC values from the requested channels
        """
        channels = np.ones(1,np.uint8) * channels
        self._write_cmd(Commands.READ_DAC,np.uint8(channels),False)
        result = self.serial.read(np.uint8(channels).size * 4) #channel count x float32
        result = np.frombuffer(result,np.float32).copy()
        result = self._scale_output_voltages(result)
        return result
    
    def read_ADC(self,channels):
        """Read Analog to Digital Converter values from potentiostat.
        Consult "ADC" class for channel information

        Args:
            channels (list): list of channel(s)

        Returns:
            list: List of float32 ADC values from the requested channels
        """
        #read ADC values
        channels = np.ones(1,np.uint8) * channels
        self._write_cmd(Commands.READ_ADC,np.uint8(channels),False)
        result = self.serial.read(np.uint8(channels).size * 4) #channel count x float32
        result = np.frombuffer(result,np.float32).copy()
        for i in range(len(channels)):
            if channels[i] == ADC.WE_OUT: #V-I conversion channel, process by resistor value
                result[i] = self._scale_output_voltages(result[i])
                result[i] /= (-1 * self.res_vals[self.Resistor])
            elif (channels[i] == ADC.TEMP) or (channels[i] == ADC.HUMID): #Skip temperature and humidiy
               pass 
            else:  #normal ADC, just scale the range
                result[i] = self._scale_output_voltages(result[i])
        return result
    
    def read_ADC_gain(self,channels):
        """Read Analog to Digital Converter values from potentiostat
        Additionally request for gain information (resistor index).
        Consult "ADC" class for channel information.
        This function automatically updates the resistor value of the class.
        Also processes the current reading accordingly.
        
        Args:
            channels (list): list of channel(s)

        Returns:
            list: List of float32 ADC values from the requested channels
        """
        channels = np.ones(1,np.uint8) * channels       
        self._write_cmd(Commands.READ_ANALOG_GAIN,np.uint8(channels),False)
        result = self.serial.read((np.uint8(channels).size * 4) + 1)
        ch_result = result[0:(len(channels) * 4)]
        ch_result = np.frombuffer(ch_result,np.float32).copy()
        gain_result = result[(len(channels) * 4):]
        gain_result = np.frombuffer(gain_result,np.uint8).copy()
        # if not(gain_result[0] == self.Resistor): 
        #     print("Switched gain to: " + str(gain_result)) 
        self.Resistor = gain_result[0]
        self.ResistorVal = self.res_vals[self.Resistor]
        for i in range(len(channels)):
            if channels[i] == ADC.WE_OUT:
                ch_result[i] = self._scale_output_voltages(ch_result[i])
                ch_result[i] /= (-1 * self.res_vals[self.Resistor])
            elif (channels[i] == ADC.TEMP) or (channels[i] == ADC.HUMID):
               pass 
            else:
                ch_result[i] = self._scale_output_voltages(ch_result[i])
        return ch_result
    
    def read_auto_gain(self) -> bool:
        """_summary_

        Returns:
            bool: Whether the auto-gain is turned on.
        """
        self._write_cmd(Commands.READ_AUTO_GAIN,np.uint8(0),False)
        result = self.serial.read(1) #read single byte bool
        result = np.frombuffer(result,np.uint8) #cast to uint8
        if (result == 0):
            self._auto_gain = False
        else:
            self._auto_gain = True
        return self._auto_gain
    
    def write_auto_gain(self,state:bool=False) -> bool:
        """_summary_

        Args:
            state (bool, optional): Whether the auto-gain is turned on(True). Defaults to False(off).

        Returns:
            bool: _description_
        """
        self._write_cmd(Commands.WRITE_AUTO_GAIN,np.uint8(state)) #single byte state bool
        self._auto_gain = state

    def read_current(self):
        """Read A current (I) between WE and CE

        Returns:
            np.float32: Current (I) between WE and CE (A)
        """
        return self.read_ADC_gain(channels=[ADC.WE_OUT])
    
    def read_potential(self):
        """Read potential (V) between WE and RE

        Returns:
            np.float32: Potential (V) between WE and RE
        """
        return self.read_ADC_gain(channels=[ADC.RE_OUT])
    
    def read_potential_current(self):
        """Read potential (V) between WE-RE and current Ampere (I) between WE-CE

        Returns:
            list: Potential (V) between WE-RE and current (I) between WE-CE (A)
        """
        return self.read_ADC_gain(channels=[ADC.RE_OUT,ADC.WE_OUT])
    
    def write_potential(self,potential_V:np.float32):
        """Read potential (V) between WE-RE in Volts

        Args:
            potential_V (np.float32): potential (V) between WE-RE in Volts
        """
        self.write_dac(DAC.CE_IN,potential_V)
    
    def read_ocp(self,restore_switch_state = True)->np.float32:
        """Read Open Circuit Potential in Volts. Disconnects CE-WE connection and reads potential.

        Args:
            restore_switch_state (bool, optional): Whether to restore previous switch state. Defaults to True.

        Returns:
            np.float32: OCP in Volts
        """
        prev_switch_state = self._switch_state
        self.write_switch(SwitchState.Off)
        if self._auto_gain:
            for i in range(Resistors.R_1M):
                self.read_potential() #Read current multiple times to allow auto-gain
        result = self.read_potential()
        if not (prev_switch_state == SwitchState.Off) and restore_switch_state:
            self.write_switch(SwitchState.On) #restore previous switch state
        return result[0]

    def perform_CV(self,min_V, max_V, cycles,mV_s, step_hz, start_V=None, last_V=None):
        """Performs CV with given parameters.

        Returns:
            _type_: 2 columns, column 0: I (A) | column 1: V
        """

        #if start_V and/or last_V is None, start/end with OCP
        if (start_V is None) or (last_V is None):
            ocp = self.read_ocp()
            if start_V is None:
                start_V = ocp
            if last_V is None:
                last_V = ocp

        self.write_current_hold_stop()
        #if SwitchState == False:
        self.write_switch(True)

        V_s = mV_s / 1000
        step_V = V_s / step_hz

        #start to min
        r1 = np.abs(min_V - start_V)
        p1 = np.linspace(start_V,min_V,int(np.round(r1/step_V)))

        #min to max
        r2 = np.abs(max_V - min_V)
        p2 = np.linspace(min_V,max_V,int(np.round(r2/step_V)))

        #max to min
        r3 = np.abs(min_V- max_V)
        p3 = np.linspace(max_V,min_V,int(np.round(r3/step_V)))

        #min to last
        r4 = np.abs(last_V - min_V)
        p4 = np.linspace(min_V,last_V,int(np.round(r4/step_V)))

        cv = []
        if r1:
            cv = p1 #start to min
        for i in range(cycles):
            cv = np.append(cv,p2) #min to max
            cv = np.append(cv,p3) #max to min
        if r4:
            cv = np.append(cv,p4) #min to last

        rtn = self.write_voltage_batch(voltages = cv,delay = int(np.round(1000/step_hz)))
        num_points = rtn.shape[0]
        cycle_points = num_points // cycles
        duration_s = num_points / step_V
        time_stamps = np.linspace(0, duration_s, num_points)
        cycle_nums = np.zeros(num_points)
        for i in range(0, cycles):
            cycle_nums[i * cycle_points: (i + 1) * cycle_points] = np.full(cycle_points, i)
        return np.column_stack((time_stamps, rtn[:, 1], rtn[:, 0], cycle_nums, np.zeros(num_points), cv))

    def perform_LSV(self,
                    start_V: float,
                    end_V: float,
                    mV_s: float,
                    step_hz: float,
                    hold_start_s: float = 0.0,
                    hold_end_s: float = 0.0) -> np.ndarray:
        """
        Performs Linear Sweep Voltammetry (LSV).
        Returns array with columns:
        [time (s), potential (V), current (A), cycle_num, exp_num, applied_voltage (V)]
        """
        # --- check inputs ---
        if step_hz <= 0:
            raise ValueError("step_hz must be > 0")
        if mV_s <= 0:
            raise ValueError("mV_s (scan rate) must be > 0")

        # stop current hold and start
        self.write_current_hold_stop()
        self.write_switch(True)

        V_s = float(mV_s) / 1000.0         # V/s
        step_V = V_s / float(step_hz)      # step
        if step_V <= 0:
            raise ValueError("Computed step_V must be > 0")

        r = abs(float(end_V) - float(start_V))
        n_sweep = int(np.floor(r / step_V)) + 1  
        if n_sweep < 2:
            n_sweep = 2                         

        sweep = np.linspace(start_V, end_V, n_sweep, endpoint=True, dtype=np.float32)

        delay_ms = max(1, int(np.round(1000.0 / float(step_hz))))

        rtn = self.write_voltage_batch(voltages=sweep, delay=delay_ms)

        num_points = rtn.shape[0]
        dt = delay_ms / 1000.0
        time_stamps = (np.arange(num_points, dtype=np.float32) * dt)

        cycle_nums = np.zeros(num_points, dtype=np.float32)
        exp_nums   = np.zeros(num_points, dtype=np.float32)

        # rtn: [:,0]=I(A), [:,1]=V(V)
        return np.column_stack((time_stamps, rtn[:, 1], rtn[:, 0], cycle_nums, exp_nums, sweep))

    
    def perform_DPV(self, start_V, pulse_V, step_V, end_V, potential_hold_ms, pulse_hold_ms, cycles, sample_hz):
        """Performs DPV with given parameters.

        Returns:
            _type_: 2 columns, column 0: I (A) | column 1: V
        """
        self.write_current_hold_stop()
        if SwitchState == False:
            self.write_switch(True)

        step_ms = int(np.round(np.ceil(1000 / sample_hz)))
        def hold(v,ms):
            n = int(np.round(ms/step_ms))
            return np.zeros(n,np.float32) + v
        dpv = []
        ascend_list = np.linspace(start_V,end_V,int(np.round(abs(end_V - start_V)/step_V)))
        descend_list = np.flip(ascend_list)
        for i in range(cycles):
            for step in ascend_list[:-1]: #ascending
                dpv = np.append(dpv,hold(step,potential_hold_ms)) #potential hold at stair step
                dpv = np.append(dpv,hold(step+pulse_V,pulse_hold_ms)) #potential hold of the peak before the next stair step
            for step in descend_list[:-1]: #same but descending
                dpv = np.append(dpv,hold(step,potential_hold_ms)) 
                dpv = np.append(dpv,hold(step-pulse_V,pulse_hold_ms))
        dpv = np.append(dpv,hold(start_V,potential_hold_ms))
        # np.savetxt("dpv_targets.csv",dpv)
        return self.write_voltage_batch(voltages = dpv,delay = step_ms)

    def perform_CDPV(self,
                     min_V: float,
                     pulse_V: float,
                     step_V: float,
                     max_V: float,
                     potential_hold_ms: int,
                     pulse_hold_ms: int,
                     voltage_hold_s: float,
                     start_V: float = None,
                     cycles: int = 1,
                     sample_hz = 1000
                     ):
        """
        performs cyclic DPV experiment from ocp and ends up with ocp
        :param min_V:
        :param pulse_V:
        :param step_V:
        :param max_V:
        :param potential_hold_ms:
        :param pulse_hold_ms:
        :param cycles:
        :param sample_hz:
        :return:
        """
        if start_V is None:
            start_V = self.read_ocp()
        stop_V = start_V

        self.write_current_hold_stop()
        self.write_potential(start_V)
        self.write_switch(True)
        time.sleep(voltage_hold_s)

        step_ms = int(np.round(np.ceil(1000 / sample_hz)))

        def hold(v, ms):
            n = int(np.round(ms / step_ms))
            return np.zeros(n, np.float32) + v

        dpv = []

        p1 = np.linspace(start_V, min_V, int(np.round(abs(min_V - start_V) / step_V)))
        p2 = np.linspace(min_V, max_V, int(np.round(abs(max_V - min_V) / step_V)))
        p3 = np.linspace(max_V, stop_V, int(np.round(abs(max_V - stop_V) / step_V)))

        for i in range(cycles):
            for step in p1[:-1]:  # start_V to min
                dpv = np.append(dpv, hold(step, potential_hold_ms))  # potential hold at stair step
                dpv = np.append(dpv, hold(step + pulse_V,
                                          pulse_hold_ms))  # potential hold of the peak before the next stair step
            for step in p2[:-1]:  # min to max
                dpv = np.append(dpv, hold(step, potential_hold_ms))
                dpv = np.append(dpv, hold(step - pulse_V, pulse_hold_ms))

            for step in p3[:-1]:  # max to stop_V
                dpv = np.append(dpv, hold(step, potential_hold_ms))
                dpv = np.append(dpv, hold(step + pulse_V, pulse_hold_ms))

        dpv = np.append(dpv, hold(start_V, potential_hold_ms))
        rtn = self.write_voltage_batch(voltages=dpv, delay=step_ms)
        num_points = rtn.shape[0]
        cycle_points = num_points // cycles
        duration_s = num_points/sample_hz
        time_stamps = np.linspace(voltage_hold_s, voltage_hold_s+duration_s, num_points)
        cycle_nums = np.zeros(num_points)
        for i in range(0, cycles):
            cycle_nums[i * cycle_points: (i+1) * cycle_points] = np.full(cycle_points, i)
        return np.column_stack((time_stamps, rtn[:, 1], rtn[:, 0], cycle_nums, np.zeros(num_points), dpv))

    def perform_multi_CV(self,
                        min_V: float,
                        max_V: float,
                        cycles: int,
                        scan_rate_list: list,
                        step_hz: float,
                        start_V: float = None,
                        last_V: float = None):
        """
        Perform Cyclic Voltammetry (CV) at multiple scan rates.

        Args:
            min_V (float): Minimum potential (V).
            max_V (float): Maximum potential (V).
            cycles (int): Number of CV cycles per scan rate.
            scan_rate_list (list): List of scan rates in V/s (e.g., [0.02, 0.04, 0.06]).
            step_hz (float): Sampling frequency in Hz.
            start_V (float, optional): Starting potential (V). If None, OCP is used.
            last_V (float, optional): Final potential (V). If None, OCP is used.

        Returns:
            dict: Dictionary mapping each scan rate to its CV data array.
                Each array has columns:
                [time (s), potential (V), current (A),
                cycle_num, exp_num, applied_voltage (V)]
        """
        results = {}

        for scan_rate in scan_rate_list:
            print(f"Running CV at {scan_rate*1000:.0f} mV/s ...")
            cv_data = self.perform_CV(min_V=min_V,
                                    max_V=max_V,
                                    cycles=cycles,
                                    mV_s=scan_rate * 1000,  # convert V/s → mV/s
                                    step_hz=step_hz,
                                    start_V=start_V,
                                    last_V=last_V)
            results[scan_rate] = cv_data

        return results


    def process_CDPV(self, data: np.ndarray, file_basename: Union[str, Path]):
        base = Path(file_basename)
        base_no_ext = base.with_suffix("")
        out_dir = base_no_ext.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_raw = base_no_ext.with_name(f"{base_no_ext.stem}_CDPV_raw.csv")
        png_raw = base_no_ext.with_name(f"{base_no_ext.stem}_CDPV_proc.png")
        csv_proc = base_no_ext.with_name(f"{base_no_ext.stem}_CDPV_proc.csv")
        
        np.savetxt(csv_raw, data, delimiter=",", fmt="%.3E,%.3E,%.3E,%d,%d,%.3E",
                   header="time,voltage,current,cycle_num,exp_num,voltage_applied")
        proc_cdpv = plot_cdpv(data, png_raw, True, log_file=None)[:,1:3]
        np.savetxt(csv_proc, proc_cdpv, delimiter=",", fmt="%.3E,%.3E",
                   header="voltage,current")
        
    def process_CV(self, data: np.ndarray, file_basename: Union[str, Path]):
        base = Path(file_basename)
        base_no_ext = base.with_suffix("")
        out_dir = base_no_ext.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_raw = base_no_ext.with_name(f"{base_no_ext.stem}_CV_raw.csv")
        png_raw = base_no_ext.with_name(f"{base_no_ext.stem}_CV_proc.png")
        csv_proc = base_no_ext.with_name(f"{base_no_ext.stem}_CV_proc.csv")
        np.savetxt(csv_raw, data, delimiter=",", fmt="%.3E,%.3E,%.3E,%d,%d,%.3E",
                   header="time,voltage,current,cycle_num,exp_num,voltage_applied")
        proc_cv = plot_cv(data, png_raw)
        np.savetxt(csv_proc, proc_cv, delimiter=",",fmt="%.3E,%.3E",
                   header="voltage,current")
        
    def process_LSV(self, data: np.ndarray, file_basename: Union[str, Path]):
        """
        Process LSV data:
        - Save raw data (time, voltage, current, cycle_num, exp_num, voltage_applied)
        - Plot LSV curve
        - Save processed voltage-current data

        Args:
            data (np.ndarray): LSV raw data returned by perform_LSV
                file_basename (Union[str, Path]): Base filename for saving results

        Returns:
            np.ndarray: Processed LSV data [voltage, current]
        """
        base = Path(file_basename)
        base_no_ext = base.with_suffix("")
        out_dir = base_no_ext.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        # file path
        csv_raw = base_no_ext.with_name(f"{base_no_ext.stem}_LSV_raw.csv")
        png_proc = base_no_ext.with_name(f"{base_no_ext.stem}_LSV_proc.png")
        csv_proc = base_no_ext.with_name(f"{base_no_ext.stem}_LSV_proc.csv")

        # save the original
        np.savetxt(csv_raw, data, delimiter=",",
                fmt="%.3E,%.3E,%.3E,%d,%d,%.3E",
                header="time,voltage,current,cycle_num,exp_num,voltage_applied")

        # call the plotting function
        proc_lsv = plot_lsv(data, png_proc)

        # save the processed one
        np.savetxt(csv_proc, proc_lsv, delimiter=",", fmt="%.3E,%.3E",
                header="voltage,current")

        return proc_lsv

    def process_multi_CV(self,
                        cv_results: dict,
                        file_basename: Union[str, Path]):
        """
        Process and save results of multiple CV experiments.
        Each scan rate gets its own raw/proc CSV and PNG.

        Args:
            cv_results (dict): Dictionary {scan_rate: cv_data} from perform_multi_CV
            file_basename (Union[str, Path]): Base filename (e.g., "results/multi_cv")

        Returns:
            dict: {scan_rate: processed_data}
                where processed_data is np.ndarray [voltage, current]
        """
        base = Path(file_basename)
        base_no_ext = base.with_suffix("")
        out_dir = base_no_ext.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        processed = {}

        for scan_rate, data in cv_results.items():
            # e.g. 0.02 V/s → 20mVs
            rate_str = f"{int(scan_rate*1000)}mVs"

            # file name
            file_base = base_no_ext.with_name(f"{base_no_ext.stem}_{rate_str}")

            # call process_CV
            proc_cv = self.process_CV(data, file_base)

            processed[scan_rate] = proc_cv

        return processed

    
    
if __name__ == "__main__":
    poten_name = "/dev/poten_2" #"/dev/potentiostat0" + sys.argv[1]
    file_name = sys.argv[2]

    ps = Potentiostat(serial_port=poten_name)
    print("ps created, connecting...")
    ps.connect()
    print("ps connected")
    ps.write_switch(0)
    ps.write_dac(channels=[DAC.CE_IN,DAC.A_REF,DAC.V_AN], voltages=[0,-5,0]) #initialize like this
    ocp = ps.read_ocp()
    print(f"ocp is, {ocp}")

    # Test CDPV
    print("CDPV")
    rtn = ps.perform_CDPV(0.0, 0.11, 0.01, 0.8, 500, 50, 5, 0)
    #rtn = ps.perform_CDPV(-0.8, 0.11, 0.01, 0.5, 500, 50, 5, 0)
    np.savetxt(f"{file_name}_CDPV_raw_poten{sys.argv[1]}.csv", rtn, delimiter=",",
               fmt="%.3E,%.3E,%.3E,%d,%d,%.3E")
    proc_cdpv = plot_cdpv(rtn, f"{file_name}_CDPV_proc_poten{sys.argv[1]}.png",
            True, f"ref_fit_log_poten{sys.argv[1]}.log")
    np.savetxt(f"{file_name}_CDPV_proc_poten{sys.argv[1]}.csv", proc_cdpv[:,0:5], delimiter=",",
               fmt="%.3E,%.3E,%.3E,%d,%d")

    # Test CV
    print("CV")
    rtn = ps.perform_CV(-0.2, 1, 5, 200, 250)
    # rtn = ps.perform_CV(-1.2, 1.2, 5, 500, 250)
    np.savetxt(f"{file_name}_CV_raw_poten{sys.argv[1]}.csv", rtn, delimiter=",",
               fmt="%.3E,%.3E,%.3E,%d,%d,%.3E")
    proc_cv = plot_cv(rtn, f"{file_name}_CV_proc_poten{sys.argv[1]}.png")
    np.savetxt(f"{file_name}_CV_proc_poten{sys.argv[1]}.csv", proc_cv, delimiter=",",
               fmt="%.3E,%.3E")

    # close poten
    ps.write_switch(0)
    ps.disconnect()

# scan_rate_list = [20e-3, 40e-3, 60e-3]  # V/s

# # 1. 跑多速率CV
# cv_results = pstat.perform_multi_CV(min_V=-0.5,
#                                     max_V=1.0,
#                                     cycles=2,
#                                     scan_rate_list=scan_rate_list,
#                                     step_hz=20)

# # 2. 保存和处理
# proc_results = pstat.process_multi_CV(cv_results, "results/multi_cv")
