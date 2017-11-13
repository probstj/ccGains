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

from decimal import Decimal
import pandas as pd
from datetime import datetime
from dateutil import tz
from collections import namedtuple
import json

import logging
log = logging.getLogger(__name__)


PaymentReport = namedtuple(
        'PaymentReport',
        'ptype, exchange, sell_date, currency, to_pay, fee_ratio, '
        'bag_date, bag_amount, bag_spent, cost_currency, spent_cost, '
        'short_term, ex_rate, proceeds, profit')
try:
    PaymentReport.__doc__ += (
        "\nThis is a container for a couple of values that are gathered "
        "at every payment, which will be needed for creating a capital "
        "gains report.")
except AttributeError:
    # Older versions do not allow setting the docstring
    pass


def _json_encode_default(obj):
    if isinstance(obj, Decimal):
        return {'type(Decimal)': str(obj)}
    elif isinstance(obj, datetime):
        return {'type(datetime)': str(obj)}
    else:
        raise TypeError(repr(obj) + " is not JSON serializable")

def _json_decode_hook(obj):
    if 'type(Decimal)' in obj:
        return Decimal(obj['type(Decimal)'])
    elif 'type(datetime)' in obj:
        return pd.Timestamp(obj['type(datetime)'])
    return obj


class CapitalGainsReport(object):
    """This class facilitates the collecting of data like price,
    proceeds, profit etc. that accrue when processing payments,
    sales etc. with foreign or digital currencies. Afterwards, provided
    methods for creating reports from the gathered data can be used.
    Capital gains reports created from the gathered data can then be
    exported to csv, markdown, html, pdf etc., using the provided
    methods.

    """
    # TODO: Implement translation support (i18n)
    # add plotting & statistical functions
    def __init__(self, data=[]):
        """Create a CaptialGainsReport object.

        Then, with every processed payment, you should add data
        with `add_payment`.

        :param data: list of PaymentReport objects or list of
            lists/tuples with entries corresponding to
            PaymentReport._fields, default: empty list;
            The internal report data will be initialized with the
            payment reports in the list.

        """
        self.data = [PaymentReport._make(d) for d in data]

    def to_json(self, **kwargs):
        """Convert the collected data to a JSON formatted string.

        :param kwargs:
            Keyword arguments that will be forwarded to `json.dumps`.

        :returns: JSON formatted string

        """
        return json.dumps(
            self.__dict__,
            default=_json_encode_default, **kwargs)

    def add_payment(self, payment_report):
        """Add payment data.

        :param payment_report: PaymentReport object;
            Contains the data to be collected from a processed payment.

        """
        if not isinstance(payment_report, PaymentReport):
            raise ValueError(
                "Only PaymentReport objects may be added.")
        self.data.append(payment_report)

    def get_report_data(self, year=None, date_precision='D', combine=True,
            harmonize_timezone=True, strip_timezone=True, extended=False):
        """Return a pandas.DataFrame listing the capital gains made
        with the processed trades.

        :param year: None or 4-digit integer, default: None;
            Leave `None` to return all sales or select a specific
            year to return.
        :param date_precision: one of 'D', 'H' or 'T' for dayly, hourly
            or minutely, respectively (may also be multiplied, e.g.:
            '5T' for 5-minutely), default: 'D';
            Floors all datetimes to the specified frequency.
            Does nothing if date_precision is False.
        :param combine: boolean, default True;
            Combines consecutive transactions which only differ in
            the amounts 'to_pay', 'bag_amount', 'bag_spent',
            'spent_cost', 'proceeds' and 'profit'. Such transactions
            will be combined by summing up the values in these columns.
            This is only useful if *date_precision* is set, since
            otherwise consecutive dates will very seldomly match.
            Therefore, does nothing if *date_precision* is False.
        :param harmonize_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates (i.e. purchase_date and sell_date entries) will
            be harmonized to this timezone, if it is not False. The
            default value, True, will lead to a harmonization to the
            locale timezone according to the system's locale setting.
            Otherwise, specify a parameter that will be forwarded to
            pandas.Timestamp.tz_convert().
        :param strip_timezone: boolean, default True;
            After harmonization, the timezone info will be removed from
            all dates. Will not be done if *harmonize_timezone* is
            False.
        :param extended: boolean, default False:
            By default, the returned DataFrame contains the columns:
                ['type', 'amount', 'currency', 'purchase_date',
                'sell_date', 'exchange', 'short_term',
                'cost', 'proceeds', 'profit'].
            If *extended* is True, these columns will be returned:
                ['ptype', 'exchange', 'sell_date',
                'currency', 'to_pay','fee_ratio',
                'bag_date', 'bag_amount', 'bag_spent',
                'cost_currency', 'spent_cost', 'short_term',
                'ex_rate', 'proceeds', 'profit']
            Note the renaming of columns in the small dataset:
                'ptype'->'type', 'bag_spent'->'amount',
                'bag_date'->'purchase_date' and 'spent_cost'->'cost'.
        :returns: A pandas.DataFrame with the requested data.

        """
        if extended:
            df = pd.DataFrame(self.data)
        else:
            df = pd.DataFrame(
                (pr._asdict() for pr in self.data),
                columns=[
                    'ptype', 'bag_spent', 'currency', 'bag_date',
                    'sell_date', 'exchange', 'short_term', 'spent_cost',
                    'proceeds', 'profit'])


        # Harmonize dates and reduce precision:
        if not date_precision:
            freq = 'S'
            combine = False
        else:
            freq = date_precision
        if harmonize_timezone is True:
            harmonize_timezone = tz.tzlocal()
        if harmonize_timezone:
            if strip_timezone:
                appfun = (
                    lambda dt:
                        dt.tz_convert(
                            harmonize_timezone).tz_localize(None).floor(freq))
            else:
                appfun = (lambda dt:
                    dt.tz_convert(harmonize_timezone).floor(freq))
        else:
            appfun = lambda dt: dt.floor(freq)
        if appfun is not None:
            df.loc[:, 'bag_date'] = df.loc[:, 'bag_date'].apply(
                    appfun)
            df.loc[:, 'sell_date'] = df.loc[:, 'sell_date'].apply(appfun)

        # Select year:
        if year is not None:
            df = df[  (df['sell_date'] >= str(year))
                    & (df['sell_date'] < str(year + 1))]

        # Combine entries:
        if df.size and combine and date_precision:
            cols = df.columns
            # Group by all non-numeric columns, sum numeric columns:
            # (except 'fee_ratio' and 'ex_rate')
            groupbycols = []
            for i, col in enumerate(df.columns):
                # Assuming all entries in a column are the same type:
                if (not isinstance(df.iat[0, i], Decimal)
                    or col in ['fee_ratio', 'ex_rate']):
                        groupbycols.append(col)
            df = df.groupby(groupbycols, as_index=False, sort=False).sum()
            # Revert column order:
            df = df.reindex_axis(cols, axis=1)

        # rename some columns, so the small dataset makes more sense:
        if not extended:
            df.columns = pd.Index(
                ['type', 'amount', 'currency', 'purchase_date',
                 'sell_date', 'exchange', 'short_term',
                 'cost', 'proceeds', 'profit'])

        return df

    def save_report_to_csv(
            self, path_or_buf=None, year=None, date_precision='D',
            combine=True, harmonize_timezone=True, strip_timezone=True,
            convert_short_term=['no', 'yes'], **kwargs):
        """Write the capital gains table to a csv file.

        The csv table will contain the columns:
        'type', 'amount', 'currency', 'purchase_date', 'sell_date',
        'exchange', 'short_term', 'cost', 'proceeds' and 'profit'.

        :param path_or_buf: string or file handle, default None
            File path or object, if None is provided the result
            is returned as a string.
        :param year: None or 4-digit integer, default: None;
            Leave `None` to export all sales or select a specific
            year to export.
        :param date_precision: one of 'D', 'H' or 'T' for dayly, hourly
            or minutely, respectively (may also be multiplied, e.g.:
            '5T' for 5-minutely), default: 'D';
            Floors all datetimes to the specified frequency.
            Does nothing if date_precision is False.
        :param combine: boolean, default True;
            Combines consecutive transactions which only differ in
            the 'amount', 'cost', 'proceeds' and 'profit'. Such
            transactions will be combined by summing up the values
            in these columns. This is only useful if *date_precision*
            is set, since otherwise consecutive dates will very
            seldomly match. Therefore, does nothing if
            *date_precision* is False.
        :param harmonize_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates (i.e. purchase_date and sell_date entries) will
            be harmonized to this timezone, if it is not False. The
            default value, True, will lead to a harmonization to the
            locale timezone according to the system's locale setting.
            Otherwise, specify a parameter that will be forwarded to
            pandas.Timestamp.tz_convert().
        :param strip_timezone: boolean, default True;
            After harmonization, the timezone info will be removed from
            all dates. Will not be done if *harmonize_timezone* is
            False.

        """
        df = self.get_report_data(
                year=year,
                date_precision=date_precision,
                combine=combine,
                harmonize_timezone=harmonize_timezone,
                strip_timezone=strip_timezone,
                extended=False)

        if df.size == 0:
            log.warning(
                "Capital gains report could not be saved. "
                "There is no data%s." % (
                    ' for year %i' % year if year else ''))
            return

        # convert Decimal numbers to float, so it will be properly
        # formatted in to_csv:
        df = df.astype(
            {'amount': float, 'cost': float, 'proceeds': float,
             'profit': float})

        # convert short term:
        if convert_short_term is not None:
            df.loc[:, 'short_term'] = df.loc[:, 'short_term'].apply(
                    lambda b: convert_short_term[b])

        result = df.to_csv(
            path_or_buf,
            float_format='%.8f',
            index=False,
            **kwargs)

        if path_or_buf is None:
            return result

        log.info("Saved capital gains report %sto %s",
                 'for year %i ' % year if year else '',
                 str(path_or_buf))
