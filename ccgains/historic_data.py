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
from dateutil import tz

import logging
log = logging.getLogger(__name__)

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

          pandas.DataFrame with two columns:

            - data_col: the weighted averages,
            - weight_col: the summed weights

        else:

          pandas.Series with weighted averages

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
        return df.at[pd.Timestamp(dtime).floor(df.index.freq)]


class HistoricDataCSV(HistoricData):

    def __init__(self, file_name, unit, interval='H'):
        """Initialize a HistoricData object with data loaded from a csv
        file. The unit must be a string given in the form
        'currency_one/currency_two', e.g. 'EUR/BTC'.
        The csv must consist of three columns: first a unix timestamp,
        second the rate given in *unit*, third the amount traded.
        (Such a csv can be downloaded from bitcoincharts.com)

        The file may also be compressed and will be deflated on-the-fly;
        allowed extensions are: '.gz', '.bz2', '.zip' or '.xz'.

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
        self.dataset = '{0:s}_{1:s}'.format(self.cto, self.cfrom)

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

            if csvtime <= h5time:
                # Quick load from h5 file, but only if data matches:
                self.file_name = fbase + '.h5'
                try:
                    with pd.HDFStore(self.file_name, mode='r') as store:
                        self.data = store[self.dataset]
                except (KeyError, AttributeError, IOError):
                    # Will force csv to be reloaded:
                    h5time = 0

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
                self.file_name = fbase + '.h5'
                with pd.HDFStore(self.file_name) as store:
                    store[self.dataset] = self.data

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
        # Poloniex limits the amount of trades returned per query:
        self.max_trades_per_query = 50000
        self.command = 'returnTradeHistory'
        self.currency_pair = '{0.cto:s}_{0.cfrom:s}'.format(self)
        self.last_query_time = pd.Timestamp.now()
        self.connection_error = requests.ConnectionError(
            'Price data for %s could not be loaded from %s '
            '- are you online?' % (self.currency_pair, self.url))
        file_name = path.join(
            cache_folder,
            'Poloniex_{0.cto:s}_{0.cfrom:s}_{0.interval:s}.h5'.format(self))
        # flipped currency pair:
        file_name_f = path.join(
            cache_folder,
            'Poloniex_{0.cfrom:s}_{0.cto:s}_{0.interval:s}.h5'.format(self))
        # See if the currency pair is already cached:
        if path.exists(file_name):
            self.file_name = file_name
        elif path.exists(file_name_f):
            # flip currency pair:
            self.cfrom, self.cto = self.cto, self.cfrom
            self.unit = self.cto + '/' + self.cfrom
            self.file_name = file_name_f
            self.currency_pair = '{0.cto:s}_{0.cfrom:s}'.format(self)
        else:
            # Query the api to see if the pair is available:
            try:
                req = requests.get(
                    self.url,
                    params={'command' : 'returnTicker'})
            except requests.ConnectionError:
                raise self.connection_error
            if self.currency_pair in req.json():
                self.file_name = file_name
            else:
                # try if flipped currency pair is available:
                currency_pair_f = '{0.cfrom:s}_{0.cto:s}'.format(self)
                if not currency_pair_f in req.json():
                    raise ValueError(
                        'Neither currency pair "{0:s}" nor pair "{1:s}" is '
                        'available on "{2:s}".'.format(
                            self.currency_pair, currency_pair_f, self.url))
                # flip currency pair:
                self.cfrom, self.cto = self.cto, self.cfrom
                self.unit = self.cto + '/' + self.cfrom
                self.currency_pair = currency_pair_f
                self.file_name = file_name_f

    def _fetch_from_api(self, start, end=None):
        """Fetch historical trading data from API.

        :param start: UNIX Timestamp (seconds); Start of range to fetch.
        :param end: UNIX timestamp (seconds); End of range to fetch.
            If None (default), will fetch a range of one day, i.e.
            end will be `start + 86400`.
        :returns: tuple (number of fetched trades, resampled data)

        The returned data will be resampled to `self.interval`. The
        data will consist of weighted historical prices, averaged over
        each interval using the traded amounts as weights.

        In case there is a limit on the number of trades returned by
        the API, not the full requested range from `start` to `end`
        can be returned by this function. Check the returned
        data and the number of fetched trades to determine if data
        is missing. In such a case, the weighted averages of prices
        at the missing ends of the range cannot be trusted.

        """
        if end is None:
            # fetch a time span of one day:
            end = start + 86400
        # Wait for the min call time to pass:
        now = pd.Timestamp.now()
        delta = (now - self.last_query_time).total_seconds()
        self.last_query_time = now
        if delta <= self.query_wait_time:
            log.info('waiting %f s', self.query_wait_time - delta)
            sleep(self.query_wait_time - delta)
            log.info('continuing')
        # Make request:
        try:
            req = requests.get(
                self.url,
                params={'command': self.command,
                        'currencyPair': self.currency_pair,
                        'start': int(start),
                        'end': int(end)})
        except requests.ConnectionError:
            raise self.connection_error
        log.info('Fetched historical price data with request: %s', req.url)
        try:
            df = pd.read_json(
                req.text, orient='records', precise_float=True,
                convert_axes=False, convert_dates=['date'],
                keep_default_dates=False, dtype={
                        'tradeID': False, 'globalTradeID': False,
                        'total': False, 'type': False, 'date': False,
                        'rate': float, 'amount': float})
            log.info('Successfully fetched %i trades', len(df))
        except ValueError:
            # There might have been an error returned from Poloniex,
            # which cannot be parsed the same way than regular data.
            j = pd.io.json.loads(req.text)
            if 'error' in j:
                raise ValueError(
                    "Poloniex API returned error: {0:s}\n"
                    "Requested URL was: {1:s}".format(
                            j['error'],
                            req.url))
            else:
                raise
        df.set_index('date', inplace=True)

        # Get weighted prices, resampled with interval:
        # (this will only return one column, the weighted prices;
        # the total volume won't be needed anymore)
        data = resample_weighted_average(
                df, self.interval, 'rate', 'amount')

        # In case the data has been upsampled (Some events
        # beeing more separated than interval), the resulting
        # Series will have some NaNs. Forward-fill them with
        # the last prices before:
        data.ffill(inplace=True)

        if data.index.tzinfo is None:
            data.index = data.index.tz_localize('UTC')

        return len(df), data

    def prepare_request(self, dtime):
        """Return a Pandas DataFrame which contains the data for the
        requested datetime *dtime*.

        """
        dtime = pd.Timestamp(dtime).tz_convert(tz.tzutc())
        key = "d{a:04d}{m:02d}{d:02d}".format(
                a=dtime.year, m=dtime.month, d=dtime.day)
        with pd.HDFStore(self.file_name, mode='a') as store:
            if key in store:
                try:
                    self.data = store.get(key)
                    # Check whether the data can be accessed:
                    self.data.at[
                            pd.Timestamp(dtime).floor(self.data.index.freq)]
                    return self.data
                except (KeyError, AttributeError):
                    # In case the hdf5 file got corrupted somehow,
                    # with the requested date missing from the data,
                    # reload the data from the API:
                    log.warning(
                        'Date %s missing in cached data. '
                        'Repeating request to API', dtime)

            # We need to fetch the data from the poloniex api:
            start = dtime.floor('D').value // 10 ** 9
            count, self.data = self._fetch_from_api(start)

            # Did we reach the limit?
            while count == self.max_trades_per_query:
                # The API might not have returned all requested trades.
                # If Poloniex omits data, the end of the requested range
                # is returned.
                # Remove first faulty interval:
                # (faulty because data might be missing)
                del self.data[self.data.index[0]]
                # end time of next request:
                end = self.data.index[0].value // 10 ** 9 - 1
                # new request:
                count, data = self._fetch_from_api(start, end)
                if len(data) <= 1 and count == self.max_trades_per_query:
                    # It seems our interval is too big or there are just
                    # too many trades in the interval, so that we cannot
                    # fetch one interval with a single request.
                    raise Exception(
                        "There are too many trades in the chosen "
                        "interval of %s ending on %s. Please try again "
                        "with an HistoricDataAPI object with smaller "
                        "interval size." % (
                            self.data.index.freq,
                            self.data.index[0]))
                self.data = self.data.combine_first(data)



            store.put(key, self.data, format="fixed")
            return self.data


class HistoricDataAPIBinance(HistoricData):

    def __init__(self, cache_folder, unit, interval='H'):
        """Initialize a HistoricData object which will transparently fetch
        data on request (`get_price`) from the public Binance API:
        https://api.binance.com/api/v1/aggTrades

        For faster loading times on future calls, a HDF5 file is created
        from the requested data and used transparently the next time a
        request for the same day and pair is made. These HDF5 files are
        saved in *cache_folder*.

        The *unit* must be a string in the form
        'currency_one/currency_two', e.g. 'NEO/BTC'.

        The data will be resampled by calculating the weighted price
        for interval steps specified by *interval*. See:
        http://pandas.pydata.org/pandas-docs/stable/timeseries.html#offset-aliases
        for possible values.
        """

        super(HistoricDataAPIBinance, self).__init__(unit)
        self.interval = interval
        self.url = 'https://api.binance.com/api/v1'
        self.command = '/klines'

        # Applicable Binance rate limit is 1000 / min (for aggTrade requests)
        self.query_wait_time = 0.06
        self.max_trades_per_query = 1000
        self.last_query_time = pd.Timestamp.now()

        # Binance does not use any separator between base and quote assets
        # Binance pairs are listed as 'from to' (e.g. XRPBTC is price of 1 XRP in BTC)
        self.currency_pair = '{0.cfrom:s}{0.cto:s}'.format(self)

        self.connection_error = requests.ConnectionError(
            'Price data for %s could not be loaded from %s '
            '- are you online?' % (self.currency_pair, self.url))

        file_name = path.join(
            cache_folder,
            'Binance_{0.cfrom:s}{0.cto:s}_{0.interval:s}.h5'.format(self))
        # Flipped currency pair:
        flipped_file_name = path.join(
            cache_folder,
            'Binance_{0.cto:s}{0.cfrom:s}_{0.interval:s}.h5'.format(self))

        # See if the currency pair is already cached:
        if path.exists(file_name):
            self.file_name = file_name
        elif path.exists(flipped_file_name):
            # Flip currency pair
            self.cfrom, self.cto = self.cto, self.cfrom
            self.unit = self.cto + '/' + self.cfrom
            self.file_name = flipped_file_name
            self.currency_pair = '{0.cfrom:s}{0.cto:s}'.format(self)
        else:
            # Query the API to see if the pair is available:
            try:
                req = requests.get(self.url + '/exchangeInfo')
            except requests.ConnectionError:
                raise self.connection_error

            known_symbols = [info['symbol'] for info in req.json()['symbols']]

            if self.currency_pair in known_symbols:
                self.file_name = file_name
            else:
                # Try flipped currency pair
                flipped_currency_pair = '{0.cto:s}{0.cfrom:s}'.format(self)
                if flipped_currency_pair not in known_symbols:
                    raise ValueError(
                        'Neither currency pair "{0:s}" nor pair "{1:s}" is '
                        'available on "{2:s}".'.format(
                            self.currency_pair, flipped_currency_pair, self.url))
                # Flip currency pair
                self.cfrom, self.cto = self.cto, self.cfrom
                self.unit = self.cto + '/' + self.cfrom
                self.currency_pair = flipped_currency_pair
                self.file_name = flipped_file_name

    def _wait_if_needed(self):
        # Wait for the minimum call time to pass:
        now = pd.Timestamp.now()
        delta = (now - self.last_query_time).total_seconds()

        if delta < self.query_wait_time:
            log.info('waiting %f s', self.query_wait_time - delta)
            sleep(self.query_wait_time - delta)
            log.info('continuing')

    def _fetch_from_api(self, start, end=None):
        """Fetch historical trading data from API.

        :param start: UNIX timestamp (seconds); Start of range to fetch.
        :param end: UNIX timestamp (seconds); End of range to fetch.
            If None (default), will fetch a range of one day, i.e.
            end will be `start + 86400`.
        :returns: tuple (number of fetched trades, resampled data)

        The returned data will be resampled to `self.interval`. The
        data will consist of weighted historical prices, averaged over
        each interval using the traded amounts as weights.

        In case there is a limit on the number of trades returned by
        the API, several queries will be sent to capture the full
        range of prices. Binance limit is 1000 per response
        """

        end = end or start + 86400  # Fetch a time span of one day:

        # Binance uses milliseconds instead of seconds
        start = int(start * 1000)
        end = int(end * 1000)

        # Set up to pull data from the API
        kline_interval = '1m'
        interval_ms = pd.Timedelta(kline_interval).total_seconds() * 1000
        req_params = {
            'symbol': self.currency_pair,
            'interval': kline_interval,
            'limit': self.max_trades_per_query
        }

        chunk_delta = int(interval_ms * self.max_trades_per_query)
        chunk_start = start
        remaining_time = pd.Timedelta((end - start), 'ms')

        df = pd.DataFrame()

        while remaining_time > pd.Timedelta(0):
            # Set up to get the next chunk
            chunk_end = min(end, chunk_start + chunk_delta)

            req_params.update({'startTime': chunk_start, 'endTime': chunk_end})
            response = self._call_api(req_params)

            klines = pd.DataFrame(
                response.json(),
                columns=[
                    'OpenTime',
                    'Open', 'High', 'Low', 'Close', 'Volume',
                    'CloseTime',
                    'QuoteAssetVolume', 'NumTrades',
                    'TakerBuyBaseAssetVolume', 'TakerBuyQuoteAssetVolume',
                    'Ignore'])
            # Drop the columns we don't need
            klines = klines.iloc[:, [4, 5, 6]]
            # Index by interval close time and add to previous results
            klines.CloseTime = pd.to_datetime(klines.CloseTime, unit='ms')
            klines = klines.astype({'Close': float, 'Volume': float})
            klines.set_index('CloseTime', inplace=True)
            df = df.append(klines)

            # Set up for next loop (if needed). If less than limit klines were
            # returned, that means we got all we needed so OK to be negative
            remaining_time -= self.max_trades_per_query * pd.Timedelta(kline_interval)
            chunk_start = chunk_end

            log.info('Fetched historical price data with request: %s', response.url)

        # Get weighted prices, resampled with interval:
        # (this will only return one column, the weighted prices;
        # the total volume won't be needed anymore)
        data = resample_weighted_average(
            df, self.interval, 'Close', 'Volume')

        # In case the data has been upsampled (some events
        # being more separated than interval), the resulting
        # Series will have some NaNs. Forward-fill them
        # with the last prices before:
        data.ffill(inplace=True)

        if data.index.tzinfo is None:
            data.index = data.index.tz_localize('UTC')

        return len(df), data

    def _call_api(self, params):
        """Call Binance API with *params*, validate the response,
        and return the results
        """

        # Be nice to the API
        self._wait_if_needed()

        # Make the API call
        try:
            url = self.url + self.command
            req = requests.get(url, params=params)
            self.last_query_time = pd.Timestamp.now()
        except requests.ConnectionError:
            raise self.connection_error

        # Check for valid response:
        if req.status_code in [429, 418]:
            raise ConnectionError('Binance Rate limits exceeded')
        elif req.status_code >= 400:
            err_code = req.json()['code']
            err_msg = req.json()['msg']
            raise ValueError(
                'Cannot retrieve trade data from Binance '
                'because of error code %s (%s) when querying URL "%s"'
                % (err_code, err_msg, req.url))

        return req

    def prepare_request(self, dtime):
        """Return a pandas DataFrame which contains the data for the
        requested datetime *dtime*.
        """

        dtime = pd.Timestamp(dtime).tz_convert(tz.tzutc())
        key = "d{a:04d}{m:02d}{d:02d}".format(
            a=dtime.year, m=dtime.month, d=dtime.day)
        with pd.HDFStore(self.file_name, mode='a') as store:
            if key in store:
                try:
                    self.data = store.get(key)
                    # Check whether data can be accessed:
                    self.data.at[pd.Timestamp(dtime).floor(self.data.index.freq)]
                    return self.data
                except (KeyError, AttributeError):
                    # In case of the hdf5 file got corrupted somehow,
                    # with the requested date missing from the data,
                    # reload the data from the API:
                    log.warning(
                        'Date %s missing in cached data. '
                        'Repeating request to API', dtime)

            # We need to fetch the data from the Binance API
            start = dtime.floor('D').value // 10 ** 9
            count, self.data = self._fetch_from_api(start)

            # For Binance, _fetch_from_api() already ensures that all data
            # is collected (repeating subsequent queries if needed)

            store.put(key, self.data, format="fixed")
            return self.data
