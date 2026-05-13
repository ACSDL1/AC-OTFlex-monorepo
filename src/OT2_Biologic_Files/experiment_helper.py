import math
import os
import re
import time
from typing import List, Tuple, Dict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from client import biologic_stream

def run_experiment(channel, usb_port, techniques, save_path, experiment_id):
    """Stream data from the Biologic client and write CSV files per technique."""

    dfData = pd.DataFrame()
    intID_tech = 0
    intID_tech_add = 0
    strCurrentTechnique = ""
    boolNewTechnique = False
    boolAdd1ToTechIndex = False
    boolFirstTechnique = True
    fltTime_prev = 0
    fltTime_curr = 0

    runner = biologic_stream(
        channel=channel,
        techniques=techniques,
        usb_port=usb_port,
    )

    for data_temp in runner:
        if boolFirstTechnique:
            strCurrentTechnique = (
                str(type(data_temp.data)).split("'")[1].split(".")[-2]
            )
            boolFirstTechnique = False

        if data_temp.tech_index != intID_tech:
            boolNewTechnique = True

        if "process_index" in data_temp.data.to_json():
            dfData_temp = pd.DataFrame(
                data_temp.data.process_data.to_json(), index=[0]
            )
        else:
            dfData_temp = pd.DataFrame(
                data_temp.data.to_json(), index=[0]
            )
            if "time" in data_temp.data.to_json():
                fltTime_prev = fltTime_curr
                fltTime_curr = float(data_temp.data.to_json()["time"])
            if (fltTime_prev - 2 > fltTime_curr) and (
                data_temp.tech_index == intID_tech
            ):
                boolAdd1ToTechIndex = True
                boolNewTechnique = True

        if boolNewTechnique:
            dfData.to_csv(
                os.path.join(
                    save_path,
                    f"{experiment_id}_{intID_tech+intID_tech_add}_{strCurrentTechnique}.csv",
                ),
                index=False,
            )
            dfData = pd.DataFrame()
            boolNewTechnique = False
            if boolAdd1ToTechIndex:
                intID_tech_add += 1
                boolAdd1ToTechIndex = False
            intID_tech = data_temp.tech_index
            strCurrentTechnique = (
                str(type(data_temp.data)).split("'")[1].split(".")[-2]
            )

        dfData = pd.concat([dfData, dfData_temp], ignore_index=True)
    else:
        time.sleep(1)

    dfData.to_csv(
        os.path.join(
            save_path,
            f"{experiment_id}_{intID_tech+intID_tech_add}_{strCurrentTechnique}.csv",
        ),
        index=False,
    )
