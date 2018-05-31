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

# import the library
import ccgains

########################################
####### Calculate taxable profit #######
########################################

def main():
    #########################################################################
    # 1. Provide list of BTC historical prices in your native fiat currency #
    #########################################################################

    # Hourly data for a lot of exchanges is available for download at:
    # https://api.bitcoincharts.com/v1/csv/
    # To understand which file to download, consult this list:
    # https://bitcoincharts.com/markets/list/

    # E.g., for EUR prices on Bitcoin.de, download:
    # https://api.bitcoincharts.com/v1/csv/btcdeEUR.csv.gz
    # and place it in the ../data folder.

    # The file consists of three comma-separated columns:
    # the unix timestamp, the price, and the volume (amount traded).

    # Create the HistoricData object by loading the mentioned file and
    # specifying the price unit, i.e. fiat/btc:
    h1 = ccgains.HistoricDataCSV(
        '../data/bitcoin_de_EUR_abridged_as_example.csv.gz', 'EUR/BTC')

    # (Note: the abridged file provided with the source code on Github only
    # covers a small time range - please download the full file yourself)

    #########################################################################
    # 2. Provide source of historical BTC prices for all traded alt coins   #
    #########################################################################

    # For all coins that you possessed at some point, their historical price
    # in your native fiat currency must be known, which can also be derived
    # from their BTC price and the BTC/fiat price given above (or even from
    # their price in any other alt-coin, whose price can be derived, in
    # turn.)

    # This data can be provided from any website that serves this data
    # through an API, or from a csv-file, like above. Note that currently,
    # only the API from Poloniex.com is implemented.

    # Create HistoricData objects to fetch rates from Poloniex.com:
    # (it is important to mention at least all traded coins here)
    h2 = ccgains.HistoricDataAPI('../data', 'btc/xmr')
    h3 = ccgains.HistoricDataAPI('../data', 'btc/eth')
    h4 = ccgains.HistoricDataAPI('../data', 'btc/usdt')
    h5 = ccgains.HistoricDataAPI('../data', 'btc/pasc')
    h6 = ccgains.HistoricDataAPI('../data', 'btc/gnt')


    #########################################################################
    # 3. Add all objects from above into a single 'CurrencyRelation' object #
    #########################################################################

    # Create a CurrencyRelation object that puts all provided HistoricData
    # currencies in relation in order to serve exchange rates for any pair
    # of these currencies:
    rel = ccgains.CurrencyRelation(h1, h2, h3, h4, h5, h6)


    #########################################################################
    # 4. Create the 'BagFIFO', which calculates the capital gains           #
    #########################################################################

    # Create the BagFIFO object that calculates taxable profit from trades
    # using the first-in/first-out method:
    # (this needs to know your native fiat currency and the CurrencyRelation
    # created above)
    bf = ccgains.BagFIFO('EUR', rel)


    #########################################################################
    # 5. Create the object that will load all your trades                   #
    #########################################################################

    # The TradeHistory object provides methods to load your trades from
    # csv-files exported from various exchanges or apps.
    th = ccgains.TradeHistory()


    #########################################################################
    # 6. Load all your trades from csv-files                                #
    #########################################################################

    # Export your trades from exchanges or apps as comma-separated files
    # and append them to the list of trades managed by the TradeHistory
    # object. All trades will be sorted automatically.

    # To load from a supported exchange, use the methods named
    # `append_<exchange_name>_csv` found in TradeHistory (see trades.py).
    # If your exchange is not supported yet, please file a new issue
    # on the GitHub repo https://github.com/probstj/ccgains/issues together
    # with a short example csv exported from your exchange and I will add
    # a method to import it.

    # Append from a Bitcoin.de csv:
    th.append_bitcoin_de_csv(
            './example_csv/bitcoin.de_account_statement_2017_fabricated.csv')

    # Append trades from Poloniex. Deposits, withdrawals and trades are
    # exported separately by Poloniex, import each one separately:
    th.append_poloniex_csv(
            './example_csv/poloniex_depositHistory_2017_fabricated.csv',
            'deposits')
    th.append_poloniex_csv(
            './example_csv/poloniex_tradeHistory_2017_fabricated.csv',
            'trades',
            condense_trades=True)
    th.append_poloniex_csv(
            './example_csv/poloniex_withdrawalHistory_2017_fabricated.csv',
            'withdr')

    # From Bisq (formerly Bitsquare), we need the exported trade history csv
    # and the transaction history csv:
    th.append_bitsquare_csv(
            './example_csv/bisq_trades_2017_fabricated.csv',
            './example_csv/bisq_transactions_2017_fabricated.csv')

    #th.append_monero_wallet_csv('./csv/xmr_wallet_show_transfers')


    #########################################################################
    # 7. Optionally, fix withdrawal fees                                    #
    #########################################################################

    # Some exchanges, like Poloniex, does not include withdrawal fees in
    # their exported csv files. This will try to add these missing fees
    # by comparing withdrawn amounts with amounts deposited on other
    # exchanges shortly after withdrawal. Call this only after all
    # transactions from every involved exchange and wallet were imported.

    # This uses a really simple algorithm, so it is not guaranteed to
    # work in every case, especially if you made withdrawals in tight
    # succession on different exchanges, so please check the output.

    th.add_missing_transaction_fees(raise_on_error=False)


    #########################################################################
    # 8. Optionally, export all trades for future reference                 #
    #########################################################################

    # You can export all imported trades for future reference into a single
    # file, optionally filtered by year.

    # ...either as a comma-separated text file (can be imported into ccgains):
    th.export_to_csv('transactions2017.csv', year=2017)

    # ...or as html or pdf file, with the possibility to filter or rename
    # column headers or contents:
    # (This is an example for a translation into German)
    my_column_names=[
        'Art', 'Datum', 'Kaufmenge', 'Verkaufsmenge', u'Gebühren', u'Börse']
    transdct = {'Purchase': 'Anschaffung',
                'Exchange': 'Tausch', 'Disbursement': 'Abhebung',
                'Deposit': 'Einzahlung', 'Withdrawal': 'Abhebung',
                'Received funds': 'Einzahlung',
                'Withdrawn from wallet': 'Abhebung',
                'Create offer fee: a5ed7482': u'Börsengebühr',
                'Buy BTC' : 'Anschaffung',
                'MultiSig deposit: a5ed7482': 'Abhebung',
                'MultiSig payout: a5ed7482' : 'Einzahlung'}
    th.export_to_pdf('Transactions2017.pdf',
          year=2017, drop_columns=['mark', 'comment'],
          font_size=12,
          caption=u"Handel mit digitalen Währungen %(year)s",
          intro=u"<h4>Auflistung aller Transaktionen zwischen "
                 "%(fromdate)s und %(todate)s:</h4>",
          locale="de_DE",
          custom_column_names=my_column_names,
          custom_formatters={
              'Art': lambda x: transdct[x] if x in transdct else x})


    #########################################################################
    # 9. Now, finally, the calculation is ready to start                    #
    #########################################################################

    # If the calculation run for previous years already, we can load the state
    # of the bags here, no need to calculate everything again:
#    bf.load('./status2016.json')

    # Or, if the current calculation crashed (e.g. you forgot to add a traded
    # currency in #2 above), the file 'precrash.json' will be created
    # automatically. Load it here to continue:
#    bf.load('./precrash.json')

    # The following just looks where to start calculating trades, in case you
    # already calculated some and restarted by loading 'precrash.json':
    last_trade = 0
    while (last_trade < len(th.tlist)
           and th[last_trade].dtime <= bf._last_date):
        last_trade += 1
    if last_trade > 0:
        logger.info("continuing with trade #%i" % (last_trade + 1))

    # Now, the calculation. This goes through your imported list of trades:
    for i, trade in enumerate(th.tlist[last_trade:]):
        # Most of this is just the log output to the console and to the
        # file 'ccgains_<date-time>.log'
        # (check out this file for all gory calculation details!):
        logger.info('TRADE #%i', i + last_trade + 1)
        logger.info(trade)
        # This is the important part:
        bf.process_trade(trade)
        # more logging:
        log_bags(bf)
        logger.info("Totals: %s", str(bf.totals))
        logger.info("Gains (in %s): %s\n" % (bf.currency, str(bf.profit)))


    #########################################################################
    # 10. Save the state of your holdings for the calculation due next year #
    #########################################################################

    bf.save('status2017.json')


    #########################################################################
    # 11. Create your capital gains report for cryptocurrency trades        #
    #########################################################################

    # The default column names used in the report don't look very nice:
    # ['kind', 'bag_spent', 'currency', 'bag_date', 'sell_date',
    # 'exchange', 'short_term', 'spent_cost', 'proceeds', 'profit'],
    # so we rename them:
    my_column_names=[
        'Type', 'Amount spent', u'Currency', 'Purchase date',
        'Sell date', u'Exchange', u'Short term', 'Purchase cost',
        'Proceeds', 'Profit']

    # Here we create the report pdf for capital gains in 2017.
    # The date_precision='D' means we only mention the day of the trade, not
    # the precise time. We also set combine=True, so multiple trades made on
    # the same day and on the same exchange are combined into a single trade
    # on the report:
    bf.report.export_report_to_pdf(
        'Report2017.pdf', year=2017,
        date_precision='D', combine=True,
        custom_column_names=my_column_names,
        locale="en_US"
    )

    # And now, let's translate it to German, by using a different
    # html template file:
    my_column_names=[
        'Art', 'Verkaufsmenge', u'Währung', 'Erwerbsdatum',
        'Verkaufsdatum', u'Börse', u'in\xa0Besitz',
        'Anschaffungskosten', u'Verkaufserlös', 'Gewinn']
    transdct = {'sale': u'Veräußerung',
                'withdrawal fee': u'Börsengebühr',
                'deposit fee': u'Börsengebühr',
                'exchange fee': u'Börsengebühr'}
    convert_short_term=[u'>\xa01\xa0Jahr', u'<\xa01\xa0Jahr']

    bf.report.export_report_to_pdf(
        'Report2017_de.pdf', year=2017,
        date_precision='D', combine=True,
        custom_column_names=my_column_names,
        custom_formatters={
            u'in\xa0Besitz': lambda b: convert_short_term[b],
            'Art': lambda x: transdct[x]},
        locale="de_DE",
        template_file='shortreport_de.html'
    )

    # If you rather want your report in a spreadsheet, you can export
    # to csv:
    bf.report.export_short_report_to_csv(
            'report_2017.csv', year=2017,
        date_precision='D', combine=False,
        convert_timezone=True, strip_timezone=True)


    #########################################################################
    # 12. Optional: Create a detailed report outlining the calculation      #
    #########################################################################

    # The simple capital gains report created above is just a plain listing
    # of all trades and the gains made, enough for the tax report.
    # A more detailed listing outlining the calculation is also available:

    bf.report.export_extended_report_to_pdf(
        'Details_2017.pdf', year=2017,
        date_precision='S', combine=False,
        font_size=10, locale="en_US")

    # And again, let's translate this report to German:
    # (Using transdct from above again to translate the payment kind)
    bf.report.export_extended_report_to_pdf(
        'Details_2017_de.pdf', year=2017,
        date_precision='S', combine=False,
        font_size=10, locale="de_DE",
        template_file='fullreport_de.html',
        payment_kind_translation=transdct)







#######################################################
###               Setup logger                      ###
#######################################################

# Don't worry about the following. It just sets up the logger,
# which manages output and prints to the file
# "ccgains_<date-time>.log".

import logging, time, sys

logger = logging.getLogger('ccgains')
logger.setLevel(logging.DEBUG)
# This is my highest logger, don't propagate to root logger:
logger.propagate = 0
# Reset logger in case any handlers were already added:
for h in logger.handlers[::-1]:
    h.close()
    logger.removeHandler(h)
# Create file handler which logs even debug messages
fname = 'ccgains_%s.log' % time.strftime("%Y%m%d-%H%M%S")
fh = logging.FileHandler(fname, mode='w')
fh.setLevel(logging.DEBUG)
# Create console handler for debugging:
ch = logging.StreamHandler(stream=sys.stdout)
ch.setLevel(logging.DEBUG)
# Create formatters and add them to the handlers
fhformatter = logging.Formatter(
    '%(asctime)s %(levelname)-8s - %(module)13s -> %(funcName)-13s: '
    '%(message)s')
chformatter = logging.Formatter('%(levelname)-8s: %(message)s')
#fh.setFormatter(fhformatter)
fh.setFormatter(chformatter)
ch.setFormatter(chformatter)
# Add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

def log_bags(bags):
    logger.info("State of bags: \n%s\n",
                '    ' + '\n    '.join(str(bags).split('\n')))


# run the main() function above:
if __name__ == "__main__":
    main()

