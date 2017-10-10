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

import logging
log = logging.getLogger(__name__)


class Bag(object):
    def __init__(self, dtime, currency, amount, cost_currency, cost):
        """Create a bag which holds an *amount* of *currency*.

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

        """
        self.original_amount = Decimal(amount)
        self.current_amount = self.original_amount
        self.currency = currency
        # datetime of purchase:
        self.dtime = dtime
        # total cost, incl. fees:
        self.original_cost = Decimal(cost)
        self.base_value = self.original_cost
        self.cost_currency = cost_currency
        self.price = self.original_cost / self.original_amount

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
        if amount >= self.current_amount:
            result = (
                    self.current_amount,
                    self.base_value,
                    amount - self.current_amount)
            self.current_amount = 0
            self.base_value = 0
            return result
        value = amount * self.price
        self.current_amount -= amount
        self.base_value -= value
        return amount, value, 0

    def is_empty(self):
        return self.current_amount == 0


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
        self.pdbags = pd.DataFrame()
        self.first_filled_bag = 0
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

    def to_data_frame(self):
        d = [
                ("date", [b.dtime for b in self.bags]),
                ("amount", [b.current_amount for b in self.bags]),
                ("currency", [b.currency for b in self.bags]),
                ("cost", [b.base_value for b in self.bags]),
                ("costcur", [b.cost_currency for b in self.bags])
            ]
        return pd.DataFrame.from_items(d)

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
        amount = Decimal(amount)
        if amount <= 0:
            return
        if currency == self.currency:
            raise ValueError('Buying the base currency is not possible.')
        self.bags.append(Bag(
                dtime=dtime,
                currency=currency,
                amount=amount,
                cost_currency=self.currency,
                cost=cost))
        self.totals[currency] = (
                self.totals.get(currency, Decimal()) + amount)

    def withdraw(self, amount, currency):
        """Withdraw *amount* *currency* from an exchange.

        The pair `withdraw` and `deposit` is used for transfers of the
        same currency from one exhange to another.

        Withdrawal fees must be paid separately with `pay`.

        If the amount is more than the total available, a ValueError
        will be raised.

        The amount will not be taken out of bags, but marked as
        'on-hold', which decreases the total amount of currency
        available for trades. Call `deposit` to decrease the amount
        'on hold'. A trade done while some money is still in transit
        (i.e. withdrawn, but not deposited yet), will still be paid for
        with money from the first bag (FIFO).

        Note: This is done this way because I am not sure if the tax
        agency would allow to park money by sending some to a wallet.
        This should be made user-selectable in future.

        """
        if currency == self.currency:
            raise ValueError(
                    'Withdrawing the base currency is not possible.')
        amount = Decimal(amount)
        total = self.totals.get(currency, 0)
        on_hold = self.on_hold.get(currency, 0)
        if amount > total - on_hold:
            raise ValueError(
                "Withdrawn amount ({1} {0}) higher than total available "
                "({2} {0}, of which {3} {0} are on hold already).".format(
                        currency, amount, total, on_hold))
        self.on_hold[currency] = on_hold + amount

    def deposit(self, dtime, amount, currency):
        """Deposit *amount* *currency* into an exchange, making it
        available for trading.

        The pair `withdraw` and `deposit` is used for transfers of the
        same currency from one exhange to another.

        Fees must be paid separately with `pay`.

        If the amount is more than the amount withdrawn before, a
        warning will be printed and a bag created with a base cost of 0.

        See also `withdraw`.

        """
        if currency == self.currency:
            raise ValueError(
                    'Depositing the base currency is not possible.')
        amount = Decimal(amount)
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

    def pay(self, dtime, amount, currency):
        """Pay *amount* with *currency*. The money is taken out of
        the first bag with the proper currency first. The bag's price
        is not changed, but it's current amount and base value are
        decreased. *dtime*, a datetime, is the time of payment.

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
        log.info("Paying %.8f %s", to_pay, currency)
        # Find bags with this currency and use them to pay for
        # this, starting from first non-empty bag (FIFO):
        i = self.first_filled_bag
        while to_pay > 0:
            while (self.bags[i].currency != currency
                   or self.bags[i].is_empty()):
                i += 1
            bag = self.bags[i]

            # Spend as much as possible from this bag:
            log.info("Paying with bag from %s, containing %.8f %s",
                 bag.dtime, bag.current_amount, bag.currency)
            spent, bvalue, remainder = bag.spend(to_pay)
            log.info("Contents of bag after payment: %.8f %s (spent %.8f %s)",
                 bag.current_amount, bag.currency, spent, currency)


            # The revenue is the value of spent amount at dtime:
            rate = Decimal(
                    self.relation.get_rate(dtime, currency, self.currency))
            thisrev = spent * rate
            rev += thisrev
            cost += bvalue
            short_term = relativedelta(dtime, bag.dtime).years < 1
            if short_term:
                tprofit += (thisrev - bvalue)

            log.info("Profits in this transaction:\n"
                 "    Original bag cost: %.2f %s (Price %.8f %s/%s)\n"
                 "    Proceeds         : %.2f %s (Price %.8f %s/%s)\n"
                 "    Profit/loss      : %.2f %s\n"
                 "    Taxable?         : %s (held for %s than a year)",
                 bvalue, self.currency, bag.price, bag.cost_currency, currency,
                 thisrev, self.currency, rate, self.currency, currency,
                 (thisrev - bvalue), self.currency,
                 'yes' if short_term else 'no',
                 'less' if short_term else 'more')

            to_pay = remainder
            if to_pay > 0:
                log.info("Still to be paid with another bag: %.8f %s",
                     to_pay, currency)
            i += 1

        # update self.first_filled_bag:
        while self.bags[self.first_filled_bag].is_empty():
            self.first_filled_bag += 1

        self.totals[currency] = total - amount

        return tprofit, cost, rev

    def process_trade(self, trade):
        log.info(
            'Processing trade: %s', trade.to_csv_line().strip('\n'))
        if trade.sellcur == self.currency and trade.sellval != 0:
            # Paid for with our base currency, simply add new bag:
            # (The cost is directly translated to the base value
            # of the bags)
            self.buy_with_base_currency(
                    dtime=trade.dtime,
                    amount=trade.buyval,
                    currency=trade.buycur,
                    cost=trade.sellval)

        elif not trade.sellcur or trade.sellval == 0:
            # Paid nothing, so it must be a deposit:
            self.deposit(trade.dtime, trade.buyval, trade.buycur)
            # any fees?
            if trade.feeval > 0:
                _, cost, _ = self.pay(
                        trade.dtime, trade.feeval, trade.feecur)
                # TODO make user option how to handle fees.

                # For now, the only logical way how to handle fees
                # (which are directly resulting from and connected to
                # trading activity!), is to count the base value of
                # these fees (recorded in our base currency) as loss:
                self.profit -= cost
                # A quick explanation for this: You buy an amount of
                # Bitcoin for X fiat money, i.e. X fiat is leaving your
                # bank account. Then you trade, fees are paid, then say
                # later you have a little less Bitcoin than you
                # initially bought, due to fees. Then you change your
                # Bitcoin back to fiat, but at a better price than
                # earlier such that coincidentally, you get the same
                # amount X fiat money back into your bank account. For
                # tax purposes, this must equal a profit of zero. The
                # only way to have this result is if fees are losses:
                # For example:
                # - buy 1BTC @ 1000EUR
                # - withdrawal & deposit fees: 0.1BTC ->
                #   0.9BTC @ 900EUR in bag (current total loss: -100EUR)
                # - sell 0.9BTC for 1000EUR ->
                #   revenue 100EUR - total loss 100EUR = profit of 0 EUR
                # - OR: sell 0.9BTC for 2000EUR ->
                #   revenue 1100EUR - 100EUR = profit of 1000EUR

        elif not trade.buycur or trade.buyval == 0:
            # Got nothing, so it must be a withdrawal:
            self.withdraw(trade.sellval, trade.sellcur)
            # any fees?
            if trade.feeval > 0:
                _, cost, _ = self.pay(
                        trade.dtime, trade.feeval, trade.feecur)
                # TODO make user option how to handle fees.
                # For now, fees directly connected with trading
                # activities are losses (see explanation above):
                self.profit -= cost

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
