import requests
import json
import logging
from typing import Literal, Union

# from prefect import task

LOGGER = logging.getLogger(__name__)

class opentronsClient:
    '''
    each object will represent a single experiment
    '''

    def __init__(self,
                 strRobotIP: str,
                 dicHeaders: dict = {"opentrons-version": "*"},
                 strRobot: Literal["flex","ot2"] = "ot2"):
        '''
        initializes the object with the robot IP and headers

        arguments
        ----------
        strRobotIP: str
            the IP address of the robot

        dicHeaders: dict
            the headers to be used in the requests

        returns
        ----------
        None
        '''
        self.robotType = strRobot
        self.robotIP = strRobotIP
        self.headers = dicHeaders
        self.runID = None
        self.commandURL = None

        # *** NEED TO ADD FIXED TRASH TO LABWARE BY DEFAULT ***
        self.labware = {}#{"fixed-trash": {'id': 'fixed-trash', 'slot': 12}}

        self.pipettes = {}
        self.__initalizeRun()

    # @task
    def __initalizeRun(self):
        '''
        creates a new blank run on the opentrons with command endpoints
        
        arguments
        ----------
        None

        returns
        ----------
        None
        '''

        strRunURL = f"http://{self.robotIP}:31950/runs"
        # create a new run
        response = requests.post(url=strRunURL,
                                 headers=self.headers
                                 )

        if response.status_code == 201:
            dicResponse = json.loads(response.text)
            # get the run ID
            self.runID = dicResponse['data']['id']
            # setup command endpoints
            self.commandURL = strRunURL + f"/{self.runID}/commands"

            # LOG - info
            LOGGER.info(f"New run created with ID: {self.runID}")
            LOGGER.info(f"Command URL: {self.commandURL}")

        else:
            raise Exception(f"Failed to create a new run.\nError code: {response.status_code}\n Error message: {response.text}")
        
    def getRunInfo(self):
        '''
        gets the information for the current run

        arguments
        ----------
        None

        returns
        ----------
        dicRunInfo: dict
            the information for the current run
        '''

        # LOG - info
        LOGGER.info(f"Getting information for run: {self.runID}")

        response = requests.get(
            url = f"http://{self.robotIP}:31950/runs/{self.runID}",
            headers = self.headers
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 200:
            jsonRunInfo = json.loads(response.text)
            # LOG - info
            LOGGER.info(f"Run information retrieved.")

        else:
            raise Exception(f"Failed to get run information.\nError code: {response.status_code}\n Error message: {response.text}")
        
        return jsonRunInfo
        
        
    def loadLabware(self,
                    strSlot: Union[str, int],
                    strLabwareName: str,
                    strLabwareLocation:str=None,
                    strNamespace: str = "opentrons",
                    intVersion: int = 1,
                    strIntent: str = "setup"):
        '''
        loads labware onto the robot

        arguments
        ----------
        intSlot: int
            the slot number where the labware is to be loaded

        strLabwareName: str
            the name of the labware to be loaded
            
        strNamespace: str
            the namespace of the labware to be loaded
            default: "opentrons"

        intVersion: int
            the version of the labware to be loaded
            default: 1

        strIntent: str
            the intent of the command
            default: "setup"

        returns
        ----------
        strLabwareIdentifier_temp: str
            the identifier of the labware that was loaded

        '''

        loc = {"slotName": str(strSlot)}
        if strLabwareLocation != None: 
            loc = {"labwareId":str(self.labware[strLabwareLocation]['id'])}
        dicCommand = {
            "data": {
                "commandType": "loadLabware",
                "params": {
                    "location": loc,
                    "loadName": strLabwareName,
                    "namespace": strNamespace,
                    "version": str(intVersion)
                },
                "intent": strIntent
            }
        }

        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Loading labware: {strLabwareName} in slot: {strSlot}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # convert response to dictionary
            dicResponse = json.loads(response.text)
            if dicResponse['data']['status'] == "failed":
                # log the error
                LOGGER.error(f"Failed to load labware.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
                # raise exception
                raise Exception(f"Failed to load labware.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
            else:
                strLabwareID = dicResponse['data']['result']['labwareId']
                #strLabwareURi = dicResponse['data']['result']['labwareUri']
                strLabwareIdentifier_temp = strLabwareName + "_" + str(strSlot)
                self.labware[strLabwareIdentifier_temp] = {"id": strLabwareID, "slot": strSlot}
                # LOG - info
                LOGGER.info(f"Labware loaded with name: {strLabwareName} and ID: {strLabwareID}")
        else:
            raise Exception(f"Failed to load labware.\nError code: {response.status_code}\n Error message: {response.text}")
        
        return strLabwareIdentifier_temp
        
    def loadCustomLabwareFromFile(self, strSlot, strFilePath, strLabware=None):
        with open(strFilePath, 'r', encoding='utf-8') as f:
            labware = self.loadCustomLabware(
                dicLabware = json.load(f),
                strSlot = strSlot,
                strLabware=strLabware
            )
            return labware
    
    def loadCustomLabware(self,
                          dicLabware: dict,
                          strSlot: Union[str,int],
                          strLabware:str=None
                          ):
        '''
        loads custom labware onto the robot

        arguments
        ----------
        dicLabware: dict
            the JSON object of the custom labware to be loaded (directly from opentrons labware definitions)

        intSlot: int
            the slot number where the labware is to be loaded

        strLabwareID: str
            the ID of the labware to be loaded - to be used for loading the same labware multiple times
            default: None

        returns
        ----------
        None
        '''

        dicCommand = {'data' : dicLabware}

        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Loading custom labware: {dicLabware['parameters']['loadName']} in slot: {strSlot}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        response = requests.post(
            url = f"http://{self.robotIP}:31950/runs/{self.runID}/labware_definitions",
            headers = self.headers,
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # convert response to dictionary
            dicResponse = json.loads(response.text)
            # if the response failed
            # if dicResponse['data']['status'] == "failed":
            #     # log the error
            #     LOGGER.error(f"Failed to load custom labware.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
            #     # raise exception
            #     raise Exception(f"Failed to load custom labware.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
            if False: pass
            else:
                # LOG - info
                LOGGER.info(f"Custome labware {dicLabware['parameters']['loadName']} loaded in slot: {strSlot} successfully.")
                # load the labware
                strLabwareIdentifier_temp = self.loadLabware(strSlot = strSlot,
                                                            strLabwareName = dicLabware['parameters']['loadName'],
                                                            strNamespace = dicLabware['namespace'],
                                                            intVersion = dicLabware['version'],
                                                            strIntent = "setup",
                                                            strLabwareLocation=strLabware
                                                            )
                return strLabwareIdentifier_temp
        else:
            raise Exception(f"Failed to load custom labware.\nError code: {response.status_code}\n Error message: {response.text}")

    def loadPipette(self,
                    strPipetteName: str,
                    strMount: str):
        '''
        loads a pipette onto the robot

        arguments
        ----------
        strPipetteName: str
            the name of the pipette to be loaded

        strMount: str
            the mount where the pipette is to be loaded

        returns
        ----------
        None
        '''

        dicCommand = {
            "data": {
                "commandType": "loadPipette",
                "params": {
                    "pipetteName": strPipetteName,
                    "mount": strMount
                },
                "intent": "setup"
            }
        }

        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Loading pipette: {strPipetteName} on mount: {strMount}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # convert response to dictionary
            dicResponse = json.loads(response.text)
            # if the response failed
            if dicResponse['data']['status'] == "failed":
                # log the error
                LOGGER.error(f"Failed to load pipette.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
                # raise exception
                raise Exception(f"Failed to load pipette.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
            else:
                strPipetteID = dicResponse['data']['result']['pipetteId']
                self.pipettes[strPipetteName] = {"id": strPipetteID, "mount": strMount}
                # LOG - info
                LOGGER.info(f"Pipette loaded with name: {strPipetteName} and ID: {strPipetteID}")
        else:
            raise Exception(
                f"Failed to load pipette.\nError code: {response.status_code}\n Error message: {response.text}"
            )

    def homeRobot(self):
        '''
        homes the robot - this should be done before doing any other movements of the robot per instance but need to implement this***

        arguments
        ----------
        None

        returns
        ----------
        None
        '''

        strCommand = json.dumps({"target": "robot"})

        # LOG - info
        LOGGER.info(f"Homing the robot")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        response = requests.post(
            url = f"http://{self.robotIP}:31950/robot/home",
            headers = self.headers,
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")
        if response.status_code == 200:
            # LOG - info
            LOGGER.info(f"Robot homed successfully.")
        else:
            raise Exception(
                f"Failed to home the robot.\nError code: {response.status_code}\n Error message: {response.text}"
            )

    def pickUpTip(self,
                  strLabwareName: str,
                  strPipetteName: str,
                  strOffsetStart: str = "top",
                  fltOffsetX: float = 0,
                  fltOffsetY: float = 0,
                  fltOffsetZ: float = 0,
                  strWellName: str = "A1",
                  strIntent: str = "setup"
                  ):
        '''
        picks up a tip from a labware

        arguments
        ----------
        strLabwareName: str
            the name of the labware from which the tip is to be picked up

        strPipetteName: str
            the name of the pipette to be used for picking up the tip

        strOffsetStart: str
            the starting point of the pick up
            default: "top"

        fltOffsetX: float
            the x offset of the pick up
            default: 0

        fltOffsetY: float
            the y offset of the pick up
            default: 0

        fltOffsetZ: float
            the z offset of the pick up
            default: 0 

        strWellName: str
            the name of the well from which the tip is to be picked up
            default: "A1"

        strIntent: str
            the intent of the command
            default: "setup"

        returns
        ----------
        None
        '''

        # *** WIP ***
        # build in some check to see if the tip is already picked up

        dicCommand = {
            "data": {
                "commandType": "pickUpTip",
                "params": {
                    "labwareId": self.labware[strLabwareName]["id"],
                    "wellName": strWellName,
                    "wellLocation": {
                        "origin": strOffsetStart,
                        "offset": {"x": fltOffsetX,
                                   "y": fltOffsetY,
                                   "z": fltOffsetZ}
                        },
                    "pipetteId": self.pipettes[strPipetteName]["id"],
                },
                "intent": strIntent
            }
        }

        jsonCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Picking up tip from labware: {strLabwareName}")
        # LOG - debug
        LOGGER.debug(f"Command: {jsonCommand}")

        jsonResponse = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = jsonCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {jsonResponse.text}")

        if jsonResponse.status_code == 201:
            # convert response to dictionary
            dicResponse = json.loads(jsonResponse.text)
            if dicResponse['data']['status'] == "failed":
                # log the error
                LOGGER.error(f"Failed to pick up tip.\nResponse error code: {dicResponse['data']['error']['errorCode']}\n Error type: {dicResponse['data']['error']['errorType']}\n Error message: {dicResponse['data']['error']['detail']}")
                # raise exception
                raise Exception(f"Failed to pick up tip.\nResponse error code: {dicResponse['data']['error']['errorCode']}\n Error type: {dicResponse['data']['error']['errorType']}\n Error message: {dicResponse['data']['error']['detail']}")
            else:
                # LOG - info
                LOGGER.info(f"Tip picked up from labware: {strLabwareName}, well: {strWellName}")
        else:
            raise Exception(f"Failed to pick up tip.\nError code: {jsonResponse.status_code}\n Error message: {jsonResponse.text}")
        
    def liquidProbe(self,
            strLabwareName: str,
            strPipetteName: str,
            strOffsetStart: str = "top",
            fltOffsetX: float = 0,
            fltOffsetY: float = 0,
            fltOffsetZ: float = 0,
            strWellName: str = "A1",
            strIntent: str = "setup"
            ):


        # *** WIP ***
        # build in some check to see if the tip is already picked up

        dicCommand = {
            "data": {
                "commandType": "liquidProbe",
                "params": {
                    "labwareId": self.labware[strLabwareName]["id"],
                    "wellName": strWellName,
                    "wellLocation": {
                        "origin": strOffsetStart,
                        "offset": {"x": fltOffsetX,
                                   "y": fltOffsetY,
                                   "z": fltOffsetZ}
                        },
                    "pipetteId": self.pipettes[strPipetteName]["id"],
                },
                "intent": strIntent
            }
        }

        jsonCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Picking up tip from labware: {strLabwareName}")
        # LOG - debug
        LOGGER.debug(f"Command: {jsonCommand}")

        jsonResponse = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = jsonCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {jsonResponse.text}")

        if jsonResponse.status_code == 201:
            # convert response to dictionary
            dicResponse = json.loads(jsonResponse.text)
            if dicResponse['data']['status'] == "failed":
                # log the error
                LOGGER.error(f"Failed to pick up tip.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
                # raise exception
                raise Exception(f"Failed to pick up tip.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
            else:
                # LOG - info
                LOGGER.info(f"Tip picked up from labware: {strLabwareName}, well: {strWellName}")
        else:
            raise Exception(f"Failed to pick up tip.\nError code: {jsonResponse.status_code}\n Error message: {jsonResponse.text}")

    def __moveTipToDisposal(self,
                   strPipetteName: str,
                   intSpeed: int = 100, # mm/s
                   strIntent: str = "setup"
                   ):
        
        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "moveToAddressableAreaForDropTip",
                "params": {
                    # "minimumZHeight": 50,
                    # "forceDirect": False,
                    "speed": intSpeed,
                    "pipetteId": self.pipettes[strPipetteName]["id"],
                    "addressableAreaName":'movableTrashA3' if self.robotType == "flex" else 'fixedTrash' # ID of disposal chute
                },
                "intent": strIntent
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Disposing of held tip: {strPipetteName}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # LOG - info
            LOGGER.info(f"Tip dropped into disposal: {strPipetteName}")
        else:
            raise Exception(f"Failed to drop tip.\nError code: {response.status_code}\n Error message: {response.text}")

    def moveToLabware(self,
                strLabwareName:str,
                strPipetteName: str,
                intMinimumZHeight:int=60,
                boolStayAtHighestZ:bool=False,
                intSpeed: int = 130, # mm/s
                strIntent: str = "setup",
                fltOffsetX:float = 0,
                fltOffsetY:float = 0,
                fltOffsetZ:float = 0,
                ):
        
        labwareLocation = self.labware[strLabwareName]["slot"]

        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "moveToAddressableArea",
                "params": {
                    "minimumZHeight": intMinimumZHeight,
                    "forceDirect": False, # Opentrons does not care for any labware on deck, keep set to false
                    "speed": intSpeed,
                    "pipetteId": self.pipettes[strPipetteName]["id"],
                    "addressableAreaName":labwareLocation,
                    "stayAtHighestPossibleZ":boolStayAtHighestZ,
                    "offset": {
                        "x":fltOffsetX,
                        "y":fltOffsetY,
                        "z":fltOffsetZ,
                    }
                },
                "intent": strIntent
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Disposing of held tip: {strPipetteName}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # LOG - info
            LOGGER.info(f"Tip dropped into disposal: {strPipetteName}")
        else:
            raise Exception(f"Failed to drop tip.\nError code: {response.status_code}\n Error message: {response.text}")
        
    def moveGripper(self,
                fltOffsetX:float,
                fltOffsetY:float,
                fltOffsetZ:float,
                strIntent: str = "setup"
                ):
        
        # #! Home extensionZ axis command
        # dicCommand = {
        #     "data": {
        #         "commandType": "home",
        #         "params": {
        #             "axes": [
        #                 "extensionZ",
        #             ]
        #         },
        #         "intent": strIntent
        #     }
        # }

        # homeResponse = requests.post(
        #     url = self.commandURL,
        #     headers = self.headers,
        #     params = {"waitUntilComplete": True},
        #     data = json.dumps(dicCommand)
        # )

        # pass


        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "robot/moveTo",
                "params": {
                    "mount":"extension",
                    "destination": {
                        "x":fltOffsetX,
                        "y":fltOffsetY,
                        "z":fltOffsetZ,
                    },
                    "speed":100
                },
                "intent": strIntent
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        # LOGGER.info(f"Disposing of held tip: {strPipetteName}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        pass
        # # LOG - debug
        # LOGGER.debug(f"Response: {response.text}")

        # if response.status_code == 201:
        #     # LOG - info
        #     LOGGER.info(f"Tip dropped into disposal: {strPipetteName}")
        # else:
        #     raise Exception(f"Failed to drop tip.\nError code: {response.status_code}\n Error message: {response.text}")


    def __dropTipInPlace(self, 
                         strPipetteName: str,
                         strIntent: str = "setup",
                         boolHomeAfter:bool = False):
        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "dropTipInPlace",
                "params": {
                    "pipetteId": self.pipettes[strPipetteName]["id"],
                    "homeAfter": boolHomeAfter
                    },
                "intent": strIntent
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Dropping tip in place: {strPipetteName}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # LOG - info
            LOGGER.info(f"Tip dropped at current location")
        else:
            raise Exception(f"Failed to drop tip in place.\nError code: {response.status_code}\n Error message: {response.text}")


    def dropTip(self,
                strPipetteName: str,
                boolDropInDisposal:bool = True,
                strLabwareName: str = None,
                strWellName: str = "A1",
                strOffsetStart: str = "center",
                fltOffsetX: float = 0,
                fltOffsetY: float = 0,
                fltOffsetZ: float = 0,
                boolHomeAfter: bool = False,
                boolAlternateDropLocation: bool = False,
                intSpeed:int = 200, # mm/s
                strIntent: str = "setup",
                ):
        '''
        drops a tip into the robot's disposal or a labware well

        arguments
        ----------
        strPipetteName: str
            the name of the pipette from which the tip is to be dropped

        strLabwareName: str
            the name of the labware into which the tip is to be dropped
            default: "fixed-trash"

        boolDropInPlace: bool
            when true will drop the pipette into the specified well
            default: True

        strWellName: str
            the name of the well into which the tip is to be dropped
            default: "A1"

        strOffsetStart: str
            the starting point of the drop
            default: "center"

        fltOffsetX: float
            the x offset of the drop
            default: 0

        fltOffsetY: float
            the y offset of the drop
            default: 0

        fltOffsetZ: float
            the z offset of the drop
            default: 0

        boolHomeAfter: bool
            whether the robot should home after the drop
            default: False

        boolAlternateDropLocation: bool
            whether the robot should use an alternate drop location
            default: False

        strIntent: str
            the intent of the command
            default: "setup"
        '''

        # *** BUILD IN CHECK TO SEE IF THERE IS A TIP TO DROP ***

        # If tip is to be dropped into trash
        if boolDropInDisposal:
            self.__moveTipToDisposal(strPipetteName=strPipetteName, intSpeed=intSpeed, strIntent=strIntent)
            self.__dropTipInPlace(strPipetteName=strPipetteName, strIntent=strIntent, boolHomeAfter=boolHomeAfter)
            return

        # Drop the tip in a labware well
        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "dropTip",
                "params": {
                    "pipetteId": self.pipettes[strPipetteName]["id"],
                    "labwareId": self.labware[strLabwareName]["id"],
                    "wellName": strWellName,
                    "wellLocation": {
                        "origin": strOffsetStart,
                        "offset": {"x": fltOffsetX,
                                   "y": fltOffsetY,
                                   "z": fltOffsetZ}
                    },
                    "homeAfter": boolHomeAfter,
                    "alternateDropLocation": boolAlternateDropLocation
                },
                "intent": strIntent
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Dropping tip into labware: {strLabwareName}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # convert response to dictionary
            dicResponse = json.loads(response.text)
            if dicResponse['data']['status'] == "failed":
                # log the error
                LOGGER.error(f"Failed to drop tip.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
                # raise exception
                raise Exception(f"Failed to drop tip.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
            else:
                # LOG - info
                LOGGER.info(f"Tip dropped into labware: {strLabwareName}, well: {strWellName}")
        else:
            raise Exception(f"Failed to drop tip.\nError code: {response.status_code}\n Error message: {response.text}")

    def aspirate(self,
                 strLabwareName: str,
                 strWellName: str,
                 strPipetteName: str,
                 intVolume: int,                        # uL
                 fltFlowRate: float = 274.7,            # uL/s -- need to check this
                 strOffsetStart: str = "center",
                 fltOffsetX: float = 0,
                 fltOffsetY: float = 0,
                 fltOffsetZ: float = 0,
                 strIntent: str = "setup"
                 ):
        '''
        aspirates liquid from a well

        arguments
        ----------
        strLabwareName: str
            the name of the labware from which the liquid is to be aspirated

        strWellName: str
            the name of the well from which the liquid is to be aspirated

        strPipetteName: str
            the name of the pipette to be used for aspiration

        intVolume: int  
            the volume of liquid to be aspirated
            units: uL

        intFlowRate: int
            the flow rate of the aspiration
            units: uL/s
            default: 7

        strOffsetStart: str
            the starting point of the aspiration
            default: "top"

        fltOffsetX: float
            the x offset of the aspiration
            default: 0

        fltOffsetY: float
            the y offset of the aspiration
            default: 0

        fltOffsetZ: float
            the z offset of the aspiration
            default: 0

        strIntent: str
            the intent of the command
            default: setup

        returns
        ----------
        None
        '''

        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "aspirate",
                "params": {
                    "labwareId": self.labware[strLabwareName]["id"],
                    "wellName": strWellName,
                    "wellLocation": {
                        "origin": strOffsetStart,
                        "offset": {"x": fltOffsetX,
                                   "y": fltOffsetY,
                                   "z": fltOffsetZ}
                    },
                    "flowRate": str(fltFlowRate),
                    "volume": str(intVolume),
                    "pipetteId": self.pipettes[strPipetteName]["id"]
                },
                "intent": strIntent
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Aspirating from labware: {strLabwareName}, well: {strWellName}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # convert response to dictionary
            dicResponse = json.loads(response.text)
            if dicResponse['data']['status'] == "failed":
                # Get error info safely
                error_info = dicResponse.get('data', {}).get('error', {})
                error_code = error_info.get('errorCode', 'Unknown')
                error_type = error_info.get('errorType', 'Unknown')
                error_detail = error_info.get('detail', 'No details available')
                
                # log the error
                LOGGER.error(f"Failed to aspirate.\nResponse error code: {error_code}\n Error type: {error_type}\n Error message: {error_detail}")
                # raise exception
                raise Exception(f"Failed to aspirate.\nResponse error code: {error_code}\n Error type: {error_type}\n Error message: {error_detail}")
            else:
                # LOG - info
                LOGGER.info(f"Aspiration successful.")
        else:
            raise Exception(
                f"Failed to aspirate.\nError code: {response.status_code}\n Error message: {response.text}"
            )

    def dispense(self,
                 strLabwareName: str,
                 strWellName: str,
                 strPipetteName: str,
                 intVolume: int,                        # uL
                 fltFlowRate: float = 274.7,            # uL/s -- need to check this
                 strOffsetStart: str = "top",
                 fltOffsetX: float = 0,
                 fltOffsetY: float = 0,
                 fltOffsetZ: float = 0,
                 strIntent: str = "setup"
                 ):
        '''
        dispenses liquid into a well

        arguments
        ----------
        strLabwareName: str
            the name of the labware from which the liquid is to be aspirated

        strWellName: str
            the name of the well from which the liquid is to be aspirated

         strPipetteName: str
            the name of the pipette to be used for aspiration

        intVolume: int  
            the volume of liquid to be aspirated
            units: uL

        intFlowRate: int
            the flow rate of the aspiration
            units: uL/s
            default: 7

        strOffsetStart: str
            the starting point of the aspiration
            default: "top"

        fltOffsetX: float
            the x offset of the aspiration
            default: 0

        fltOffsetY: float
            the y offset of the aspiration
            default: 0

        fltOffsetZ: float
            the z offset of the aspiration
            default: 0

        strIntent: str
            the intent of the command
            default: setup

        returns
        ----------
        None
        '''

        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "dispense",
                "params": {
                    "labwareId": self.labware[strLabwareName]["id"],
                    "wellName": strWellName,
                    "wellLocation": {
                        "origin": strOffsetStart,
                        "offset": {"x": fltOffsetX,
                                   "y": fltOffsetY,
                                   "z": fltOffsetZ}
                    },
                    "flowRate": fltFlowRate,
                    "volume": intVolume,
                    "pipetteId": self.pipettes[strPipetteName]["id"]
                },
                "intent": strIntent
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Dispensing into labware: {strLabwareName}, well: {strWellName}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # convert response to dictionary
            dicResponse = json.loads(response.text)
            if dicResponse['data']['status'] == "failed":
                # log the error
                LOGGER.error(f"Failed to dispense.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
                # raise exception
                raise Exception(f"Failed to dispense.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
            else:
                # LOG - info
                LOGGER.info("Dispense successful.")
        else:
            raise Exception(f"Failed to dispense.\nError code: {response.status_code}\n Error message: {response.text}")
        
    def blowout(self,
                strLabwareName: str,
                strWellName: str,
                strPipetteName: str,
                fltFlowRate: float = 274.7,            # uL/s -- need to check this
                strOffsetStart: str = "top",
                fltOffsetX: float = 0,
                fltOffsetY: float = 0,
                fltOffsetZ: float = 0
                ) -> None:
        '''
        blows out liquid from a pipette

        arguments
        ----------
        strLabwareName: str
            the name of the labware from which the liquid is to be aspirated

        strWellName: str
            the name of the well from which the liquid is to be aspirated

        strPipetteName: str
            the name of the pipette to be used for aspiration

        fltFlowRate: float
            the flow rate of the aspiration
            units: uL/s
            default: 274.7

        strOffsetStart: str
            the starting point of the aspiration
            default: "top"

        fltOffsetX: float
            the x offset of the aspiration
            default: 0

        fltOffsetY: float
            the y offset of the aspiration
            default: 0

        fltOffsetZ: float
            the z offset of the aspiration
            default: 0

        returns
        ----------
        None
        '''

        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "blowout",
                "params": {
                    "labwareId": self.labware[strLabwareName]["id"],
                    "wellName": strWellName,
                    "wellLocation": {
                        "origin": strOffsetStart,
                        "offset": {"x": fltOffsetX,
                                   "y": fltOffsetY,
                                   "z": fltOffsetZ}
                    },
                    "flowRate": fltFlowRate,
                    "pipetteId": self.pipettes[strPipetteName]["id"]
                },
                "intent": "setup"
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Blowing out from labware: {strLabwareName}, well: {strWellName}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # convert response to dictionary
            dicResponse = json.loads(response.text)
            # if the response failed
            if dicResponse['data']['status'] == "failed":
                # log the error
                LOGGER.error(f"Failed to blowout.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
                # raise exception
                raise Exception(f"Failed to blowout.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
            else:
                # LOG - info
                LOGGER.info("Blowout successful.")
        else:
            raise Exception(f"Failed to blowout.\nError code: {response.status_code}\n Error message: {response.text}")

    def moveToWell(self,
                   strLabwareName: str,
                   strWellName: str,
                   strPipetteName: str,
                   strOffsetStart: str = "top",
                   fltOffsetX: float = 0,
                   fltOffsetY: float = 0,
                   fltOffsetZ: float = 0,
                   strIntent: str = "setup",
                   intSpeed: int = 400   # mm/s
                   ):
        '''
        moves the pipette to a well

        arguments
        ----------
        strLabwareName: str
            the name of the labware to which the pipette is to be moved

        strWellName: str
            the name of the well to which the pipette is to be moved

        strPipetteName: str
            the name of the pipette to be moved

        strOffsetStart: str
            the starting point of the move
            default: "top"

        fltOffsetX: float
            the x offset of the move
            default: 0

        fltOffsetY: float
            the y offset of the move
            default: 0

        fltOffsetZ: float
            the z offset of the move
            default: 0

        strIntent: str
            the intent of the command
            default: setup  

        returns
        ----------
        None
        '''

        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "moveToWell",
                "params": {
                    "speed": intSpeed,
                    "labwareId": self.labware[strLabwareName]["id"],
                    "wellName": strWellName,
                    "wellLocation": {
                        "origin": strOffsetStart,
                        "offset": {"x": fltOffsetX,
                                   "y": fltOffsetY,
                                   "z": fltOffsetZ},
                    },
                    "pipetteId": self.pipettes[strPipetteName]["id"],
                },
                "intent": strIntent,
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Moving pipette to labware: {strLabwareName}, well: {strWellName}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # convert response to dictionary
            dicResponse = json.loads(response.text)
            # if the response failed
            if dicResponse['data']['status'] == "failed":
                # log the error
                LOGGER.error(f"Failed to move pipette.\nResponse error code: {dicResponse.get('error', {}).get('errorCode', 'Unknown')}\n Error type: {dicResponse.get('error', {}).get('errorType', 'Unknown')}\n Error message: {dicResponse.get('error', {}).get('detail', 'Unknown')}")
                # raise exception
                raise Exception(f"Failed to move pipette.\nFull Response: {dicResponse}")
            else:
                # LOG - info
                LOGGER.info("Move successful.")
        else:
            raise Exception(
                f"Failed to move pipette.\nError code: {response.status_code}\n Error message: {response.text}"
            )


    def moveLabware(self, strMovingLabware:str=None, strDestinationLabware:str=None, strIntent:str="setup"):
        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "moveLabware",
                "params": {
                    "labwareId": self.labware[strMovingLabware]['id'],
                    "newLocation": {
                        "labwareId":self.labware[strDestinationLabware]['id']
                    },
                    "strategy":"usingGripper",
                    "dropOffset":{
                        "x":0,
                        "y":0,
                        "z":-8,
                    }
                },
                "intent": strIntent
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        #! LOGGER.info(f"Openning the gripper")
        # LOG - debug
        #! LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # LOG - info
            LOGGER.info(f"Moved labware successfully.")
        else:
            raise Exception(
                f"Failed to mve labware.\nError code: {response.status_code}\n Error message: {response.text}"
            )

    def pipetteHasTip(self, strPipetteName, strIntent: str = "setup"):
        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "verifyTipPresence",
                "params": {
                    "pipetteId": self.pipettes[strPipetteName]['id'],
                    "expectedState": "absent"},
                "intent": strIntent
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Checking for tip on pipette {strPipetteName}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # Check if request succeeded
            if (data:=json.loads(response.text)['data'])["status"] == "succeeded":
                LOGGER.info(f"No tip is present on {strPipetteName}.")
                return False
            elif data['error']['errorType'] == 'TipAttachedError':
                LOGGER.info(f"A tip is present on {strPipetteName}.")
                return True
        else:
            raise Exception(
                f"Failed to check for tip.\nError code: {response.status_code}\n Error message: {response.text}"
            )

    def closeGripper(self,
                 fltGripForce: float = None,
                 strIntent: str = "setup"):

        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "robot/closeGripperJaw",
                "params": {},
                "intent": strIntent
            }
        }

        # add force parameter if passed, if none robot will use built-in default force
        if fltGripForce != None:
            dicCommand['data']['params'].update({'force':fltGripForce})

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        #LOGGER.info(f"Closing the gripper{f" with {fltGripForce}N of force" if fltGripForce else ""}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # # make request
        # payload = {
        #     "data": {
        #         "commandType": "calibration/calibrateGripper",
        #         "params": {
        #         }
        #     }
        # }

        # HEADERS = {
        #     "Content-Type": "application/json",
        #     "opentrons-version": "*"
        # }

        # url = self.commandURL
        
        # response = requests.post(url, headers=HEADERS, data=json.dumps(payload))

        response = requests.post(
            url = self.commandURL,#self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # LOG - info
            LOGGER.info(f"Closed grip successfully.")
        else:
            raise Exception(
                f"Failed to close gripper.\nError code: {response.status_code}\n Error message: {response.text}"
            )
        
    def openGripper(self,
                 strIntent: str = "setup"):

        # make command dictionary
        dicCommand = {
            "data": {
                "commandType": "robot/openGripperJaw",
                "params": {},
                "intent": strIntent
            }
        }

        # dump to string
        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Openning the gripper")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        response = requests.post(
            url = self.commandURL,#self.commandURL,
            headers = self.headers,
            params = {"waitUntilComplete": True},
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # LOG - info
            LOGGER.info(f"Openned gripper successfully.")
        else:
            raise Exception(
                f"Failed to open gripper.\nError code: {response.status_code}\n Error message: {response.text}"
            )

    def addLabwareOffsets(self,
                          strLabwareName : str,
                          fltXOffset: float,
                          fltYOffset: float,
                          fltZOffset: float
                          ):
        '''
        adds offsets to the labware

        arguments
        ----------
        strLabwareName: str
            the name of the labware to which the offsets are to be added

        fltXOffset: float
            the x offset to be added

        fltYOffset: float
            the y offset to be added

        fltZOffset: float
            the z offset to be added

        returns
        ----------
        None
        '''

        # from the self.labware dictionary, get the labware ID
        strLabwareID = self.labware[strLabwareName]["id"]

        print(strLabwareID)

        dicRunInfo = self.getRunInfo()
        print(dicRunInfo)

        # find the list of labware from the run info
        lstLabware = dicRunInfo['data']['labware']

        strDefinitionUri = None

        # for every dictionary in the list of labware
        for dicLabware_temp in lstLabware:
            # if the labware ID matches the labware ID of the labware we are looking for
            if dicLabware_temp['id'] == strLabwareID:
                # get the definitionUri
                strDefinitionUri = dicLabware_temp['definitionUri']
                # get the slot
                strSlot = dicLabware_temp['location']['slotName']
    
        print(strDefinitionUri)

        # if the definitionUri is not found
        if strDefinitionUri == None:
            raise Exception(f"Labware not found in run information.")

        # make the command dictionary
        dicCommand = {
            "data": {
                "definitionUri": strDefinitionUri,
                "location":{"slotName": strSlot},
                "vector": {"x": str(fltXOffset),
                           "y": str(fltYOffset),
                           "z": str(fltZOffset)}
            }
        }

        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Adding offsets to labware: {strLabwareName}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = f"http://{self.robotIP}:31950/runs/{self.runID}/labware_offsets",
            headers = self.headers,
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # convert response to dictionary
            dicResponse = json.loads(response.text)
            # if the response failed
            if dicResponse['data']['status'] == "failed":
                # log the error
                LOGGER.error(f"Failed to add offsets to labware.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
                # raise exception
                raise Exception(f"Failed to add offsets to labware.\nResponse error code: {dicResponse.error.errorCode}\n Error type: {dicResponse.error.errorType}\n Error message: {dicResponse.error.detail}")
            else:
                # LOG - info
                LOGGER.info(f"Offsets added to labware: {strLabwareName}")
        else:
            raise Exception(f"Failed to add offsets to labware.\nError code: {response.status_code}\n Error message: {response.text}")

    def lights(self,
               strState: str = 'true'
               )-> None:
        '''
        turns the lights on or off

        arguments
        ----------
        strState: string
            whether the lights should be turned on or off
            default: true (on)

        returns
        ----------
        None
        '''

        # make strState a string if it is not already
        if type(strState) != str:
            strState = str(strState)

        # make strState lowercase
        strState = strState.lower()

        # check if the state is valid
        if strState not in ['true', 'false']:
            raise Exception(f"Invalid state: {strState}, needs to be 'true' or 'false'")

        # make command dictionary
        dicCommand = {
            "on": strState
        }

        # dump to string
        strCommand = json.dumps(dicCommand)


        # LOG - info
        LOGGER.info(f"Lights On: {strState}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        # make request
        response = requests.post(
            url = f"http://{self.robotIP}:31950/robot/lights",
            headers = self.headers,
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 200:
            # LOG - info
            LOGGER.info(f"Light change successful.")
        else:
            # LOG - error
            LOGGER.error(f"Failed to turn lights {strState}.")
            # raise exception
            raise Exception(f"Failed to turn lights {strState}.\nError code: {response.status_code}\n Error message: {response.text}")

    def controlAction(self,
                      strAction: str):
        '''
        performs a control action

        arguments
        ----------
        strAction: str
            the action to be performed
            options: "pause", "play", "stop"

        returns
        ----------
        None
        '''
        # make strAction lowercase
        strAction = strAction.lower()

        # check if the action is valid
        if strAction not in ["pause", "play", "stop"]:
            raise Exception(f"Invalid action: {strAction}, needs to be 'pause', 'play', or 'stop'")

        # make command dictionary
        dicCommand = {
            "data": {
                "actionType": strAction,
        }}

        strCommand = json.dumps(dicCommand)

        # LOG - info
        LOGGER.info(f"Performing action: {strAction}")
        # LOG - debug
        LOGGER.debug(f"Command: {strCommand}")

        response = requests.post(
            url = f"http://{self.robotIP}:31950/runs/{self.runID}/actions",
            headers = self.headers,
            data = strCommand
        )

        # LOG - debug
        LOGGER.debug(f"Response: {response.text}")

        if response.status_code == 201:
            # LOG - info
            LOGGER.info(f"Action: {strAction} successful.")
        else:
            raise Exception(f"Failed to perform action.\nError code: {response.status_code}\n Error message: {response.text}")
        

            
    '''
    TODO LIST 
    -----------

    ADD CHECK TO SEE WELL IS VALID FOR ASPIRATION/DISPENSE

    '''


# oc = opentronsClient(strRobotIP="100.64.26.170", strRobot="flex")  # FLEX
# oc.closeGripper()