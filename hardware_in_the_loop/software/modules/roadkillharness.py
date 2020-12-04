# Base python imports
import os
import logging
import configparser
from typing import Optional

# Project imports
from modules.ecu import ECU
from modules.utils import get_logging_config, root_path, artifacts_path
from modules.iocontroller import IOController
from modules.cancontroller import CANController


class RoadkillHarness:
    """Class to represent the entire tester

    `Confluence <https://docs.olinelectricmotorsports.com/display/AE/Roadkill+Harness>`_
    """

    def __init__(self, pin_config: Optional[str] = None):
        # Read config
        config = configparser.ConfigParser(interpolation=None)
        config.read(os.path.join(artifacts_path, "config.ini"))

        # Create logger
        get_logging_config()
        self.log = logging.getLogger(name=__name__)

        # Create IOController
        self.log.info("Creating IOController...")
        if not pin_config:
            pin_config = config.get("PATHS", "pin_config", fallback="pin_info.csv")

        self.io = IOController(
            pin_info_path=os.path.join(artifacts_path, pin_config),
            serial_path=config.get("PATHS", "serial_path", fallback="/dev/arduino"),
        )

        # Create all ECUs
        ecus = {}

        self.log.info("Creating throttle ecu...")
        self.throttle = ECU(name="throttle", io=self.io)
        ecus["throttle"] = self.throttle

        self.log.info("Creating dashboard ecu...")
        self.dashboard = ECU(name="dashboard", io=self.io)
        ecus["dashboard"] = self.dashboard


        self.log.info("Creating air_ctrl ecu...")
        self.air_ctrl = ECU(name="air_ctrl", io=self.io)
        ecus["air_ctrl"] = self.air_ctrl

        self.log.info("Creating bms_core ecu...")
        self.bms_core = ECU(name="bms_core", io=self.io)
        ecus["bms_core"] = self.bms_core

        self.log.info("Creating brakelight_bspd ecu...")
        self.brakelight_bspd = ECU(name="brakelight_bspd", io=self.io)
        ecus["brakelight_bspd"] = self.brakelight_bspd


        # Add more ECUs here

        # Create CANController
        self.log.info("Creating CANController...")
        self.can = CANController(ecus=ecus, can_spec_path=os.path.join(artifacts_path, config.get("PATHS", "dbc_path")))
