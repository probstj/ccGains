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

from ccgains import relations

class TestCurrencyRelation(unittest.TestCase):

    def setUp(self):
        self.rel = relations.CurrencyRelation()

    def test_update_pairs_one(self):
        # Create dummy pairs:
        pairs = [('A', 'B')]
        # Expected result:
        d = {('A', 'B'): (1, [('A', 'B', False)]),
             ('B', 'A'): (1, [('A', 'B', True)])}

        # Make dummy historic data dict:
        for p in pairs:
            self.rel.hdict[p] = None
        self.rel.update_available_pairs()

        self.assertDictEqual(self.rel.pairs, d)

    def test_update_pairs_two_separate(self):
        # Create dummy pairs:
        pairs = [('A', 'B'), ('C', 'D')]
        # Expected result:
        d = {('A', 'B'): (1, [('A', 'B', False)]),
             ('B', 'A'): (1, [('A', 'B', True)]),
             ('C', 'D'): (1, [('C', 'D', False)]),
             ('D', 'C'): (1, [('C', 'D', True)])}

        # Make dummy historic data dict:
        for p in pairs:
            self.rel.hdict[p] = None
        self.rel.update_available_pairs()

        self.assertDictEqual(self.rel.pairs, d)

    def test_update_pairs_two_joined(self):
        # Create dummy pairs:
        pairs = [('A', 'B'), ('B', 'C')]
        # Expected result:
        d = {('A', 'B'): (1, [('A', 'B', False)]),
             ('B', 'A'): (1, [('A', 'B', True)]),
             ('B', 'C'): (1, [('B', 'C', False)]),
             ('C', 'B'): (1, [('B', 'C', True)]),
             ('A', 'C'): (2, [('A', 'B', False), ('B', 'C', False)]),
             ('C', 'A'): (2, [('B', 'C', True), ('A', 'B', True)])}

        # Make dummy historic data dict:
        for p in pairs:
            self.rel.hdict[p] = None
        self.rel.update_available_pairs()

        self.assertDictEqual(self.rel.pairs, d)

    def test_update_pairs_two_joinedreverse(self):
        # Create dummy pairs:
        pairs = [('A', 'B'), ('C', 'B')]
        # Expected result:
        d = {('A', 'B'): (1, [('A', 'B', False)]),
             ('B', 'A'): (1, [('A', 'B', True)]),
             ('C', 'B'): (1, [('C', 'B', False)]),
             ('B', 'C'): (1, [('C', 'B', True)]),
             ('A', 'C'): (2, [('A', 'B', False), ('C', 'B', True)]),
             ('C', 'A'): (2, [('C', 'B', False), ('A', 'B', True)])}

        # Make dummy historic data dict:
        for p in pairs:
            self.rel.hdict[p] = None
        self.rel.update_available_pairs()

        self.assertDictEqual(self.rel.pairs, d)

    def test_update_pairs_two_separate_then_joined(self):
        # Diff for this test case might be long. Disable length constraint:
        oldmaxDiff = self.maxDiff
        self.maxDiff = None

        # Create dummy pairs:
        pairs = [('A', 'B'), ('C', 'D')]
        pair_extra = ('B', 'C')
        # Expected result:
        d = {('A', 'B'): (1, [('A', 'B', False)]),
             ('B', 'A'): (1, [('A', 'B', True)]),
             ('C', 'D'): (1, [('C', 'D', False)]),
             ('D', 'C'): (1, [('C', 'D', True)])}
        d_extra = {
             ('B', 'C'): (1, [('B', 'C', False)]),
             ('C', 'B'): (1, [('B', 'C', True)]),
             ('A', 'C'): (2, [('A', 'B', False), ('B', 'C', False)]),
             ('C', 'A'): (2, [('B', 'C', True), ('A', 'B', True)]),
             ('B', 'D'): (2, [('B', 'C', False), ('C', 'D', False)]),
             ('D', 'B'): (2, [('C', 'D', True), ('B', 'C', True)]),
             ('A', 'D'): (3,
                 [('A', 'B', False), ('B', 'C', False), ('C', 'D', False)]),
             ('D', 'A'): (3,
                 [('C', 'D', True), ('B', 'C', True), ('A', 'B', True)])}

        # Make dummy historic data dict:
        for p in pairs:
            self.rel.hdict[p] = None
        self.rel.update_available_pairs()

        self.assertDictEqual(self.rel.pairs, d)

        # make this a dummy HistoricData object:
        self.cfrom, self.cto = pair_extra
        self.rel.add_historic_data(self)

        d.update(d_extra)
        self.assertDictEqual(self.rel.pairs, d)

        # If everything went well, reset maxDiff:
        self.maxDiff = oldmaxDiff

    def test_update_pairs_two_separate_then_joinedreverse(self):
        # Diff for this test case might be long. Disable length constraint:
        oldmaxDiff = self.maxDiff
        self.maxDiff = None

        # Create dummy pairs:
        pairs = [('A', 'B'), ('C', 'D')]
        pair_extra = ('C', 'B')
        # Expected result:
        d = {('A', 'B'): (1, [('A', 'B', False)]),
             ('B', 'A'): (1, [('A', 'B', True)]),
             ('C', 'D'): (1, [('C', 'D', False)]),
             ('D', 'C'): (1, [('C', 'D', True)])}
        d_extra = {
             ('B', 'C'): (1, [('C', 'B', True)]),
             ('C', 'B'): (1, [('C', 'B', False)]),
             ('A', 'C'): (2, [('A', 'B', False), ('C', 'B', True)]),
             ('C', 'A'): (2, [('C', 'B', False), ('A', 'B', True)]),
             ('B', 'D'): (2, [('C', 'B', True), ('C', 'D', False)]),
             ('D', 'B'): (2, [('C', 'D', True), ('C', 'B', False)]),
             ('A', 'D'): (3,
                 [('A', 'B', False), ('C', 'B', True), ('C', 'D', False)]),
             ('D', 'A'): (3,
                 [('C', 'D', True), ('C', 'B', False), ('A', 'B', True)])}

        # Make dummy historic data dict:
        for p in pairs:
            self.rel.hdict[p] = None
        self.rel.update_available_pairs()

        self.assertDictEqual(self.rel.pairs, d)

        # make this a dummy HistoricData object:
        self.cfrom, self.cto = pair_extra
        self.rel.add_historic_data(self)

        d.update(d_extra)
        self.assertDictEqual(self.rel.pairs, d)

        # If everything went well, reset maxDiff:
        self.maxDiff = oldmaxDiff

    def test_update_pairs_two_separate_then_joined_then_optimized(self):
        # Create dummy pairs:
        pairs = [('A', 'B'), ('C', 'D')]
        pair_extra = ('B', 'C')

        # Make dummy historic data dict:
        for p in pairs:
            self.rel.hdict[p] = None
        self.rel.update_available_pairs()

        # make this a dummy HistoricData object:
        self.cfrom, self.cto = pair_extra
        self.rel.add_historic_data(self)

        # add pair with direct exchange rate data:
        direct_pair = ('A', 'D')
        self.cfrom, self.cto = direct_pair
        self.rel.add_historic_data(self)

        self.assertTupleEqual(
                self.rel.pairs[direct_pair],
                (1, [('A', 'D', False)]))
        self.assertTupleEqual(
                self.rel.pairs[direct_pair[::-1]],
                (1, [('A', 'D', True)]))


if __name__ == '__main__':
    unittest.main()
