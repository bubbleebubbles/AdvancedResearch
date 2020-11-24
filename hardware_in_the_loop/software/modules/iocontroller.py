# Imports
import serial
import logging
from typing import Tuple


class IOController:
    """High level python object to interface with hardware.

    Used to set analog and digital pins for simulation.

    https://docs.olinelectricmotorsports.com/display/AE/IO+Controller
    """

    def __init__(self, pin_info_path: str, serial_path: str):
        # Create logger (all config should already be set by RoadkillHarness)
        self.log = logging.getLogger(name=__name__)

        self.pin_info = self.read_pin_info(path=pin_info_path)
        try:
            self.serial = serial.Serial(port=serial_path, baudrate=115200, timeout=5)
        except serial.serialutil.SerialException as e:
            # Couldn't open the specified port; initialize w/o hardware for testing
            self.log.error(f"Failed to connect to hardware at {pin_info_path}")
            self.log.error(e)
            self.serial = None

    def set_state(self, pin: str, value) -> None:
        """Set the value of an IO pin in the HitL system

        Args:
            pin (str): The name of the pin to update (e.x. THROTTLE_PEDAL_1)

            value (int or float): The value to set the pin to (e.x. 2.5)
                - 0 or 1 for digital, volts for analog

        Message format:
            4 bytes (all big endian)

            Byte 0:
                Bit 0: 1 (indicates a set request)
                Bits 1-7: Board number of the signal we want to set

            Byte 1:
                Bits 0-7: Pin number of the signal we want to set

            Bytes 2-3:
                Bits 0-15: 16 bit precision value to set, with 0% = 0x0000 and  100% = 0xFFFF
        """
        # If no hardware, log an error
        if not self.serial:
            self.log.error("Could not set state; no hardware connection")
            return

        # Byte 1
        board = self.pin_info[pin]["board"] | (1 << 7)  # set the leftmost bit to 1 to designate message as setter

        # Byte 2
        pin_num = self.pin_info[pin]["pin"]

        # Bytes 3-4
        byte2 = 0  # most significant byte
        byte3 = 0  # least significant byte

        if self.pin_info[pin]["type"] == "DIGITAL":
            if value == 1:
                byte2 = byte3 = 0xFF  # oh yea, this syntax works :)
        elif self.pin_info[pin]["type"] == "ANALOG":
            byte2, byte3 = self._map_to_machine(value, self.pin_info[pin]["min"], self.pin_info[pin]["max"])
        else:
            raise Exception(f"Unsupported signal type: {self.pin_info[pin]['type']}")

        request = bytes([board, pin_num, byte2, byte3])
        self._send_request(request)
        self.log.info(f"Set state of {pin} to {value}")

    def get_state(self, pin: str):
        """Request a hardware state from the HitL system.

        Args:
            pin (str): The name of the state we want to get (e.x. "THROTTLE_POT_1", not 11)

        Message format:
            2 bytes (all big endian):

            Byte 0:
                Bit 0: 0 (indicates a get request)
                Bits 1-7: Board number of the signal we want to get

            Byte 1:
                Bits 0-7: Pin number of the signal we want to get

        Returns:
            int or float: The value of the requested state
        """
        # If no hardware, log an error
        if not self.serial:
            raise Exception ("Could not get state, no hardware connection")

        # Flush the serial buffer, in case anything has come in
        self.serial.flush()

        # Create and send request
        board = self.pin_info[pin]["board"]
        pin_num = self.pin_info[pin]["pin"]
        request = bytes([board, pin_num])
        self._send_request(request)

        # Wait for response. We want this to block (which it does)
        response = self.serial.read(size=2)  # Read 2 bytes
        self.log.debug(f"Received {response}")

        out = 0  # Type float or int
        if self.pin_info[pin]["type"] == "DIGITAL":
            out = 0 if int.from_bytes(response, "big") == 0 else 1
        elif self.pin_info[pin]["type"] == "ANALOG":
            out = self._map_to_human(response, self.pin_info[pin]["min"], self.pin_info[pin]["max"])
        else:
            raise Exception(f"Unsupported signal type: {self.pin_info[pin]['type']}")

        self.log.info(f"Got state of {pin}: {out}")
        return out

    def read_pin_info(self, path: str) -> dict:
        """Read in the pin address information, given a path to a .csv file

        Args:
            path: The path to the .csv file containing pin information (see
            https://docs.google.com/spreadsheets/d/15hpe0DXfQto9N2hawawvfeHTE1sq-UT7sgDl__hCTZ4/edit?usp=sharing
            for details)

        Returns:
            dict: A dictionary of (str: dict) pairs
        """
        out = {}
        with open(path, "r") as f:
            line = f.readline()  # clear the header line
            line = f.readline()  # get the first data line ready
            while line != "":  # keep reading until we hit the end
                # parse line
                data = line.split(",")
                add = data[0]
                board = data[1]
                pin = data[2]
                sim = data[3]
                sig = data[4]
                sig_type = data[5]
                sig_min = data[6]
                sig_max = data[7]

                # add data to dictionary
                sig_dict = {}
                sig_dict["address"] = int(add)
                sig_dict["board"] = int(add)
                sig_dict["pin"] = int(add)
                sig_dict["simulator"] = sim
                sig_dict["type"] = sig_type
                sig_dict["min"] = float(sig_min)
                sig_dict["max"] = float(sig_max)
                out[sig] = sig_dict

                # read new line
                line = f.readline()

        return out

    def _map_to_machine(self, value: float, low: float, high: float) -> Tuple[int, int]:
        """Map from a floating point value to a 16 bit precision value, from min to max

        Args:
            value (float): The value (usually a voltage) requested
            low, high (floats): The min and max acceptable voltages

            Example: _map_to_machine(3.0, 2.5, 5) -> (0x00, 0x??)

        Returns:
            Tuple[int, int]: the two int values (0-255) that represent the scaled value
        """
        if not (low < value < high):
            raise Exception(f"Value {value} not in range [{low}-{high}]! Cannot set value.")
        mapped = int((value - low) * (0xFFFF - 0x0000) / (high - low))
        byte0 = mapped >> 8
        byte1 = mapped & 0x00FF
        return byte0, byte1

    def _map_to_human(self, value: bytes, low: float, high: float) -> float:
        """Inverse of map to machine; convert from 2 bytes to a float

        Args:
            value (float): The bytes received
            low, high (floats): The min and max acceptable voltages

            Example: _map(3.0, 2.5, 5) -> (0x00, 0x??)

        Returns:
            Tuple[int, int]: the two int values (0-255) that represent the scaled value
        """
        response = int.from_bytes(value, "big")

        mapped = (response - 0x0000) * (high - low) / (0xFFFF - 0x0000)

        if not (low < mapped < high):
            raise Exception(f"Value {value} not in range [{low}-{high}]! Invalid response received")

        return mapped

    def _send_request(self, request: bytes) -> None:
        """Send a request over serial to set a pin's value

        Args:
            request (bytes): The bytes to send
        """
        self.log.debug(f"Sent {request}")
        self.serial.write(request)

    def __del__(self) -> None:
        """Destructor (called when the program ends)

        Close the serial port for a clean teardown
        """
        if self.serial:
            self.serial.close()
