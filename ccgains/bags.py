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
from dateutil.relativedelta import relativedelta
from datetime import datetime
import json
from os import path
from operator import attrgetter
from ccgains import reports

import logging
log = logging.getLogger(__name__)


def is_short_term(adate, tdate):
    """Return whether a transaction/trade done on *tdate* employing
    currency acquired on *adate* is a short term activity, i.e. the
    profits and/or losses made with it are taxable.

    Currently, this simply returns whether the difference between the
    two dates is less than one year, as is the rule in some countries,
    e.g. Germany and the U.S.A.

    TODO: This needs to be made user-configurable in future, to adapt
    to laws in different countries.

    """
    return abs(
        relativedelta(
            tdate.astimezone(adate.tzinfo), adate).years) < 1


def _json_encode_default(obj):
    if isinstance(obj, Decimal):
        return {'type(Decimal)': str(obj)}
    elif isinstance(obj, Bag):
        return {'type(Bag)': obj.__dict__}
    elif isinstance(obj, datetime):
        return {'type(datetime)': str(obj)}
    elif isinstance(obj, reports.CapitalGainsReport):
        return {'type(CapitalGainsReport)': obj.__dict__}
    else:
        raise TypeError(repr(obj) + " is not JSON serializable")

def _json_decode_hook(obj):
    if 'type(Decimal)' in obj:
        return Decimal(obj['type(Decimal)'])
    elif 'type(Bag)' in obj:
        return Bag(**obj['type(Bag)'])
    elif 'type(datetime)' in obj:
        return pd.Timestamp(obj['type(datetime)'])
    elif 'type(CapitalGainsReport)' in obj:
        return reports.CapitalGainsReport(
            data=obj['type(CapitalGainsReport)']['data'])
    return obj


class Bag(object):
    def __init__(
            self, id, dtime, currency, amount, cost_currency, cost,
            price=None):
        """Create a bag which holds an *amount* of *currency*.

        :param id (integer):
            A unique number for each bag. Usually the first created bag
            receives an id of 1, which increases for every bag created.
        :param dtime:
            The datetime when the currency was purchased.
        :param currency:
            The currency this bag holds, the currency that was bought.
        :param amount:
            The amount of currency that was bought. This is the amount
            that is available, i.e. fees are already substracted.
        :param cost_currency:
            The base currency which was paid for the money in this bag.
            The base value of this bag is recorded in this currency.
        :param cost:
            The amount of *cost_currency* paid for the money in this
            bag. This covers all expenses, so fees are included.
        :param price: (optional, default: None):
            If *price* is given, *cost* will be ignored and calculated
            from *price*: *cost* = *amount* * *price*.

        """
        self.id = id
        self.amount = Decimal(amount)
        self.currency = str(currency).upper()
        # datetime of purchase:
        self.dtime = pd.Timestamp(dtime).tz_convert('UTC')
        self.cost_currency = str(cost_currency).upper()
        # total cost, incl. fees:
        if price is None:
            self.cost = Decimal(cost)
            self.price = self.cost / self.amount
        else:
            self.price = Decimal(price)
            self.cost = self.amount * self.price

    def spend(self, amount):
        """Spend some amount out of this bag. This updates the current
        amount and the base value, but leaves the price constant.

        :returns: the tuple (spent_amount, bcost, remainder),
            where

             - *spent_amount* is the amount taken out of the bag, in
               units of `self.currency`;
             - *bcost* is the base cost of the spent amount, in
               units of `self.cost_currency`;
             - *remainder* is the leftover of *amount* after the
               spent amount is substracted.

        """
        amount = Decimal(amount)
        if amount >= self.amount:
            result = (
                    self.amount,
                    self.cost,
                    amount - self.amount)
            self.amount = 0
            self.cost = 0
            return result
        value = amount * self.price
        self.amount -= amount
        self.cost -= value
        return amount, value, 0

    def is_empty(self):
        return self.amount == 0

    def __str__(self):
        return json.dumps(self.__dict__, default=str)


class BagFIFO(object):
    def __init__(
            self, base_currency, relation, json_dump='./precrash.json'):
        """Create a BagFIFO object.

        This is the class that processes trades, handles all bags (i.e.
        creating and spending them) and calculates the capital gains.
        After calculation, the member BagFIFO.report provides methods
        to create reports.

        :param base_currency:
            The base currency (string, e.g. "EUR"). All bags' base cost
            (the money spent for them at buying time) will be recorded
            in units of this currency and finally the capital gains
            will be calculated for this currency.

        :param relation:
            A CurrencyRelation object which serves exchange rates
            between all currencies involved in trades which will later
            be added to this BagFIFO.

        :param json_dump: (filename)
            If specified, the state of the BagFIFO will be saved as
            JSON formatted file with this file name just before an error
            is raised due to missing or conflicting data. If the error
            is fixed, the state can be loaded from this file and the
            calculation might be able to continue from that point.

        """
        self.currency = str(base_currency).upper()
        self.relation = relation
        # The profit (or loss if negative), recorded in self.currency:
        # (dictionary of {str(year): profit})
        self.profit = {}
        # dictionary of {exchange: list of bags}
        self.bags = {}
        # dictionary of {exchange: {currency: total amount}}:
        # (also contains: {'in_transit': {currency: total amount}})
        self.totals = {}
        # dictionary of {currency: list of bags in transit};
        # Bags are added here when currency is withdrawn from an
        # exchange and removed again when they arrive (are deposited)
        # at another exchange:
        # (self.totals['in_transit'] is updated in parallel)
        self.in_transit = {}

        # Collects data for capital gains reports with every payment:
        self.report = reports.CapitalGainsReport()

        self._last_date = pd.Timestamp(0, tz='UTC')
        self.num_created_bags = 0
        self.dump_file = path.abspath(json_dump) if json_dump else None

    def _abort(self, msg):
        """Raise ValueError with the message *msg*.
        Before raising, the current state of the file will be saved
        to self.dump_file.

        """
        self.save(self.dump_file)
        raise ValueError(msg)

    def _check_order(self, dtime):
        """Raise ValueError if *dtime* is older than the last
        checked datetime. Also complains (raises an error) if
        *dtime* does not include timezone information.

        """
        if dtime.tzinfo is None:
            self._abort(
                'To eliminate ambiguity, only transactions including '
                'timezone information in their datetime are allowed.')
        if dtime < self._last_date:
            self._abort(
                'Trades must be processed in order. Last processed trade '
                'was from %s, this one is from %s' % (
                        self._last_date, dtime))
        self._last_date = pd.Timestamp(dtime).tz_convert('UTC')

    def _add_profit(self, dtime, profit):
        """Adds *profit* to self.profit, classified by the year
        given in *dtime*

        """
        if isinstance(dtime, (int, str)):
            year = str(dtime)
        else:
            year = str(dtime.year)
        self.profit[year] = self.profit.get(year, Decimal(0)) + profit

    def to_json(self, **kwargs):
        """Return a JSON formatted string representation of the current
        state of this BagFIFO and its list of bags.

        As an external utility, self.relation will not be included in
        this string.

        :param kwargs:
            Keyword arguments that will be forwarded to `json.dumps`.

        :returns: JSON formatted string
        """
        return json.dumps(
            {k: v for k, v in self.__dict__.items() if k != 'relation'},
            default=_json_encode_default, **kwargs)

    def save(self, filepath_or_buffer):
        """Save the current state of this BagFIFO and its list of bags
        to a JSON formatted file, so that it can later be restored
        with `self.load`.

        As an external utility, self.relation will not be included in
        this string.

        :param filepath_or_buffer: The destination file's name, which
            will be overwritten if existing, or a general buffer with
            a `write()` method.

        """
        if hasattr(filepath_or_buffer, 'write'):
            json.dump(
                {k: v for k, v in self.__dict__.items() if k != 'relation'},
                fp=filepath_or_buffer,
                default=_json_encode_default, indent=4)
            if hasattr(filepath_or_buffer, 'name'):
                log.info("Saved bags' state to %s", filepath_or_buffer.name)
        else:
            with open(filepath_or_buffer, 'w') as f:
                self.save(f)


    def load(self, filepath_or_buffer):
        """Restore a previously saved state of a BagFIFO and its list
        of bags from a JSON formatted file.

        Everything from the current BagFIFO object will be overwritten
        with the file's contents.

        :param filepath_or_buffer:
            The filename of the JSON formatted file or a general buffer
            with a `read()` method streaming the JSON formatted string.

        """
        if hasattr(filepath_or_buffer, 'read'):
            d = json.load(
                    fp=filepath_or_buffer,
                    object_hook=_json_decode_hook)
            # remove zero totals:
            for ex in d['totals']:
                for cur, val in list(d['totals'][ex].items()):
                    if val == 0:
                        del d['totals'][ex][cur]
                if not d['totals'][ex]:
                    del d['totals'][ex]

            # restore state:
            self.__dict__.update(d)

            # check consistency of totals:
            check_totals = {}
            for ex in self.bags:
                check_totals[ex] = {}
                for bag in self.bags[ex]:
                    if bag.amount != 0:
                        check_totals[ex][bag.currency] = (
                            check_totals[ex].get(bag.currency, 0)
                            + bag.amount)
                        if bag.cost_currency != self.currency:
                            raise Exception(
                                "Could not load, file is corrupted (bags' "
                                "cost and base_currency do not match).")
            check_transit = {}
            for cur in self.in_transit:
                for bag in self.in_transit[cur]:
                    if bag.amount != 0:
                        check_transit[cur] = (
                            check_transit.get(cur, 0) + bag.amount)
            if check_transit:
                check_totals['in_transit'] = check_transit
            if check_totals != self.totals:
                raise Exception(
                    "Could not load, file is corrupted "
                    "(totals don't add up).")

            if hasattr(filepath_or_buffer, 'name'):
                log.info("Restored bags' state from %s",
                         filepath_or_buffer.name)
        else:
            with open(filepath_or_buffer, 'r') as f:
                self.load(f)

    def to_data_frame(self):
        """Put all bags from all exchanges in one big pandas.DataFrame. """
        l = [dict(list(bag.__dict__.items()) + [('exchange', ex)])
                for ex, bgs in self.bags.items() for bag in bgs]
        # Also add bags in transit:
        l.extend([dict(
                    list(bag.__dict__.items())
                    + [('exchange', '<in_transit>')])
                for bgs in self.in_transit.values() for bag in bgs])
        cols = [
            'id', 'exchange', 'dtime',
            'currency', 'amount', 'cost_currency', 'cost', 'price']
        return pd.DataFrame(l, columns=cols).set_index('id').rename_axis(
                {'dtime': 'date', 'cost_currency': 'costcur'},
                axis='columns')

    def __str__(self):
        return self.to_data_frame().to_string(
                formatters={'amount': '{0:.8f}'.format,
                            'cost': '{0:.8f}'.format,
                            'price': '{0:.8f}'.format})

    def _move_bags(self, src, dest, amount, currency):
        """Move *amount* of *currency* from one list of bags to another list
        of bags.

        Will split the last needed bag in *src* if only a part of its amount
        needs to be moved, i.e. a new bag will be created in *dest* with the
        amount taken out of that last bag in *src*.

        :param src: List of Bag objects where bags totaling *amount* will be
            removed from, starting from the first bag.
        :param dest: List where Bag objects will be added to.
        :param amount: amount to be moved.
        :param currency: currency to be moved.
        :return: amount that could not be moved because src is empty

        """
        # Find bags with this currency and move them completely
        # or (the last one) partially:
        i = 0
        to_move = Decimal(amount)
        while to_move > 0:
            while src[i].currency != currency:
                i += 1
                if i == len(src):
                    # No more usable bags left in src
                    return to_move
            bag = src[i]
            if bag.amount <= to_move:
                # Move complete bag:
                dest.append(bag)
                del src[i]
                to_move -= bag.amount
                if i == len(src):
                    # No more usable bags left in src
                    return to_move
            else:
                # We need to split the bag:
                spent, cost, _ = bag.spend(to_move)
                self.num_created_bags += 1
                dest.append(Bag(
                    id=self.num_created_bags,
                    dtime=bag.dtime,
                    currency=bag.currency,
                    amount=spent,
                    cost_currency=bag.cost_currency,
                    cost=cost))
                to_move -= spent
        return to_move

    def buy_with_base_currency(self, dtime, amount, currency, cost, exchange):
        """Create a new bag with *amount* money in *currency*.

        Creation time of the bag is the datetime *dtime*. The *cost* is
        paid in base currency, so no money is taken out of another bag.
        Any fees for the transaction should already have been
        substracted from *amount*, but included in *cost*.

        """
        self._check_order(dtime)
        exchange = str(exchange).capitalize()
        amount = Decimal(amount)
        if amount <= 0:
            return
        if currency == self.currency:
            self._abort('Buying the base currency is not possible.')
        if exchange not in self.bags:
            self.bags[exchange] = []
        self.bags[exchange].append(Bag(
                id=self.num_created_bags + 1,
                dtime=dtime,
                currency=currency,
                amount=amount,
                cost_currency=self.currency,
                cost=cost))
        self.num_created_bags += 1
        if exchange not in self.totals:
            self.totals[exchange] = {}
        tot = self.totals[exchange].get(currency, Decimal())
        self.totals[exchange][currency] = tot + amount

    def withdraw(self, dtime, currency, amount, fee, exchange):
        """Withdraw *amount* monetary units of *currency* from an
        exchange for a *fee* (also given in *currency*). The fee is
        included in amount. The withdrawal happened at datetime *dtime*.

        The pair of methods `withdraw` and `deposit` is used for
        transfers of the same currency from one exhange to another.

        If the amount is more than the total available, a ValueError
        will be raised.

        ---

        Losses made by fees (which must be directly resulting from and
        connected to short term trading activity!) are substracted from
        the total taxable profit (recorded in base currency).

        This approach can be logically justified by looking at what
        happens to the amount of fiat money that leaves a bank account
        solely for trading with cryptocurrencies, which in turn are sold
        entirely for fiat money before the end of the year. If nothing
        else was bought with the cryptocurrencies in between, the
        difference between the amount of fiat before and after trading
        is exactly the taxable profit. For simplicity, say we buy some
        Bitcoin at one exchange for X fiat money (i.e. X fiat money is
        leaving the bank account), then transfer it to another exchange
        (paying withdrawal and/or deposit fees) where we sell it again
        for fiat, e.g.:

            - buy 1 BTC @ 1000 EUR at exchangeA;
              now we own 1 BTC with base value 1000 EUR
            - transfer 1 BTC to exchangeB for 0.1 BTC fees;
              now we own 0.9 BTC with base value 900 EUR,
              100 EUR for the fees are counted as loss
            - Example 1: We sell 0.9 BTC at a better price than before:
              we get exactly 1000 EUR. The immediate profit is 100 EUR
              (1000 EUR proceeds minus 900 EUR base value), but minus
              the 100 EUR fee loss from earlier we have exactly a
              taxable profit of 0 EUR, which makes sense considering
              we started with 1000 EUR and now still have only 1000 EUR.
            - Example 2: We sell 0.9 BTC at a much better price:
              we get exactly 2000 EUR. The immediate profit is 1100 EUR
              (2000 EUR proceeds minus 900 EUR base value), but minus
              the 100 EUR fee loss from earlier we have exactly a
              taxable profit of 1000 EUR, which also makes sense since
              we started with 1000 EUR and now have 2000 EUR.

        Note: The exact way how withdrawal, deposit and in general
        transaction fees are handled should be made user-configurable
        in future.

        """
        self._check_order(dtime)
        if amount <= 0: return
        exchange = str(exchange).capitalize()
        if currency == self.currency:
            self._abort(
                    'Withdrawing the base currency is not possible.')
        amount = Decimal(amount)
        fee = Decimal(fee)
        if exchange not in self.totals:
            total = 0
        else:
            total = self.totals[exchange].get(currency, 0)
        if amount > total:
            self._abort(
                "Withdrawn amount ({1} {0}) is higher than total available "
                "on {3}: {2} {0}.".format(
                        currency, amount, total, exchange))
        # any fees?
        if fee > 0:
            prof, _ = self.pay(
                dtime, currency, fee, exchange, fee_ratio=1,
                report_info={'kind': 'withdrawal fee'})
            self._add_profit(dtime, prof)
            log.info("Taxable loss due to fees: %.3f %s",
                     prof, self.currency)

        # Move bags to self.in_transit:
        if currency not in self.in_transit:
            self.in_transit[currency] = []
        remainder = self._move_bags(
            self.bags[exchange], self.in_transit[currency],
            amount - fee, currency)
        if remainder:
            # Corrupt data error: don't dump state.
            raise Exception(
                "There are no bags left with the requested currency")
        # TODO: Add sending and/or receiving wallet adress (whichever
        # available) to each transit? Then it may be unambigiously
        # matched with the destination exchange in self.deposit.

        # update and clean up totals:
        if total - amount == 0:
            del self.totals[exchange][currency]
            if not self.totals[exchange]:
                del self.totals[exchange]
            if not self.bags[exchange]:
                del self.bags[exchange]
        else:
            self.totals[exchange][currency] = total - amount
        if 'in_transit' not in self.totals:
            self.totals['in_transit'] = {}
        in_transit = self.totals['in_transit'].get(currency, 0)
        self.totals['in_transit'][currency] = in_transit + amount - fee

    def deposit(self, dtime, currency, amount, fee, exchange):
        """Deposit *amount* monetary units of *currency* into an
        exchange for a *fee* (also given in *currency*), making it
        available for trading. The fee is included in amount. The
        deposit happened at datetime *dtime*.

        The pair of methods `withdraw` and `deposit` is used for
        transfers of the same currency from one exhange to another.

        If the amount is more than the amount withdrawn before (minus
        fees), a warning will be printed and a bag created with a base
        cost of 0.

        See also `withdraw` about the handling of fees.

        Note that, currently, the fees for this deposit, if any, will
        be taken from the oldest funds on the exchange after the deposit,
        which are not necessarily the deposited funds.

        """
        self._check_order(dtime)
        if amount <= 0: return
        exchange = str(exchange).capitalize()
        if currency == self.currency:
            self._abort(
                'Depositing the base currency is not possible.')
        amount = Decimal(amount)
        fee = Decimal(fee)

        # Move bags to self.bags:
        if exchange not in self.bags:
            self.bags[exchange] = []
        if currency in self.in_transit:
            remainder = self._move_bags(
                self.in_transit[currency], self.bags[exchange],
                amount, currency)
            # We always use oldest funds first, so in case there were
            # some funds on the exchange newer than the deposited ones:
            self.bags[exchange].sort(key=attrgetter('dtime'), reverse=False)
        else:
            remainder = amount

        if remainder:
            log.warning(
                "Depositing more money ({1} {0}) than "
                "was withdrawn before ({2} {0}).".format(
                        currency, amount, amount - remainder)
                + " Assuming the additional amount ({1} {0}) was bought "
                "with 0 {2}.".format(currency, remainder, self.currency))
            self.buy_with_base_currency(
                dtime, remainder, currency, 0, exchange)

        # update self.totals and clean up:
        if 'in_transit' in self.totals:
            if currency in self.totals['in_transit']:
                self.totals['in_transit'][currency] -= amount
                if self.totals['in_transit'][currency] <= 0:
                    del self.totals['in_transit'][currency]
            if not self.totals['in_transit']:
                del self.totals['in_transit']
            if currency in self.in_transit and not self.in_transit[currency]:
                del self.in_transit[currency]

        if exchange not in self.totals:
            self.totals[exchange] = {}
        tot = self.totals[exchange].get(currency, Decimal())
        # remainder was added in self.buy_with_base_currency before:
        self.totals[exchange][currency] = tot + amount - remainder

        # any fees?
        # TODO: Must the fees be paid from deposited bags or from oldest
        # bags on exchange (now it's done the latter way)?
        if fee > 0:
            prof, _ = self.pay(
                    dtime, currency, fee, exchange, fee_ratio=1,
                    report_info={'kind': 'deposit fee'})
            self._add_profit(dtime, prof)
            log.info("Taxable loss due to fees: %.3f %s",
                     prof, self.currency)

    def pay(self, dtime, currency, amount, exchange, fee_ratio=0,
            custom_rate=None, report_info=None):
        """Spend an amount of funds.

        The money is taken out of the oldest bag on the exchange with
        the proper currency first, then from the next fitting bags in
        line each time a bag is emptied (FIFO principle). The bags'
        prices are not changed, but their current amount and base value
        (original cost) are decreased proportionally.

        This transaction and any profits or losses made will be logged
        and added to the capital gains report data.

        If *amount* is higher than the available total amount,
        ValueError is raised.

        :param dtime: (datetime) The date and time when the payment
            occured.
        :param amount: (number, decimal or parsable string)
            The amount being spent, including fees.
        :param currency: (string) The currency being spent.
        :param exchange: (string) The unique name of the
            exchange/wallet where the funds that are being spent are
            taken from.
        :param fee_ratio: (number, decimal or parsable string),
            0 <= fee_ratio <= 1; The ratio of *amount* that are fees.
            Default: 0.
        :param custom_rate: (number, decimal or parsable string),
            Default: None;
            Provide a custom rate for conversion of *currency* to the
            base currency. Usually (i.e. if this is None), the rate is
            fetched from the CurrencyRelation object provided when this
            BagFIFO object was created. In some cases, one should rather
            provide a rate, for example when base currency was bought
            with this payment, meaning a more specific rate for this
            trade can be provided than relying on the averaged historic
            data used otherwise.
        :param report_info: dict, default None;
            Additional information that will be added to the capital
            gains report data. Currently, the only keys looked for are:
            'kind', 'buy_currency' and 'buy_ratio'. For each one of
            them omitted in the dict, these default values will be used:

             `{'kind': 'payment', 'buy_currency': '', 'buy_ratio': 0}`,

            This is also the default dict used when *report_info* is
            `None`.

             - 'kind' is the type of transaction, i.e. 'sale',
               'withdrawal fee', 'payment' etc.;
             - 'buy_currency' is the currency bought in this trade;
             - 'buy_ratio' is the amount of 'buy_currency' bought with
               one unit of *currency*, i.e. `bought_amount / spent_amount`;
               only used if 'buy_currency' is not empty.

        :returns: the tuple `(short_term_profit, total_proceeds)`,
            with each value given in units of the base currency, where:

              - `short_term_profit`

               is the taxable short term profit (or
               loss if negative) made in this sale. This only takes into
               account the part of *amount* which was acquired less than
               a year prior to *dtime* (or whatever time period is used by
               `is_short_term`). The short term profit equals the proceeds
               made by liquidating this amount for its price at *dtime*
               minus its original cost, with the fees already substracted
               from these proceeds.

              - `total_proceeds`

               are the total proceeds returned from this
               sale, i.e. it includes the full *amount* (held for any amount
               of time) at its price at *dtime*, with fees already
               substracted. This value equals the base cost of any new
               currency purchased with this sale.

        """
        self._check_order(dtime)
        amount = Decimal(amount)
        fee_ratio = Decimal(fee_ratio)
        if amount <= 0: return
        exchange = str(exchange).capitalize()
        if currency == self.currency:
            self._abort(
                'Payments with the base currency are not relevant here.')
        if exchange not in self.bags or not self.bags[exchange]:
            self._abort(
                "You don't own any funds on %s" % exchange)
        if fee_ratio < 0 or fee_ratio > 1:
            self._abort("Fee ratio must be between 0 and 1.")
        if exchange not in self.totals:
            total = 0
        else:
            total = self.totals[exchange].get(currency, 0)
        if amount > total:
            self._abort(
                "Amount to be paid ({1} {0}) is higher than total "
                "available on {3}: {2} {0}.".format(
                        currency, amount, total, exchange))
        # expenses (original cost of spent money):
        cost = Decimal()
        # expenses only of short term trades:
        st_cost = Decimal()
        # proceeds (value of spent money at dtime):
        proc = Decimal()
        # proceeds only of short term trades:
        st_proc = Decimal()
        # exchange rate at time of payment:
        if custom_rate is not None:
            rate = Decimal(custom_rate)
        else:
            try:
                rate = Decimal(
                    self.relation.get_rate(dtime, currency, self.currency))
            except KeyError:
                self._abort(
                    'Could not fetch the price for currency_pair %s_%s on '
                    '%s from provided CurrencyRelation object.' % (
                            currency, self.currency, dtime))
        # due payment:
        to_pay = amount
        log.info(
            "Paying %(to_pay).8f %(curr)s from %(exchange)s "
            "(including %(fees).8f %(curr)s fees)",
            {'to_pay': to_pay, 'curr': currency,
             'exchange': exchange, 'fees': to_pay * fee_ratio})
        # Find bags with this currency and use them to pay for
        # this, starting from first bag (FIFO):
        i = 0
        while to_pay > 0:
            # next bag in line with fitting currency:
            while self.bags[exchange][i].currency != currency:
                i += 1
                if i == len(self.bags[exchange]):
                    # Corrupt data error: don't dump state.
                    raise Exception(
                        "There are no bags left with the requested currency")
            bag = self.bags[exchange][i]

            # Spend as much as possible from this bag:
            log.info("Paying with bag from %s, containing %.8f %s",
                     bag.dtime, bag.amount, bag.currency)
            spent, bcost, remainder = bag.spend(to_pay)
            log.info("Contents of bag after payment: %.8f %s (spent %.8f %s)",
                 bag.amount, bag.currency, spent, currency)

            # The proceeds are the value of spent amount at dtime:
            thisproc = spent * rate
            # update totals for the full payment:
            proc += thisproc
            cost += bcost
            short_term = is_short_term(bag.dtime, dtime)
            if short_term:
                st_proc += thisproc
                st_cost += bcost

            # fee-corrected proceeds for this partial sale:
            corrproc = thisproc * (1 - fee_ratio)
            # profit for this partial sale (not short term only):
            prof = corrproc - bcost

            log.info("Profits in this transaction:\n"
                 "    Original bag cost: %.3f %s (Price %.8f %s/%s)\n"
                 "    Proceeds         : %.3f %s (Price %.8f %s/%s)\n"
                 "    Proceeds w/o fees: %.3f %s\n"
                 "    Profit           : %.3f %s\n"
                 "    Taxable?         : %s (held for %s than a year)",
                 bcost, self.currency, bag.price, bag.cost_currency,
                 currency,
                 thisproc, self.currency, rate, self.currency, currency,
                 corrproc, self.currency,
                 prof, self.currency,
                 'yes' if short_term else 'no',
                 'less' if short_term else 'more')

            # Store report data:
            repinfo = {
                'kind': 'payment', 'buy_currency': '', 'buy_ratio': 0}
            if report_info is not None:
                repinfo.update(report_info)
            if not repinfo.get('buy_currency', ''):
                repinfo['buy_ratio'] = 0
            self.report.add_payment(
                reports.PaymentReport(
                    kind=repinfo['kind'],
                    exchange=exchange,
                    sell_date=pd.Timestamp(dtime).tz_convert('UTC'),
                    currency=currency,
                    to_pay=to_pay,
                    fee_ratio=fee_ratio,
                    bag_date=bag.dtime,
                    bag_amount=bag.amount + spent,
                    bag_spent=spent,
                    cost_currency=bag.cost_currency,
                    spent_cost=bcost,
                    short_term=short_term,
                    ex_rate=rate,
                    proceeds=corrproc,
                    profit=prof,
                    buy_currency=repinfo['buy_currency'],
                    buy_ratio=repinfo['buy_ratio']))

            to_pay = remainder
            if to_pay > 0:
                log.info("Still to be paid with another bag: %.8f %s",
                     to_pay, currency)
            if bag.is_empty():
                del self.bags[exchange][i]
            else:
                i += 1

        # update and clean up totals:
        if total - amount == 0:
            del self.totals[exchange][currency]
            if not self.totals[exchange]:
                del self.totals[exchange]
            if not self.bags[exchange]:
                del self.bags[exchange]
        else:
            self.totals[exchange][currency] = total - amount

        # Return the tuple (short_term_profit, total_proceeds):
        # Note: if it is not completely clear how we arrive at these
        # formulas (i.e. the proceeds are the value of the spent amount,
        # minus fees, at time of payment; the profit equals these
        # proceeds minus the initial cost of the full amount), here
        # is a different view point:
        # The cost and proceeds attributable to fees are split
        # proportionately from st_cost and st_proceeds, i.e.
        # the fee's cost is `fee_p * st_cost` and the lost proceeds
        # due to the fee is `fee_p * st_proceeds`.
        # The fee's cost is counted as loss:
        # (but only the taxable short term portion!)
        # ==>
        # Total profit =
        #  profit putting fees aside: (1-fee_p) * (st_proceeds - st_cost)
        #  - fee cost loss          : - fee_p * st_cost
        #  = (1 - fee_p) * st_proceeds - st_cost
        return st_proc * (1 - fee_ratio) - st_cost, proc * (1 - fee_ratio)

    def process_trade(self, trade):
        """Process the trade or transaction documented in a Trade object.

        The trade must be newer than the last processed trade, otherwise
        a ValueError is raised.

        Pay attention to the definitions in Trade.__init__, especially
        that *buy_amount* is given without transaction fees, while
        *sell_amount* includes them.

        """
        log.info(
            'Processing trade: %s', trade.to_csv_line().strip('\n'))
        self._check_order(trade.dtime)
        if trade.buyval < 0 or trade.sellval < 0 or trade.feeval < 0:
            self._abort(
                'Negative values for buy, sell or fee amount not supported.')
        if not str(trade.dtime.year) in self.profit:
            # initialize profit for this year:
            self.profit[str(trade.dtime.year)] = Decimal(0)

        if ((trade.sellcur == self.currency and trade.sellval != 0) or
            (trade.kind.upper() == 'DISTRIBUTION' and trade.sellval == 0)):
            # Paid for with our base currency, simply add new bag:
            # (The cost is directly translated to the base value
            # of the bags)
            log.info("Buying %.8f %s for %.8f %s at %s (%s)",
                trade.buyval, trade.buycur, trade.sellval, trade.sellcur,
                trade.exchange, trade.dtime)
            self.buy_with_base_currency(
                    dtime=trade.dtime,
                    amount=trade.buyval,
                    currency=trade.buycur,
                    cost=trade.sellval,
                    exchange=trade.exchange)

        elif ((not trade.buycur or trade.buyval == 0) and
              (not trade.sellcur or trade.sellval == 0)):
            # Probably some fees to pay:
            if trade.feeval > 0 and trade.feecur:
                prof, _, = self.pay(
                    trade.dtime, trade.feecur, trade.feeval, trade.exchange,
                    fee_ratio=1,
                    report_info={'kind': 'exchange fee'})
                self._add_profit(trade.dtime, prof)
                log.info("Taxable loss due to fees: %.3f %s",
                         prof, self.currency)

        elif (trade.kind.upper() != 'PAYMENT' and
             (not trade.buycur or (trade.buyval == 0
            # In Poloniex' csv data, there is sometimes a trade listed
            # with a non-zero sellval but with 0 buyval, because the
            # latter amounts to less than 5e-9, which is rounded down.
            # But it is not a withdrawal, so exclude it here:
                and (trade.exchange != 'Poloniex'
                     or trade.kind == 'Withdrawal')))):
            # Got nothing, so it must be a withdrawal:
            log.info("Withdrawing %.8f %s from %s (%s, fee: %.8f %s)",
                trade.sellval, trade.sellcur,
                trade.exchange, trade.dtime,
                trade.feeval, trade.feecur)
            if trade.feeval > 0 and trade.sellcur != trade.feecur:
                self._abort(
                    'Fees with different currency than withdrawn '
                    'currency not supported.')
            self.withdraw(
                    trade.dtime, trade.sellcur, trade.sellval, trade.feeval,
                    trade.exchange)

        elif not trade.sellcur or trade.sellval == 0:
            # Paid nothing, so it must be a deposit:
            log.info("Depositing %.8f %s at %s (%s, fee: %.8f %s)",
                trade.buyval, trade.buycur,
                trade.exchange, trade.dtime,
                trade.feeval, trade.feecur)
            if trade.feeval > 0 and trade.buycur != trade.feecur:
                self._abort(
                    'Fees with different currency than deposited '
                    'currency not supported.')
            self.deposit(
                    trade.dtime, trade.buycur, trade.buyval, trade.feeval,
                    trade.exchange)

        else:
            # We paid with a currency which must be in some bag and
            # bought another currency with it. This is where we make
            # a profit or a loss, which is the difference between the
            # proceeds we get for selling our held currency minus the
            # expenses we had to initially buy it.

            log.info("Selling %.8f %s for %.8f %s at %s (%s, fee: %.8f %s)",
                 trade.sellval, trade.sellcur, trade.buyval, trade.buycur,
                 trade.exchange, trade.dtime, trade.feeval, trade.feecur)

            # Get the fee's proportion of traded amount:
            if trade.feeval > 0:
                if trade.feecur == trade.sellcur:
                    # fee is included in sellval
                    fee_p = trade.feeval / trade.sellval
                elif trade.feecur == trade.buycur:
                    # fee is not included in buyval
                    fee_p = trade.feeval / (trade.buyval + trade.feeval)
                elif trade.feecur == 'BNB':
                    # Some exchanges, like Binance, offer to pay the fee in
                    # a native currency (BNB for Binance). In that case, convert
                    # the fee amount to the sell currency, calculate the fee
                    # percentage, and initiate a pay() for the fee
                    fee_in_sell_cur = Decimal(self.relation.get_rate(
                        trade.dtime, trade.feecur, trade.sellcur))
                    fee_p = fee_in_sell_cur / (trade.sellval + fee_in_sell_cur)
                    self.pay(trade.dtime, trade.feecur, trade.feeval,
                             trade.exchange, fee_ratio=1, report_info={
                                'kind': 'exchange fee'})
                else:
                    self._abort(
                        'Fees with different currency than one of the '
                        'exchanged currencies not supported.')
            else:
                fee_p = Decimal()

            # If we bought base currency with this trade, use the trade's
            # exchange rate rather than the historic data used by default
            # in self.pay:
            if trade.buycur == self.currency:
                rate = trade.buyval / trade.sellval / (1 - fee_p)
            else:
                rate = None

            # Pay the sold money (including fees):
            prof, proc = self.pay(
                trade.dtime, trade.sellcur, trade.sellval,
                trade.exchange, fee_ratio=fee_p,
                custom_rate=rate,
                report_info={
                    'kind': 'sale',
                    'buy_currency': trade.buycur,
                    'buy_ratio': trade.buyval / trade.sellval})
            self._add_profit(trade.dtime, prof)

            # Did we trade for another foreign/cryptocurrency?
            if trade.buycur != self.currency:
                # We use the total proceeds from our most recent selling
                # excluding the fee's proportion to buy the new currency:
                self.buy_with_base_currency(
                    trade.dtime, trade.buyval, trade.buycur,
                    cost=proc,
                    exchange=trade.exchange)
