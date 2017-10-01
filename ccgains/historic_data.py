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

from os import path
import pandas as pd

def resample_weighted_average(df, freq, data_col, weight_col):
    """Resample a DataFrame with a DatetimeIndex. Return weighted
    averages of groups.

    :param df:
        The pandas.DataFrame to be resampled
    :param freq:
        The new frequency of the resampled time series
    :param data_col:
        Column to take the average of
    :param weight_col:
        Column with the weights
    :return:
        pandas.Series with weighted averages

    Source: ErnestScribbler, https://stackoverflow.com/a/44683506

    """
    # Create a new column with data * weight. The trick is that
    # this column will be grouped along with the other data and
    # can thus be used in aggregation:
    df['data_times_weight'] = df[data_col] * df[weight_col]
    g = df.resample(freq)
    result = g['data_times_weight'].sum() / g[weight_col].sum()
    del df['data_times_weight']
    return result

class HistoricData(object):
    def __init__(self, file_name, unit, interval='H'):
        """Initialize a HistoricData object with data loaded from a csv
        file. The unit must be a string given in the form
        'currency_one/currency2', e.g. 'EUR/BTC'.
        The csv must consist of three columns: first a unix timestamp,
        second the rate given in *unit*, third the amount traded.
        (Such a csv can be downloaded from bitcoincharts.com)

        The data will be resampled by calculating the weighted price
        for interval steps specified by *interval*. See:
        http://pandas.pydata.org/pandas-docs/stable/timeseries.html#offset-aliases
        for possible values.

        For faster loading times, a HDF5 file is created from the csv
        the first time it is loaded and used transparently the next
        time an HistoricData object is created with the same csv. If
        the csv file is newer than the HDF5 file, the latter will be
        updated.

        """
        try:
            self.cto, self.cfrom = unit.upper().split('/')
        except:
            raise ValueError(
                    'Please supply the currency exchange rate unit '
                    'in the correct form, e.g. "EUR/USD"')
        self.unit = self.cto + '/' + self.cfrom
        self.interval = interval
        self.data = None

        fbase, fext = path.splitext(file_name)
        if fext != '.h5':
            # For faster loading, convert 'csv' file to HDF5 and load the
            # latter, unless the 'csv' file is newer:
            try:
                csvtime = path.getmtime(file_name)
            except OSError:
                csvtime = 0
            try:
                h5time = path.getmtime(fbase + '.h5')
            except OSError:
                h5time = 0
            if csvtime == 0 and h5time == 0:
                raise IOError('File does not exist: %s' % file_name)

            if csvtime > h5time:
                self.data = pd.read_csv(
                        file_name,
                        header=None, index_col='time',
                        names=['time', self.unit, 'volume'])
                # parse timestamps:
                # (quicker than doing it directly in pd.read_csv)
                self.data.index = pd.to_datetime(
                        self.data.index, unit='s', utc=True)
                # sort the data by time:
                self.data.sort_index(inplace=True)
                # create new HDF5 file:
                store = pd.HDFStore(fbase + '.h5', mode='w')
                store['data'] = self.data
                store.close()

        self.file_name = fbase + '.h5'
        self.store = pd.HDFStore(self.file_name, mode='r')
        # load it into memory:
        self.data = self.store['data']
        self.store.close()

        # Get weighted prices, resampled with interval:
        # (this will only return one column, the weighted prices; the
        # total volume won't be needed anymore)
        self.data = resample_weighted_average(
                self.data, interval, self.unit, 'volume')

        # In case the data has been upsampled (Some events beeing more
        # separated than interval), the resulting Series will have some
        # NaNs. Forward-fill them with the last prices before:
        self.data.ffill(inplace=True)

        # Don't change self.data's DateTimeIndex into PeriodIndex since
        # periods don't support timezones, which we want to keep.
        # (https://github.com/pandas-dev/pandas/issues/2106)


    def get_price(self, time):
        """Return the price at *time*"""
        return self.data.loc[pd.Timestamp(time).floor(self.data.index.freq)]


