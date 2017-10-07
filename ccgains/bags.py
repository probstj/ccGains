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


class Bag(object):
    def __init__(self, time, currency, amount, cost_currency, cost):
        """A bag holds an amount of currency bought with cost
        (in both, any fees are already subtracted).

        """
        self.original_amount = Decimal(amount)
        self.current_amount = self.original_amount
        self.currency = currency
        # time of purchase:
        self.time = time
        # total cost, incl. fees:
        self.original_cost = Decimal(cost)
        self.base_value = self.original_cost
        self.cost_currency = cost_currency
        self.price = self.original_cost / self.original_amount

    def spend(self, amount):
        """Spend some amount out of this bag. This updates the current amount
        and the base value, but leaves the price constant.
        Returns the remainder of *amount* after the spent amount of this bag
        was substracted.

        """
        amount = Decimal(amount)
        if amount >= self.current_amount:
            unspent = amount - self.current_amount
            self.current_amount = 0
            self.base_value = 0
            print 'emptied bag. unspent:', unspent
            return unspent
        self.current_amount -= amount
        self.base_value = self.price * self.current_amount
        print 'spent amount', amount, '; remaining in bag:', self.current_amount
        return 0

    def is_empty(self):
        return self.current_amount == 0


class BagFIFO(object):
    def __init__(self, base_currency, relation):
        """Create a BagFIFO object.

        params: base_currency:
            The base currency (string, e.g. "EUR"). All bag's values
            (the money spent for them at buying time) will be recorded
            in this currency and finally the gain will be calculated
            for this currency.

        :param relation:
            A CurrencyRelation object which serves exchange rates
            between all currencies involved in trades which will later
            be added to this BagFIFO.

        """
        self.currency = str(base_currency).upper()
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
                ("time", [b.time for b in self.bags]),
                ("amount", [b.current_amount for b in self.bags]),
                ("currency", [b.currency for b in self.bags]),
                ("value", [b.base_value for b in self.bags]),
                ("valcur", [b.cost_currency for b in self.bags])
            ]
        return pd.DataFrame.from_items(d)

    def __repr__(self):
        return str(self.to_data_frame())

    def buy_with_base_currency(self, time, amount, currency, cost):
        """Create a new bag with *amount* *currency*. The *cost* is
        paid in base currency, so no other bag is emptied. Both
        *amount* and *cost* should be without any fees.

        """
        if amount <= 0:
            return
        self.bags.append(Bag(
                time=time,
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

        Withdrawal fees must be paid separately with `pay_fees`.

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

        """
        total = self.totals.get(currency, 0)
        on_hold = self.on_hold.get(currency, 0)
        if amount > total - on_hold:
            raise ValueError(
                "Withdrawn amount ({1} {0}) higher than total available "
                "({2} {0}). ({3} {0} is on hold already)".format(
                        currency, amount, total, on_hold))
        self.on_hold[currency] = on_hold + amount

    def deposit(self, amount, currency):
        """Deposit *amount* *currency* into an exchange, making it available
        for trading.

        The pair `withdraw` and `deposit` is used for transfers of the
        same currency from one exhange to another.

        Fees must be paid separately with `pay_fees`.

        If the amount is more than the amount withdrawn before, a ValueError
        will be raised.

        See also `withdraw`.

        """
        on_hold = self.on_hold.get(currency, 0)
        if amount > on_hold:
            raise ValueError(
                "Trying to deposit more money ({1} {0}) than was "
                "withdrawn before ({2}, {0}).".format(
                        currency, amount, on_hold))
        self.on_hold[currency] = on_hold - amount

    def pay_fees(self, amount, currency):
        """Pay *amount* fees with *currency*. The fees are taken out of
        the first bag with the proper currency. The bag's price is not
        changed, but it's current amount and value are decreased.

        If the fees are higher than available total amount, ValueError
        is raised.

        """
        total = self.totals.get(currency, 0)
        on_hold = self.on_hold.get(currency, 0)
        if amount > total - on_hold:
            raise ValueError(
                "Fees ({1} {0}) higher than total available "
                "({2} {0}). ({3} {0} is on hold)".format(
                        currency, amount, total, on_hold))
        # remove from first bag(s):
        to_pay = amount
        while to_pay > 0:
            # Find bags with this currency and empty them to pay for
            # this, starting from first non-empty bag (FIFO):
            i = self.first_filled_bag
            while self.bags[i].currency != currency:
                i += 1
            # spend returns remaining amount that still needs to be paid:
            to_pay = self.bags[i].spend(to_pay)

            # update self.first_filled_bag in case a bag was emptied:
            while self.bags[self.first_filled_bag].is_empty():
                self.first_filled_bag += 1
        self.totals[currency] = total - amount

    def trade(self, time):
        pass

    def process_trade(self, trade):
        print 'processing trade:\n' + trade.to_csv_line()
        if trade.sellcur == self.currency:
            # Paid for with our base currency, simply add new bag:
            self.buy_with_base_currency(
                    time=trade.time,
                    amount=trade.buyval,
                    currency=trade.buycur,
                    cost=trade.sellval)

        elif not trade.sellcur or trade.sellval == 0:
            # Paid nothing, so it must be a deposit:
            self.deposit(trade.buyval, trade.buycur)
            # any fees?
            if trade.feeval > 0:
                self.pay_fees(trade.feeval, trade.feecur)

        elif not trade.buycur or trade.buyval == 0:
            # Got nothing, so it must be a withdrawal:
            self.withdraw(trade.sellval, trade.sellcur)
            # any fees?
            if trade.feeval > 0:
                self.pay_fees(trade.feeval, trade.feecur)

        else: #TODO: check & use relation to create new bag with `buy_with_base_currency`
            # We paid with a currency which must be in some bag and
            # bought another currency.
            to_pay = trade.sellval
            while to_pay > 0:
                # Find bags with this currency and empty them to pay for
                # this, starting from first non-empty bag (FIFO):
                i = self.first_filled_bag
                while self.bags[i].currency != trade.sellcur:
                    i += 1
                print 'spending from bag', i
                # spend returns remaining amount that still needs to be paid:
                to_pay = self.bags[i].spend(to_pay)
                if self.bags[i].is_empty():
                    print 'bag was emptied'

                # update self.first_filled_bag in case a bag was emptied:
                while self.bags[self.first_filled_bag].is_empty():
                    self.first_filled_bag += 1
            self.totals[trade.sellcur] -= trade.sellval
            self.totals[trade.buycur] = (
                    self.totals.get(trade.buycur, Decimal()) + trade.buyval)
            print 'amount spent:', trade.sellval, '(remaining:', to_pay, ')\n\n'
