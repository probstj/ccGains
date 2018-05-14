.. ccGains documentation master file, created by
   sphinx-quickstart on Mon Apr 30 19:15:34 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to the ccGains documentation!
=====================================

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
  - for highest accuracy, uses the `decimal data type <https://docs.python.org/3/library/decimal.html>`_ for all amounts 
  - supports saving and loading the state of your portfolio as JSON file for use in ccGains calculations in following years


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   ./ccgains


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
