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

import ccgains
import logging, sys
import pandas as pd


############################
####### Setup logger #######
############################

logger = logging.getLogger('ccgains')
logger.setLevel(logging.DEBUG)
# This is my highest logger, don't propagate to root logger:
logger.propagate = 0
# Reset logger in case any handlers were already added:
for h in logger.handlers[::-1]:
    h.close()
    logger.removeHandler(h)
# Create file handler which logs even debug messages
fh = logging.FileHandler('debug.log', mode='w')
fh.setLevel(logging.DEBUG)
# Create console handler for debugging:
ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(logging.DEBUG)
# Create formatters and add them to the handlers
fhformatter = logging.Formatter(
    '%(asctime)s %(levelname)-8s - %(module)13s -> %(funcName)-13s: '
    '%(message)s')
chformatter = logging.Formatter('%(levelname)-8s: %(message)s')
fh.setFormatter(fhformatter)
ch.setFormatter(chformatter)
# Add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)



########################################
####### Calculate taxable profit #######
########################################

def main():
    # Load list of BTC historical prices in EUR:
    # (file from http://api.bitcoincharts.com/v1/csv/btcdeEUR.csv.gz)
    h1 = ccgains.HistoricDataCSV('../data/bitcoin_de_EUR.csv', 'EUR/BTC')
    # Create HistoricData that fetches BTC_XMR rates from Poloniex.com:
    h2 = ccgains.HistoricDataAPI('../data', 'btc/xmr')
    # Create a CurrencyRelation object that serves exchange rates:
    rel = ccgains.CurrencyRelation(h1, h2)

    # Create the BagFIFO that calculates taxable profit from trades.
    bf = ccgains.BagFIFO('EUR', rel)

    # Load a list of trades:
    th = ccgains.TradeHistory.from_csv('./example_trades.csv')

    for trade in th.tlist:
        bf.process_trade(trade)

    logger.info("State of bags: \n%s\n",
                '    ' + '\n    '.join(str(bf).split('\n')))
    logger.info("Totals: %s", str(bf.totals))
    logger.info("of which are not available: %s", str(bf.on_hold))
    print("Profit: %s %.2f " % (bf.currency, bf.profit))

if __name__ == "__main__":
    main()

