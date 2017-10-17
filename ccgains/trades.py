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

import logging
log = logging.getLogger(__name__)

###########################################################
###  Locations of Trade's parameters in exported CSVs:  ###
###########################################################
# Each entry denotes the column number where the parameter is to be
# found in the csv. If the value is not in the csv, use -1 to use an
# empty value, a string for a constant value to fill the parameter with
# or a function of one parameter (will be called for each row with a
# list of the splitted strings in the row as parameter).
#
# For reference, the list of parameters accepted by Trade:
# ["ttype", "dtime", "buy_currency", "buy_amount", "sell_currency",
# "sell_amount", "fee_currency", "fee_amount",
# "exchange", "mark", "comment"]
# (Note that buy and sell values may be given in reverse order if one
# of them is negative)

# Trade parameters in csv from Poloniex.com:
TPLOC_POLONIEX_TRADES = {
    'ttype': 2, 'dtime': 0,
    'buy_currency': lambda cols: cols[1].split('/')[0],
    'buy_amount': 10,
    'sell_currency': lambda cols: cols[1].split('/')[1],
    'sell_amount': 9,
    'fee_currency': lambda cols: cols[1].split('/')[cols[3]=='Sell'],
    'fee_amount': lambda cols:
        Decimal(cols[[5, 6][cols[3]=='Sell']])
        - Decimal(cols[[10, 9][cols[3]=='Sell']]),
    'exchange': 'Poloniex', 'mark': 3, 'comment': -1}
# 'comment' is the wallet address withdrawn to:
TPLOC_POLONIEX_WITHDRAWALS = [
    "Withdrawal", 0, '', '0', 1, 2, -1, -1, "Poloniex", -1, 3]
# 'comment' is the wallet address deposited to:
TPLOC_POLONIEX_DEPOSITS = [
    "Deposit", 0, 1, 2, '', '0', -1, -1, "Poloniex", -1, 3]

# Trade parameters in csv from Bitcoin.de:
TPLOC_BITCOINDE = {
    'ttype': 1, 'dtime': 0,
    'buy_currency': 'BTC', 'buy_amount': 9,
    'sell_currency': 'EUR', 'sell_amount': 8,
    'fee_currency': 'BTC',
    'fee_amount': lambda cols:
        (Decimal(cols[5]) - Decimal(cols[7])) / 2 if cols[5] else 0,
    'exchange': 'Bitcoin.de', 'mark': -1, 'comment': 3}

# Trade parameters in csv from bisq or Bitsquare:
# 'comment' is the trade ID:
TPLOC_BISQ_TRADES = [
        5, 1, lambda cols: cols[2].split(' ')[1],
        lambda cols: cols[2].split(' ')[0],
        lambda cols: cols[4].split(' ')[1],
        lambda cols: cols[4].split(' ')[0],
        -1, -1, 'Bitsquare/Bisq', '', 0]
TPLOC_BISQ_TRANSACTIONS = [
        1, 0, 'BTC', 4, '', '0', -1, -1, "Bitsquare/Bisq", '', 2]


def _parse_trades(str_list, param_dict, default_timezone):
    """Parse list of strings *str_list* into a Trade object according
    to *param_locs*.

    :param param_dict (dict):
        Locations of Trade's parameters in str_list.
        Each value denotes the index where a `Trade`-parameter is
        to be found in str_list, the keys are the parameter names.
        If the parameter value is not in str_list, use -1 for an empty
        value, a string for a constant value to fill the parameter with,
        or a function of one parameter (which will accept str_list as
        parameter).
        Note that buy and sell values may be given in reverse order
        if one of them is negative.

    :param default_timezone (tzinfo subclass):
        This parameter is ignored if there is timezone data in the
        datetime string inside str_list. Otherwise the time data will
        be interpreted as time given in *default_timezone*.

    :return: Trade object

    """
    pdict = {}
    for key, val in param_dict.items():
        if isinstance(val, int):
            if val == -1:
                pdict[key] = ''
            else:
                pdict[key] = str_list[val].strip('" \n\t')
        elif callable(val):
            pdict[key] = val(str_list)
        else:
            pdict[key] = val

    # parse datetime:
    try:
        dt = dateparse(pdict['dtime'])
    except ValueError:
        raise ValueError(
            "Could not parse datetime. Is the correct column "
            "specified in `param_locs`?")
    # add timezone if not in string:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_timezone)
    pdict['dtime'] = dt

    return Trade(**pdict)


class Trade(object):

    def __init__(
            self, ttype, dtime, buy_currency, buy_amount,
            sell_currency, sell_amount, fee_currency='', fee_amount=0,
            exchange='', mark='', comment=''):
        """Create a Trade object.

        All parameters may be strings, the numerical values will be
        converted to decimal.Decimal values, *dtime* to a datetime.

        :param ttype: a string denoting the type of transaction, which
            may be e.g. "trade", "withdrawal", "deposit". Not currently
            used, so it can be any comment.

        :param dtime: a string or datetime object:
            The date and time of the transaction.

        :param buy_amount:
            The amount of *buy_currency* bought. This value excludes any
            transaction fees, i.e. it is the amount that is fully
            available after the transaction.

        :param sell_amount:
            The amount of *sell_currency* sold. This value includes fees
            that may have been paid for the transaction, i.e. it is the
            total amount that left the account for the transaction.

        *buy_amount* and *sell_amount* may be given in any order if
        exactly one of the two values is negative, which will then be
        identified as the sell amount. In that case, *buy_currency* and
        *sell_currency* will be swapped accordingly, so the currency
        will always stay with the amount. It's an error if both values
        are negative.

        :param fee_amount:
            The fees paid, given in *fee_currency*. May have any sign,
            the absolute value will be taken as fee amount regardless.
        """
        self.typ = ttype
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
        if self.sellval < 0 and self.buyval < 0:
            raise ValueError(
                    'Ambiguity: Only one of buy_amount or '
                    'sell_amount may be negative')
        elif self.buyval < 0:
            self.buyval, self.sellval = self.sellval, abs(self.buyval)
            self.buycur, self.sellcur = self.sellcur, self.buycur
        else:
            self.sellval = abs(self.sellval)

        if not fee_amount:
            self.feeval = Decimal()
            if fee_currency != self.sellcur and self.buycur:
                self.feecur = self.buycur
            else:
                self.feecur = self.sellcur
        else:
            self.feeval = abs(Decimal(fee_amount))
            self.feecur = fee_currency
        self.exchange = exchange
        self.mark = mark
        self.comment = comment
        # save the time as datetime object:
        if isinstance(dtime, datetime):
            self.dtime = dtime
        elif isinstance(dtime, (float, int)):
            self.dtime = datetime.utcfromtimestamp(dtime).replace(
                    tzinfo=tz.tzutc())
        else:
            self.dtime = dateparse(dtime)

        if (self.feeval > 0
                and self.feecur != buy_currency
                and self.feecur != sell_currency):
            raise ValueError(
                    'fee_currency must match either buy_currency or '
                    'sell_currency')

    def to_csv_line(self, delimiter=', ', endl='\n'):
        strings = []
        for i, val in enumerate([
                self.typ, self.dtime,
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

    def __str__(self):
        s = ("%(typ)s on %(dtime)s: Acquired %(buyval).8f %(buycur)s, "
             "disposed of %(sellval).8f %(sellcur)s "
             "for a fee of %(feeval).8f %(feecur)s") % self.__dict__
        if self.exchange:
            s += " on %(exchange)s" % self.__dict__
        if self.mark:
            s += " (%(mark)s)" % self.__dict__
        if self.comment:
            s += " [%(comment)s]" % self.__dict__
        return s

    def __eq__(self, other):
        return self.__dict__ == other.__dict__


class TradeHistory(object):
    """The TradeHistory class is a container for a sorted list of
    `Trade` objects, but most importantly it provides methods for
    importing transactions exported from various exchanges, programs
    and web applications.

    """
    def __init__(self):
        """Create a TradeHistory object."""
        self.tlist = []

    def __getitem__(self, item):
        return self.tlist[item]

    def add_missing_transaction_fees(self, raise_on_error=True):
        """Some exchanges does not include withdrawal fees in their
        exported csv files. This will try to add these missing fees
        by comparing withdrawn amounts with amounts deposited on other
        exchanges shortly after withdrawal. Call this only after all
        transactions from every involved exchange and wallet were
        imported.

        This uses a really simple algorithm, so it is not guaranteed to
        work in every case. Basically, it finds the first deposit
        following each withdrawal and compares the withdrawn amount
        with the deposited amount. The difference (withdrawn - deposited)
        is then assigned as the fee for the withdrawal, if this fee
        is greater than zero. This will not work if there are
        withdrawals in tight succession whose deposits register in a
        different order than the withdrawals.

        If *raise_on_error* is True (which is the default), a Valueerror
        will be raised if a pair is found that cannot possibly match
        (higher deposit than withdrawal), otherwise only a warning
        is logged and the withdrawal ignored while the deposit is
        matched to the next withdrawal.

        """
        # Filter out all deposits and withdrawals from self.tlist.
        # Make a list of tuples:
        #   (tlist index,
        #    'w' or 'd' for 'withdrawal' OR 'deposit', respectively,
        #    withdrawal amount - fees OR deposit amount, respectively):
        translist = []
        for i, t in enumerate(self.tlist):
            if t.buyval == 0 and t.sellval > 0:
                # This should be a withdrawal
                if t.feeval and t.sellcur != t.feecur:
                    raise ValueError(
                        'In trade %i, encountered withdrawal with different '
                        'fee currency than withdrawn currency.')
                translist.append((i, 'w', t.sellval - t.feeval))
            elif t.sellval == 0 and t.buyval > 0:
                # This should be a deposit
                translist.append((i, 'd', t.buyval))
        unhandled_withdrawals = []
        num_unmatched = 0
        num_feeless = 0
        for i, typ, amount in translist:
            if typ == 'w':
                unhandled_withdrawals.append((i, amount))
                num_unmatched += 1
                num_feeless += self[i].feeval == 0
            else:
                # deposit
                while len(unhandled_withdrawals) > 0:
                    j, wamount = unhandled_withdrawals[0]
                    if wamount < amount:
                        errs = (
                            "The withdrawal from %s (%.8f %s) is lower than "
                            "the first deposit (%s, %.8f %s) following it" % (
                                self[i].dtime, amount, self[i].buycur,
                                self[j].dtime, wamount, self[j].sellcur))
                        if raise_on_error:
                            raise ValueError(errs)
                        else:
                            log.warning(errs + " Ignoring this withdrawal, "
                                        "trying next one.")
                        del unhandled_withdrawals[0]
                    else:
                        # found a match
                        num_unmatched -= 1
                        num_feeless -= self[j].feeval == 0
                        self.tlist[j].feeval += wamount - amount
                        log.info('amended withdrawal: %s', self[j])
                        del unhandled_withdrawals[0]
                        break
        if len(unhandled_withdrawals) > 0:
            log.warning(
                '%i withdrawals could not be matched with deposits, of which '
                '%i have no assigned withdrawal fees.' % (
                        num_unmatched, num_feeless))

    def append_csv(
            self, file_name, param_locs=range(11), delimiter=',', skiprows=1,
            default_timezone=None):
        """Import trades from a csv file and add them to this
        TradeHistory.

        Afterwards, all trades will be sorted by date and time.

        :param param_locs: (list or dict):
            Locations of Trade's parameters in csv-file.
            Each entry denotes the column number where a `Trade`-parameter
            can be found in the csv (Columns are counted starting with 0).
            If the value is not in the csv, use -1 to use an empty value,
            a string for a constant value to fill the parameter with,
            or a function of one parameter (which will be called for
            each row with a list of the splitted strings in the row as
            parameter).
            Note that buy and sell values may be given in reverse order
            if one of them is negative.

        :param default_timezone:
            This parameter is ignored if there is timezone data in the
            csv string. Otherwise, if None (default) the time data in
            the csv will be interpreted as time in the local timezone
            according to the locale setting; or it must be a tzinfo
            subclass (from dateutil.tz or pytz)

        """
        with open(file_name) as f:
            csvlines = f.readlines()
        # make a dict:
        if not isinstance(param_locs, dict):
            varnames = Trade.__init__.__code__.co_varnames[1:]
            param_locs = dict(
                    (varnames[i], p) for i, p in enumerate(param_locs))
        if default_timezone is None:
            default_timezone = tz.tzlocal()

        numtrades = len(self.tlist)

        # convert input lines to Trades:
        for csvline in csvlines[skiprows:]:
            line = csvline.split(delimiter)
            self.tlist.append(
                _parse_trades(line, param_locs, default_timezone))

        log.info("Loaded %i transactions from %s",
                 len(self.tlist) - numtrades, file_name)
        # trades must be sorted:
        self.tlist.sort(key=attrgetter('dtime'), reverse=False)

    def append_poloniex_csv(
            self, file_name, which_data='trades',
            delimiter=',', skiprows=1, default_timezone=tz.tzutc()):
        """Import trades from a csv file exported from Poloniex.com and
        add them to this TradeHistory.

        Afterwards, all trades will be sorted by date and time.

        :param which_data (string):
            Must be one of "trades", "withdrawals" or "deposits".
            Poloniex only allows exporting the tree categories
            'trading history', 'withdrawal history' and 'deposit history'
            in separate csv files. Specify which type is loaded here.
            Default is 'trades'.
        :param default_timezone:
            This parameter is ignored if there is timezone data in the
            csv string. Otherwise, if None, the time data in the csv
            will be interpreted as time in the local timezone
            according to the locale setting; or it must be a tzinfo
            subclass (from dateutil.tz or pytz);
            The default is UTC time, which is what Poloniex exports
            at time of writing, but it might change in future.

        """
        wdata = which_data[:5].lower()
        if wdata not in ['trade', 'withd', 'depos']:
            raise ValueError(
                    '`which_data` must be one of "trades", '
                    '"widthdrawals" or "deposits".')
        if wdata =='withd':
            plocs = TPLOC_POLONIEX_WITHDRAWALS
            log.warning(
                'Poloniex does not include withdrawal fees in exported '
                'csv-files. Please include the fees manually, or call '
                '`add_missing_transaction_fees` after transactions from all '
                'relevant exchanges were imported.')
        elif wdata == 'depos':
            plocs = TPLOC_POLONIEX_DEPOSITS
        else:
            plocs = TPLOC_POLONIEX_TRADES
        return self.append_csv(
                file_name=file_name,
                param_locs=plocs,
                delimiter=delimiter,
                default_timezone=default_timezone)

    def append_bisq_csv(
            self, trade_file_name, transactions_file_name,
            delimiter=',', skiprows=1, default_timezone=None):
        """Import trades from the csv files exported from Bisq (former
        Bitsquare) and add them to this TradeHistory.

        Afterwards, all trades will be sorted by date and time.

        From the Bisq program, two kinds of csv files can be exported:
        One with the trading history and one with the transaction
        history. Because of how Bisq works, these two histories are
        intertwined and in order to properly connect the fees to
        trades, both files must be imported together.

        :param trade_file_name:
            The csv file name with the trading history
        :param transaction_file_name:
            The csv file name with the transaction history
        :param default_timezone:
            This parameter is ignored if there is timezone data in the
            csv string. Otherwise, if None, the time data in the csv
            will be interpreted as time in the local timezone
            according to the locale setting; or it must be a tzinfo
            subclass (from dateutil.tz or pytz);
            The default is None, i.e. the local timezone,
            which is what Bitsquare exports at time of writing, but it
            might change in future.

        """
        if default_timezone is None:
            default_timezone = tz.tzlocal()

        with open(trade_file_name) as f:
            tradelines = f.readlines()
        with open(transactions_file_name) as f:
            txlines = f.readlines()

        # make sure param_locs are dicts:
        tdp = TPLOC_BISQ_TRADES
        txp = TPLOC_BISQ_TRANSACTIONS
        varnames = Trade.__init__.__code__.co_varnames[1:]
        if not isinstance(tdp, dict):
            tdp = dict((varnames[i], p) for i, p in enumerate(tdp))
        if not isinstance(txp, dict):
            txp = dict((varnames[i], p) for i, p in enumerate(txp))

        # convert input lines to Trades:
        tdl = []
        txl = []
        for csvline in tradelines[skiprows:]:
            line = csvline.split(delimiter)
            tdl.append(_parse_trades(line, tdp, default_timezone))
        for csvline in txlines[skiprows:]:
            line = csvline.split(delimiter)
            txl.append(_parse_trades(line, txp, default_timezone))
        tdl.sort(key=attrgetter('dtime'), reverse=False)
        txl.sort(key=attrgetter('dtime'), reverse=False)

        # For each trade from tdl, pop the accompanying data from
        # transactions list txl:
        txlpos = 0
        for trade in tdl:
            found = []
            # the trade id:
            tid = trade.comment
            # find matching transactions, which will have tid in ttype:
            while txlpos < len(txl):
                tx = txl[txlpos]
                if tid in tx.typ:
                    found.append(txl.pop(txlpos))
                else:
                    txlpos += 1
            # Use the data in `found` to add fee to trade:
            trade.feeval += trade.buyval - reduce(
                    lambda sm, tx: sm + tx.buyval - tx.sellval,
                    found, Decimal())
            # The transactions in `found` can now be discarded

        # TODO: Also filter some transactions, which might be due to
        # failed transactions, or fees for created offers that were
        # never taken. Those fees are not tax deductable, so they must
        # be marked with ttype 'Loss'; and then we'd also need to
        # introduce proper handling of losses in bags.BagFIFO...

        # Add both lists to self.tlist:
        numtrades = len(self.tlist)
        self.tlist.extend(tdl)
        self.tlist.extend(txl)
        log.warning(
                'Bitsquare/Bisq does not include withdrawal fees in exported '
                'csv-files. Please include the fees manually, or call '
                '`add_missing_transaction_fees` after transactions from all '
                'relevant exchanges were imported.')
        log.info("Loaded %i transactions from %s and %s",
                 len(self.tlist) - numtrades,
                 trade_file_name, transactions_file_name)
        # trades must be sorted:
        self.tlist.sort(key=attrgetter('dtime'), reverse=False)

    # alias:
    append_bitsquare_csv = append_bisq_csv

    def append_bitcoin_de_csv(
            self, file_name,
            delimiter=';', skiprows=1, default_timezone=None):
        """Import trades from a csv file exported from Bitcoin.de
        and add them to this TradeHistory.

        Afterwards, all trades will be sorted by date and time.

        :param default_timezone:
            This parameter is ignored if there is timezone data in the
            csv string. Otherwise, if None, the time data in the csv
            will be interpreted as time in the local timezone
            according to the locale setting; or it must be a tzinfo
            subclass (from dateutil.tz or pytz);
            The default is None, i.e. the local timezone,
            which is what Bitcoin.de exports at time of writing, but
            it might change in future.

        """
        with open(file_name) as f:
            csvlines = f.readlines()
        # make sure param locs is a dict:
        param_locs = TPLOC_BITCOINDE
        if not isinstance(param_locs, dict):
            varnames = Trade.__init__.__code__.co_varnames[1:]
            param_locs = dict(
                    (varnames[i], p) for i, p in enumerate(param_locs))
        if default_timezone is None:
            default_timezone = tz.tzlocal()

        tlist = []

        # convert input lines to Trades:
        for csvline in csvlines[skiprows:]:
            line = csvline.split(delimiter)
            tlist.append(
                _parse_trades(line, param_locs, default_timezone))

        # The fees connected to disbursements are given on
        # an extra line; merge them:
        i = 0
        while i < len(tlist):
            if (tlist[i].typ == 'Network fee'
                    and tlist[i - 1].comment == tlist[i].comment):
                tlist[i - 1].sellval += tlist[i].sellval
                tlist[i - 1].feeval += tlist[i].feeval

                del tlist[i]
            else:
                i += 1
        numtrades = len(self.tlist)
        self.tlist.extend(tlist)
        log.info("Loaded %i transactions from %s",
                 len(self.tlist) - numtrades, file_name)
        # trades must be sorted:
        self.tlist.sort(key=attrgetter('dtime'), reverse=False)

