#!/usr/bin/env python3
# Copyright (c) 2011-2019, Emmanuel Blot <emmanuel.blot@free.fr>
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

import unittest
from hashlib import sha1
from os import environ
from random import randint, seed
from struct import pack as spack
from time import time as now
from pyftdi.ftdi import Ftdi
from pyftdi.misc import hexdump, pretty_size
from pyftdi.spi import SpiController
from pyftdi.usbtools import UsbTools
from spiflash.serialflash import SerialFlashManager

#pylint: disable-msg=invalid-name
#pylint: disable-msg=too-many-locals


class SerialFlashTestCase(unittest.TestCase):
    """Configuration can be changed through environment variables:

       * FTDI_DEVICE: URL to access the FTDI device/interface
       * SPI_FREQUENCY: SPI bus frequency in Hz
    """

    @classmethod
    def setUpClass(cls):
        # FTDI device should be defined to your actual setup
        cls.ftdi_url = environ.get('FTDI_DEVICE', 'ftdi://ftdi:2232/1')
        cls.frequency = float(environ.get('SPI_FREQUENCY', 12E6))
        print('Using FTDI device %s' % cls.ftdi_url)

    def setUp(self):
        self.flash = None

    def tearDown(self):
        del self.flash

    def test_flashdevice_1_name(self):
        """Retrieve device name
        """
        self.flash = SerialFlashManager.get_flash_device(self.ftdi_url, 0,
                                                         self.frequency)
        print("Flash device: %s @ SPI freq %0.1f MHz" %
              (self.flash, self.flash.spi_frequency/1E6))

    def test_flashdevice_2_read_bandwidth(self):
        """Read the whole device to get READ bandwith
        """
        self.flash = SerialFlashManager.get_flash_device(self.ftdi_url, 0,
                                                         self.frequency)
        delta = now()
        data = self.flash.read(0, len(self.flash))
        delta = now()-delta
        length = len(data)
        self._report_bw('Read', length, delta)
        f = open('spiDataP5.bin','wb')
        f.write(data)
        print("Data read length: %d", length)
        f.close()
    # def test_flashdevice_3_small_rw(self):
    #     """Short R/W test
    #     """
    #     self.flash = SerialFlashManager.get_flash_device(self.ftdi_url, 0,
    #                                                      self.frequency)
    #     self.flash.unlock()
    #     self.flash.erase(0x007000, 4096)
    #     data = self.flash.read(0x007020, 128)
    #     ref = bytes([0xff] * 128)
    #     self.assertEqual(data, ref)
    #     test = 'This is a serial SPI flash test.' * 3
    #     ref2 = bytearray(test.encode('ascii'))
    #     self.flash.write(0x007020, ref2)
    #     data = self.flash.read(0x007020, 128)
    #     ref2.extend(ref)
    #     ref2 = ref2[:128]
    #     self.assertEqual(data, ref2)

    # def test_flashdevice_4_long_rw(self):
    #     """Long R/W test
    #     """
    #     # Max size to perform the test on
    #     size = 1 << 20
    #     # Whether to test with random value, or contiguous values to ease debug
    #     randomize = True
    #     # Fill in the whole flash with a monotonic increasing value, that is
    #     # the current flash 32-bit address, then verify the sequence has been
    #     # properly read back
    #     # limit the test to 1MiB to keep the test duration short, but performs
    #     # test at the end of the flash to verify that high addresses may be
    #     # reached
    #     self.flash = SerialFlashManager.get_flash_device(self.ftdi_url, 0,
    #                                                      self.frequency)
    #     length = min(len(self.flash), size)
    #     start = len(self.flash)-length
    #     print("Erase %s from flash @ 0x%06x (may take a while...)" %
    #           (pretty_size(length), start))
    #     delta = now()
    #     self.flash.unlock()
    #     self.flash.erase(start, length, True)
    #     delta = now()-delta
    #     self._report_bw('Erased', length, delta)
    #     if str(self.flash).startswith('SST'):
    #         # SST25 flash devices are tremendously slow at writing (one or two
    #         # bytes per SPI request MAX...). So keep the test sequence short
    #         # enough
    #         length = 16 << 10
    #     print("Build test sequence")
    #     if not randomize:
    #         buf = bytearray()
    #         for address in range(0, length, 4):
    #             buf.extend(spack('>I', address))
    #         # Expect to run on x86 or ARM (little endian), so swap the values
    #         # to ease debugging
    #     else:
    #         seed(0)
    #         buf = bytearray()
    #         buf.extend((randint(0, 255) for _ in range(0, length)))
    #     print("Writing %s to flash (may take a while...)" %
    #           pretty_size(len(buf)))
    #     delta = now()
    #     self.flash.write(start, buf)
    #     delta = now()-delta
    #     length = len(buf)
    #     self._report_bw('Wrote', length, delta)
    #     wmd = sha1()
    #     wmd.update(buf)
    #     refdigest = wmd.hexdigest()
    #     print("Reading %s from flash" % pretty_size(length))
    #     delta = now()
    #     back = self.flash.read(start, length)
    #     delta = now()-delta
    #     self._report_bw('Read', length, delta)
    #     # print "Dump flash"
    #     # print hexdump(back.tobytes())
    #     print("Verify flash")
    #     rmd = sha1()
    #     rmd.update(back)
    #     newdigest = rmd.hexdigest()
    #     print("Reference:", refdigest)
    #     print("Retrieved:", newdigest)
    #     if refdigest != newdigest:
    #         errcount = 0
    #         for pos in range(len(buf)):
    #             if buf[pos] != back[pos]:
    #                 print('Invalid byte @ offset 0x%06x: 0x%02x / 0x%02x' %
    #                       (pos, buf[pos], back[pos]))
    #                 errcount += 1
    #                 # Stop report after 16 errors
    #                 if errcount >= 32:
    #                     break
    #         raise self.fail('Data comparison mismatch')

    # def test_usb_device(self):
    #     """Demo instanciation from an existing UsbDevice.
    #     """
    #     candidate = Ftdi.get_identifiers(self.ftdi_url)
    #     usbdev = UsbTools.get_device(candidate[0])
    #     spi = SpiController(cs_count=1)
    #     spi.configure(usbdev, interface=candidate[1])
    #     flash = SerialFlashManager.get_from_controller(spi, cs=0,
    #                                                    freq=self.frequency)

    # def test_spi_controller(self):
    #     """Demo instanciation with an SpiController.
    #     """
    #     spi = SpiController(cs_count=1)
    #     spi.configure(self.ftdi_url)
    #     flash = SerialFlashManager.get_from_controller(spi, cs=0,
    #                                                    freq=self.frequency)

    @classmethod
    def _report_bw(cls, action, length, time_):
        if time_ < 1.0:
            print("%s %s in %d ms @ %s/s" % (action, pretty_size(length),
                  int(1000*time_), pretty_size(length/time_)))
        else:
            print("%s %s in %d seconds @ %s/s" % (action, pretty_size(length),
                  int(time_), pretty_size(length/time_)))


def suite():
    return unittest.makeSuite(SerialFlashTestCase, 'test')


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
