from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

""" Constant used in the program"""
# When the board is first connected it is necessary to send it a three byte
# initialisation code:
INITIALIZASION_CODE = b'\x21\x01\x00'
# The board will then send back a three byte confirmation code:
CONFIRMATION_CHARACTERISTICS = b'\x21\x01\x00'
# The signals from the board consist of a sequence of 38 bytes.
# The first two are:
HEAD_BUFFER = b'\x01\x24'
#  Communications using BLE
WRITECHARACTERISTICS = '1B7E8272-2877-41C3-B46E-CF057C562023'
READCONFIRMATION = '1B7E8273-2877-41C3-B46E-CF057C562023'
READDATA = '1B7E8262-2877-41C3-B46E-CF057C562023'
DEVICELIST = ['Chessnut Air', 'Smart Chess']

# Within each byte the lower 4 bits represent the
# first square and the higher 4 bits represent the
# second square
MASKLOW = 0b00001111

# Each square has a value specifying the piece:
convertDict = {0: " ",
               1: "q",
               2: "k",
               3: "b",
               4: "p",
               5: "n",
               6: "R",
               7: "P",
               8: "r",
               9: "B",
               10: "N",
               11: "Q",
               12: "K"}

"""Discover chessnut Air devices.
See pdf file Chessnut_comunications.pdf
for more information."""


class GetChessnutAirDevices:
    """Class created to discover chessnut Air devices.
    It returns the first device with a name that maches
    the names in DEVICELIST.
    """

    def __init__(self, timeout=10.0):
        self.deviceNameList = DEVICELIST  # valid device name list
        self.device = self.advertisement_data = None

    def filter_by_name(
        self,
        device: BLEDevice,
        advertisement_data: AdvertisementData,
    ) -> None:
        """Callback for each discovered device.
        return True if the device name is in the list of
        valid device names otherwise it returns False"""
        if any(ext in device.name for ext in self.deviceNameList):
            self.device = device
            return True
        else:
            return False

    async def discover(self, timeout=10.0):
        """Scan for chessnut Air devices"""
        print("scanning, please wait...")
        await BleakScanner.find_device_by_filter(
            self.filter_by_name)
        if self.device is None:
            print("No chessnut Air devices found")
            return
        print("done scanning")
