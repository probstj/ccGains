#!/bin/bash

# discover and run all tests:
python -m unittest discover 

# for help, see:
#python -m unittest -h


# only a single TestCase, e.g.:
#python -m unittest tests.test_relations
# or
#python tests/test_relations.py

# only a single test from a TestCase, e.g.:
#python -m unittest tests.test_bags.TestBagFIFO.test_trading_profits_no_fees
# or
#python tests/test_bags.py TestBagFIFO.test_trading_profits_no_fees

