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
        self.bf = bags.BagFIFO('EUR', self.rel)

    def tearDown(self):
        for h in self.logger.handlers[::-1]:
            h.close()
            self.logger.removeHandler(h)

    def log_bags(self, bagfifo):
        self.logger.info("State of bags: \n%s",
                '    ' + '\n    '.join(str(bagfifo).split('\n')))

    def test_trading_profits_no_fees(self):
        # Add handler to the logger (uncomment this to enable output)
        #self.logger.addHandler(self.handler)

        # Make up some trades:
        budget = 1000
        day1 = self.rng[0]
        day2 = self.rng[2]
        day3 = self.rng[4]
        btc = self.rel.get_rate(day1, 'EUR', 'BTC') * budget
        t1 = trades.Trade('Buy', day1, 'BTC', btc, 'EUR', budget)
        xmr = self.rel.get_rate(day2, 'BTC', 'XMR') * btc
        t2 = trades.Trade(
                'Trade', day2, 'XMR', xmr, 'BTC', btc, 'XMR', '0')
        proceeds = self.rel.get_rate(day3, 'XMR', 'EUR') * xmr
        t3 = trades.Trade(
                'Trade', day3, 'EUR', proceeds, 'XMR', xmr, '', '0')
        self.test_trades = [t1, t2, t3]
        for t in self.test_trades:
            self.bf.process_trade(t)
            self.log_bags(self.bf)
            self.logger.info("Profit so far: %.2f %s\n",
                             self.bf.profit, self.bf.currency)

        for tot in self.bf.totals.values():
            self.assertEqual(tot, 0)
        self.assertEqual(proceeds - budget, self.bf.profit)

    def test_trading_profits_with_fee(self):
        # Add handler to the logger (uncomment this to enable output)
        #self.logger.addHandler(self.handler)

        # Make up some trades:
        budget = 1000
        # 2.5% fee:
        fee_p = D('0.025')
        day1 = self.rng[0]
        day2 = self.rng[2]
        day3 = self.rng[4]
        btc = self.rel.get_rate(day1, 'EUR', 'BTC') * budget
        t1 = trades.Trade('Buy', day1, 'BTC', btc, 'EUR', budget)
        self.bf.process_trade(t1)
        p1 = self.bf.profit
        self.log_bags(self.bf)
        self.logger.info("Profit so far: %.2f %s\n",
                         p1, self.bf.currency)

        xmr = self.rel.get_rate(day2, 'BTC', 'XMR') * btc
        xmrfee = xmr * fee_p
        xmr -= xmrfee
        t2 = trades.Trade(
                'Trade', day2, 'XMR', xmr, 'BTC', btc, 'XMR', xmrfee)
        self.bf.process_trade(t2)
        self.log_bags(self.bf)
        self.logger.info("Profit so far: %.2f %s\n",
                         self.bf.profit, self.bf.currency)
        # expected profit without fees:
        p02 = self.rel.get_rate(day2, 'BTC', 'EUR') * btc - budget
        # actual profit
        pf2 = self.bf.profit
        # fee in fiat currency:
        ffee = self.rel.get_rate(day2, 'XMR', 'EUR') * xmrfee
        # TODO: The following is not implemented yet. Maybe, if I'll
        # implement it later, it will be a configurable option.
        # With or without it, the end result (i.e. the taxable profit)
        # is the same if all trades have been done in the same year. If
        # it is enabled, the profit immediatly after a trade is a little
        # lower (by the fee losses *ffee*), but therefore the new bag's
        # base value is lower by *ffee*, so the gains when selling the
        # new bag later will be exactly *ffee* higher, making up for
        # the lower profit counted earlier. Thus enabling it, IF the
        # tax agency allows it, would make it possible to push a small
        # amount of profits into the next year or even cancel them
        # completely if the new bag is held for more than a year.
        #self.assertEqual(pf2, p02 - ffee)
        #self.assertEqual(
        #        self.bf.bags[-1].base_value,
        #        (1 - fee_p) * (budget + p02))

        proceeds = self.rel.get_rate(day3, 'XMR', 'EUR') * xmr
        t3 = trades.Trade(
                'Trade', day3, 'EUR', proceeds, 'XMR', xmr, '', '0')
        self.bf.process_trade(t3)
        self.log_bags(self.bf)
        self.logger.info("Profit so far: %.2f %s\n",
                         self.bf.profit, self.bf.currency)

        for tot in self.bf.totals.values():
            self.assertEqual(tot, 0)
        self.assertEqual(proceeds - budget, self.bf.profit)

    def test_saving_loading(self):
        # Add handler to the logger (uncomment this to enable output)
        #self.logger.addHandler(self.handler)

        # Make up some trades:
        budget = 1000
        day1 = self.rng[0]
        day2 = self.rng[2]
        day3 = self.rng[4]
        btc = self.rel.get_rate(day1, 'EUR', 'BTC') * budget
        t1 = trades.Trade('Buy', day1, 'BTC', btc, 'EUR', budget)
        xmr = self.rel.get_rate(day2, 'BTC', 'XMR') * btc
        t2 = trades.Trade(
                'Trade', day2, 'XMR', xmr, 'BTC', btc, 'XMR', '0')
        proceeds = self.rel.get_rate(day3, 'XMR', 'EUR') * xmr
        t3 = trades.Trade(
                'Trade', day3, 'EUR', proceeds, 'XMR', xmr, '', '0')

        # only process first two trades:
        for t in [t1, t2]:
            self.bf.process_trade(t)
            self.log_bags(self.bf)
            self.logger.info("Profit so far: %.2f %s\n",
                             self.bf.profit, self.bf.currency)

        # save state
        outfile = StringIO()
        self.bf.save(outfile)
        # create new BagFIFO and restore state:
        bf2 = bags.BagFIFO('EUR', self.rel)
        outfile.seek(0)
        bf2.load(outfile)

        # skip bf2.bags, since the bags are new objects:
        self.assertDictEqual(
            {k:v for k, v in self.bf.__dict__.items() if k != 'bags'},
            {k:v for k, v in bf2.__dict__.items() if k != 'bags'})
        # But the bags' contents must be equal:
        for i, b in enumerate(self.bf.bags):
            self.assertDictEqual(b.__dict__, bf2.bags[i].__dict__)

        # process another trade:
        self.bf.process_trade(t3)
        bf2.process_trade(t3)

        # equal, because now, bags list should be empty:
        self.assertDictEqual(self.bf.__dict__, bf2.__dict__)


if __name__ == '__main__':
    unittest.main()
