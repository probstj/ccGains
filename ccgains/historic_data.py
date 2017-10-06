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
from time import sleep

def resample_weighted_average(
        df, freq, data_col, weight_col, include_weights=False):
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
    :param include_weights: (default False)
        If True, include the summed weights in result
    :return:
        if include_weights:
            pandas.Series with weighted averages
        else:
            pands.DataFrame with two columns:
                data_col: the weighted averages,
                weight_col: the summed weights

    Source: ErnestScribbler, https://stackoverflow.com/a/44683506

    """
    # Create a new column with data * weight. The trick is that
    # this column will be grouped along with the other data and
    # can thus be used in aggregation:
    df['data_times_weight'] = df[data_col] * df[weight_col]
    g = df.resample(freq)
    avgs = g['data_times_weight'].sum() / g[weight_col].sum()
    del df['data_times_weight']
    if include_weights:
        return pd.DataFrame(
                {data_col: avgs, weight_col: g[weight_col].sum()})
    else:
        return avgs

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

    def prepare_request(self, dtime):
        """Return a Pandas DataFrame which contains the data at the
        requested datetime *dtime*.

        """
        return self.data

    def get_price(self, dtime):
        """Return the price at datetime *dtime*"""
        df = self.prepare_request(dtime)
        return df.loc[pd.Timestamp(dtime).floor(df.index.freq)]


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
        # Poloniex does not allow more than 6 queries per second;
        # Wait at least this number of seconds between queries:
        self.query_wait_time = 0.17
        self.command = 'returnTradeHistory'
        self.currency_pair = '{0:s}_{1:s}'.format(self.cto, self.cfrom)
        self.file_name = path.join(
                cache_folder,
                'Poloniex_{0:s}_{1:s}.h5'.format(
                        self.currency_pair, self.interval))
        # See if the currency pair exists:
        self.last_query_time = pd.Timestamp.now()
        if not path.exists(self.file_name):
            # If a cache with the correct file name already exists,
            # there's no need to query the api again
            req = requests.get(
                self.url,
                params={'command' : 'returnTicker'})
            if not self.currency_pair in req.json():
                # try if flipped currency pair is available:
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
                self.file_name = path.join(
                        cache_folder,
                        'Poloniex_{0:s}_{1:s}.h5'.format(
                                self.currency_pair, self.interval))

    def prepare_request(self, dtime):
        """Return a Pandas DataFrame which contains the data for the
        requested datetime *dtime*.

        """
        dtime = pd.Timestamp(dtime)
        key = "d{a:04d}{m:02d}{d:02d}".format(
                a=dtime.year, m=dtime.month, d=dtime.day)
        with pd.HDFStore(self.file_name, mode='a') as store:
            if key in store:
                return store.get(key)
            else:
                # We need to fetch the data from the poloniex api
                start = dtime.floor('D').value // 10 ** 9
                # fetch a time span of one day:
                end = start + 86400
                # Wait for the min call time to pass:
                now = pd.Timestamp.now()
                delta = (now - self.last_query_time).total_seconds()
                self.last_query_time = now
                if delta <= self.query_wait_time:
                    sleep(self.query_wait_time - delta)
                # Make request:
                req = requests.get(
                        self.url,
                        params={'command': self.command,
                                'currencyPair': self.currency_pair,
                                'start': start,
                                'end': end})
                try:
                    df = pd.read_json(
                        req.text, orient='records', precise_float=True,
                        convert_axes=False, convert_dates=['date'],
                        keep_default_dates=False, dtype={
                                'tradeID': False, 'globalTradeID': False,
                                'total': False, 'type': False, 'date': False,
                                'rate': float, 'amount': float})
                except ValueError:
                    # There might have been an error returned from Poloniex,
                    # which cannot be parsed the same way than regular data.
                    j = pd.json.loads(req.text)
                    if 'error' in j:
                        raise ValueError(
                            "Poloniex API returned error: {0:s}\n"
                            "Requested URL was: {1:s}".format(
                                    j['error'],
                                    req.url))
                    else:
                        raise
                df.set_index('date', inplace=True)
                self.data = resample_weighted_average(
                        df, self.interval, 'rate', 'amount')
                store.put(key, self.data, format="fixed")
                return self.data
