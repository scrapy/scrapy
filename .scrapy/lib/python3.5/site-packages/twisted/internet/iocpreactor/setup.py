# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Distutils file for building low-level IOCP bindings from their Pyrex source
"""


from distutils.core import setup
from distutils.extension import Extension
from Cython.Distutils import build_ext

setup(name='iocpsupport',
      ext_modules=[Extension('iocpsupport',
                   ['iocpsupport/iocpsupport.pyx',
                    'iocpsupport/winsock_pointers.c'],
                   libraries = ['ws2_32'],
                   )
                  ],
      cmdclass = {'build_ext': build_ext},
      )

