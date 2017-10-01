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
    def __init__(self, base_currency):
        self.currency = base_currency
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

    def process_trade(self, trade):
        print 'processing trade:\n' + trade.to_csv_line()
        if trade.sellcur in ['', self.currency]:
            # Either we paid nothing, which means it must be a deposit,
            # or it is paid for with our base currency:
            # simply add new bag:
            self.bags.append(Bag(
                    time=trade.time,
                    currency=trade.buycur,
                    amount=trade.buyval,
                    cost_currency=trade.sellcur,
                    cost=trade.sellval))
            self.totals[trade.buycur] = (
                    self.totals.get(trade.buycur, Decimal()) + trade.buyval)
       # elif:


        else:
            # We paid with a currency which must be in some bag.
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

                # update self.first_filled_bag if a bag got emptied:
                while self.bags[self.first_filled_bag].is_empty():
                    self.first_filled_bag += 1
            self.totals[trade.sellcur] -= trade.sellval
            self.totals[trade.buycur] = (
                    self.totals.get(trade.buycur, Decimal()) + trade.buyval)
            print 'amount spent:', trade.sellval, '(remaining:', to_pay, ')\n\n'
