from techniques_builder import (
    make_ocv,
    make_peis,
    make_lp,
    make_cp,
    make_cp_pulse,
    make_cv_uniform_scan_rate,
)


ocvTech_15sec = make_ocv(
    rest_time_s=15,
    record_every_dT=0.1,
    record_every_dE=10,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
)

ocvTech_30sec = make_ocv(
    rest_time_s=30,
    record_every_dT=0.1,
    record_every_dE=10,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
)


# ---------- PEIS: no OER ----------
peisTech_noOER = make_peis(
    initial_voltage_step=0.0,
    vs_initial=True, # OCV
    duration_step=5,
    amplitude_voltage=0.01,
    initial_frequency=200000,
    final_frequency=0.1,
    frequency_number=32,
    average_n_times=2,
    record_every_dT=0.1,
    record_every_dI=0.01,
    sweep=SweepMode.Logarithmic,
    correction=False,
    wait_for_steady=0.1,
    bandwidth=BANDWIDTH.BW_5,
    E_range=E_RANGE.E_RANGE_2_5V,
)

# ---------- PEIS: under OER ----------
peisTech_OER = make_peis(
    initial_voltage_step=1.5,
    vs_initial=False, # OER
    duration_step=15,
    amplitude_voltage=0.01,
    initial_frequency=200000,
    final_frequency=0.1,
    frequency_number=32,
    average_n_times=2,
    record_every_dT=0.1,
    record_every_dI=0.01,
    sweep=SweepMode.Logarithmic,
    correction=False,
    wait_for_steady=0.1,
    bandwidth=BANDWIDTH.BW_5,
    E_range=E_RANGE.E_RANGE_2_5V,
)


    

# ---------- CVA: different sweep speeds ----------


cvTech_20 = make_cv_uniform_scan_rate(
    Ei_V=1.275, 
    E1_V=1.325, 
    E2_V=1.225, 
    Ef_V=1.275, 
    scan_rate=0.02, 
    n_cycles=2, 
    vs_initial=False, 
    record_every_dE=0.01, 
    average_over_dE=True,
    begin_measuring_i=0.5,
    end_measuring_i=1,
    E_range=E_RANGE.E_RANGE_2_5V,
    I_range=I_RANGE.I_RANGE_100mA,
    bandwidth=BANDWIDTH.BW_5,
)

cvTech_40 = make_cv_uniform_scan_rate(
    Ei_V=1.275, 
    E1_V=1.325, 
    E2_V=1.225, 
    Ef_V=1.275, 
    scan_rate=0.04, 
    n_cycles=2, 
    vs_initial=False, 
    record_every_dE=0.01, 
    average_over_dE=True,
    begin_measuring_i=0.5,
    end_measuring_i=1,
    E_range=E_RANGE.E_RANGE_2_5V,
    I_range=I_RANGE.I_RANGE_100mA,
    bandwidth=BANDWIDTH.BW_5,
)

cvTech_60 = make_cv_uniform_scan_rate(
    Ei_V=1.275, 
    E1_V=1.325, 
    E2_V=1.225, 
    Ef_V=1.275, 
    scan_rate=0.06, 
    n_cycles=2, 
    vs_initial=False, 
    record_every_dE=0.01, 
    average_over_dE=True,
    begin_measuring_i=0.5,
    end_measuring_i=1,
    E_range=E_RANGE.E_RANGE_2_5V,
    I_range=I_RANGE.I_RANGE_100mA,
    bandwidth=BANDWIDTH.BW_5,
)

cvTech_80 = make_cv_uniform_scan_rate(
    Ei_V=1.275, 
    E1_V=1.325, 
    E2_V=1.225, 
    Ef_V=1.275, 
    scan_rate=0.08, 
    n_cycles=2, 
    vs_initial=False, 
    record_every_dE=0.01, 
    average_over_dE=True,
    begin_measuring_i=0.5,
    end_measuring_i=1,
    E_range=E_RANGE.E_RANGE_2_5V,
    I_range=I_RANGE.I_RANGE_100mA,
    bandwidth=BANDWIDTH.BW_5,
)

cvTech_100 = make_cv_uniform_scan_rate(
    Ei_V=1.275, 
    E1_V=1.325, 
    E2_V=1.225, 
    Ef_V=1.275, 
    scan_rate=0.10, 
    n_cycles=2, 
    vs_initial=False, 
    record_every_dE=0.01, 
    average_over_dE=True,
    begin_measuring_i=0.5,
    end_measuring_i=1,
    E_range=E_RANGE.E_RANGE_2_5V,
    I_range=I_RANGE.I_RANGE_100mA,
    bandwidth=BANDWIDTH.BW_5,
)


#---------- CP 10mA/cm-2 ----------

cpTech_OER_10mAcm_2 = make_cp(
    current=0.025,
    duration=120,
    vs_initial=False,
    record_every_dT=0.1,
    record_every_dE=0.001,
    n_cycles=0,
    I_range=I_RANGE.I_RANGE_100mA,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
)

cpTech_OER_5mAcm_2 = make_cp(
    current=0.0125,
    duration=120,
    vs_initial=False,
    record_every_dT=0.1,
    record_every_dE=0.001,
    n_cycles=0,
    I_range=I_RANGE.I_RANGE_100mA,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
)


# ---------- LSV: OER performance ----------
lpTech_lsv_OER = make_lp(
    Ei_voltage=1.3,
    El_voltage=2,
    vs_initial_scan=False,
    scan_rate=0.01,
    rest_time_s=5,
    record_every_dTr=0.1,
    record_every_dEr=10,
    record_every_dE=0.001,
    average_over_dE=True,
    begin_measuring_I=0.5,
    end_measuring_I=1,
    I_range=I_RANGE.I_RANGE_100mA,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
)


cpTech_10mAcm_2_pulse = make_cp_pulse(
    current_on=0.025,
    current_off=0.0,
    duration_on=5,
    duration_off=30,
    n_cycles=2,
    vs_initial=False,
    record_every_dT=0.1,
    record_every_dE=0.001,
    I_range=I_RANGE.I_RANGE_100mA,
    E_range=E_RANGE.E_RANGE_2_5V,
    bandwidth=BANDWIDTH.BW_5,
)

OER_chara_techniques = [ocvTech_15sec, 
            cpTech_OER_10mAcm_2, 
            ocvTech_30sec,
            cpTech_10mAcm_2_pulse,
            peisTech_noOER, 
            peisTech_OER, 
            lpTech_lsv_OER,
            lpTech_lsv_OER,
            lpTech_lsv_OER,
            ocvTech_15sec,
            cvTech_20, 
            cvTech_40, 
            cvTech_60, 
            cvTech_80, 
            cvTech_100,]