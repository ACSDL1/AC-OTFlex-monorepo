
from biologic import connect, BANDWIDTH, I_RANGE, E_RANGE
from biologic.techniques.ocv import OCVTechnique, OCVParams, OCVData
from biologic.techniques.peis import PEISTechnique, PEISParams, SweepMode, PEISData
from biologic.techniques.ca import CATechnique, CAParams, CAStep, CAData
from biologic.techniques.cpp import CPPTechnique, CPPParams, CPPData
from biologic.techniques.pzir import PZIRTechnique, PZIRParams, PZIRData
from biologic.techniques.cv import CVTechnique, CVParams, CVStep, CVData
from biologic.techniques.lp import LPTechnique, LPParams, LPStep, LPData
from biologic.techniques.cp import CPTechnique, CPParams, CPStep, CPData
import numpy as np

# ====================== OCV TEMPLATE ======================
def make_ocv(
    rest_time_s = 10,
    record_every_dT=0.1,
    record_every_dE=10,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
):
    """
    Create an Open Circuit Voltage (OCV) technique.

    Args:
        rest_time_s: Rest time duration in seconds. Defaults to 10.
        record_every_dT: Time interval for recording data in seconds. Defaults to 0.1.
        record_every_dE: Voltage change threshold for recording in V. Defaults to 10.
        E_range: Voltage range setting. Defaults to E_RANGE.E_RANGE_2_5V.
        bandwidth: Bandwidth setting for the measurement. Defaults to BANDWIDTH.BW_5.

    Returns:
        OCVTechnique: Configured OCV technique ready for execution.
    """
    return OCVTechnique(OCVParams(
        rest_time_T=rest_time_s,
        record_every_dT=record_every_dT,
        record_every_dE=record_every_dE,
        E_range=E_range,
        bandwidth=bandwidth,
    ))

# ====================== CV TEMPLATE ======================
def make_cv_uniform_scan_rate(
    Ei_V: float,
    E1_V: float,
    E2_V: float,
    Ef_V: float,
    scan_rate: float,
    n_cycles: int = 1,
    vs_initial: bool = False,
    record_every_dE: float = 0.01,
    average_over_dE: bool = True,
    begin_measuring_i: float = 0.5,
    end_measuring_i: float = 1,
    E_range=E_RANGE.E_RANGE_2_5V,
    I_range=I_RANGE.I_RANGE_10mA,
    bandwidth=BANDWIDTH.BW_5,
):
    """
    Create a Cyclic Voltammetry (CV) technique with uniform scan rate and vs_initial for all CV steps.

    Args:
        Ei_V: Initial voltage in V.
        E1_V: First vertex voltage in V.
        E2_V: Second vertex voltage in V.
        Ef_V: Final voltage in V.
        scan_rate: Scan rate in V/s.
        n_cycles: Number of cycles to perform. Defaults to 1.
        vs_initial: Whether voltages are relative to initial potential. Defaults to False (vs reference electrode).
        record_every_dE: Voltage change threshold for recording in V. Defaults to 0.01.
        average_over_dE: Whether to average data over dE. Defaults to True.
        begin_measuring_i: Unknown usage.
        end_measuring_i: Unknown usage
        E_range: Voltage range setting. Defaults to E_RANGE.E_RANGE_2_5V.
        I_range: Current range setting. Defaults to I_RANGE.I_RANGE_10mA.
        bandwidth: Bandwidth setting for the measurement. Defaults to BANDWIDTH.BW_5.

    Returns:
        CVTechnique: Configured CV technique ready for execution.
    """
    Ei = CVStep(
        voltage=Ei_V,
        scan_rate=scan_rate,
        vs_initial=vs_initial,
    )
    E1 = CVStep(
        voltage=E1_V,
        scan_rate=scan_rate,
        vs_initial=vs_initial,
    )
    E2 = CVStep(
        voltage=E2_V,
        scan_rate=scan_rate,
        vs_initial=vs_initial,
    )
    Ef = CVStep(
        voltage=Ef_V,
        scan_rate=scan_rate,
        vs_initial=vs_initial,
    )

    params = CVParams(
        Ei=Ei,
        E1=E1,
        E2=E2,
        Ef=Ef,
        record_every_dE=record_every_dE,
        average_over_dE=average_over_dE,
        n_cycles=n_cycles,
        begin_measuring_i=begin_measuring_i,
        end_measuring_i=end_measuring_i,
        E_range=E_range,
        I_range=I_range,
        bandwidth=bandwidth,
    )

    return CVTechnique(params)


# ====================== CA TEMPLATE ======================
def make_ca(
    voltage,
    duration,
    vs_initial=False,
    record_every_dT=0.1,
    record_every_dI=10,
    n_cycles=0,
    I_range=I_RANGE.I_RANGE_100mA,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
):
    """
    Create a Chronoamperometry (CA) technique for potentiostatic deposition.

    Args:
        voltage: Applied voltage in V
        duration: Duration in seconds
        I_range: Current range setting
        E_range: Voltage range setting
        record_every_dT: Time interval for recording in seconds
        record_every_dI: Current change threshold for recording in A
        n_cycles: Number of cycles (0 = single run)
        bandwidth: Bandwidth setting

    Returns:
        CATechnique: Configured CA technique ready for execution
    """
    ca_step = CAStep(
        voltage=voltage,
        duration=duration,
        vs_initial=vs_initial,
    )

    ca_params = CAParams(
        record_every_dT=record_every_dT,
        record_every_dI=record_every_dI,
        n_cycles=n_cycles,
        steps=[ca_step],
        E_range=E_range,
        I_range=I_range,
        bandwidth=bandwidth,
    )

    return CATechnique(ca_params)

def make_ca_staircase(
    voltage_initial,
    voltage_final,
    voltage_step,
    voltage_step_duration=2,
    ocv_in_between=True,
    ocv_step_duration=15,
    vs_initial=False,
    record_every_dT=0.1,
    record_every_dI=10,
    n_cycles=0,
    I_range=I_RANGE.I_RANGE_100mA,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
):
    """
    Create a staircase Chronoamperometry (CA) technique with sequential voltage steps and optional OCV relaxation steps.

    Args:
        voltage_initial: Starting voltage (V) of the staircase.
        voltage_final: Final voltage (V) of the staircase.
        voltage_step: Step size (V) between each voltage.
        voltage_step_duration: Duration (s) for each voltage step. Defaults to 2 seconds.
        ocv_in_between: If True, insert an OCV step after staircase steps. Defaults to True.
        ocv_step_duration: Duration (s) of each OCV step. Defaults to 15 seconds.
        vs_initial: If True, set each voltage step relative to OCV; otherwise, relative to reference. Defaults to False.
        record_every_dT: Time interval (s) for recording current/voltage. Defaults to 0.1 s.
        record_every_dI: Current change threshold (A) for extra recordings. Defaults to 10.
        n_cycles: Number of staircase/OCV cycles (0 = single run).
        I_range: Current range setting for the experiment.
        E_range: Voltage range setting for the experiment.
        bandwidth: Bandwidth setting for the measurement.

    Returns:
        CATechnique: Configured Chronoamperometry technique ready for execution.
    """


    steps = []
    for i in np.linspace(voltage_initial, voltage_final, voltage_step):
        steps.append(CAStep(
            voltage=i,
            duration=voltage_step_duration,
            vs_initial=vs_initial, # vs reference electrode
        ))
        if ocv_in_between:
            steps.append(CAStep(
                voltage=0,
                duration=ocv_step_duration,
                vs_initial=True, # vs ocv potential
            ))


    ca_params = CAParams(
        record_every_dT=record_every_dT,
        record_every_dI=record_every_dI,
        n_cycles=n_cycles,
        steps=steps,
        E_range=E_range,
        I_range=I_range,
        bandwidth=bandwidth,
    )

    return CATechnique(ca_params)

# ====================== PEIS TEMPLATE ======================
def make_peis(
    initial_voltage_step,
    vs_initial=False,
    duration_step=5,
    amplitude_voltage=0.01,
    initial_frequency=200000,
    final_frequency=1,
    frequency_number=60,
    average_n_times=2,
    record_every_dT=0.5,
    record_every_dI=0.01,
    sweep=SweepMode.Logarithmic,
    correction=False,
    wait_for_steady=0.1,
    bandwidth=BANDWIDTH.BW_5,
    E_range=E_RANGE.E_RANGE_2_5V,
):
    """
    Create a potentiostatic electrochemical impedance spectroscopy (PEIS) technique.

    Args:
        initial_voltage_step: Initial voltage step (V) to apply before EIS.
        vs_initial: If True, voltage is referenced to the initial value. Defaults to False. (False means vs reference electrode)
        duration_step: Duration (s) to hold the initial step before EIS.
        amplitude_voltage: Amplitude (V) of the sinusoidal perturbation.
        initial_frequency: Starting frequency (Hz) for the impedance scan. Defaults to 200000.
        final_frequency: Final frequency (Hz) for the scan. Defaults to 1.
        frequency_number: Number of frequencies to sample. Defaults to 60.
        average_n_times: Number of repetitions to average at each frequency. Defaults to 2.
        record_every_dT: Time interval for recording (s). Defaults to 0.5.
        record_every_dI: Current change threshold for recording (A). Defaults to 0.01.
        sweep: Sweep direction/mode for frequency (e.g., logarithmic). Defaults to SweepMode.Logarithmic.
        correction: Apply automatic impedance correction if True. Defaults to False.
        wait_for_steady: Wait time (s) for steady state before EIS. Defaults to 0.1.
        bandwidth: Bandwidth setting for measurement. Defaults to BANDWIDTH.BW_5.
        E_range: Voltage range setting. Defaults to E_RANGE.E_RANGE_2_5V.

    Returns:
        PEISTechnique: Configured PEIS technique ready for execution.
    """
    peis_params = PEISParams(
        vs_initial=vs_initial,
        initial_voltage_step=initial_voltage_step,
        duration_step=duration_step,
        record_every_dT=record_every_dT,
        record_every_dI=record_every_dI,
        final_frequency=final_frequency,
        initial_frequency=initial_frequency,
        sweep=sweep,
        amplitude_voltage=amplitude_voltage,
        frequency_number=frequency_number,
        average_n_times=average_n_times,
        correction=correction,
        wait_for_steady=wait_for_steady,
        bandwidth=bandwidth,
        E_range=E_range,
    )
    return PEISTechnique(peis_params)

# ====================== LP TEMPLATE ======================
def make_lp(
    Ei_voltage,
    El_voltage,
    vs_initial_scan,
    scan_rate,
    rest_time_s=5,
    record_every_dTr=0.5,
    record_every_dEr=0.01,
    record_every_dE=0.001,
    average_over_dE=True,
    begin_measuring_I=0.5,
    end_measuring_I=1,
    I_range=I_RANGE.I_RANGE_100mA,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
):
    """
    Create a Linear Polarization (LP) technique for corrosion monitoring.

    The LP technique is used to determine the polarization resistance (Rp) of a material
    and corrosion current (Icorr) through potential steps around the corrosion potential.

    Args:
        Ei_voltage: Initial voltage scan value (V).
        El_voltage: Final voltage scan value (V).
        vs_initial_scan: If True, voltage is referenced to the initial scan value.
        scan_rate: Scan rate (V/s) for the voltage sweep.
        rest_time_s: Rest time (s) before starting the scan. Defaults to 5.
        record_every_dTr: Time interval (s) for recording during rest. Defaults to 0.5.
        record_every_dEr: Voltage change threshold (V) for recording during rest. Defaults to 0.01.
        record_every_dE: Voltage change threshold (V) for recording during scan. Defaults to 0.001.
        average_over_dE: If True, average measurements over dE interval. Defaults to True.
        begin_measuring_i: Unknown usage.
        end_measuring_i: Unknown usage.
        I_range: Current range setting. Defaults to I_RANGE.I_RANGE_100mA.
        E_range: Voltage range setting. Defaults to E_RANGE.E_RANGE_2_5V.
        bandwidth: Bandwidth setting for measurement. Defaults to BANDWIDTH.BW_5.

    Returns:
        LPTechnique: Configured LP technique ready for execution.
    """
    Ei_step = LPStep(
        voltage_scan=Ei_voltage,
        scan_rate=scan_rate,
        vs_initial_scan=vs_initial_scan,
    )
    El_step = LPStep(
        voltage_scan=El_voltage,
        scan_rate=scan_rate,
        vs_initial_scan=vs_initial_scan,
    )
    lp_params = LPParams(
        record_every_dEr=record_every_dEr,
        rest_time_T=rest_time_s,
        record_every_dTr=record_every_dTr,
        Ei=Ei_step,
        El=El_step,
        record_every_dE=record_every_dE,
        average_over_dE=average_over_dE,
        begin_measuring_I=begin_measuring_I,
        end_measuring_I=end_measuring_I,
        I_range=I_range,
        E_range=E_range,
        bandwidth=bandwidth,
    )
    return LPTechnique(lp_params)

# ====================== CP TEMPLATE ======================
def make_cp(
    current,
    duration,
    vs_initial=False,
    record_every_dT=0.1,
    record_every_dE=0.001,
    n_cycles=1,
    I_range=I_RANGE.I_RANGE_100mA,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
):
    """
    Create a Chronopotentiometry (CP) technique.

    The CP technique applies a constant current to the electrochemical cell
    and measures the resulting potential over time.

    Args:
        current: Applied current (A) for the CP step.
        duration: Duration (s) of the current step.
        vs_initial: If True, potential is referenced to the initial value. Defaults to False.
        record_every_dT: Time interval (s) for recording data. Defaults to 0.1.
        record_every_dE: Voltage change threshold (V) for recording. Defaults to 0.001.
        n_cycles: Number of cycles to repeat. Defaults to 1.
        I_range: Current range setting. Defaults to I_RANGE.I_RANGE_100mA.
        E_range: Voltage range setting. Defaults to E_RANGE.E_RANGE_2_5V.
        bandwidth: Bandwidth setting for measurement. Defaults to BANDWIDTH.BW_5.

    Returns:
        CPTechnique: Configured CP technique ready for execution.
    """
    cp_step = CPStep(
        current=current,
        duration=duration,
        vs_initial=vs_initial,
    )
    cp_params = CPParams(
        record_every_dT=record_every_dT,
        record_every_dE=record_every_dE,
        n_cycles=n_cycles,
        steps=[cp_step],
        I_range=I_range,
        E_range=E_range,
        bandwidth=bandwidth,
    )
    return CPTechnique(cp_params)

def make_cp_pulse(
    current_on,
    current_off,
    duration_on,
    duration_off,
    n_cycles=1,
    vs_initial=False,
    record_every_dT=0.1,
    record_every_dE=0.001,
    I_range=I_RANGE.I_RANGE_100mA,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
):
    """
    Create a Chronopotentiometry (CP) pulse technique.

    The CP pulse technique applies alternating current pulses (on/off) to the
    electrochemical cell and measures the resulting potential over time.

    Args:
        current_on: Applied current (A) during the "on" phase of the pulse.
        current_off: Applied current (A) during the "off" phase of the pulse.
        duration_on: Duration (s) of the "on" phase of the pulse.
        duration_off: Duration (s) of the "off" phase of the pulse.
        n_cycles: Number of pulse cycles to repeat. Defaults to 1.
        vs_initial: If True, potential is referenced to the initial value. Defaults to False.
        record_every_dT: Time interval (s) for recording data. Defaults to 0.1.
        record_every_dE: Voltage change threshold (V) for recording. Defaults to 0.001.
        I_range: Current range setting. Defaults to I_RANGE.I_RANGE_100mA.
        E_range: Voltage range setting. Defaults to E_RANGE.E_RANGE_2_5V.
        bandwidth: Bandwidth setting for measurement. Defaults to BANDWIDTH.BW_5.

    Returns:
        CPTechnique: Configured CP pulse technique ready for execution.
    """
    # Create the on and off steps
    cp_step_on = CPStep(
        current=current_on,
        duration=duration_on,
        vs_initial=vs_initial,
    )
    cp_step_off = CPStep(
        current=current_off,
        duration=duration_off,
        vs_initial=vs_initial,
    )

    cp_params = CPParams(
        record_every_dT=record_every_dT,
        record_every_dE=record_every_dE,
        n_cycles=n_cycles,
        steps=[cp_step_on, cp_step_off],
        I_range=I_range,
        E_range=E_range,
        bandwidth=bandwidth,
    )
    return CPTechnique(cp_params)
