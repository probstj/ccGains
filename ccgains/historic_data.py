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
import requests

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
    def __init__(self, unit):
        """Create a HistoricData object with no data.
        The unit must be a string given in the form
        'currency_one/currency_two', e.g. 'EUR/BTC'.

        Only use this constructor if you want to manually set
        the data, otherwise use one of the subclasses
        `HistoricDataCSV` or `HistoricDataAPI`.

        To manually set data, self.data must be a pandas time series
        with a fixed frequency.

        """
        try:
            self.cto, self.cfrom = unit.upper().split('/')
        except:
            raise ValueError(
                    'Please supply the currency exchange rate unit '
                    'in the correct form, e.g. "EUR/USD"')
        self.unit = self.cto + '/' + self.cfrom
        self.interval = None
        self.data = None

    def prepare_request(self, time):
        """Return a Pandas DataFrame which contains the data for the
        requested *time*.

        """
        return self.data

    def get_price(self, time):
        """Return the price at *time*"""
        df = self.prepare_request(time)
        return df.loc[pd.Timestamp(time).floor(self.data.index.freq)]


class HistoricDataCSV(HistoricData):

    def __init__(self, file_name, unit, interval='H'):
        """Initialize a HistoricData object with data loaded from a csv
        file. The unit must be a string given in the form
        'currency_one/currency_two', e.g. 'EUR/BTC'.
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
        super(HistoricDataCSV, self).__init__(unit)
        self.interval = interval

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


class HistoricDataAPI(HistoricData):
    def __init__(self, cache_folder, unit, interval='H'):
        """Initialize a HistoricData object which tranparently fetch data
        on request (`get_price`) from the public Poloniex API:
        https://poloniex.com/public?command=returnTradeHistory

        For faster loading times on future calls, a HDF5 file is created
        from the requested data and used transparently the next time a
        request for the same day and pair is made. These HDF5 files are
        saved in *cache_folder*.

        The *unit* must be a string given in the form
        'currency_one/currency_two', e.g. 'EUR/BTC'.

        The data will be resampled by calculating the weighted price
        for interval steps specified by *interval*. See:
        http://pandas.pydata.org/pandas-docs/stable/timeseries.html#offset-aliases
        for possible values.



        """
        super(HistoricDataAPI, self).__init__(unit)
        self.interval = interval
        self.url = 'https://poloniex.com/public'

        # see if the currency pair exists and the api is reachable:
        req = requests.get(
                'https://poloniex.com/public',
                params={'command' : 'returnTicker'})
        self.currency_pair = '{0:s}_{1:s}'.format(self.cto, self.cfrom)
        if not self.currency_pair in req.json():
            currency_pair2 = '{0:s}_{1:s}'.format(self.cfrom, self.cto)
            if not currency_pair2 in req.json():
                raise ValueError(
                    'Neither currency pair "{0:s}" nor pair "{1:s}" is '
                    'available on "{2:s}".'.format(
                            self.currency_pair, currency_pair2, self.url))
            # flip currency pair:
            self.cfrom, self.cto = self.cto, self.cfrom
            self.unit = self.cto + '/' + self.cfrom
            self.currency_pair = currency_pair2
        self.params = {'command': 'returnTradeHistory',
                       'currencyPair': self.currency_pair}

        ######## errors: ##############
        # more than 1 month:
        #r = requests.get('https://poloniex.com/public?command=returnTradeHistory&currencyPair=BTC_XMR&start=0&end=1483142400')

        # wrong cur.pair:
        #https://poloniex.com/public?command=returnTradeHistory&currencyPair=BTC_PMR&start=1410158341&end=1410499372


        # tiny data year 2016 end:
        #r = requests.get('https://poloniex.com/public?command=returnTradeHistory&currencyPair=BTC_XMR&start=1483228700&end=1483228800')


        #df = pd.read_json(req.text)
        #print df

        self.urlfmt = (
                'https://poloniex.com/public?command=returnTradeHistory&'
                'currencyPair={0:s}_{1:s}&start={2:d}&end={3:d}')

        #url = self.urlfmt.format(
        #        self.cto, self.cfrom,
        #        self.start.value // 10 ** 9, self.end.value // 10 ** 9)
        #print url
        #r = urllib2.urlopen(url)
        #print r.read()[:100]
        #with open('/home/juergen/Coding/projects/ccGains/data/polotest.json') as f:
        #    pd.read_json(f)
        #    print pd

    def prepare_request(self, time):
        """Return a Pandas DataFrame which contains the data for the
        requested *time*.

        """
        # request data for the same day:
        params
        return self.data

