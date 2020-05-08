#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2010-2020 Emmanuel Blot <emmanuel.blot@free.fr>
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

#pylint: disable-msg=no-self-use

from codecs import open as codec_open
from os import close, unlink
from os.path import abspath, dirname, join as joinpath
from py_compile import compile as pycompile, PyCompileError
from re import split as resplit, search as research
from sys import stderr
from tempfile import mkstemp
from setuptools import find_packages, setup
from setuptools.command.build_py import build_py


NAME = 'pyspiflash'
PACKAGES = find_packages(where='.')
META_PATH = joinpath('spiflash', '__init__.py')
KEYWORDS = ['driver', 'ftdi', 'usb', 'spi', 'flash', 'mtd']
CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'Environment :: Other Environment',
    'Natural Language :: English',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: MacOS :: MacOS X',
    'Operating System :: POSIX',
    'Operating System :: Microsoft :: Windows',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Programming Language :: Python :: 3.7',
    'Programming Language :: Python :: 3.8',
    'Topic :: Software Development :: Libraries :: Python Modules',
    'Topic :: System :: Hardware :: Hardware Drivers',
]
INSTALL_REQUIRES = [
    'pyftdi >= 0.42, < 0.60'
]

HERE = abspath(dirname(__file__))


def read(*parts):
    """
    Build an absolute path from *parts* and and return the contents of the
    resulting file.  Assume UTF-8 encoding.
    """
    with codec_open(joinpath(HERE, *parts), 'rb', 'utf-8') as dfp:
        return dfp.read()


META_FILE = read(META_PATH)


def find_meta(meta):
    """
    Extract __*meta*__ from META_FILE.
    """
    meta_match = research(
        r"(?m)^__{meta}__ = ['\"]([^'\"]*)['\"]".format(meta=meta),
        META_FILE
    )
    if meta_match:
        return meta_match.group(1)
    raise RuntimeError("Unable to find __{meta}__ string.".format(meta=meta))


class BuildPy(build_py):
    """Override byte-compile sequence to catch any syntax error issue.

       For some reason, distutils' byte-compile when it forks a sub-process
       to byte-compile a .py file into a .pyc does NOT check the success of
       the compilation. Therefore, any syntax error is explictly ignored,
       and no output file is generated. This ends up generating an incomplete
       package w/ a nevertheless successfull setup.py execution.

       Here, each Python file is build before invoking distutils, so that any
       syntax error is catched, raised and setup.py actually fails should this
       event arise.

       This step is critical to check that an unsupported syntax (for ex. 3.6
       syntax w/ a 3.5 interpreter) does not end into a 'valid' package from
       setuptools perspective...
    """

    def byte_compile(self, files):
        for file in files:
            if not file.endswith('.py'):
                continue
            pfd, pyc = mkstemp('.pyc')
            close(pfd)
            try:
                pycompile(file, pyc, doraise=True)
                self._check_line_width(file)
                continue
            except PyCompileError as exc:
                # avoid chaining exceptions
                print(str(exc), file=stderr)
                raise SyntaxError("Cannot byte-compile '%s'" % file)
            finally:
                unlink(pyc)
        super().byte_compile(files)

    def _check_line_width(self, file):
        with open(file, 'rt') as pfp:
            for lpos, line in enumerate(pfp, start=1):
                if len(line) > 80:
                    print('\n  %d: %s' % (lpos, line.rstrip()))
                    raise RuntimeError("Invalid line width '%s'" % file)


def main():
    setup(
        cmdclass={'build_py': BuildPy},
        name=NAME,
        description=find_meta('description'),
        license=find_meta('license'),
        url=find_meta('uri'),
        version=find_meta('version'),
        author=find_meta('author'),
        author_email=find_meta('email'),
        maintainer=find_meta('author'),
        maintainer_email=find_meta('email'),
        keywords=KEYWORDS,
        long_description=read('README.rst'),
        packages=PACKAGES,
        package_dir={'': '.'},
        package_data={'spiflash': ['*.rst']},
        classifiers=CLASSIFIERS,
        install_requires=INSTALL_REQUIRES,
        python_requires='>=3.5',
    )


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(exc, file=stderr)
        exit(1)
