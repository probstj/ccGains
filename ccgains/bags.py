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
import json

import logging
log = logging.getLogger(__name__)


def _json_default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    elif isinstance(obj, Bag):
        return obj.__dict__
    elif isinstance(obj, pd.Timestamp):
        return str(obj)
    else:
        raise TypeError(repr(obj) + " is not JSON serializable")

def _json_to_bagfifo_hook(obj):
    if 'bags' in obj:
        # obj seems to be the JSON-ified BagFIFO
        obj['bags'] = [Bag(**bagkw) for bagkw in obj['bags']]
        obj['profit'] = Decimal(obj['profit'])
        for key in ['totals', 'on_hold']:
            obj[key] = {k: Decimal(v) for k, v in obj[key].items()}
        obj['_last_date'] = pd.Timestamp(obj['_last_date'])
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
        self.dtime = pd.Timestamp(dtime)
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

        :returns: the tuple (spent_amount, bvalue, remainder),
            where
                - *spent_amount* is the amount taken out of the bag, in
                  units of self.currency;
                - *bvalue* is the base value of the spent amount, in
                  units of self.cost_currency;
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
    def __init__(self, base_currency, relation):
        """Create a BagFIFO object.

        param: base_currency:
            The base currency (string, e.g. "EUR"). All bag's values
            (the money spent for them at buying time) will be recorded
            in units of this currency and finally the gain will be
            calculated for this currency.

        :param relation:
            A CurrencyRelation object which serves exchange rates
            between all currencies involved in trades which will later
            be added to this BagFIFO.

        """
        self.currency = str(base_currency).upper()
        self.relation = relation
        # The profit (or loss if negative), recorded in self.currency:
        self.profit = Decimal(0)
        self.bags = []
        # dictionary of {currency: total amount};
        self.totals = {}
        # dictionary of {curreny: amount on hold},
        # An amount is on hold e.g. if it is transfered from one
        # exhange to another. A withrawel puts an amount on hold,
        # a deposit removes the held amount:
        self.on_hold = {}
        # TODO: Another option (user selectable) would be to place an
        # amount on hold directly in the bags, where the first bag in
        # the chain is put on hold first. Then a transaction can
        # be done with a bag which is further down in the chain, while
        # the money in a prior bag is on hold - I am not sure if this
        # is allowed tax wise though.

        self._last_date = pd.Timestamp(0, tz='UTC')
        self.num_created_bags = 0

    def _check_order(self, dtime):
        """Raise ValueError if *dtime* is older than the last
        checked datetime. Also complains (raises an error) if
        *dtime* does not include timezone information.

        """
        if dtime.tzinfo is None:
            raise ValueError(
                'To eliminate ambiguity, only transactions including '
                'timezone information in their datetime are allowed.')
        if dtime < self._last_date:
            raise ValueError(
                'Trades must be processed in order. Last processed trade '
                'was from %s, this one is from %s' % (
                        self._last_date, dtime))
        self._last_date = pd.Timestamp(dtime)

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
            default=_json_default, **kwargs)

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
                default=_json_default, indent=4)
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
                    object_hook=_json_to_bagfifo_hook)
            self.__dict__.update(d)
        else:
            with open(filepath_or_buffer, 'r') as f:
                self.load(f)

    def to_data_frame(self):
        d = [
                ("id", [b.id for b in self.bags]),
                ("date", [b.dtime for b in self.bags]),
                ("amount", [b.amount for b in self.bags]),
                ("currency", [b.currency for b in self.bags]),
                ("cost", [b.cost for b in self.bags]),
                ("costcur", [b.cost_currency for b in self.bags])
            ]
        return pd.DataFrame.from_items(d).set_index('id')

    def __str__(self):
        return self.to_data_frame().to_string(
                formatters={'amount': '{0:.8f}'.format,
                            'cost': '{0:.8f}'.format})

    def buy_with_base_currency(self, dtime, amount, currency, cost):
        """Create a new bag with *amount* money in *currency*.

        Creation time of the bag is the datetime *dtime*. The *cost* is
        paid in base currency, so no money is taken out of another bag.
        Any fees for the transaction should already have been
        substracted from *amount*, but included in *cost*.

        """
        self._check_order(dtime)
        amount = Decimal(amount)
        if amount <= 0:
            return
        if currency == self.currency:
            raise ValueError('Buying the base currency is not possible.')
        self.bags.append(Bag(
                id=self.num_created_bags + 1,
                dtime=dtime,
                currency=currency,
                amount=amount,
                cost_currency=self.currency,
                cost=cost))
        self.num_created_bags += 1
        self.totals[currency] = (
                self.totals.get(currency, Decimal()) + amount)

    def withdraw(self, dtime, currency, amount, fee):
        """Withdraw *amount* monetary units of *currency* from an
        exchange for a *fee* (also given in *currency*). The fee is
        included in amount. The withdrawal happened at datetime *dtime*.

        The pair of methods `withdraw` and `deposit` is used for
        transfers of the same currency from one exhange to another.

        If the amount is more than the total available, a ValueError
        will be raised.

        ---

        The amount (minus fee) will not be taken out of bags, but marked
        as 'on-hold', which decreases the total amount of currency
        available for trades. Call `deposit` to decrease the amount
        'on hold'. A trade done while some money is still in transit
        (i.e. withdrawn, but not deposited yet), will still be paid for
        with money from the first bag (FIFO).

        Note: This is done this way because I am not sure if the tax
        agency would allow to park money by sending some to a wallet.
        This should be made user-configurable in future.

        ---

        Losses made by fees (which must be directly resulting from and
        connected to trading activity!) are substracted from the total
        taxable profit (recorded in base currency).

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
        if currency == self.currency:
            raise ValueError(
                    'Withdrawing the base currency is not possible.')
        amount = Decimal(amount)
        fee = Decimal(fee)
        total = self.totals.get(currency, 0)
        on_hold = self.on_hold.get(currency, 0)
        if amount > total - on_hold:
            raise ValueError(
                "Withdrawn amount ({1} {0}) higher than total available "
                "({2} {0}, of which {3} {0} are on hold already).".format(
                        currency, amount, total, on_hold))

        # any fees?
        if fee > 0:
            _, cost, _ = self.pay(dtime, fee, currency, is_fee=True)
            self.profit -= cost
            log.info("Taxable loss due to fees: %.3f %s",
                     -cost, self.currency)

        self.on_hold[currency] = on_hold + amount - fee

    def deposit(self, dtime, currency, amount, fee):
        """Deposit *amount* monetary units of *currency* into an
        exchange for a *fee* (also given in *currency*), making it
        available for trading. The fee is included in amount. The
        deposit happened at datetime *dtime*.

        The pair of methods `withdraw` and `deposit` is used for
        transfers of the same currency from one exhange to another.

        If the amount is more than the amount withdrawn before (minus
        fees), a warning will be printed and a bag created with a base
        cost of 0.

        See also `withdraw` about the money placed 'on-hold' and about
        the handling of fees.

        """
        self._check_order(dtime)
        if currency == self.currency:
            raise ValueError(
                    'Depositing the base currency is not possible.')
        amount = Decimal(amount)
        fee = Decimal(fee)
        on_hold = self.on_hold.get(currency, 0)
        if amount > on_hold:
            diff = amount - on_hold
            log.warning(
                "Depositing more money ({1} {0}) than "
                "was withdrawn before ({2} {0}).".format(
                        currency, amount, on_hold)
                + " Assuming the additional amount ({1} {0}) was bought "
                "with 0 {2}.".format(currency, diff, self.currency))
            self.on_hold[currency] = Decimal()
            self.buy_with_base_currency(dtime, diff, currency, 0)
        else:
            self.on_hold[currency] = on_hold - amount
        # any fees?
        if fee > 0:
            _, cost, _ = self.pay(dtime, fee, currency, is_fee=True)
            self.profit -= cost
            log.info("Taxable loss due to fees: %.3f %s",
                     -cost, self.currency)

    def pay(self, dtime, amount, currency, is_fee=False):
        """Pay *amount* with *currency*. The money is taken out of
        the first bag with the proper currency first. The bag's price
        is not changed, but it's current amount and base value are
        decreased. *dtime*, a datetime, is the time of payment.

        Set *is_fee* to tell if this payment is just for fees or not.
        This only changes the logging output, nothing else. The returned
        tuple is the same in both cases; whether fees are a taxable loss
        or not must thus be decided by the caller.

        If the amount is higher than available total amount, ValueError
        is raised.

        :returns: a tuple (tprofit, expenses, revenue), all in units of
            the base currency, where *expenses* is the original amount
            paid for the amount taken out of bags, *revenue* is the
            worth of this amount on time of payment, and *tprofit* is
            the taxable profit, i.e the difference (revenue - expenses)
            if all involved bags where purchased less than a year ago,
            otherwise accordingly less due to tax-free revenue of bags
            held for more than a year.

        """
        self._check_order(dtime)
        if currency == self.currency:
            raise ValueError(
                'Payments with the base currency are not relevant here.')
        total = self.totals.get(currency, 0)
        on_hold = self.on_hold.get(currency, 0)
        amount = Decimal(amount)
        if amount > total - on_hold:
            raise ValueError(
                "Amount to pay ({1} {0}) is higher than total available "
                "({2} {0}). ({3} {0} is on hold)".format(
                        currency, amount, total, on_hold))
        # expenses (original cost of spent money):
        cost = Decimal()
        # revenue (value of spent money at dtime):
        rev = Decimal()
        # taxable profit,
        # i.e. rev - cost for bags purchased less than one year ago:
        tprofit = Decimal()
        # due payment:
        to_pay = amount
        log.info(
                "Paying %.8f %s%s",
                to_pay, currency, " (fees)" if is_fee else "")
        # Find bags with this currency and use them to pay for
        # this, starting from first bag (FIFO):
        i = 0
        while to_pay > 0:
            while self.bags[i].currency != currency:
                i += 1
            bag = self.bags[i]

            # Spend as much as possible from this bag:
            log.info("Paying%s with bag from %s, containing %.8f %s",
                     " fee" if is_fee else "",
                     bag.dtime, bag.amount, bag.currency)
            spent, bvalue, remainder = bag.spend(to_pay)
            log.info("Contents of bag after payment: %.8f %s (spent %.8f %s)",
                 bag.amount, bag.currency, spent, currency)

            # The revenue is the value of spent amount at dtime:
            rate = Decimal(
                    self.relation.get_rate(dtime, currency, self.currency))
            thisrev = spent * rate
            rev += thisrev
            cost += bvalue
            short_term = relativedelta(
                    dtime.astimezone(bag.dtime.tz), bag.dtime).years < 1
            if short_term:
                tprofit += (thisrev - bvalue)

            if not is_fee:
                log.info("Profits in this transaction:\n"
                     "    Original bag cost: %.2f %s (Price %.8f %s/%s)\n"
                     "    Proceeds         : %.2f %s (Price %.8f %s/%s)\n"
                     "    Profit/loss      : %.2f %s\n"
                     "    Taxable?         : %s (held for %s than a year)",
                     bvalue, self.currency, bag.price, bag.cost_currency,
                     currency,
                     thisrev, self.currency, rate, self.currency, currency,
                     (thisrev - bvalue), self.currency,
                     'yes' if short_term else 'no',
                     'less' if short_term else 'more')

            to_pay = remainder
            if to_pay > 0:
                log.info("Still to be paid with another bag: %.8f %s",
                     to_pay, currency)
            if bag.is_empty():
                del self.bags[i]
            else:
                i += 1

        self.totals[currency] = total - amount

        return tprofit, cost, rev

    def process_trade(self, trade):
        log.info(
            'Processing trade: %s', trade.to_csv_line().strip('\n'))
        self._check_order(trade.dtime)
        if trade.buyval < 0 or trade.sellval < 0 or trade.feeval < 0:
            raise ValueError(
                'Negative values for buy, sell or fee amount not supported.')
        if trade.sellcur == self.currency and trade.sellval != 0:
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
                    cost=trade.sellval)

        elif not trade.sellcur or trade.sellval == 0:
            # Paid nothing, so it must be a deposit:
            log.info("Depositing %.8f %s at %s (%s, fee: %.8f %s)",
                trade.buyval, trade.buycur,
                trade.exchange, trade.dtime,
                trade.feeval, trade.feecur)
            if trade.feeval > 0 and trade.buycur != trade.feecur:
                raise ValueError(
                    'Sorry, fees with different currency than deposited '
                    'currency not supported.')
            self.deposit(
                    trade.dtime, trade.buycur, trade.buyval, trade.feeval)

        elif not trade.buycur or trade.buyval == 0:
            # Got nothing, so it must be a withdrawal:
            log.info("Withrawing %.8f %s from %s (%s, fee: %.8f %s)",
                trade.sellval, trade.sellcur,
                trade.exchange, trade.dtime,
                trade.feeval, trade.feecur)
            if trade.feeval > 0 and trade.sellcur != trade.feecur:
                raise ValueError(
                    'Fees with different currency than withdrawn '
                    'currency not supported.')
            self.withdraw(
                    trade.dtime, trade.sellcur, trade.sellval, trade.feeval)

        else:
            # We paid with a currency which must be in some bag and
            # bought another currency with it. This is where we make
            # a profit or a loss, which is the difference between the
            # revenue we get for selling our held currency minus the
            # expenses we had to initially buy it:
            log.info("Selling %.8f %s for %.8f %s at %s (%s)",
                 trade.sellval, trade.sellcur, trade.buyval, trade.buycur,
                 trade.exchange, trade.dtime)
            tprofit, _, revenue = self.pay(
                    trade.dtime, trade.sellval, trade.sellcur)
            self.profit += tprofit

            # Did we trade for another foreign/cryptocurrency?
            if trade.buycur != self.currency:
                # We use the full *revenue* from our most recent selling
                # to buy the new currency:
                self.buy_with_base_currency(
                    trade.dtime, trade.buyval, trade.buycur, revenue)
