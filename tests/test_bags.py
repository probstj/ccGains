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

from __future__ import division

import unittest

from ccgains import trades, historic_data, relations, bags
import pandas as pd
import numpy as np
from decimal import Decimal as D
import logging
try:
    # for Python2:
    from StringIO import StringIO
    # in Python 2, io.StringIO won't work
except ImportError:
    # Python 3:
    from io import StringIO


class TestBagFIFO(unittest.TestCase):

    def setUp(self):
        self.logger = logging.getLogger('ccgains')
        self.logger.setLevel(logging.DEBUG)
        # Create console handler for debugging:
        self.handler = logging.StreamHandler()
        self.handler.setLevel(logging.DEBUG)
        # Create formatters and add them to the handlers
        chformatter = logging.Formatter('%(name)-13s %(levelname)-8s: %(message)s')
        self.handler.setFormatter(chformatter)
        self.logger.addHandler(logging.NullHandler())
        # Add the handlers to the logger
        # (uncomment this to enable output for all tests):
        #self.logger.addHandler(self.handler)

        # Make up some historic data:
        self.rng = pd.date_range('2017-01-01', periods=5, freq='D', tz='UTC')
        h1 = historic_data.HistoricData('EUR/BTC')
        h1.data = pd.Series(
                data=map(D, np.linspace(1000, 3000, num=5)), index=self.rng)
        h2 = historic_data.HistoricData('XMR/BTC')
        h2.data = pd.Series(
                data=map(D, np.linspace(50, 30, num=5)), index=self.rng)
        self.rel = relations.CurrencyRelation(h1, h2)

    def tearDown(self):
        for h in self.logger.handlers[::-1]:
            h.close()
            self.logger.removeHandler(h)

    def log_bags(self, bagfifo):
        self.logger.info("State of bags: \n%s",
                '    ' + '\n    '.join(str(bagfifo).split('\n')))

    def trading_set(
            self, bagfifo, budget, currency, dayslist, currlist, feelist):
        """Starting with a budget, exchange all of the available budget
        every day in a given list to another currency.

        The trades will be processed by *bagfifo* and exchange rates
        taken from self.rel. Make sure that the involved currencies'
        exchange rates for the given days are available in self.rel.

        :param bagfifo: The BagFIFO object which will process the trades
        :param budget: The starting budget
        :param currency: The currency of starting budget
        :param dayslist: List of datetimes. On each of these days, one
            currency exchange, using all of the available budget in
            whatever currency that day, will be made.
        :param currlist: List of currencies, same length as *dayslist*.
            Each day, the available budget will be exchanged into
            the day's currency in this list.
        :param feelist: List of (fee_portion, fee_currency)-tuples, same
            length as *dayslist*. For each day's trade, a ratio of
            the budget (or currency traded into) will be used for paying
            the exchange fee. This fee amounts to `fee_portion * budget`
            or `fee_portion * budget * exhange_rate`, depending on
            fee_currency.
        :returns: The budget after the last trade, i.e. the available
            amount of currency currlist[-1].

        Examine *bagfifo* to see profits etc. afterwards.

        Some intermediate results about the profits and bag's status
        will be logged (info level). To see this, add a handler to
        self.logger before calling this.

        """
        current_budget = D(budget)
        current_curr = currency
        for i, day in enumerate(dayslist):
            to_curr = currlist[i]
            fee_p, fee_c = D(feelist[i][0]), feelist[i][1]
            rate = D(self.rel.get_rate(day, current_curr, to_curr))
            if fee_c == current_curr or fee_p == 0:
                fee = current_budget * fee_p
                to_amount = rate * (current_budget - fee)
            elif fee_c == to_curr:
                to_amount = rate * current_budget
                fee = to_amount * fee_p
                to_amount -= fee
            else:
                raise ValueError(
                    'The fee currency must be one of the two available '
                    'currencies on the given day: either the current '
                    'budget\'s or the currency to be traded into.')
            trade = trades.Trade(
                    'Trade', day, to_curr, to_amount,
                    current_curr, current_budget, fee_c, fee)
            bagfifo.process_trade(trade)
            self.log_bags(bagfifo)
            self.logger.info(
                    "Profit so far: %.2f %s\n",
                    bagfifo.profit, bagfifo.currency)
            current_budget = to_amount
            current_curr = to_curr
        return to_amount

    def test_trading_profits_no_fees(self):
        # Add handler to the logger (uncomment this to enable output)
        #self.logger.addHandler(self.handler)

        bagfifo = bags.BagFIFO('EUR', self.rel)
        budget=1000
        # Make up and process some trades:
        proceeds = self.trading_set(
            bagfifo,
            budget=budget,
            currency='EUR',
            dayslist=[self.rng[0], self.rng[2], self.rng[4]],
            currlist=['BTC', 'XMR', 'EUR'],
            feelist=[(0, ''), (0, ''), (0, '')])

        # check correct profit:
        self.assertEqual(proceeds - budget, bagfifo.profit)
        # check that bagfifo is empty and cleaned up:
        self.assertFalse(bagfifo.totals)
        self.assertFalse(bagfifo.bags)
        self.assertFalse(bagfifo.in_transit)

    def test_trading_profits_with_fees(self):
        # Add handler to the logger (uncomment this to enable output)
        #self.logger.addHandler(self.handler)

        budget=1000
        # List of fee percentages to be tested:
        fee_p = [D('0.00025'), D(1)/D(3), D(2)/D(3)]
        days = [self.rng[0], self.rng[2], self.rng[4]]
        currlist = ['BTC', 'XMR', 'EUR']
        for fee in fee_p:
            for trade_to_fee in range(len(currlist)):
                for i in range(2):
                    feelist = [(0, '')] * len(currlist)
                    feelist[trade_to_fee] = (fee, currlist[trade_to_fee - i])
                    self.logger.info("Testing fee list %s" % feelist)
                    self.logger.info("Working with new empty BagFIFO object")
                    bagfifo = bags.BagFIFO('EUR', self.rel)
                    # Make up and process some trades:
                    proceeds = self.trading_set(
                        bagfifo,
                        budget=budget,
                        currency='EUR',
                        dayslist=days,
                        currlist=currlist,
                        feelist=feelist)

                    # check correct profit:
                    self.assertEqual(proceeds - budget, bagfifo.profit)
                    # check that bagfifo is empty and cleaned up:
                    self.assertFalse(bagfifo.totals)
                    self.assertFalse(bagfifo.bags)
                    self.assertFalse(bagfifo.in_transit)

    def test_bag_cost_after_trading_with_fees(self):
        # Add handler to the logger (uncomment this to enable output)
        #self.logger.addHandler(self.handler)

        budget=1000
        # List of fee percentages to be tested:
        fee_p = [0, D('0.00025'), D(1)/D(3), D(2)/D(3)]
        days = [self.rng[0], self.rng[2]]
        currlist = ['BTC', 'XMR']
        for fee in fee_p:
            for fee_cur in currlist:
                bagfifo = bags.BagFIFO('EUR', self.rel)
                self.logger.info("Working with new empty BagFIFO object")
                # Make up and process some trades:
                self.trading_set(
                    bagfifo,
                    budget=budget,
                    currency='EUR',
                    dayslist=days,
                    currlist=currlist,
                    feelist=[(0, ''), (fee, fee_cur)])

                self.assertEqual(
                    bagfifo.bags[''][-1].cost, budget + bagfifo.profit)

    def test_saving_loading(self):
        # Add handler to the logger (uncomment this to enable output)
        #self.logger.addHandler(self.handler)

        bagfifo = bags.BagFIFO('EUR', self.rel)

        # Make up some transactions:
        budget = 1000
        day1 = self.rng[0]
        day2 = self.rng[2]
        day3 = self.rng[4]
        btc = self.rel.get_rate(day1, 'EUR', 'BTC') * budget
        t1 = trades.Trade('Buy', day1, 'BTC', btc, 'EUR', budget)
        # also include withdrawal and deposit:
        t2 = trades.Trade('Withdraw', day1, '', 0, 'BTC', btc / 3)
        t3 = trades.Trade('Deposit', day2, 'BTC', btc / 3, '', 0)
        xmr = self.rel.get_rate(day2, 'BTC', 'XMR') * btc
        t4 = trades.Trade(
                'Trade', day2, 'XMR', xmr, 'BTC', btc, 'XMR', '0')
        proceeds = self.rel.get_rate(day3, 'XMR', 'EUR') * xmr
        t5 = trades.Trade(
                'Trade', day3, 'EUR', proceeds, 'XMR', xmr, '', '0')

        # Only process first two transactions, so we have a bag in
        # bagfifo.bags and one in bagfifo.in_transit to save:
        for t in [t1, t2]:
            bagfifo.process_trade(t)
            self.log_bags(bagfifo)
            self.logger.info("Profit so far: %.2f %s\n",
                             bagfifo.profit, bagfifo.currency)

        # save state
        outfile = StringIO()
        bagfifo.save(outfile)
        # create new BagFIFO and restore state:
        bf2 = bags.BagFIFO('EUR', self.rel)
        outfile.seek(0)
        bf2.load(outfile)

        # skip bf2.bags, bf2.in_transit and bf2.report, since the bags
        # and the report are new objects:
        excl = ['bags', 'in_transit', 'report']
        self.assertDictEqual(
            {k:v for k, v in bagfifo.__dict__.items() if k not in excl},
            {k:v for k, v in bf2.__dict__.items() if k not in excl})
        # But the bags' contents must be equal:
        for ex in bagfifo.bags:
            for i, b in enumerate(bagfifo.bags[ex]):
                self.assertDictEqual(b.__dict__, bf2.bags[ex][i].__dict__)
        for cur in bagfifo.in_transit:
            for i, b in enumerate(bagfifo.in_transit[cur]):
                self.assertDictEqual(
                    b.__dict__, bf2.in_transit[cur][i].__dict__)
        # We did not pay anything yet, thus, the report should be empty:
        self.assertListEqual(bagfifo.report.data, bf2.report.data)
        self.assertListEqual(bf2.report.data, [])

        # process the rest of the transactions:
        for t in [t3, t4, t5]:
            bagfifo.process_trade(t)
            bf2.process_trade(t)
            self.log_bags(bagfifo)
            self.logger.info("Profit so far: %.2f %s\n",
                             bagfifo.profit, bagfifo.currency)

        # Now, bags lists should be empty, but we still need to
        # check the report manually:
        self.assertDictEqual(
            {k:v for k, v in bagfifo.__dict__.items() if k != 'report'},
            {k:v for k, v in bf2.__dict__.items() if k != 'report'})
        self.assertListEqual(bagfifo.report.data, bf2.report.data)


if __name__ == '__main__':
    unittest.main()
