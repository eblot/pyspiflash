from array import array as Array
from pyftdi.spi import SpiController

vendor = 0x403
product = 0x6010
interface = 1
cs = 0
freq = 100000

ctrl = SpiController(turbo=False)
ctrl.configure(vendor, product, interface)
spi = ctrl.get_port(cs)
spi.set_frequency(freq)
for i in range(10):
    tx = Array('B', [0x30+i])
    rx = spi.exchange(tx, 0)
print rx.tostring()
