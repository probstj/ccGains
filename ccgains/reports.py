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
import jinja2
import babel.numbers, babel.dates
import weasyprint

import logging
log = logging.getLogger(__name__)


PaymentReport = namedtuple(
        'PaymentReport',
        'kind, exchange, sell_date, currency, to_pay, fee_ratio, '
        'bag_date, bag_amount, bag_spent, cost_currency, spent_cost, '
        'short_term, ex_rate, proceeds, profit, '
        'buy_currency, buy_ratio')
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
            convert_timezone=True, strip_timezone=True, extended=False,
            custom_column_names=None):
        """Return a pandas.DataFrame listing the capital gains made
        with the processed trades.

        :param year: None or 4-digit integer, default: None;
            Leave `None` to return all sales or choose a specific
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
        :param convert_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates (i.e. purchase_date and sell_date entries) will
            be converted to this timezone. The default value, True,
            will lead to a conversion to the locale timezone according
            to the system's locale setting. False keeps all dates at
            UTC time. Otherwise, specify a parameter that will be
            forwarded to pandas.Timestamp.tz_convert().
        :param strip_timezone: boolean, default True;
            After conversion, the timezone info will be removed from
            all dates.
        :param extended: boolean, default False:
            By default, the returned DataFrame contains the columns:
                ['kind', 'bag_spent', 'currency', 'bag_date',
                 'sell_date', 'exchange', 'short_term',
                 'spent_cost', 'proceeds', 'profit'];
            If *extended* is True, these columns will be returned:
                ['kind', 'exchange', 'sell_date',
                'currency', 'to_pay','fee_ratio',
                'bag_date', 'bag_amount', 'bag_spent',
                'cost_currency', 'spent_cost', 'short_term',
                'ex_rate', 'proceeds', 'profit',
                'buy_currency, buy_ratio']
            Note the reordering of columns in the small dataset.
        :param custom_column_names: None or list of strings;
            If None (default), the column names will be as described
            above, depending on *extended*. To rename them, supply a
            list of proper length, either 10 if not *extended or 17
            otherwise.
        :returns: A pandas.DataFrame with the requested data.

        """
        if extended:
            df = pd.DataFrame(self.data)
        else:
            df = pd.DataFrame(
                (pr._asdict() for pr in self.data),
                columns=[
                    'kind', 'bag_spent', 'currency', 'bag_date',
                    'sell_date', 'exchange', 'short_term', 'spent_cost',
                    'proceeds', 'profit'])

        # Select year:
        if year is not None:
            df = df[  (df['sell_date'] >= str(year))
                    & (df['sell_date'] < str(year + 1))]

        # Convert timezones and reduce precision:
        if not date_precision:
            freq = 'S'
            combine = False
        else:
            freq = date_precision
        if not convert_timezone:
            convert_timezone = 'UTC'
        elif convert_timezone is True:
            convert_timezone = tz.tzlocal()
        if strip_timezone:
            appfun = (
                lambda dt:
                    dt.tz_convert(
                        convert_timezone).tz_localize(None).floor(freq))
        else:
            appfun = (lambda dt:
                dt.tz_convert(convert_timezone).floor(freq))
        df.loc[:, 'bag_date'] = df.loc[:, 'bag_date'].apply(
                appfun)
        df.loc[:, 'sell_date'] = df.loc[:, 'sell_date'].apply(appfun)

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

        # rename columns:
        if custom_column_names:
            df.columns = pd.Index(custom_column_names)

        return df

    def export_short_report_to_csv(
            self, path_or_buf=None, year=None, date_precision='D',
            combine=True, convert_timezone=True, strip_timezone=True,
            custom_column_names=None, **kwargs):
        """Write the capital gains table to a csv file.

        The csv table will contain the columns:
        'kind', 'amount', 'currency', 'purchase_date', 'sell_date',
        'exchange', 'short_term', 'cost', 'proceeds' and 'profit'.

        :param path_or_buf: string or file handle, default None
            File path or object, if None is provided the result
            is returned as a string.
        :param year: None or 4-digit integer, default: None;
            Leave `None` to export all sales or choose a specific
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
        :param convert_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates (i.e. purchase_date and sell_date entries) will
            be converted to this timezone. The default value, True,
            will lead to a conversion to the locale timezone according
            to the system's locale setting. False keeps all dates at
            UTC time. Otherwise, specify a parameter that will be
            forwarded to pandas.Timestamp.tz_convert().
        :param strip_timezone: boolean, default True;
            After conversion, the timezone info will be removed from
            all dates.
        :param custom_column_names: None or list of strings;
            If None (default), the column names will be:
            ['kind', 'amount', 'currency', 'purchase_date', 'sell_date',
            'exchange', 'short_term', 'cost', 'proceeds', 'profit'].
            To rename them, supply a list of length 10.

        """
        if custom_column_names is None:
            custom_column_names=[
                'kind', 'amount', 'currency', 'purchase_date',
                'sell_date', 'exchange', 'short_term',
                'cost', 'proceeds', 'profit']
        df = self.get_report_data(
                year=year,
                date_precision=date_precision,
                combine=combine,
                convert_timezone=convert_timezone,
                strip_timezone=strip_timezone,
                extended=False,
                custom_column_names=custom_column_names)

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

        result = df.to_csv(
            path_or_buf,
            float_format='%.8f',
            index=False,
            **kwargs)

        if path_or_buf is None:
            return result

        log.info("Exported capital gains report data %sto %s",
                 'for year %i ' % year if year else '',
                 str(path_or_buf))

    def get_report_html(
            self, year=None, date_precision='D', combine=True,
            convert_timezone=True, font_size=12,
            template_file='shortreport_en.html',
            custom_column_names=None, custom_formatters=None,
            locale=None, extended_data=False):
        """Return the capital gains report as HTML-formatted string.

        :param year: None or 4-digit integer, default: None;
            Leave `None` to export all sales or choose a specific
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
        :param convert_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates (i.e. purchase_date and sell_date entries) will
            be converted to this timezone. The default value, True,
            will lead to a conversion to the locale timezone according
            to the system's locale setting. False keeps all dates at
            UTC time. Otherwise, specify a parameter that will be
            forwarded to pandas.Timestamp.tz_convert().
        :param template_file: file name of html template inside package
            folder: `ccgains/templates`. Default: 'shortreport_en.html'
        :param custom_column_names: None or list of strings;
            If None (default), the column names of the DataFrame
            returned from `get_report_data(extended=extended_data)`
            will be used. To rename them, supply a list with same length
            than number of columns (depending on *extended_data*).
        :param custom_formatters: None or dict of one-parameter functions;
            If None (default), a set of default formatters for each
            column will be used, using babel.numbers and babel.dates.
            Individual formatting functions can be supplied with the
            (renamed) column names as keys. The result of each function
            must be a unicode string.
        :param locale: None or locale identifier, e.g. 'de_DE' or 'en_US';
            The locale used for formatting numeric and date values with
            babel. If None (default), the locale will be taken from the
            `LC_NUMERIC` or `LC_TIME` environment variables on your
            system, for numeric or date values, respectively.
        :param extended_data: Boolean, default: False;
            If the *template_file* makes use of some of the extended data
            returned from `get_report_data` when called with parameter
            `extended=True`, this must also be True. See documentation
            of `get_report_data` for extended data fields.
        :returns:
            HTML-formatted string

        """

        env = jinja2.Environment(
                loader=jinja2.PackageLoader('ccgains', 'templates'))

        df = self.get_report_data(
                year=year,
                date_precision=date_precision, combine=combine,
                convert_timezone=convert_timezone,
                # Don't strip timezone, will be handled by formatters:
                strip_timezone=False,
                extended=extended_data)

        total_profit = df['profit'].sum()
        # taxable profit is zero if long_term:
        df['profit'] = df['profit'].where(df['short_term'], 0)
        short_term_profit = df['profit'].sum()

        # use custom column names:
        if custom_column_names is not None:
            renamed = {k:v for k, v in zip(df.columns, custom_column_names)}
            df.columns = custom_column_names
        else:
            renamed = {k:k for k in df.columns}

        # Build formatters for all columns:
        # all entries should have same cost_currency, see bags.py:
        cost_currency = self.data[0].cost_currency
        price_formatter = lambda x: babel.numbers.format_currency(
            x, cost_currency, format=u'#,##0.00\xa0¤¤',
            locale=locale if locale else babel.numbers.LC_NUMERIC)

#        amount_formatter = lambda x: babel.numbers.format_decimal(
#            x, format=u'#,##0.00000000',
#            locale=locale if locale else babel.numbers.LC_NUMERIC)

        # The following is a hackish replacement for using
        # `lambda num: babel.numbers.format_decimal(num, u'#,##0.00000000')`
        # directly, which we cannot use, since `1E-8` is formatted as
        #`u'1.E-8,00000000'`. While this bug is being fixed in babel,
        # we use our own algorithm, copied from
        # `babel.numbers.NumberPattern.apply`, with a modification:
        fmt=u'#,##0.00000000'
        pattern = babel.numbers.parse_pattern(fmt)
        precision = Decimal('1.' + '1' * pattern.frac_prec[1])

        def my_format_decimal(num, locale):
            if not isinstance(num, Decimal):
                num = Decimal(str(num))
            is_negative = int(num.is_signed())
            rounded = num.quantize(precision)
            # this line contains the bugfix:
            a, sep, b = format(abs(rounded), 'f').partition(".")
            number = (
                pattern._format_int(
                    a, pattern.int_prec[0],
                    pattern.int_prec[1], locale)
                + pattern._format_frac(
                    b or '0', locale, pattern.frac_prec))
            return u'%s%s%s' % (
                pattern.prefix[is_negative], number,
                pattern.suffix[is_negative])

        amount_formatter = lambda x: my_format_decimal(
            x, locale=locale if locale else babel.numbers.LC_NUMERIC)


        date_offset = pd.tseries.frequencies.to_offset(date_precision)
        if date_offset.nanos < 86400000000000:
            # show date and time:
            date_formatter = lambda x: babel.dates.format_datetime(
                x, format='medium',
                locale=locale if locale else babel.dates.LC_TIME)
        else:
            # date offset a day or more; show only date:
            date_formatter = lambda x: babel.dates.format_date(
                x, format='medium',
                locale=locale if locale else babel.dates.LC_TIME)

        # default formatters:
        formatters={
            renamed['kind']: lambda x: x.capitalize(),
            renamed['bag_spent']: amount_formatter,
            renamed['currency']: None,
            renamed['bag_date']: date_formatter,
            renamed['sell_date']: date_formatter,
            renamed['exchange']: None,
            renamed['short_term']: lambda b: ['no', 'yes'][b],
            renamed['spent_cost']: price_formatter,
            renamed['proceeds']: price_formatter,
            renamed['profit']: price_formatter}
        # update with given formatters:
        if custom_formatters is not None:
            formatters.update(custom_formatters)

        # Add some formatters to Jinja environment, so they can be
        # used in the template:
        env.filters['format_currency'] = babel.numbers.format_currency
        env.filters['format_base_currency'] = price_formatter
        env.filters['format_percent'] = babel.numbers.format_percent
        env.filters['format_decimal'] = babel.numbers.format_decimal
        env.filters['format_amount'] = amount_formatter
        env.filters['format_date'] = babel.dates.format_date
        env.filters['format_datetime'] = babel.dates.format_datetime
        env.filters['format_adapted_date'] = date_formatter

        # start counting rows at 1:
        df.index = pd.RangeIndex(start=1, stop=len(df) + 1)

        if year is None:
            fromdate = df[renamed['sell_date']].iat[0]
            todate = df[renamed['sell_date']].iat[-1]
        else:
            fromdate = babel.dates.date(year=year, month=1, day=1)
            todate = babel.dates.date(year=year, month=12, day=31)

        template = env.get_template(template_file)

        # Rounding affects the babel.numbers.format_... formatters:
        # We'll floor everything:
        with babel.numbers.decimal.localcontext(
            babel.numbers.decimal.Context(
                rounding=babel.numbers.decimal.ROUND_DOWN)):
            html = template.render({
                'year'    :
                        year if year else '',
                'today'   :
                        babel.dates.format_date(
                            babel.dates.date.today(),
                            locale=locale if locale else babel.dates.LC_TIME),
                'fontsize':
                        font_size,
                "fromdate":
                        babel.dates.format_date(
                            fromdate,
                            locale=locale if locale else babel.dates.LC_TIME),
                "todate"  :
                        babel.dates.format_date(
                            todate,
                            locale=locale if locale else babel.dates.LC_TIME),
                "total_profit":
                        price_formatter(total_profit),
                "short_term_profit":
                        price_formatter(short_term_profit),
                "num_trades":
                        len(df),
                "sales_data":
                        df,
                "formatters":
                        formatters,
                "cgtable":
                        df.to_html(
                            index=True, bold_rows=False,
                            classes='align-right-columns',
                            formatters=formatters)})
        return html

    def export_report_to_pdf(
            self, file_name, year=None, date_precision='D',
            combine=True, convert_timezone=True,
            font_size=12, template_file='shortreport_en.html',
            custom_column_names=None, custom_formatters=None,
            locale=None):
        """Export the capital gains report to a pdf file.

        :param file_name: string;
            Destination file name.
        :param year: None or 4-digit integer, default: None;
            Leave `None` to export all sales or choose a specific
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
        :param convert_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates (i.e. purchase_date and sell_date entries) will
            be converted to this timezone. The default value, True,
            will lead to a conversion to the locale timezone according
            to the system's locale setting. False keeps all dates at
            UTC time. Otherwise, specify a parameter that will be
            forwarded to pandas.Timestamp.tz_convert().
        :param template_file: file name of html template inside package
            folder: `ccgains/templates`. Default: 'shortreport_en.html'
        :param custom_column_names: None or list of strings;
            If None (default), the column names of the DataFrame
            returned from `get_report_data(extended=False)` will be
            used. To rename them, supply a list of length 10.
        :param custom_formatters: None or dict of one-parameter functions;
            If None (default), a set of default formatters for each
            column will be used, using babel.numbers and babel.dates.
            Individual formatting functions can be supplied with the
            (renamed) column names as keys. The result of each function
            must be a unicode string.
        :param locale: None or locale identifier, e.g. 'de_DE' or 'en_US';
            The locale used for formatting numeric and date values with
            babel. If None (default), the locale will be taken from the
            `LC_NUMERIC` or `LC_TIME` environment variables on your
            system, for numeric or date values, respectively.

        """
        html = self.get_report_html(
                year=year,
                date_precision=date_precision, combine=combine,
                convert_timezone=convert_timezone,
                font_size=font_size, template_file=template_file,
                custom_column_names=custom_column_names,
                custom_formatters=custom_formatters,
                locale=locale)
        doc = weasyprint.HTML(string=html)
        doc.write_pdf(file_name)
        log.info("Saved short capital gains report %sto %s",
                 'for year %i ' % year if year else '',
                 str(file_name))

    def get_extended_report_html(
            self, year=None, date_precision='D', combine=True,
            convert_timezone=True, font_size=10,
            template_file='fullreport_de.html',
            payment_kind_translation=None,
            locale=None):
        """Return an extended capital gains report as HTML-formatted
        string.

        :param year: None or 4-digit integer, default: None;
            Leave `None` to export all sales or choose a specific
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
        :param convert_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates (i.e. purchase_date and sell_date entries) will
            be converted to this timezone. The default value, True,
            will lead to a conversion to the locale timezone according
            to the system's locale setting. False keeps all dates at
            UTC time. Otherwise, specify a parameter that will be
            forwarded to pandas.Timestamp.tz_convert().
        :param template_file: file name of html template inside package
            folder: `ccgains/templates`. Default: 'fullreport_de.html'
        :param payment_kind_translation: None (default) or dictionary;
            This allows for the payment kind (one out of
            ['sale', 'withdrawal fee', 'deposit fee', 'exchange fee'])
            to be translated (the dict keys must be the mentioned english
            strings, the values are the translations used in the output).
        :param locale: None or locale identifier, e.g. 'de_DE' or 'en_US';
            The locale used for formatting numeric and date values with
            babel. If None (default), the locale will be taken from the
            `LC_NUMERIC` or `LC_TIME` environment variables on your
            system, for numeric or date values, respectively.
        :returns:
            HTML-formatted string

        """
        if payment_kind_translation is not None:
            custom_formatter = {
                'kind': lambda x: payment_kind_translation[x]}
        else:
            custom_formatter = None
        return self.get_report_html(
                year=year,
                date_precision=date_precision,
                combine=combine,
                convert_timezone=convert_timezone,
                font_size=font_size,
                template_file=template_file,
                custom_column_names=None,
                custom_formatters=custom_formatter,
                locale=locale,
                extended_data=True)

    def export_extended_report_to_pdf(
            self, file_name, year=None, date_precision='D', combine=True,
            convert_timezone=True, font_size=10,
            template_file='fullreport_en.html',
            payment_kind_translation=None,
            locale=None):
        """Export the extended capital gains report to a pdf file.

        :param file_name: string;
            Destination file name.
        :param year: None or 4-digit integer, default: None;
            Leave `None` to export all sales or choose a specific
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
        :param convert_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates (i.e. purchase_date and sell_date entries) will
            be converted to this timezone. The default value, True,
            will lead to a conversion to the locale timezone according
            to the system's locale setting. False keeps all dates at
            UTC time. Otherwise, specify a parameter that will be
            forwarded to pandas.Timestamp.tz_convert().
        :param template_file: file name of html template inside package
            folder: `ccgains/templates`. Default: 'fullreport_de.html'
        :param payment_kind_translation: None (default) or dictionary;
            This allows for the payment kind (one out of
            ['sale', 'withdrawal fee', 'deposit fee', 'exchange fee'])
            to be translated (the dict keys must be the mentioned english
            strings, the values are the translations used in the output).
        :param locale: None or locale identifier, e.g. 'de_DE' or 'en_US';
            The locale used for formatting numeric and date values with
            babel. If None (default), the locale will be taken from the
            `LC_NUMERIC` or `LC_TIME` environment variables on your
            system, for numeric or date values, respectively.

        """
        html = self.get_extended_report_html(
                year=year,
                date_precision=date_precision, combine=combine,
                convert_timezone=convert_timezone,
                font_size=font_size, template_file=template_file,
                payment_kind_translation=payment_kind_translation,
                locale=locale)
        doc = weasyprint.HTML(string=html)
        doc.write_pdf(file_name)
        log.info("Saved detailed capital gains report %sto %s",
                 'for year %i ' % year if year else '',
                 str(file_name))

