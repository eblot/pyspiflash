#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2010-2016 Emmanuel Blot <emmanuel.blot@free.fr>
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

try:
    # try to use setuptools first, so extended command set such as
    # python setup.py develop is available
    from setuptools import setup
except ImportError:
    # if setuptools package is not available, fall back to the default
    # distribution package.
    from distutils.core import setup
from spiflash import __version__ as VERSION


def _read(fname):
    import os
    return open(os.path.join(os.path.dirname(__file__), 'spiflash',
                fname)).read()

setup(
    name='pyspiflash',
    version=VERSION,
    description='SPI data flash device drivers (pure Python)',
    author='Emmanuel Blot',
    author_email='emmanuel.blot@free.fr',
    license='MIT',
    keywords='driver ftdi usb serial spi flash mtd',
    url='http://github.com/eblot/pyspiflash',
    download_url='https://github.com/eblot/pyspiflash/archive/v%s.tar.gz' %
                 VERSION,
    packages=['spiflash'],
    package_data={'spiflash': ['*.rst']},
    requires=['pyftdi (>= 0.13.2, < 0.20.0)'],
    install_requires=['pyftdi>=0.13.2'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Other Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3.5',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Hardware :: Hardware Drivers',
    ],
    long_description=_read('README.rst'),
)
