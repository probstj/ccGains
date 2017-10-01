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
from datetime import datetime
from dateutil import tz
from dateutil.parser import parse as dateparse
from operator import attrgetter


class Trade(object):
    params_names_list = [
            "Typ", "Datum", "Kaufwährung", "Kauf",
            "Verkaufswährung", "Verkauf",
            "Gebührenwährung", "Gebühr",
            "Börse", "Merkmal", "Kommentar"]

    def __init__(
            self, ttype, time, buy_currency, buy_amount,
            sell_currency, sell_amount, fee_currency='', fee_amount=0,
            exchange='', mark='', comment=''):
        self.type = ttype
        if buy_amount:
            self.buyval = Decimal(buy_amount)
        else:
            self.buyval = Decimal()
        self.buycur = buy_currency
        if sell_amount:
            self.sellval = Decimal(sell_amount)
        else:
            self.sellval = Decimal()
        self.sellcur = sell_currency
        if not fee_amount:
            self.feeval = Decimal()
            if fee_currency != sell_currency:
                self.feecur = self.buycur
            else:
                self.feecur = self.sellcur
        else:
            self.feeval = Decimal(fee_amount)
            self.feecur = fee_currency
        self.exchange = exchange
        self.mark = mark
        self.comment = comment
        # save the time as datetime object:
        if isinstance(time, datetime):
            self.time = time
        elif isinstance(time, (float, int)):
            self.time = datetime.utcfromtimestamp(time).replace(
                    tzinfo=tz.tzutc())
        else:
            self.time = dateparse(time)

        if self.feecur != buy_currency and self.feecur != sell_currency:
            raise ValueError(
                    'fee_currency must match either buy_currency or '
                    'sell_currency')

    def to_csv_line(self, delimiter=', ', endl='\n'):
        strings = []
        for i, val in enumerate([
                self.type, self.time,
                self.buycur, self.buyval,
                self.sellcur, self.sellval,
                self.feecur, self.feeval,
                self.exchange, self.mark,
                self.comment]):
            if isinstance(val, Decimal):
                strings.append("{0:0.8f}".format(float(val)))
            else:
                strings.append(str(val))
        return delimiter.join(strings) + endl


class TradeHistory(object):
    def __init__(self):
        self.tlist = []

    @classmethod
    def from_csv(
            cls, file_name, param_loc_in_csv=range(11), delimiter=',',
            default_timezone=None):
        """
        param: param_loc_in_csv:
            Tells in which columns the params for the Trade class are found,
            i.e. `param_loc_in_csv[1]` is the csv's column where the date
            is to be found. Columns are counted starting with 0.
        param: default_timezone:
            This parameter is ignored if there is timezone data in the
            csv string. Otherwise, if None (default) the time data in
            the csv will be interpreted as time in the local timezone
            according to the locale setting; or it must be a tzinfo
            subclass (from dateutil.tz or pytz)

        """
        th = cls()
        with open(file_name) as f:
            csvlines = f.readlines()
        header = csvlines[0]
        expectedheader = ['""'] * len(header.split(delimiter))
        for i, p in enumerate(param_loc_in_csv):
            if p != -1:
                expectedheader[p] = Trade.params_names_list[i]
        expectedheader = ', '.join(expectedheader)
        print(
            'Please check whether the supplied `param_loc_in_csv` is '
            'correct:\n'
            'The csv file''s header: "%s"\n'
            'should match: "%s"' %(header, expectedheader))

        # convert input lines to Trades:
        for csvline in csvlines[1:]:
            line = csvline.split(delimiter)
            vals = [line[p].strip('" \n') if p != -1 else ''
                    for p in param_loc_in_csv]
            # parse datetime:
            if vals[1]:
                vals[1] = dateparse(vals[1])
                # add timezone if not in csv string:
                if vals[1].tzinfo is None:
                    if default_timezone is None:
                        default_timezone = tz.tzlocal()
                    vals[1] = vals[1].replace(tzinfo=default_timezone)
            th.tlist.append(Trade(*vals))
        print 'input:', len(th.tlist), 'trades'
        # trades must be sorted:
        th.tlist.sort(key=attrgetter('time'), reverse=False)

        return th
