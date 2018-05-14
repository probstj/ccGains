# ccGains

The ccGains (cryptocurrency gains) package provides a python library for calculating capital gains made by trading cryptocurrencies or foreign currencies.

Some of its features are:

  - calculates the capital gains using the first-in/first out (FIFO) principle,
  - creates capital gains reports as CSV, HTML or PDF (instantly ready to print out for the tax office),
  - can create a more detailed capital gains report outlining the calculation and used bags,
  - differs between short and long term gains (amounts held for less or more than a year),
  - treats amounts held and traded on different exchanges separately,
  - treats exchange fees and transaction fees directly resulting from trading properly as losses,
  - provides methods to import your trading history from various exchanges,
  - loads historic cryptocurrency prices from CSV files and/or
  - loads historic prices from APIs provided by exchanges,
  - caches historic price data on disk for quicker and offline retrieval and less traffic to exchanges,
  - for highest accuracy, uses the [decimal data type](https://docs.python.org/3/library/decimal.html) for all amounts 
  - supports saving and loading the state of your portfolio as JSON file for use in ccGains calculations in following years

Please have a look at some example PDF reports in `examples/example_output/`.


## Installation

You'll need Python (ccGains is tested under Python 2.7 and Python 3.x). Get it here: https://www.python.org/


ccGains can then easily be installed via the Python package manager pip:

  - Download the source code, e.g. by `git clone https://github.com/probstj/ccgains.git`
  - Inside the main ccGains directory run: `pip install .` 
  (note the `.` at the end)
  
    - Alternatively, to install locally without admin rights: `pip install --user .`
    - And if you want to add changes to the source code and quickly want to try it without reinstalling, pip can install by linking to the source code folder: `pip install -e .`


## Usage

Please have a look at `examples/example.py` and follow the comments to adapt it for your purposes. The main part of the script is also included here, see 'Example' below...

Then run the example with Python, e.g. with `python example.py`.

A lot of functionality is still missing, most crucially, support for more exchanges. You can help improve ccGains - programming experience not needed: See below "Bug reports & feature requests".


## License

Copyright (C) 2017 Jürgen Probst

ccGains is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

ccGains is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more details.

## Help and support

### Documentation

The ccGains documentation is available online at [Read the Docs](https://ccGains.readthedocs.io). You can also download a [PDF version](https://readthedocs.org/projects/ccGains/downloads/pdf/latest/).

### Bug reports & feature requests

A lot of functionality is still missing, most crucially, support for more exchanges. If your exchange is not supported yet, please file a `New issue` on GitHub at https://github.com/probstj/ccgains/issues together with a short example CSV exported from your exchange and I will add a method to import it.

### Example
An example script is included in the `example` subdirectory: `example.py` (or use `example_windows.py` on Windows; this is the same script, just with Windows' line endings so you can open it in any text editor). Follow the comments in the file to adapt  the script for your purposes.

All example output can already be viewed in `examples/example_output/`.

Here is the main part of the example script copied verbatim:
```python
import ccgains

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
        logger.info("Gains: %s %.12f\n" % (bf.currency, bf.profit))


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
```
