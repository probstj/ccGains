#!/usr/bin/env python
# -*- coding:utf-8 -*-
#
# ----------------------------------------------------------------------
# ccGains - Create capital gains reports for cryptocurrency trading.
# Copyright (C) 2017 Jürgen Probst
#
# This file is part of ccGains.
#
# ccGains is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ccGains is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with ccGains. If not, see <http://www.gnu.org/licenses/>.
# ----------------------------------------------------------------------
#
# Get the latest version at: https://github.com/probstj/ccGains
#

from setuptools import setup

setup(name='ccGains',
      version='1.0',
      description='Python package for calculating cryptocurrency trading '
                  'profits and creating capital gains reports',
      url='https://github.com/probstj/ccgains',
      author='Jürgen Probst',
      author_email='juergen.probst@gmail.com',
      license='LGPL-3.0-or-later',
      packages=['ccgains'],
      install_requires=[
          'tables',
          'numpy',
          'pandas',
          'requests',
          'jinja2', # I should make this and the next optional some day.
          'babel',
          'weasyprint',
          'python-dateutil',
      ],
      include_package_data=True,
      zip_safe=False)

