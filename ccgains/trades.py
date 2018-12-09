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

import pandas as pd
from decimal import Decimal
from dateutil import tz
#from operator import attrgetter

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
# ["kind", "dtime", "buy_currency", "buy_amount", "sell_currency",
# "sell_amount", "fee_currency", "fee_amount",
# "exchange", "mark", "comment"]
# (Note that buy and sell values may be swapped if one
# of them is negative)

# Trade parameters in csv from Poloniex.com:
# ('comment' is the Poloniex order number)
TPLOC_POLONIEX_TRADES = {
    'kind': 2, 'dtime': 0,
    'buy_currency': lambda cols: cols[1].split('/')[0],
    'buy_amount': 10,
    'sell_currency': lambda cols: cols[1].split('/')[1],
    'sell_amount': 9,
    'fee_currency': lambda cols: cols[1].split('/')[cols[3]=='Sell'],
    'fee_amount': lambda cols:
        Decimal(cols[[5, 6][cols[3]=='Sell']])
        - Decimal(cols[[10, 9][cols[3]=='Sell']]),
    'exchange': 'Poloniex', 'mark': 3, 'comment': 8}
# 'comment' is the wallet address withdrawn to:
TPLOC_POLONIEX_WITHDRAWALS = [
    "Withdrawal", 0, '', '0', 1, 2, -1, -1, "Poloniex", -1, 3]
# 'comment' is the wallet address deposited to:
TPLOC_POLONIEX_DEPOSITS = [
    "Deposit", 0, 1, 2, '', '0', -1, -1, "Poloniex", -1, 3]

# Trade parameters in csv from Bitcoin.de:
TPLOC_BITCOINDE = {
    'kind': 1, 'dtime': 0,
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

# Trade parameters in csv from Trezor wallet
# The currency is not present in the file, thus it has to be supplied by
# the user
TPLOC_TREZOR_WALLET = {
    'kind': lambda cols:
        'Deposit' if cols[4] == 'IN' else 'Withdrawal',
    'dtime': lambda cols:
        cols[0] + ' ' + cols[1],
    'buy_currency': '',
    'buy_amount': lambda cols:
        abs(Decimal(cols[6])) if cols[4] == 'IN' else '',
    'sell_currency': '',
    'sell_amount': lambda cols:
        abs(Decimal(cols[6])) if cols[4] == 'OUT' else '',
    'fee_currency': '',
    'fee_amount': lambda cols:
        Decimal(cols[5]) + Decimal(cols[6]) if cols[4] == 'OUT' else '0',
    'exchange': 'Trezor', 'mark': 2, 'comment': 3}


def _parse_trade(str_list, param_locs, default_timezone):
    """Parse list of strings *str_list* into a Trade object according
    to *param_locs*.

    :param param_locs (dict or list):
        Locations of Trade's parameters in str_list.
        Each value denotes the index where a `Trade`-parameter is
        to be found in str_list, the keys are the parameter names.
        If param_locs is a list, the position in the list corresponds
        to the parameter position in Trade.__init__, ignoring `self`.

        If the parameter value is not in str_list, use -1 for an empty
        value, a string for a constant value to supply as parameter,
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
    # make a dict:
    if not isinstance(param_locs, dict):
        varnames = Trade.__init__.__code__.co_varnames[1:12]
        param_locs = dict(
            (varnames[i], p) for i, p in enumerate(param_locs))

    pdict = {}
    for key, val in param_locs.items():
        if isinstance(val, int):
            if val == -1:
                pdict[key] = ''
            else:
                pdict[key] = str_list[val].strip('" \n\t')
        elif callable(val):
            pdict[key] = val(str_list)
        else:
            pdict[key] = val

    return Trade(default_timezone=default_timezone, **pdict)


class Trade(object):
    """This class holds details about a single transaction, like a trade
    between two currencies or a withdrawal of a single currency.
    """

    def __init__(
            self, kind, dtime, buy_currency, buy_amount,
            sell_currency, sell_amount, fee_currency='', fee_amount=0,
            exchange='', mark='', comment='', default_timezone=None):
        """Create a Trade object.

        All parameters may be strings, the numerical values will be
        converted to decimal.Decimal values, *dtime* to a datetime.

        :param kind: a string denoting the kind of transaction, which
            may be e.g. "trade", "withdrawal", "deposit". Not currently
            used, so it can be any comment.

        :param dtime: a string, number or datetime object:
            The date and time of the transaction. A string will be
            parsed with pandas.Timestamp; a number will be interpreted
            as the elapsed seconds since the epoch (unix timestamp),
            in UTC timezone.

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

        :param default_timezone:
            This parameter is ignored if there is timezone data included
            in *dtime*, or if *dtime* is a number (unix timestamp), in
            which case the timezone will always be UTC. Otherwise, if
            default_timezone=None (default), the time data in *dtime*
            will be interpreted as time in the local timezone according
            to the locale setting; or it must be a tzinfo subclass
            (from dateutil.tz or pytz), which will be added to *dtime*.

        """
        self.kind = kind
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
        # save the time as pandas.Timestamp object:
        if isinstance(dtime, (float, int)):
            # unix timestamp
            self.dtime = pd.Timestamp(dtime, unit='s').tz_localize('UTC')
        else:
            self.dtime = pd.Timestamp(dtime)
        # add default timezone if not included:
        if self.dtime.tzinfo is None:
            self.dtime = self.dtime.tz_localize(
                tz.tzlocal() if default_timezone is None else default_timezone)
        # internally, dtime is saved as UTC time:
        self.dtime = self.dtime.tz_convert('UTC')

        if (self.feeval > 0
                and self.feecur != buy_currency
                and self.feecur != sell_currency):
            raise ValueError(
                    'fee_currency must match either buy_currency or '
                    'sell_currency')

    def to_csv_line(self, delimiter=', ', endl='\n'):
        strings = []
        for val in [
                self.kind, self.dtime,
                self.buycur, self.buyval,
                self.sellcur, self.sellval,
                self.feecur, self.feeval,
                self.exchange, self.mark,
                self.comment]:
            if isinstance(val, Decimal):
                strings.append("{0:0.8f}".format(float(val)))
            else:
                strings.append(str(val))
        return delimiter.join(strings) + endl

    def __str__(self):
        s = ("%(kind)s on %(dtime)s: Acquired %(buyval).8f %(buycur)s, "
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
        """`TradeHistory()` creates a TradeHistory object.

            self.tlist is a sorted list of trades available after
            some trades have been imported."""
        self.tlist = []

    def __getitem__(self, item):
        return self.tlist[item]

    def to_data_frame(self, year=None, convert_timezone=True):
        """Put all trades in one big pandas.DataFrame.

        :param year: None or 4-digit integer, default: None;
            Leave `None` to export all trades or choose a specific
            year to export.
        :param convert_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates will be converted to this timezone. The default
            value, True, will lead to a conversion to the locale
            timezone according to the system's locale setting.
            False keeps all dates at UTC time. Otherwise, specify a
            parameter that will be forwarded to
            `pandas.Timestamp.tz_convert()`.

        """
        l = (trd.__dict__ for trd in self.tlist)
        # use cols to set a nice order:
        cols = ['kind', 'dtime', 'buycur', 'buyval', 'sellcur', 'sellval',
                'feecur', 'feeval', 'exchange', 'mark', 'comment']
        df = pd.DataFrame(l, columns=cols)

        # give the columns slightly better names:
        newcols = Trade.__init__.__code__.co_varnames[1:12]
        df.columns = newcols

        # Select year:
        if year is not None:
            df = df[  (df['dtime'] >= str(year))
                    & (df['dtime'] < str(year + 1))]

        # Convert timezones :
        if convert_timezone:
            if convert_timezone is True:
                convert_timezone = tz.tzlocal()
            appfun = lambda dt: dt.tz_convert(convert_timezone)
            df.loc[:, 'dtime'] = df.loc[:, 'dtime'].apply(appfun)

        return df

    def __str__(self):
        return self.to_data_frame().to_string()

    def _trade_sort_key(self, trade):
        """Utility function used for key parameter in python's
        list.sort method when sorting a list of Trade objects.

        """
        dtime = trade.dtime
        if trade.buyval > 0 and (not trade.sellval or not trade.sellcur):
            # This seems to be a deposit.
            # Some wallets are so quick, they'll register a deposit
            # at exactly the same time than the withdrawal went out
            # on the sending wallet. This in turn will make the
            # order of withdrawal and deposit unclear in the
            # sorted list of trades. Here we add 1 ns to every
            # deposit, so they will always be sorted in after a
            # simultaneous withdrawal:
            dtime += pd.Timedelta(1, 'ns')
        return dtime

    def add_missing_transaction_fees(self, raise_on_error=True):
        """Some exchanges do not include withdrawal fees in their
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
        is greater than zero. This might not work if there are
        withdrawals in tight succession whose deposits register in a
        different order than the withdrawals.

        If *raise_on_error* is True (which is the default), a ValueError
        will be raised if a pair is found that cannot possibly match
        (higher deposit than withdrawal), otherwise only a warning
        is logged and the withdrawal skipped (which will be tried to be
        matched with the next deposit) while the deposit is tried
        to be matched with another withdrawal that came before it.

        """
        # Filter out all deposits and withdrawals from self.tlist
        # by making a list of tuples:
        #   (tlist index,
        #    'w' or 'd' for 'withdrawal' OR 'deposit', respectively,
        #    withdrawal amount - fees OR deposit amount, respectively):
        # (Note: We are keeping both in one list to keep their order)
        translist = []
        for i, t in enumerate(self.tlist):
            if t.exchange == 'Bitsquare/Bisq' and t.kind.startswith('MultiSig'):
                # The Bitsquare/Bisq MultiSig deposits and payouts are
                # already taken care of and their fees properly added
                # when importing from csv in self.append_bisq_csv, so
                # skip them here:
                continue
            elif t.sellval > 0 and (not t.buycur or (not t.buyval
                # In Poloniex' csv data, there is sometimes a trade listed
                # with a non-zero sellval but with 0 buyval, because the
                # latter amounts to less than 5e-9, which is rounded down.
                # But it is not a withdrawal, so exclude it here:
                and (t.exchange != 'Poloniex'
                     or t.kind == 'Withdrawal'))):
                    # This seems to be a withdrawal
                    if t.feeval and t.sellcur != t.feecur:
                        raise ValueError(
                            'In trade %i, encountered withdrawal with '
                            'different fee currency than withdrawn '
                            'currency.' % i)
                    translist.append((i, 'w', t.sellval - t.feeval))
            elif t.buyval > 0 and (not t.sellval or not t.sellcur):
                # This seems to be a deposit
                translist.append((i, 'd', t.buyval))
        unhandled_withdrawals = []
        num_unmatched = 0
        num_feeless = 0
        for i, kind, amount in translist:
            if kind == 'w':
                unhandled_withdrawals.append((i, amount))
                num_unmatched += 1
                num_feeless += self[i].feeval == 0
            else:
                # deposit
                k = 0
                while k < len(unhandled_withdrawals):
                    j, wamount = unhandled_withdrawals[k]
                    if self[j].sellcur != self[i].buycur:
                        k += 1
                    else:
                        if wamount < amount:
                            errs = (
                                "The withdrawal from %s (%.8f %s, %s) is "
                                "lower than the first deposit "
                                "(%s, %.8f %s, %s) following it." % (
                                    self[j].dtime, wamount, self[j].sellcur,
                                    self[j].exchange,
                                    self[i].dtime, amount, self[i].buycur,
                                    self[i].exchange))
                            if raise_on_error:
                                raise ValueError(errs)
                            else:
                                log.warning(
                                    errs + " Trying next withdrawal.")
                            k += 1
                        else:
                            # found a match
                            num_unmatched -= 1
                            num_feeless -= self[j].feeval == 0
                            if wamount > amount:
                                self.tlist[j].feeval += wamount - amount
                                log.info('amended withdrawal: %s', self[j])
                            del unhandled_withdrawals[k]
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

        if default_timezone is None:
            default_timezone = tz.tzlocal()

        numtrades = len(self.tlist)

        # convert input lines to Trades:
        for csvline in csvlines[skiprows:]:
            line = csvline.split(delimiter)
            if not line:
                # ignore empty lines
                continue
            self.tlist.append(
                _parse_trade(line, param_locs, default_timezone))

        log.info("Loaded %i transactions from %s",
                 len(self.tlist) - numtrades, file_name)
        # trades must be sorted:
        self.tlist.sort(key=self._trade_sort_key, reverse=False)

    def append_ccgains_csv(
            self, file_name, delimiter=',', skiprows=1,
            default_timezone=None):
        """Import trades from a csv file exported from
        `ccgains.TradeHistory.export_to_csv()` and add them to this
        TradeHistory.

        Afterwards, all trades will be sorted by date and time.

        :param default_timezone:
            This parameter is ignored if there is timezone data in the
            csv string. Otherwise, if None (default) the time data in
            the csv will be interpreted as time in the local timezone
            according to the locale setting; or it must be a tzinfo
            subclass (from dateutil.tz or pytz)

        """
        return self.append_csv(
            file_name=file_name,
            param_locs=range(11),
            delimiter=delimiter,
            skiprows=skiprows,
            default_timezone=default_timezone)

    def append_poloniex_csv(
            self, file_name, which_data='trades', condense_trades=False,
            delimiter=',', skiprows=1, default_timezone=tz.tzutc()):
        """Import trades from a csv file exported from Poloniex.com and
        add them to this TradeHistory.

        Afterwards, all trades will be sorted by date and time.

        :param which_data: (string)
            Must be one of `"trades"`, `"withdrawals"` or `"deposits"`.
            Poloniex only allows exporting the three categories
            'trading history', 'withdrawal history' and 'deposit history'
            in separate csv files. Specify which type is loaded here.
            Default is 'trades'.
        :param condense_trades: (bool)
            Merge consecutive trades with identical order number? The
            time of the last merged trade will be used for the resulting
            trade. Only has an effect if `which_data == 'trades'`.

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
        if wdata == 'withd':
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

        if plocs == TPLOC_POLONIEX_TRADES and condense_trades:
            # special loading of trades if they need to be condensed

            with open(file_name) as f:
                csvlines = f.readlines()

            if default_timezone is None:
                default_timezone = tz.tzlocal()

            # current number of imported trades:
            numtrades = len(self.tlist)
            grouplist = []
            groupid = None

            # convert input lines to Trades:
            num = len(csvlines) - skiprows
            for i, csvline in enumerate(csvlines[skiprows:]):
                line = csvline.split(delimiter)
                trade = _parse_trade(line, plocs, default_timezone)
                if groupid is None:
                    groupid = trade.comment
                if groupid == trade.comment:
                    grouplist.append(trade)
                if groupid != trade.comment or i == num - 1:
                    # time to merge trades in grouplist and place in tlist
                    grouplist.sort(key=self._trade_sort_key, reverse=True)
                    last = grouplist[0]
                    for t in grouplist[1:]:
                        if (last.kind != t.kind
                                or last.buycur != t.buycur
                                or last.sellcur != t.sellcur
                                or last.feecur != t.feecur
                                or last.exchange != t.exchange
                                or last.mark != t.mark):
                            raise Exception(
                                "Error in csv: The trades from %s and %s "
                                "share the same order number, but differ "
                                "in market, category or kind." % (
                                    last.dtime, t.dtime))
                        else:
                            last.buyval += t.buyval
                            last.sellval += t.sellval
                            last.feeval += t.feeval
                    # add consolidated trade to self.tlist:
                    self.tlist.append(last)
                    # reset groupslist:
                    if groupid != trade.comment:
                        if i < num - 1:
                            # current trade did not match,
                            # but might match next trade:
                            grouplist = [trade]
                            groupid = trade.comment
                        else:
                            # this was the last trade and did not match:
                            self.tlist.append(trade)
                            grouplist = []
                            groupid = None
                    else:
                        # this was the last trade but was already included
                        # and merged with grouplist:
                        grouplist = []
                        groupid = None

            log.info("Loaded %i transactions from %s",
                     len(self.tlist) - numtrades, file_name)

            # trades must be sorted:
            self.tlist.sort(key=self._trade_sort_key, reverse=False)
            return
        else:
            # normal loading, using the proper plocs:
            return self.append_csv(
                file_name=file_name,
                param_locs=plocs,
                delimiter=delimiter,
                skiprows=skiprows,
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
            The csv file name with the trading history.
            In case you only made transactions and no trades, this
            may be an empty string: ""
        :param transaction_file_name:
            The csv file name with the transaction history
        :param default_timezone:
            This parameter is ignored if there is timezone data in the
            csv string. Otherwise, if None, the time data in the csv
            will be interpreted as time in the local timezone
            according to the locale setting; or it must be a tzinfo
            subclass (from dateutil.tz or pytz);
            The default is None, i.e. the local timezone,
            which is what Bitsquare exports at time of writing this,
            but it might change in future.

        """
        if default_timezone is None:
            default_timezone = tz.tzlocal()

        if trade_file_name:
            with open(trade_file_name) as f:
                tradelines = f.readlines()
        else:
            tradelines = ""
        with open(transactions_file_name) as f:
            txlines = f.readlines()

        # convert input lines to Trades:
        tdl = []
        txl = []
        for csvline in tradelines[skiprows:]:
            line = csvline.split(delimiter)
            tdl.append(_parse_trade(line, TPLOC_BISQ_TRADES,
                                    default_timezone))
        for csvline in txlines[skiprows:]:
            line = csvline.split(delimiter)
            txl.append(_parse_trade(line, TPLOC_BISQ_TRANSACTIONS,
                                    default_timezone))
        tdl.sort(key=self._trade_sort_key, reverse=False)
        txl.sort(key=self._trade_sort_key, reverse=False)

        # For each trade from tdl, find the accompanying data from
        # transactions list txl:
        txlpos = 0
        for trade in tdl:
            found = []
            # the trade id:
            tid = trade.comment
            # find 3 matching transactions, whose kind will contain tid:
            # (The multisig deposit and payout will be placed in `found`)
            while txlpos < len(txl) and len(found) < 2:
                tx = txl[txlpos]
                if 'Create offer fee' in tx.kind:
                    if tid in tx.kind:
                        # This trade's sell value is actually a fee:
                        tx.feecur, tx.feeval = tx.sellcur, tx.sellval
                        tx.sellval = 0
                    else:
                        # This is a fee for an offer that was never taken,
                        # which is a loss and not tax deductable, mark
                        # it as such:
                        # (Maybe bisq does it already? I haven't got a clue)
                        tx.kind = tx.kind.replace(
                                    'Create', 'Canceled') + ' (Loss)'
                elif tid in tx.kind:
                    # Hold the matching multisig deposit and payout:
                    found.append(tx)
                txlpos += 1
            # Substract the sum of amounts in `found` from trade.buyval,
            # which is the multisig deposit fee:
            fee = (trade.buyval
                   - found[0].buyval + found[0].sellval
                   - found[1].buyval + found[1].sellval)
            found[0].feeval = fee
            found[0].feecur = found[0].sellcur
            # Also, the multisig payout is the sum of the multisig
            # deposit and the purchased coins. But the latter is already
            # taken into account in the trade, so remove it from the
            # payout:
            found[1].buyval -= trade.buyval

        # No more trades. Find remaining canceled offer fees if any:
        while txlpos < len(txl):
            tx = txl[txlpos]
            if 'Create offer fee' in tx.kind:
                # This is a fee for an offer that was never taken,
                # which is a loss and not tax deductable, mark
                # it as such:
                # (Maybe bisq does it already? I haven't got a clue)
                tx.kind = tx.kind.replace('Create', 'Canceled') + ' (Loss)'
            txlpos += 1

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
        self.tlist.sort(key=self._trade_sort_key, reverse=False)

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

        if default_timezone is None:
            default_timezone = tz.tzlocal()

        tlist = []

        # convert input lines to Trades:
        for csvline in csvlines[skiprows:]:
            line = csvline.split(delimiter)
            tlist.append(
                _parse_trade(line, TPLOC_BITCOINDE, default_timezone))

        # The fees connected to disbursements are given on
        # an extra line; merge them:
        i = 0
        while i < len(tlist):
            if (tlist[i].kind == 'Network fee'
                    and tlist[i - 1].comment == tlist[i].comment):
                tlist[i - 1].sellval += tlist[i].sellval
                tlist[i - 1].feeval += tlist[i].sellval

                del tlist[i]
            else:
                i += 1
        numtrades = len(self.tlist)
        self.tlist.extend(tlist)
        log.info("Loaded %i transactions from %s",
                 len(self.tlist) - numtrades, file_name)
        # trades must be sorted:
        self.tlist.sort(key=self._trade_sort_key, reverse=False)

    def append_trezor_csv(self, file_name, currency, skiprows=1,
                          default_timezone=None):
        """Import trades from a csv file exported from the Trezor wallet
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

        :param currency:
            The currency corresponding to the file to be imported.
            The Trezor wallet exports the information of each wallet
            separately, but the information of the currency is not supplied.
            Therefore, the user has to supply the crypto currency accordingly
            when importing the csv file.

        """
        # Set the crypto currency
        TPLOC_TREZOR_WALLET['buy_currency'] = currency
        TPLOC_TREZOR_WALLET['sell_currency'] = currency
        TPLOC_TREZOR_WALLET['fee_currency'] = currency

        self.append_csv(file_name, TPLOC_TREZOR_WALLET, delimiter=',',
                        skiprows=skiprows, default_timezone=default_timezone)

    def export_to_csv(
            self, path_or_buf=None, year=None,
            convert_timezone=True, **kwargs):
        """Write the list of trades to a csv file.

        The csv table will contain the columns:
        'kind', 'dtime', 'buy_currency', 'buy_amount', 'sell_currency',
        'sell_amount', 'fee_currency', 'fee_amount', 'exchange',
        'mark' and 'comment'.

        :param path_or_buf: File path (string) or file handle,
            default None;
            If None is provided the result is returned as a string.
        :param year: None or 4-digit integer, default: None;
            Leave `None` to export all trades or choose a specific
            year to export.
        :param convert_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates will be converted to this timezone. The default
            value, True, will lead to a conversion to the locale
            timezone according to the system's locale setting.
            False keeps all dates at UTC time. Otherwise, specify a
            parameter that will be forwarded to
            `pandas.Timestamp.tz_convert()`.

        """
        df = self.to_data_frame(year=year, convert_timezone=convert_timezone)

        if df.size == 0:
            log.warning(
                "Trading history could not be saved. "
                "There is no data%s." % (
                    ' for year %i' % year if year else ''))
            return

        result = df.to_csv(path_or_buf, index=False, **kwargs)

        if path_or_buf is None:
            return result

        log.info("Saved trading history %sto %s",
                 'for year %i ' % year if year else '',
                 str(path_or_buf))

    def to_html(
            self, year=None, convert_timezone=True, font_size=11,
            template_file='generic_landscape_table.html',
            caption="Digital currency trades %(year)s",
            intro="<h4>Listing of all transactions between "
                  "%(fromdate)s and %(todate)s</h4>",
            merge_currencies=True,
            drop_columns=None, custom_column_names=None,
            custom_formatters=None, locale=None):
        """Return the trade history as HTML-formatted string.

        :param year: None or 4-digit integer, default: None;
            Leave `None` to export all trades or choose a specific
            year to export.
        :param convert_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates will be converted to this timezone. The default
            value, True, will lead to a conversion to the locale
            timezone according to the system's locale setting.
            False keeps all dates at UTC time. Otherwise, specify a
            parameter that will be forwarded to
            `pandas.Timestamp.tz_convert()`.
        :param template_file: file name of html template inside package
            folder: `ccgains/templates`.
            Default: 'generic_landscape_table.html'
        :param merge_currencies: Boolean, default True;
            If True, the three currency columns (e.g. 'buy_currency')
            will be dropped, with the currency names added to the
            amount columns (e.g. added to 'buy_amount').
        :param drop_columns: None or list of strings;
            Column names specified here (as returned from
            `to_data_frame`) will be omitted from output.
            If *merge_currencies* is True, don't specify the currency
            columns here, only the amount column that you want removed.
        :param custom_column_names: None or list of strings;
            If None (default), the column names of the DataFrame
            returned from `to_data_frame()` will be used.
            To rename them, supply a list of proper length (that is,
            `11 - len(drop_columns)` if *merge_currencies* is False or
            `8 -  len(drop_columns)` otherwise).
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
        :returns:
            HTML-formatted string

        """
        import jinja2
        import babel.numbers, babel.dates

        env = jinja2.Environment(
                loader=jinja2.PackageLoader('ccgains', 'templates'))
        template = env.get_template(template_file)

        # Build formatters for all columns:

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

        date_formatter = lambda x: babel.dates.format_datetime(
                x, format='medium',
                locale=locale if locale else babel.dates.LC_TIME)

        # Get DataFrame:
        df = self.to_data_frame(year=year, convert_timezone=convert_timezone)

        if merge_currencies:
            if not drop_columns:
                drop_columns = []
            for name in ['buy', 'sell', 'fee']:
                acol = '%s_amount' % name
                ccol = '%s_currency' % name
                if not acol in drop_columns:
                    df[acol] = (
                        df[acol].apply(amount_formatter)
                        + u'\xa0' + df[ccol])
                if not ccol in drop_columns:
                    drop_columns.append(ccol)

        if drop_columns:
            df.drop(drop_columns, axis=1, inplace=True)

        # right-align amount columns:
        cols_to_align_right = [
            i + 2 for i, c in enumerate(df.columns)
            if c in ['%s_amount' % name for name in ['buy', 'sell', 'fee']]]

        # use custom column names:
        if custom_column_names is not None:
            renamed = {k:v for k, v in zip(df.columns, custom_column_names)}
            df.columns = custom_column_names
        else:
            renamed = {k:k for k in df.columns}

        # default formatters:
        if merge_currencies:
            formatters={
                'kind': None,
                'dtime': date_formatter,
                'buy_amount': None,
                'sell_amount': None,
                'fee_amount': None,
                'exchange': None,
                'mark': None,
                'comment': None}
        else:
            formatters={
                'kind': None,
                'dtime': date_formatter,
                'buy_currency': None,
                'buy_amount': amount_formatter,
                'sell_currency': None,
                'sell_amount': amount_formatter,
                'fee_currency': None,
                'fee_amount': amount_formatter,
                'exchange': None,
                'mark': None,
                'comment': None}
        # apply renaming and drop dropped columns:
        formatters = {
                renamed[k]:v for k, v in formatters.items() if k in renamed}
        # update with given formatters:
        if custom_formatters is not None:
            formatters.update(custom_formatters)

        # start counting rows at 1:
        df.index = pd.RangeIndex(start=1, stop=len(df) + 1)

        if year is None:
            fromdate = df[renamed['dtime']].iat[0]
            todate = df[renamed['dtime']].iat[-1]
        else:
            fromdate = babel.dates.date(year=year, month=1, day=1)
            todate = babel.dates.date(year=year, month=12, day=31)
        fmtdict = {
            "year"    : str(year) if year else "",
            "fromdate": babel.dates.format_date(
                            fromdate,
                            locale=locale if locale else babel.dates.LC_TIME),
            "todate"  : babel.dates.format_date(
                            todate,
                            locale=locale if locale else babel.dates.LC_TIME)}

        # Rounding affects the babel.numbers.format_decimal formatter:
        # We'll floor everything:
        with babel.numbers.decimal.localcontext(
            babel.numbers.decimal.Context(
                rounding=babel.numbers.decimal.ROUND_DOWN)):
            html = template.render({
                'today'   : babel.dates.format_date(
                             babel.dates.date.today(),
                             locale=locale if locale else babel.dates.LC_TIME),
                'fontsize': font_size,
                'caption' : caption % fmtdict,
                'intro'   : intro % fmtdict,
                'table'   : df.to_html(
                                index=True, bold_rows=False,
                                classes='align-right-columns',
                                formatters=formatters),
                'cols_to_align_right': cols_to_align_right})

        return html

    def export_to_pdf(
            self, file_name, year=None, convert_timezone=True,
            font_size=11, template_file='generic_landscape_table.html',
            caption="Digital currency trades %(year)s",
            intro="<h4>Listing of all transactions between "
                  "%(fromdate)s and %(todate)s</h4>",
            drop_columns=None, custom_column_names=None,
            custom_formatters=None, locale=None):
        """Export the trade history to a pdf file.

        :param file_name: string;
            Destination file name.
        :param year: None or 4-digit integer, default: None;
            Leave `None` to export all trades or choose a specific
            year to export.
        :param convert_timezone:
            string, pytz.timezone, dateutil.tz.tzfile, True or False;
            All dates will be converted to this timezone. The default
            value, True, will lead to a conversion to the locale
            timezone according to the system's locale setting.
            False keeps all dates at UTC time. Otherwise, specify a
            parameter that will be forwarded to
            `pandas.Timestamp.tz_convert()`.
        :param template_file: file name of html template inside package
            folder: `ccgains/templates`.
            Default: 'generic_landscape_table.html'
        :param drop_columns: None or list of strings;
            Column names specified here (as returned from
            `to_data_frame`) will be omitted from output.
        :param custom_column_names: None or list of strings;
            If None (default), the column names of the DataFrame
            returned from `to_data_frame()` will be used.
            To rename them, supply a list of length 11-len(*drop_columns*).
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
        import weasyprint
        html = self.to_html(
                year=year,
                convert_timezone=convert_timezone,
                font_size=font_size, template_file=template_file,
                caption=caption, intro=intro,
                drop_columns=drop_columns,
                custom_column_names=custom_column_names,
                custom_formatters=custom_formatters,
                locale=locale)
        doc = weasyprint.HTML(string=html)
        doc.write_pdf(file_name)
        log.info("Saved trading history %sto %s",
                 'for year %i ' % year if year else '',
                 str(file_name))
