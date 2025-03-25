# Copyright (c) 2010-2025, Emmanuel Blot <emmanuel.blot@free.fr>
# All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import sys
import time
from binascii import hexlify
from typing import Iterable, Optional, Tuple, Union
from pyftdi.misc import pretty_size
from pyftdi.spi import SpiController, SpiPort


# pylint: disable-msg=too-many-arguments
# pylint: disable-msg=too-many-locals
# pylint: disable-msg=too-many-branches
# pylint: disable-msg=too-many-statements
# pylint: disable-msg=abstract-method
# pylint: disable-msg=invalid-name


class SerialFlashError(Exception):
    """Base class for all Serial Flash errors"""


class SerialFlashNotSupported(SerialFlashError):
    """Exception thrown when a non-existing feature is invoked"""


class SerialFlashUnknownJedec(SerialFlashNotSupported):
    """Exception thrown when a JEDEC identifier is not recognized"""

    def __init__(self, jedec):
        SerialFlashNotSupported.__init__(self, "Unknown flash device: %s" %
                                         hexlify(jedec))


class SerialFlashTimeout(SerialFlashError):
    """Exception thrown when a flash command cannot be completed in a timely
       manner"""


class SerialFlashValueError(ValueError, SerialFlashError):
    """Exception thrown when a parameter is out of range"""


class SerialFlashRequestError(SerialFlashError):
    """Cannot complete a flash device request"""


class SerialFlash:
    """Interface of a generic SPI flash device"""

    FEAT_NONE = 0x000          # No special feature
    FEAT_LOCK = 0x001          # Basic, revertable locking
    FEAT_INVLOCK = 0x002       # Inverted (bottom/top) locking
    FEAT_SECTLOCK = 0x004      # Arbitrary sector locking
    FEAT_OTPLOCK = 0x008       # OTP locking available
    FEAT_UNIQUEID = 0x010      # Unique ID
    FEAT_SECTERASE = 0x100     # Can erase whole sectors
    FEAT_HSECTERASE = 0x200    # Can erase half sectors
    FEAT_SUBSECTERASE = 0x400  # Can erase sub sectors
    FEAT_CHIPERASE = 0x800     # Can erase full chip

    def set_spi_frequency(self, freq: Optional[float] = None) -> None:
        """Set the SPI bus frequency to communicate with the device. Set
           default SPI frequency if none is provided."""
        raise NotImplementedError()

    def read(self, address: int, length: int) -> bytes:
        """Read a sequence of bytes from the specified address.

           :param address: the position of the first byte to read
           :param length: the count of bytes to read
           :return: an array of bytes
        """
        raise NotImplementedError()

    def write(self, address: int,
              data: Union[bytes, bytearray, Iterable[int]]) -> None:
        """Write a sequence of bytes, starting at the specified address.

           :note: the device cells are not automatically erased, which means
                  that the bytes actually stored to the device match a NAND
                  operation between the existing content of the cell and the
                  data values, i.e. it is only possible to write 0s into the
                  flash cells, not 1s. :py:meth:`erase` should be explictly
                  called to erase one or more blocks.

           :param address: the position of the first byte to write
           :param data: a sequence of bytes to write
        """
        raise NotImplementedError()

    def erase(self, address: int, length: int, verify: bool = False) -> None:
        """Erase a block of bytes.

           Address and length depends upon device-specific constraints and
           should be aligned on device blocks.

           As a special feature, specifying address as 0 and length to -1
           triggers a full chip erase.

           :param address: the position of the first byte to erase
           :param length: the count of bytes to erase
           :param verify: optionally check that the selected blocks have been
                          erased, reading them back.
        """
        raise NotImplementedError()

    def can_erase(self, address: int, length: int) -> None:
        """Verifies that a defined area can be erased on the flash device.
           It does not take into account any locking scheme, only the area
           boundary.

           :param address: the position of the first byte to erase
           :param length: the count of bytes to erase

           :raise SerialFlashValueError: if erase cannot be performed
        """
        raise NotImplementedError()

    def is_busy(self) -> bool:
        """Reports whether the flash may receive commands or is actually
           being performing internal work.

           :return: True if the device is busy and cannot accept new I/O
                    commands, False otherwise.
           """
        raise NotImplementedError()

    def get_capacity(self) -> int:
        """Get the flash device capacity in bytes.

           :return: the capacity of the device, in bytes.
        """
        return len(self)

    def unlock(self) -> None:
        """Make the whole device read/write.

           Some flash devices are write-locked at power up.
        """
        raise NotImplementedError()

    @property
    def unique_id(self) -> int:
        """Return the unique ID of the flash, if it exists.

           :return: the unique ID
        """
        raise NotImplementedError()

    def get_timings(self, timing: str) -> Tuple[float, float]:
        """Get a time tuple (typical, max).

           Timings are use to track whether a device successfully completed
           a command or if a command timed out.

           :param timing: the kind of operation
           :return: typical time to complete the operation, maximum time to
                    complete the operation
        """
        raise NotImplementedError()

    @classmethod
    def has_feature(cls, feature: int) -> bool:
        """Test whether the flash device supports a feature.

           :param feature: the feature to test
           :return: True if the feature is supported, False otherwise
        """
        raise NotImplementedError()

    @classmethod
    def match(cls, jedec: Union[bytes, bytearray, Iterable[int]]) -> bool:
        """Tells whether this class support this JEDEC identifier.

           :param jedec: device type as a sequence of bytes
           :return: True if the current class supports the detected device.
        """
        raise NotImplementedError()


class SerialFlashManager:
    """Serial flash manager.

       Automatically detects and instanciate the proper flash device class
       based on the JEDEC identifier which is read out from the device itself.
    """

    CMD_JEDEC_ID = 0x9F

    @staticmethod
    def get_from_controller(spictrl: SpiController,
                            cs: int = 0, freq: Optional[float] = None) \
            -> '_SpiFlashDevice':
        """Obtain an instance of the detected flash device, using an
           existing SpiController.

           :param spictrl: a PyFtdi configured SpiController instance
           :param cs: the /CS line to use from the controller
           :param freq: the SPI bus frequency for this flash device
           :return: new instance of the flash device, if detected
        """
        spi = spictrl.get_port(cs, freq)
        jedec = SerialFlashManager.read_jedec_id(spi)
        if not jedec:
            # it is likely that the latency setting is too low if this
            # condition is encountered
            raise SerialFlashUnknownJedec("Unable to read JEDEC Id")
        flash = SerialFlashManager._get_flash(spi, jedec)
        flash.set_spi_frequency(freq)
        return flash

    @staticmethod
    def get_flash_device(url: str, cs: int = 0, freq: Optional[float] = None) \
            -> '_SpiFlashDevice':
        """Obtain an instance of the detected flash device.

           :param url: PyFtdi controller or a PyUSB UsbDevice
           :param cs: the /CS line to use from the controller
           :param freq: the SPI bus frequency for this flash device
           :return: new instance of the flash device, if detected
        """
        ctrl = SpiController(cs_count=cs+1)
        ctrl.configure(url)
        spi = ctrl.get_port(cs, freq)
        jedec = SerialFlashManager.read_jedec_id(spi)
        if not jedec:
            # it is likely that the latency setting is too low if this
            # condition is encountered
            raise SerialFlashUnknownJedec("Unable to read JEDEC Id")
        flash = SerialFlashManager._get_flash(spi, jedec)
        flash.set_spi_frequency(freq)
        return flash

    @staticmethod
    def read_jedec_id(spi: SpiPort) -> bytes:
        """Read flash device JEDEC identifier (3 bytes)"""
        jedec_cmd = bytes((SerialFlashManager.CMD_JEDEC_ID,))
        return spi.exchange(jedec_cmd, 3)

    @staticmethod
    def _get_flash(spi: SpiPort, jedec: bytes) -> '_SpiFlashDevice':
        devices = []
        contents = sys.modules[__name__].__dict__
        for name in contents:
            if name.endswith('FlashDevice') and not name.startswith('_'):
                devices.append(contents[name])
        for device in devices:
            if device.match(jedec):
                return device(spi, jedec)
        if any(jedec):
            raise SerialFlashUnknownJedec(jedec)
        raise SerialFlashError('No serial flash detected')


class _SpiFlashDevice(SerialFlash):
    """Generic flash device implementation.

       Most SPI flash devices share commands and parameters. Those devices
       generally contains '25' in their reference. However, there are virtually
       no '25' device that is fully compliant with any counterpart from
       a concurrent manufacturer. Most differences are focused on lock and
       security features. Here comes the mess... This class contains the most
       common implementation for the basic feature, and each physical device
       inherit from this class for feature specialization.
    """

    CMD_READ_LO_SPEED = 0x03  # Read @ low speed
    CMD_READ_HI_SPEED = 0x0B  # Read @ high speed
    ADDRESS_WIDTH = 3

    def __init__(self, spiport: SpiPort):
        self._spi = spiport

    @property
    def spi_frequency(self) -> float:
        """REturn the current frequency of the SPI bus for this device.

           :return: the bus frequency in Hz.
        """
        return self._spi and self._spi.frequency

    def read(self, address: int, length: int) -> bytes:
        if address+length > len(self):
            raise SerialFlashValueError('Out of range')
        buf = bytearray()
        while length > 0:
            size = min(length, SpiController.PAYLOAD_MAX_LENGTH)
            data = self._read_hi_speed(address, size)
            length -= len(data)
            address += len(data)
            buf.extend(data)
        return bytes(buf)

    def erase(self, address: int, length: int, verify: bool = False) -> None:
        """Erase sectors/blocks/chip of a "generic" flash device.
           Erasure algorithm:
           The area to erase span across one or more sectors, which can be
           accounted as bigger blocks, depending on the start and end address
           of the location to be erased
           address ----------------- length ---------------------->
                 v                                                 v
              ...|LSS|LSS|LSS| LHS | LHS |  S  |  RHS  | RHS |RSS|RSS|RSS|....

             LSS: left subsector, RSS: right subsector
             LHS: left half-sector, RHS: right half-sector (32KB)
             S: (large) sector (64kB)
           Depending on the device capabilities, half-sector may or may not be
           used. This routine tries to find and erase the biggest flash page
           segments so that erasure time is decreased.
           Concrete implementation should provide the various sector sizes
           """
        # sanity check
        if address == 0 and length == -1:
            length = len(self)
        self.can_erase(address, length)
        if address == 0 and length == len(self):
            if self.has_feature(SerialFlash.FEAT_CHIPERASE):
                self._erase_chip(self.get_erase_command('chip'),
                                 self.get_timings('chip'))
                return
        self.get_erase_size()
        # first page to erase on the left-hand size
        start = address
        # last page to erase on the left-hand size
        end = start + length
        # first page to erase on the right-hand size
        rstart = start
        # last page to erase on the right-hand size
        rend = end
        if self.has_feature(SerialFlash.FEAT_SECTERASE):
            # Check whether one or more whole large sector can be erased
            sector_size = self.get_size('sector')
            sector_mask = ~(sector_size-1)
            s_start = (start+sector_size-1) & sector_mask
            s_end = end & sector_mask
            if s_start < s_end:
                self._erase_blocks(self.get_erase_command('sector'),
                                   self.get_timings('sector'),
                                   s_start, s_end, sector_size)
                # update the left-hand end marker
                end = s_start
                # update the right-hand start marker
                if s_end > rstart:
                    rstart = s_end
        if self.has_feature(SerialFlash.FEAT_HSECTERASE):
            # Check whether one or more left halfsectors can be erased
            hsector_size = self.get_size('hsector')
            hsector_mask = ~(hsector_size-1)
            hsl_start = (start+sector_size-1) & sector_mask
            hsl_end = end & sector_mask
            if hsl_start < hsl_end:
                self._erase_blocks(self.get_erase_command('hsector'),
                                   self.get_timings('hsector'),
                                   hsl_start, hsl_end, hsector_size)
                # update the left-hand end marker
                end = hsl_start
                # update the right-hand start marker
                if hsl_end > rstart:
                    rstart = hsl_end
        if self.has_feature(SerialFlash.FEAT_SUBSECTERASE):
            # Check whether one or more left subsectors can be erased
            subsector_size = self.get_size('subsector')
            subsector_mask = ~(subsector_size-1)
            ssl_start = (start+subsector_size-1) & subsector_mask
            ssl_end = end & subsector_mask
            if ssl_start < ssl_end:
                self._erase_blocks(self.get_erase_command('subsector'),
                                   self.get_timings('subsector'),
                                   ssl_start, ssl_end, subsector_size)
                # update the right-hand start marker
                if ssl_end > rstart:
                    rstart = ssl_end
        if self.has_feature(SerialFlash.FEAT_HSECTERASE):
            # Check whether one or more whole left halfsectors can be erased
            hsr_start = (rstart+hsector_size-1) & hsector_mask
            hsr_end = rend & hsector_mask
            if hsr_start < hsr_end:
                self._erase_blocks(self.get_erase_command('hsector'),
                                   self.get_timings('hsector'),
                                   hsr_start, hsr_end, hsector_size)
                # update the right-hand start marker
                if hsr_end > rstart:
                    rstart = hsr_end
        if self.has_feature(SerialFlash.FEAT_SUBSECTERASE):
            # Check whether one or more whole right subsectors can be erased
            ssr_start = (rstart+subsector_size-1) & subsector_mask
            ssr_end = rend & subsector_mask
            if ssr_start < ssr_end:
                self._erase_blocks(self.get_erase_command('subsector'),
                                   self.get_timings('subsector'),
                                   ssr_start, ssr_end, subsector_size)
        if verify:
            self._verify_content(address, length, 0xFF)

    def can_erase(self, address: int, length: int) -> None:
        """Tells whether a defined area can be erased on the Spansion flash
           device. It does not take into account any locking scheme."""
        if address == 0 and (length == -1 or length == len(self)):
            return
        erase_size = self.get_erase_size()
        if address & (erase_size-1):
            # start address should be aligned on a subsector boundary
            raise SerialFlashValueError('Start address not aligned on a '
                                        'erase sector boundary')
        if ((length-1) & (erase_size-1)) != (erase_size-1):
            # length should be a multiple of a subsector
            raise SerialFlashValueError('End address not aligned on a '
                                        'erase sector boundary')
        if (address + length) > len(self):
            raise SerialFlashValueError('Would erase over the flash capacity')

    def get_erase_size(self) -> int:
        """Return the erase size in bytes"""
        if self.has_feature(SerialFlash.FEAT_SUBSECTERASE):
            return self.get_size('subsector')
        if self.has_feature(SerialFlash.FEAT_HSECTERASE):
            return self.get_size('hsector')
        if self.has_feature(SerialFlash.FEAT_SECTERASE):
            return self.get_size('sector')
        raise SerialFlashNotSupported("Unknown erase size")

    def get_size(self, kind: str) -> int:
        """Return the size of a device block.

          :param kind: the block type
          :return: the size of the block, in bytes
        """
        raise NotImplementedError()

    @classmethod
    def get_erase_command(cls, block: str)-> bytes:
        """Get the erase command for a specified block kind"""
        raise NotImplementedError()

    def _read_lo_speed(self, address: int, length: int) -> bytes:
        read_cmd = bytes((self.CMD_READ_LO_SPEED,
                          (address >> 16) & 0xff, (address >> 8) & 0xff,
                          address & 0xff))
        return self._spi.exchange(read_cmd, length)

    def _read_hi_speed(self, address: int, length: int) -> bytes:
        read_cmd = bytes((self.CMD_READ_HI_SPEED,
                          (address >> 16) & 0xff, (address >> 8) & 0xff,
                          address & 0xff, 0))
        return self._spi.exchange(read_cmd, length)

    def _verify_content(self, address: int, length: int, refbyte: int) -> None:
        data = self.read(address, length)
        count = data.count(refbyte)
        if count != length:
            raise SerialFlashError('%d bytes are not erased' % (length-count))

    def _wait_for_completion(self, times: Tuple[float, float]) -> None:
        typical_time, max_time = times
        timeout = time.time()
        timeout += typical_time+max_time
        cycle = 0
        while self.is_busy():
            # need to wait at least once
            if cycle and time.time() > timeout:
                raise SerialFlashTimeout('Command timeout (%d cycles)' % cycle)
            time.sleep(typical_time)
            cycle += 1

    def _erase_blocks(self, command: int, times: Tuple[float, float],
                      start: int, end: int, size: int) -> None:
        """Erase one or more blocks."""
        raise NotImplementedError()

    def _erase_chip(self, command: int, times: Tuple[float, float]) -> None:
        """Erase an entire chip."""
        raise NotImplementedError()


class _Gen25FlashDevice(_SpiFlashDevice):
    """Generic flash device implementation for '25' series.

       Most SPI flash devices share commands and parameters. Those devices
       generally contains '25' in their reference. However, there are virtually
       no '25' device that is fully compliant with any counterpart from
       a concurrent manufacturer. Most differences are focused on lock and
       security features. Here comes the mess... This class contains the most
       common implementation for the basic feature, and each physical device
       inherit from this class for feature specialization.
    """

    PAGE_DIV = 8
    SUBSECTOR_DIV = 12
    HSECTOR_DIV = 15
    SECTOR_DIV = 16

    # these values should be overriden in concrete implementation
    JEDEC_ID = 0xFF
    DEVICES = {}
    SIZES = {}
    SPI_FREQ_MAX = 10  # MHz

    SR_WIP = 0b00000001  # Busy/Work-in-progress bit
    SR_WEL = 0b00000010  # Write enable bit
    SR_BP0 = 0b00000100  # bit protect #0
    SR_BP1 = 0b00001000  # bit protect #1
    SR_BP2 = 0b00010000  # bit protect #2
    SR_BP3 = 0b00100000  # bit protect #3
    SR_TBP = SR_BP3      # top-bottom protect bit
    SR_SP = 0b01000000
    SR_BPL = 0b10000000
    SR_PROTECT_NONE = 0  # BP[0..2] = 0
    SR_PROTECT_ALL = 0b00011100  # BP[0..2] = 1
    SR_LOCK_PROTECT = SR_BPL
    SR_UNLOCK_PROTECT = 0
    SR_BPL_SHIFT = 2

    CMD_READ_STATUS = 0x05  # Read status register
    CMD_WRITE_ENABLE = 0x06  # Write enable
    CMD_WRITE_DISABLE = 0x04  # Write disable
    CMD_PROGRAM_PAGE = 0x02  # Write page
    CMD_EWSR = 0x50  # Enable write status register
    CMD_WRSR = 0x01  # Write status register
    CMD_ERASE_SUBSECTOR = 0x20
    CMD_ERASE_HSECTOR = 0x52
    CMD_ERASE_SECTOR = 0xD8
    CMD_ERASE_CHIP = 0xC7

    def __init__(self, spi: SpiPort):
        super(_Gen25FlashDevice, self).__init__(spi)
        self._size = 0

    def __len__(self):
        return self._size

    def set_spi_frequency(self, freq: Optional[float] = None) -> None:
        default_freq = self.SPI_FREQ_MAX*1E06
        freq = min(default_freq, freq) if freq else default_freq
        self._spi.set_frequency(freq)

    def get_size(self, kind):
        try:
            div = getattr(self, '%s_DIV' % kind.upper())
            return 1 << div
        except AttributeError:
            raise SerialFlashNotSupported('%s size is not supported' %
                                          kind.title())

    @classmethod
    def get_erase_command(cls, block: str) -> str:
        """Get the erase command for a specified block kind"""
        return getattr(cls, 'CMD_ERASE_%s' % block.upper())

    @classmethod
    def has_feature(cls, feature: int) -> bool:
        """Flash device feature"""
        try:
            # all '25' devices use the same class properties
            features = cls.FEATURES
        except AttributeError:
            raise NotImplementedError('No FEATURES defined')
        return bool(features & feature)

    def get_timings(self, timing: str) -> Tuple[float, float]:
        """Get a time tuple (typical, max)"""
        try:
            # all '25' devices use the same class properties
            timings = self.TIMINGS
        except AttributeError:
            raise NotImplementedError('no TIMINGS defined')
        return timings[timing]

    @classmethod
    def match(cls, jedec: Union[bytes, bytearray, Iterable[int]]) -> bool:
        """Tells whether this class support this JEDEC identifier"""
        manufacturer, device, capacity = jedec[:3]
        if manufacturer != cls.JEDEC_ID:
            return False
        if device not in cls.DEVICES:
            return False
        if capacity not in cls.SIZES:
            return False
        return True

    def unlock(self) -> None:
        self._enable_write()
        wrsr_cmd = bytes((_Gen25FlashDevice.CMD_WRSR,
                          _Gen25FlashDevice.SR_WEL |
                          _Gen25FlashDevice.SR_PROTECT_NONE |
                          _Gen25FlashDevice.SR_UNLOCK_PROTECT))
        self._spi.exchange(wrsr_cmd)
        duration = self.get_timings('lock')
        if any(duration):
            self._wait_for_completion(duration)
        status = self._read_status()
        if status & _Gen25FlashDevice.SR_PROTECT_ALL:
            raise SerialFlashRequestError("Cannot unprotect flash device")

    def is_busy(self) -> bool:
        return self._is_busy(self._read_status())

    def write(self, address: int,
              data: Union[bytes, bytearray, Iterable[int]]) -> None:
        """Write a sequence of bytes, starting at the specified address."""
        length = len(data)
        if address+length > len(self):
            raise SerialFlashValueError('Cannot fit in flash area')
        if not isinstance(data, (bytes, bytearray)):
            data = bytes(data)
        pos = 0
        page_size = self.get_size('page')
        while pos < length:
            size = min(length-pos, page_size)
            self._write(address, data[pos:pos+size])
            address += size
            pos += size

    def _read_status(self) -> int:
        read_cmd = bytes((self.CMD_READ_STATUS,))
        data = self._spi.exchange(read_cmd, 1)
        if len(data) != 1:
            raise SerialFlashTimeout("Unable to retrieve flash status")
        return data[0]

    def _enable_write(self) -> None:
        wren_cmd = bytes((self.CMD_WRITE_ENABLE,))
        self._spi.exchange(wren_cmd)

    def _disable_write(self) -> None:
        wrdi_cmd = bytes((self.CMD_WRITE_DISABLE,))
        self._spi.exchange(wrdi_cmd)

    def _write(self, address: int, data: bytes) -> None:
        # take care not to roll over the end of the flash page
        page_mask = self.get_size('page')-1
        if address & page_mask:
            up = (address+page_mask) & ~page_mask
            count = min(len(data), up-address)
            sequences = [(address, data[:count]), (up, data[count:])]
        else:
            sequences = [(address, data)]
        for addr, chunk in sequences:
            self._enable_write()
            wcmd = bytearray((self.CMD_PROGRAM_PAGE,
                              (addr >> 16) & 0xff, (addr >> 8) & 0xff,
                              addr & 0xff))
            wcmd.extend(chunk)
            self._spi.exchange(wcmd)
            self._wait_for_completion(self.get_timings('page'))

    def _erase_blocks(self, command: int, times: Tuple[float, float],
                      start: int, end: int, size: int) -> None:
        """Erase one or more blocks."""
        while start < end:
            self._enable_write()
            cmd = bytes((command, (start >> 16) & 0xff,
                         (start >> 8) & 0xff, start & 0xff))
            self._spi.exchange(cmd)
            self._wait_for_completion(times)
            start += size

    @classmethod
    def _is_busy(cls, status: int) -> bool:
        return bool(status & cls.SR_WIP)

    @classmethod
    def _is_wren(cls, status: int) -> bool:
        return bool(status & cls.SR_WEL)


class Sst25FlashDevice(_Gen25FlashDevice):
    """SST25 flash device implementation"""

    JEDEC_ID = 0xBF
    DEVICES = {0x25: 'SST25'}
    CMD_PROGRAM_BYTE = 0x02
    CMD_PROGRAM_WORD = 0xAD  # Auto address increment (for write command)
    CMD_WRITE_STATUS_REGISTER = 0x01
    SST25_AAI = 0b01000000  # AAI mode activation flag
    SIZES = {0x41: 2 << 20, 0x4A: 4 << 20}
    SPI_FREQ_MAX = 66  # MHz
    TIMINGS = {'subsector': (0.025, 0.025),  # 25 ms
               'hsector': (0.025, 0.025),  # 25 ms
               'sector': (0.025, 0.025),  # 25 ms
               'lock': (0.0, 0.0)}  # immediate
    FEATURES = (SerialFlash.FEAT_SECTERASE |
                SerialFlash.FEAT_SUBSECTERASE |
                SerialFlash.FEAT_HSECTERASE)

    def __init__(self, spi, jedec):
        super(Sst25FlashDevice, self).__init__(spi)
        if not Sst25FlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        device, capacity = jedec[1:3]
        self._device = self.DEVICES[device]
        self._size = Sst25FlashDevice.SIZES[capacity]

    def __str__(self):
        return 'SST %s %s' % \
            (self._device, pretty_size(self._size, lim_m=1 << 20))

    def write(self, address: int, data: Iterable[int]) -> None:
        """SST25 uses a very specific implementation to write data. It offers
           very poor performances, because the device lacks an internal buffer
           which translates into an ultra-heavy load on SPI bus. However, the
           device offers lightning-speed flash erasure.
           Although the device supports byte-aligned write requests, the
           current implementation only support half-word write requests."""
        if address+len(data) > len(self):
            raise SerialFlashValueError('Cannot fit in flash area')
        if not isinstance(data, (bytes, bytearray)):
            data = bytes(data)
        length = len(data)
        if (address & 0x1) or (length & 0x1) or (length == 0):
            raise SerialFlashNotSupported("Alignement/size not supported")
        self._unprotect()
        self._enable_write()
        aai_cmd = bytes((Sst25FlashDevice.CMD_PROGRAM_WORD,
                         (address >> 16) & 0xff,
                         (address >> 8) & 0xff,
                         address & 0xff,
                         data.pop(0), data.pop(0)))
        offset = 0
        while True:
            offset += 2
            self._spi.exchange(aai_cmd)
            while self.is_busy():
                time.sleep(0.01)  # 10 ms
            if not data:
                break
            aai_cmd = bytes((Sst25FlashDevice.CMD_PROGRAM_WORD,
                             data.pop(0), data.pop(0)))
        self._disable_write()

    def _unprotect(self):
        """Disable default protection for all sectors"""
        unprotect = bytes((Sst25FlashDevice.CMD_WRITE_STATUS_REGISTER, 0x00))
        self._enable_write()
        self._spi.exchange(unprotect)
        while self.is_busy():
            time.sleep(0.01)  # 10 ms


class S25FlFlashDevice(_Gen25FlashDevice):
    """Spansion S25FL flash device implementation"""

    JEDEC_ID = 0x01
    DEVICES = {0x02: 'S25FL'}
    SIZES = {0x15: 4 << 20, 0x16: 8 << 20}
    CR_FREEZE = 0x01
    CR_QUAD = 0x02
    CR_TBPARM = 0x04
    CR_BPNV = 0x08
    CR_LOCK = 0x10
    CR_TBPROT = 0x20
    CMD_READ_CONFIG = 0x35
    SPI_FREQ_MAX = 104  # MHz (P series only)
    TIMINGS = {'page': (0.0015, 0.003),  # 1.5/3 ms
               'subsector': (0.2, 0.8),  # 200/800 ms
               'sector': (0.5, 2.0),  # 0.5/2 s
               'bulk': (32, 64),  # seconds
               'lock': (0.0015, 0.1)}  # 1.5/100 ms
    FEATURES = (SerialFlash.FEAT_SECTERASE |
                SerialFlash.FEAT_SUBSECTERASE)

    def __init__(self, spi, jedec):
        super(S25FlFlashDevice, self).__init__(spi)
        if not S25FlFlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        device, capacity = jedec[1:3]
        self._device = self.DEVICES[device]
        self._size = S25FlFlashDevice.SIZES[capacity]

    def __str__(self):
        return 'Spansion %s %s' % \
            (self._device, pretty_size(self._size, lim_m=1 << 20))

    def can_erase(self, address: int, length: int):
        # we first need to check the current configuration register, as a
        # previous configuration may prevent from altering some of the bits
        readcfg_cmd = bytes((S25FlFlashDevice.CMD_READ_CONFIG,))
        config = self._spi.exchange(readcfg_cmd, 1)[0]
        if config & S25FlFlashDevice.CR_TBPARM:
            # "parameter zone" is defined in the high sectors
            border = len(self)-2*self.get_size('sector')
            ls_size = self.get_size('sector')
            rs_size = self.get_size('subsector')
        else:
            # "parameter zone" is defined in the low sectors
            border = 2*self.get_size('sector')
            ls_size = self.get_size('subsector')
            rs_size = self.get_size('sector')
        start = address
        fend = address+length
        # sanity check
        if (start > fend) or (fend > len(self)):
            raise SerialFlashValueError('Out of flash storage range')
        if fend > border > start:
            end = border
        else:
            end = fend
        if start >= border:
            size = rs_size
        else:
            size = ls_size
        while True:  # expect 1 (no border cross) or 2 loops (border cross)
            # sanity check
            if start & (size-1):
                # start address should be aligned on a (sub)sector boundary
                raise SerialFlashValueError('Start address not aligned on a '
                                            'sector boundary')
            # sanity check
            if (((end-start)-1) & (size-1)) != (size-1):
                # length should be a multiple of a (sub)sector
                raise SerialFlashValueError('End address not aligned on a '
                                            'sector boundary')
            # stop condition
            if (start >= border) or (end >= fend):
                break
            start = end
            end = fend
            size = rs_size


class S25FSFlashDevice(_Gen25FlashDevice):
    """Spansion S25FL flash device implementation"""

    JEDEC_ID = 0x01
    DEVICES = {0x02: 'S25FS'}
    SIZES = {0x20: 64 << 20}
    CR_FREEZE = 0x01
    CR_QUAD = 0x02
    CR_TBPARM = 0x04
    CR_BPNV = 0x08
    CR_LOCK = 0x10
    CR_TBPROT = 0x20
    CMD_READ_CONFIG = 0x35
    SPI_FREQ_MAX = 104  # MHz (P series only)
    TIMINGS = {'page': (0.0015, 0.003),  # 1.5/3 ms
               'subsector': (0.2, 0.8),  # 200/800 ms
               'sector': (0.5, 2.0),  # 0.5/2 s
               'bulk': (32, 64),  # seconds
               'lock': (0.0015, 0.1),  # 1.5/100 ms
               'chip': (220, 720), # 220/720 s
    }
    FEATURES = (SerialFlash.FEAT_SECTERASE |
                SerialFlash.FEAT_SUBSECTERASE |
                SerialFlash.FEAT_CHIPERASE)

    # we only support 256K sectors for s25fs512
    SECTOR_DIV = 18
    # only works for first or last 4k param blocks
    SUBSECTOR_DIV = 12

    def __init__(self, spi, jedec):
        super(S25FSFlashDevice, self).__init__(spi)
        if not S25FSFlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        device, capacity = jedec[1:3]
        self._device = self.DEVICES[device]
        self._size = S25FSFlashDevice.SIZES[capacity]

    def __str__(self):
        return 'Spansion %s %s' % \
            (self._device, pretty_size(self._size, lim_m=1 << 20))

    def can_erase(self, address: int, length: int):
        if address == 0 and (length == -1 or length == len(self)):
            return
        # we only allow sector erase except for param zone
        erase_size = self.get_size('sector')
        readcfg_cmd = bytes((S25FSFlashDevice.CMD_READ_CONFIG,))
        config = self._spi.exchange(readcfg_cmd, 1)[0]

        if config & S25FSFlashDevice.CR_TBPARM:
            # "parameter zone" is defined in the high sectors
            border = len(self)-8*self.get_size('subsector')
            if address >= border:
                erase_size = self.get_size('subsector')
        else:
            # "parameter zone" is defined in the low sectors
            border = 8*self.get_size('subsector')
            if address + length <= border:
                erase_size = self.get_size('subsector')

        if address & (erase_size-1):
            # start address should be aligned on a subsector boundary
            raise SerialFlashValueError('Start address not aligned on a '
                                        'erase sector boundary')
        if ((length-1) & (erase_size-1)) != (erase_size-1):
            # length should be a multiple of a subsector
            raise SerialFlashValueError('End address not aligned on a '
                                        'erase sector boundary')
        if (address + length) > len(self):
            raise SerialFlashValueError('Would erase over the flash capacity')

    def erase(self, address: int, length: int, verify: bool = False) -> None:
        # we first need to check the current configuration register, as a
        # previous configuration may prevent from altering some of the bits
        readcfg_cmd = bytes((S25FSFlashDevice.CMD_READ_CONFIG,))
        config = self._spi.exchange(readcfg_cmd, 1)[0]
        if config & S25FSFlashDevice.CR_TBPARM:
            # "parameter zone" is defined in the high sectors
            # the last sector
            parameter_address_match = len(self)-length
            parameter_address = len(self)-8*self.get_size('subsector')
        else:
            # "parameter zone" is defined in the low sectors
            parameter_address_match = 0
            parameter_address = 0

        if length >= self.get_size('sector') and \
            address == parameter_address_match:
            # we want to erase the sector containing the param sector, 
            # so we need to erase the param zone additionally using 
            # subsector erase otherwise these will not be erased
            s_start = parameter_address
            s_end = 8 * self.get_size('subsector')
            self._erase_blocks(self.get_erase_command('subsector'),
                                self.get_timings('subsector'),
                                s_start, s_end, self.get_size('subsector'))
        
        super(S25FSFlashDevice, self).erase(address, length, verify)

    def _erase_chip(self, command: int, times: Tuple[float, float]):
        """Erase an entire chip"""
        self._enable_write()
        cmd = bytes((command,))
        self._spi.exchange(cmd)
        self._wait_for_completion(times)


class M25PxFlashDevice(_Gen25FlashDevice):
    """Numonix M25P/M25PX flash device implementation"""

    JEDEC_ID = 0x20
    DEVICES = {0x71: 'M25P', 0x20: 'M25PX'}
    SIZES = {0x15: 2 << 20, 0x16: 4 << 20, 0x17: 8 << 20, 0x18: 16 << 20}
    SPI_FREQ_MAX = 75  # MHz (P series only)
    TIMINGS = {'page': (0.0015, 0.003),  # 1.5/3 ms
               'subsector': (0.150, 0.150),  # 150/150 ms
               'sector': (3.0, 3.0),  # 3/3 s
               'bulk': (32, 64),  # seconds
               'lock': (0.0015, 0.003)}  # 1.5/3 ms
    FEATURES = SerialFlash.FEAT_SECTERASE | SerialFlash.FEAT_SUBSECTERASE

    def __init__(self, spi, jedec):
        super(M25PxFlashDevice, self).__init__(spi)
        if not M25PxFlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        device, capacity = jedec[1:3]
        self._device = self.DEVICES[device]
        self._size = M25PxFlashDevice.SIZES[capacity]

    def __str__(self):
        return 'Numonix %s%d %s' % \
            (self._device, len(self) >> 17,
             pretty_size(self._size, lim_m=1 << 20))


class W25xFlashDevice(_Gen25FlashDevice):
    """Winbond W25Q/W25X flash device implementation"""

    JEDEC_ID = 0xEF
    DEVICES = {0x30: 'W25X', 0x40: 'W25Q'}
    SIZES = {0x11: 1 << 17, 0x12: 1 << 18, 0x13: 1 << 19, 0x14: 1 << 20,
             0x15: 2 << 20, 0x16: 4 << 20, 0x17: 8 << 20, 0x18: 16 << 20}
    SPI_FREQ_MAX = 104  # MHz
    CMD_READ_UID = 0x4B
    UID_LEN = 0x8  # 64 bits
    READ_UID_WIDTH = 4  # 4 dummy bytes
    TIMINGS = {'page': (0.0015, 0.003),  # 1.5/3 ms
               'subsector': (0.200, 0.200),  # 200/200 ms
               'sector': (1.0, 1.0),  # 1/1 s
               'bulk': (32, 64),  # seconds
               'lock': (0.05, 0.1),  # 50/100 ms
               'chip': (4, 11)}
    FEATURES = (SerialFlash.FEAT_SECTERASE |
                SerialFlash.FEAT_SUBSECTERASE |
                SerialFlash.FEAT_CHIPERASE)

    def __init__(self, spi, jedec):
        super(W25xFlashDevice, self).__init__(spi)
        if not W25xFlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        device, capacity = jedec[1:3]
        self._device = self.DEVICES[device]
        self._size = W25xFlashDevice.SIZES[capacity]

    def __str__(self):
        return 'Winbond %s%d %s' % \
            (self._device, len(self) >> 17,
             pretty_size(self._size, lim_m=1 << 20))

    def _erase_chip(self, command: int, times: Tuple[float, float]):
        """Erase an entire chip"""
        self._enable_write()
        cmd = bytes((command,))
        self._spi.exchange(cmd)
        self._wait_for_completion(times)


class Mx25lFlashDevice(_Gen25FlashDevice):
    """Macronix MX25L flash device implementation"""

    JEDEC_ID = 0xC2
    DEVICES = {0x9E: 'MX25D', 0x26: 'MX25E', 0x20: 'MX25E06'}
    SIZES = {0x15: 2 << 20, 0x16: 4 << 20, 0x17: 8 << 20, 0x18: 16 << 20}
    SPI_FREQ_MAX = 104  # MHz
    TIMINGS = {'page': (0.0015, 0.003),  # 1.5/3 ms
               'subsector': (0.300, 0.300),  # 300/300 ms
               'hsector': (2.0, 2.0),  # 2/2 s
               'sector': (2.0, 2.0),  # 2/2 s
               'bulk': (32, 64),  # seconds
               'lock': (0.0015, 0.003)}  # 1.5/3 ms
    FEATURES = (SerialFlash.FEAT_SECTERASE |
                SerialFlash.FEAT_HSECTERASE |
                SerialFlash.FEAT_SUBSECTERASE)
    CMD_UNLOCK = 0xF3
    CMD_GBULK = 0x98
    CMD_RDBLOCK = 0xFB
    CMD_RDSBLOCK = 0x3C
    CMD_RDPLOCK = 0x3F
    CMD_BLOCKP = 0xE2
    CMD_SBLK = 0x36
    CMD_PLOCK = 0x64

    def __init__(self, spi, jedec):
        super(Mx25lFlashDevice, self).__init__(spi)
        if not Mx25lFlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        device, capacity = jedec[1:3]
        self._size = self.SIZES[capacity]
        self._device = self.DEVICES[device]

    def __str__(self):
        return 'Macronix %s%d %s' % \
            (self._device, len(self) >> 17,
             pretty_size(self._size, lim_m=1 << 20))

    def unlock(self):
        if self._device.endswith('D'):
            unlock = self.CMD_UNLOCK
        else:
            unlock = self.CMD_GBULK
        self._enable_write()
        wcmd = bytes((unlock,))
        self._spi.exchange(wcmd)
        self._wait_for_completion(self.get_timings('page'))


class En25qFlashDevice(_Gen25FlashDevice):
    """EON EN25Q flash device implementation"""

    JEDEC_ID = 0x1C
    DEVICES = {0x30: 'EN25Q'}
    SIZES = {0x15: 2 << 20, 0x16: 4 << 20, 0x17: 8 << 20}
    SPI_FREQ_MAX = 100  # MHz
    TIMINGS = {'page': (0.0015, 0.003),  # 1.5/3 ms
               'subsector': (0.300, 0.300),  # 300/300 ms
               'sector': (2.0, 2.0),  # 2/2 s
               'bulk': (32, 64),  # seconds
               'lock': (0.0015, 0.003)}  # 1.5/3 ms
    FEATURES = SerialFlash.FEAT_SECTERASE | SerialFlash.FEAT_SUBSECTERASE

    def __init__(self, spi, jedec):
        super(En25qFlashDevice, self).__init__(spi)
        if not En25qFlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        device, capacity = jedec[1:]
        self._size = En25qFlashDevice.SIZES[capacity]
        self._device = self.DEVICES[device]

    def __str__(self):
        return 'Eon %s%d %s' % \
            (self._device, len(self) >> 17,
             pretty_size(self._size, lim_m=1 << 20))


class At25FlashDevice(_Gen25FlashDevice):
    """Atmel AT25 flash device implementation"""

    JEDEC_ID = 0x1F
    SIZES = {0x46: 2 << 20, 0x47: 4 << 20, 0x48: 8 << 20, 0x84: 7 << 16}
    SPI_FREQ_MAX = 85  # MHz
    CHIP_DIV = 7 << 16
    TIMINGS = {'page': (0.0015, 0.003),  # 1.5/3 ms
               'subsector': (0.200, 0.200),  # 200/200 ms
               'sector': (0.950, 0.950),  # 950/950 ms
               'bulk': (32, 64),  # seconds
               'lock': (0.0015, 0.003),
               'chip': (4, 11)}  # 1.5/3 ms
    FEATURES = (SerialFlash.FEAT_SECTERASE |
                SerialFlash.FEAT_SUBSECTERASE |
                SerialFlash.FEAT_CHIPERASE)

    CMD_PROTECT_SOFT_WRITE = 0x36
    CMD_PROTECT_LOCK_WRITE = 0x33
    CMD_UNPROTECT_SOFT_WRITE = 0x39
    CMD_PROTECT_LOCK_READ = 0x35
    CMD_PROTECT_SOFT_READ = 0x3C
    CMD_ENABLE_LOCK_PROTECT = 0x08
    CMD_ENABLE_SOFT_PROTECT = 0x80
    ASSERT_LOCK_PROTECT = 0xD0

    def __init__(self, spi, jedec):
        super(At25FlashDevice, self).__init__(spi)
        if not At25FlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        capacity = jedec[1]
        self._size = At25FlashDevice.SIZES[capacity]
        self._device = 'AT25DF'

    def __str__(self):
        return 'Atmel %s%d %s' % \
            (self._device, len(self) >> 17,
             pretty_size(self._size, lim_m=1 << 20))

    def _erase_chip(self, command: int, times: Tuple[float, float]):
        """Erase an entire chip"""
        self._enable_write()
        cmd = bytes((command,))
        self._spi.exchange(cmd)
        self._wait_for_completion(times)

    @classmethod
    def match(cls, jedec):
        """Tells whether this class support this JEDEC identifier"""
        manufacturer, capacity, revision = jedec[:3]
        if manufacturer != cls.JEDEC_ID:
            return False
        if revision > 1:
            return False
        if capacity not in cls.SIZES:
            return False
        return True

    def unlock(self):
        self._lock(self.CMD_UNPROTECT_SOFT_WRITE, 0, self._size)

    def _erase_chip(self, command, times):
        self._enable_write()
        cmd = bytes((command,))
        self._spi.exchange(cmd)
        self._wait_for_completion(times)
        time.sleep(times[1])

    def _lock(self, command, address, length):
        # caller should have check address & length alignment
        sector_size = self.get_size('sector')
        sector_mask = ~(self.get_size('sector')-1)
        start = address & sector_mask
        end = (address+length) & sector_mask
        for addr in range(start, end, sector_size):
            self._enable_write()
            wcmd = bytearray((command,
                              (addr >> 16) & 0xff, (addr >> 8) & 0xff,
                              addr & 0xff))
            if self.CMD_PROTECT_LOCK_WRITE == command:
                wcmd.append(self.ASSERT_LOCK_PROTECT)
            self._spi.exchange(wcmd)
            self._wait_for_completion(self.get_timings('page'))


class AT25XE041BFlashDevice(_Gen25FlashDevice):
    """Atmel AT25 flash device implementation"""

    JEDEC_ID = 0x1F
    SIZES = {0x44: 4 << 17}
    SPI_FREQ_MAX = 85  # MHz
    TIMINGS = {'page': (0.0015, 0.003),  # 1.5/3 ms
               'subsector': (0.045, 0.060),  # 200/200 ms
               'hsector': (0.360, 0.450),  # 360/450 ms
               'sector': (0.720, 0.850),  # 950/950 ms
               'bulk': (32, 64),  # seconds
               'lock': (0.0015, 0.003),
               'chip': (4, 11)}  # 1.5/3 ms


    FEATURES = (SerialFlash.FEAT_SECTERASE |
                SerialFlash.FEAT_SUBSECTERASE |
                SerialFlash.FEAT_CHIPERASE |
                SerialFlash.FEAT_HSECTERASE)

    CMD_PROTECT_SOFT_WRITE = 0x36
    CMD_PROTECT_LOCK_WRITE = 0x33
    CMD_UNPROTECT_SOFT_WRITE = 0x39
    CMD_PROTECT_LOCK_READ = 0x35
    CMD_PROTECT_SOFT_READ = 0x3C
    CMD_ENABLE_LOCK_PROTECT = 0x08
    CMD_ENABLE_SOFT_PROTECT = 0x80
    ASSERT_LOCK_PROTECT = 0xD0

    PAGE_DIV = 8
    SUBSECTOR_DIV = 12
    HSECTOR_DIV = 15
    SECTOR_DIV = 16

    def __init__(self, spi, jedec):
        super(AT25XE041BFlashDevice, self).__init__(spi)
        if not AT25XE041BFlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        capacity = jedec[1]
        self._device = 'AT25XE041B'
        self._size = AT25XE041BFlashDevice.SIZES[capacity]
        print(self._size)

    def __str__(self):
        return 'Adesto %s %s' % \
            (self._device, pretty_size(self._size, lim_m=1 << 20))

    @classmethod
    def match(cls, jedec):
        """Tells whether this class support this JEDEC identifier"""
        manufacturer, capacity, revision = jedec[:3]
        if manufacturer != cls.JEDEC_ID:
            return False
        if revision < 1 :
            return False
        if capacity not in cls.SIZES:
            return False
        return True

    def unlock(self):
        self._lock(self.CMD_UNPROTECT_SOFT_WRITE, 0, self._size)

    def _erase_chip(self, command, times):
        self._enable_write()
        cmd = bytes((command,))
        self._spi.exchange(cmd)
        self._wait_for_completion(times)
        time.sleep(times[1])

    def _lock(self, command, address, length):
        # caller should have check address & length alignment
        sector_size = self.get_size('sector')
        sector_mask = ~(self.get_size('sector')-1)
        start = address & sector_mask
        end = (address+length) & sector_mask
        for addr in range(start, end, sector_size):
            self._enable_write()
            wcmd = bytearray((command,
                              (addr >> 16) & 0xff,
                              (addr >> 8) & 0xff,
                              addr & 0xff))
            if self.CMD_PROTECT_LOCK_WRITE == command:
                wcmd.append(self.ASSERT_LOCK_PROTECT)
            self._spi.exchange(wcmd)
            self._wait_for_completion(self.get_timings('page'))

class At45FlashDevice(_SpiFlashDevice):
    """Flash device implementation for AT45 (Atmel/Adesto)

       Except READ commands, the old AT45 series use a fully different
       command set than '25' series.
    """

    # for device ranging from 1Mb to 64Mb
    PAGE_DIV = [8, 8, 8, 8, 9, 9, 8]
    SUBSECTOR_DIV = [11, 11, 11, 11, 12, 12, 11]
    SECTOR_DIV = [15, 15, 16, 16, 17, 16, 18]
    CHIP_DIV = [17, 18, 19, 20, 21, 22, 23]
    JEDEC_ID = 0x1F
    SPI_FREQS_MAX = [66, 85, 85, 133, 85, 85, 85]
    TIMINGS = {'page': [(0.002, 0.004),
                        (0.0015, 0.003),
                        (0.0015, 0.003),
                        (0.002, 0.004),
                        (0.003, 0.004),
                        (0.003, 0.004),
                        (0.0015, 0.005)],
               # do not support page erasure
               'subsector': [(0.018, 0.035),
                             (0.025, 0.035),
                             (0.030, 0.035),
                             (0.030, 0.075),
                             (0.045, 0.100),
                             (0.045, 0.100),
                             (0.025, 0.050)],
               'sector': [(0.400, 0.700),
                          (0.350, 0.550),
                          (0.700, 1.100),
                          (0.700, 1.300),
                          (1.400, 2.000),
                          (0.700, 1.400),
                          (2.500, 6.500)],
               'bulk': [(1.2, 3.0),
                        (3.0, 4.0),
                        (5.0, 17.0),
                        (10.0, 20.0),
                        (22.0, 40.0),
                        (45.0, 80.0),
                        (80.0, 208.0)],
               'lock': [(1.0, 2.0),
                        (1.0, 2.0),
                        (1.0, 2.0),
                        (1.0, 2.0),
                        (1.0, 2.0),
                        (1.0, 2.0),
                        (1.0, 2.0)]}
    FEATURES = SerialFlash.FEAT_SECTERASE | SerialFlash.FEAT_SUBSECTERASE

    DEVICE_ID = 0x01
    DEVICE_MASK = 0x07
    DEVICE_SHIFT = 5
    CAPACITY_MASK = 0x1f
    CAPACITY_SHIFT = 0
    SR_READY = 0x80
    SR_COMP = 0x40
    SR_SIZE_MASK = 0x2C
    SR_PROTECT = 0x02
    SR_PAGE_SIZE_FLAG = 0x01
    SR_VERSION_BITS = 0x38  # for a AT45DB321B chip
    SR_VERSION_VALUE = 0x30  # for a AT45DB321B chip
    SECTOR_UNPROTECTED = 0x00
    SECTOR_PROTECTED = 0xFF
    SECTOR_PROTECTED1 = 0xF0
    SECTOR_PROTECT_PREFIX_A = 0x2A
    SECTOR_PROTECT_PREFIX_B = 0x7F
    SECTOR_LOCKDOWN_SUFFIX = 0x30
    SECTOR_PROTECT_READ = 0x32
    SECTOR_PROTECT_ENABLE = 0xA9
    SECTOR_PROTECT_DISABLE = 0x9A
    SECTOR_PROTECT_PROGRAM = 0xFC
    SECTOR_PROTECT_ERASE = 0xCF

    CMD_READ_STATUS = 0xD7  # Read status register
    CMD_ERASE_PAGE = 0x81
    CMD_ERASE_SUBSECTOR = 0x50
    CMD_ERASE_SECTOR = 0x7C
    CMD_WRITE_BUFFER1 = 0x84
    CMD_WRITE_BUFFER2 = 0x87
    CMD_ERASE_COMMIT_BUFFER1 = 0x83
    CMD_ERASE_COMMIT_BUFFER2 = 0x86
    CMD_COMMIT_BUFFER1 = 0x88
    CMD_COMMIT_BUFFER2 = 0x89
    CMD_MAIN_THROUGH_BUFFER1 = 0x82
    CMD_MAIN_THROUGH_BUFFER2 = 0x85
    CMD_PROTECT_WRITE = 0x3D
    CMD_PROTECT_LOCK_READ = 0x35
    CMD_PROTECT_SOFT_READ = 0x32

    def __init__(self, spi, jedec):
        super(At45FlashDevice, self).__init__(spi)
        if not At45FlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        code = jedec[1]
        capacity = (code >> self.CAPACITY_SHIFT) & self.CAPACITY_MASK
        self._devidx = capacity-2
        assert 0 <= self._devidx < len(self.PAGE_DIV)
        self._size = self.get_size('chip')
        self._device = 'AT45DB'
        self._spi.set_frequency(self.SPI_FREQS_MAX[self._devidx]*1E06)
        self._fix_page_size()

    def set_spi_frequency(self, freq=None):
        default_freq = self.SPI_FREQS_MAX[self._devidx]*1E06
        freq = min(default_freq, freq) if freq else default_freq
        self._spi.set_frequency(freq)

    def __len__(self):
        return self._size

    def __str__(self):
        return 'Atmel %s %s' % \
            (self._device, pretty_size(self._size, lim_m=1 << 20))

    def get_size(self, kind):
        try:
            divs = getattr(self, '%s_DIV' % kind.upper())
            return 1 << divs[self._devidx]
        except AttributeError:
            raise SerialFlashNotSupported('%s erase is not supported' %
                                          kind.title())

    @classmethod
    def get_erase_command(cls, block):
        """Get the erase command for a specified block kind"""
        return getattr(cls, 'CMD_ERASE_%s' % block.upper())

    @classmethod
    def has_feature(cls, feature):
        """Flash device feature"""
        return bool(cls.FEATURES & feature)

    def get_timings(self, timing):
        """Get a time tuple (typical, max)"""
        return self.TIMINGS[timing][self._devidx]

    @classmethod
    def match(cls, jedec):
        """Tells whether this class support this JEDEC identifier"""
        manufacturer, deva = jedec[:2]
        if manufacturer != cls.JEDEC_ID:
            return False
        device = (deva >> cls.DEVICE_SHIFT) & cls.DEVICE_MASK
        if device != cls.DEVICE_ID:
            return False
        capacity = (deva >> cls.CAPACITY_SHIFT) & cls.CAPACITY_MASK
        if (capacity < 2) or ((capacity-2) >= len(cls.PAGE_DIV)):
            return False
        return True

    def unlock(self):
        wcmd = bytes((self.CMD_PROTECT_WRITE,
                      self.SECTOR_PROTECT_PREFIX_A,
                      self.SECTOR_PROTECT_PREFIX_B,
                      self.SECTOR_PROTECT_DISABLE))
        self._spi.exchange(wcmd)
        duration = self.get_timings('lock')
        if any(duration):
            self._wait_for_completion(duration)

    def is_busy(self):
        return self._is_busy(self._read_status())

    def _erase_blocks(self, command, times, start, end, size):
        """Erase one or more blocks"""
        while start < end:
            wcmd = bytes((command, (start >> 16) & 0xff,
                          (start >> 8) & 0xff, start & 0xff))
            self._spi.exchange(wcmd)
            self._wait_for_completion(times)
            # very special case for first sector which is split in two
            # parts: 4KiB + 60KiB
            if (start == 0) and (command == self.CMD_ERASE_SECTOR):
                start += self.get_size('subsector')
                continue
            start += size

    def _read_status(self):
        read_cmd = bytes((self.CMD_READ_STATUS,))
        data = self._spi.exchange(read_cmd, 1)
        if len(data) != 1:
            raise SerialFlashTimeout("Unable to retrieve flash status")
        return data[0]

    @classmethod
    def _is_busy(cls, status):
        return not bool(status & cls.SR_READY)

    def write(self, address: int,
              data: Union[bytes, bytearray, Iterable[int]]) -> None:
        """Write a sequence of bytes, starting at the specified address."""
        length = len(data)
        if address+length > len(self):
            raise SerialFlashValueError('Cannot fit in flash area')
        if not isinstance(data, (bytes, bytearray)):
            data = bytes(data)
        pos = 0
        page_size = self.get_size('page')
        while pos < length:
            boffset = (address+pos) & (page_size-1)
            poffset = (address+pos) & ~(page_size-1)
            # first step: write data to the device RAM buffer
            count = min(length-pos, page_size-boffset)
            buf = bytearray([0xFF]*boffset)
            buf.extend(data[pos:pos+count])
            pad = bytes([0xFF]*(page_size-count-boffset))
            buf.extend(pad)
            assert len(buf) == page_size
            wcmd = bytearray((self.CMD_WRITE_BUFFER1, 0, 0, 0))
            wcmd.extend(buf)
            self._spi.exchange(wcmd)
            self._wait_for_completion(self.get_timings('page'))
            # second step: commit device buffer into flash cells
            wcmd = bytes((self.CMD_COMMIT_BUFFER1,
                          (poffset >> 16) & 0xff, (poffset >> 8) & 0xff,
                          poffset & 0xff))
            self._spi.exchange(wcmd)
            self._wait_for_completion(self.get_timings('page'))
            pos += page_size

    def _fix_page_size(self):
        """Fix AT45 page size to 512 bytes, rather than the default 528 bytes
           per page. This implementation is not able to cope with non 2^N bytes
           per page, which is an AT45 oddity in serial flash world
        """
        status = self._read_status()
        if status & self.SR_PAGE_SIZE_FLAG:
            # nothing to do, alreay using 2^N page size mode
            return
        wcmd = bytes((0x3d, 0x2a, 0x80, 0xa6))
        self._spi.exchange(wcmd)
        raise IOError("Please power-cycle the device to enable "
                      "binary page size mode")


class N25QFlashDevice(_Gen25FlashDevice):
    """Micron N25Q flash device implementation"""

    JEDEC_ID = 0x20
    DEVICES = {0xBA: 'N25Q'}
    SIZES = {0x15: 2 << 20, 0x16: 4 << 20, 0x17: 8 << 20, 0x18: 16 << 20}
    SPI_FREQ_MAX = 105  # MHz, using 3 dummy bytes
    TIMINGS = {'page': (0.0005, 0.005),  # 0.5/5 ms
               'subsector': (0.3, 3.0),  # 300/3000 ms
               'sector': (0.7, 3.0),  # 700/3000 ms
               'bulk': (60, 120)}  # seconds
    FEATURES = SerialFlash.FEAT_SECTERASE | SerialFlash.FEAT_SUBSECTERASE
    CMD_WRLR = 0xE5
    SECTOR_LOCK_DOWN = 1
    SECTOR_WRITE_LOCK = 0

    def __init__(self, spi, jedec):
        super(N25QFlashDevice, self).__init__(spi)
        if not N25QFlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        device, capacity = jedec[1:]
        self._size = self.SIZES[capacity]
        self._device = self.DEVICES[device]

    def __str__(self):
        return 'Micron %s%03d %s' % \
            (self._device, len(self) >> 17,
             pretty_size(self._size, lim_m=1 << 20))

    def unlock(self):
        self._enable_write()
        for sector in range(len(self) >> 16):
            addr = sector << 16
            wcmd = bytes((self.CMD_WRLR,
                          (addr >> 16) & 0xff,
                          (addr >> 8) & 0xff,
                          (addr >> 0) & 0xff,
                          (0 << self.SECTOR_LOCK_DOWN) |
                          (0 << self.SECTOR_WRITE_LOCK)))
        self._spi.exchange(wcmd)

class Gd25qFlashDevice(_Gen25FlashDevice):
    """GigaDevice GD25QxxB flash device implementation"""

    JEDEC_ID = 0x68
    DEVICES = {0x40: 'BY25Q'}
    SIZES = {0x15: 2 << 20}
    SPI_FREQ_MAX = 120  # MHz
    TIMINGS = {'page': (0.0007, 0.003),  # .7/3 ms
               'subsector': (0.100, 0.500),  # 100/500 ms
               'sector': (0.4, 2.0),  # .4/2 s
               'bulk': (10, 30)}  # seconds
    FEATURES = (SerialFlash.FEAT_SECTERASE |
                SerialFlash.FEAT_HSECTERASE |
                SerialFlash.FEAT_SUBSECTERASE |
                SerialFlash.FEAT_CHIPERASE)

    def __init__(self, spi, jedec):
        super(Gd25qFlashDevice, self).__init__(spi)
        if not Gd25qFlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        device, capacity = jedec[1:]
        self._size = Gd25qFlashDevice.SIZES[capacity]
        self._device = self.DEVICES[device]

    def __str__(self):
        return 'GigaDevice %s%d %s' % \
            (self._device, len(self) >> 17,
             pretty_size(self._size, lim_m=1 << 20))


class By25qFlashDevice(_Gen25FlashDevice):
    """Boya BY25QxxB flash device implementation"""

    JEDEC_ID = 0x68
    DEVICES = {0x40: 'BY25Q'}
    SIZES = {0x15: 2 << 20, 0x16: 4 << 20}
    SPI_FREQ_MAX = 108  # MHz
    TIMINGS = {'page': (0.0006, 0.003),  # .6/3 ms
               'subsector': (0.050, 0.300),  # 50/300 ms
               'sector': (0.25, 2.0),  # .25/2 s
               'bulk': (15, 30)}  # seconds
    FEATURES = (SerialFlash.FEAT_UNIQUEID |
                SerialFlash.FEAT_SECTERASE |
                SerialFlash.FEAT_HSECTERASE |
                SerialFlash.FEAT_SUBSECTERASE |
                SerialFlash.FEAT_CHIPERASE)

    def __init__(self, spi, jedec):
        super(By25qFlashDevice, self).__init__(spi)
        if not By25qFlashDevice.match(jedec):
            raise SerialFlashUnknownJedec(jedec)
        device, capacity = jedec[1:]
        self._size = By25qFlashDevice.SIZES[capacity]
        self._device = self.DEVICES[device]

    def __str__(self):
        return 'Boya %s%d %s' % \
            (self._device, len(self) >> 17,
             pretty_size(self._size, lim_m=1 << 20))
