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

from historic_data import HistoricData

class CurrencyRelation(object):
    def __init__(self, base_currency, hist_data_list=[]):
        """Create a CurrencyRelation object. This object contains
        methods to exchange values between currencies, using
        historical exchange rates at specific times.

        params: base_currency:
            A default currency (string, e.g. "EUR"), the so called
            'base currency' used as default in many methods.
        params: hist_data_list:
            A list with HistoricData objects. If multiple HistoricData
            objects are given with the same unit, only the last one
            in the list will be used. More/updated HistoricData
            objects can be supplied later with `add_historic_data`
            method.

        """
        self.currency = str(base_currency).upper()
        self.hdict = {}
        for hist_data in hist_data_list:
            self.hdict[(hist_data.cfrom, hist_data.cto)] = hist_data

        # self.pairs is a dictionary with keys
        # `(from_currency, to_currency)` and values
        # `(num_tsteps, tsteps)` for all pairs of currencies whose
        # exchange rates can be calculated with the provided historical
        # data sets. `tsteps` in turn is a list (with length `num_tsteps`)
        # of `(from_cur, to_cur, reciprocal?)`-tuples with exchanges
        # directly available in self.hdict that must be applied in
        # turn (maybe reciprocal) to achieve the desired translation
        # from `from_currency` to `to_currency`.
        self.pairs = {}
        self.update_available_pairs()

    def add_historic_data(self, hist_data):
        """Add an HistoricData object. If a HistoricData object with
        the same unit has already been added, it will be updated.

        """
        self.hdict[(hist_data.cfrom, hist_data.cto)] = hist_data
        self.update_available_pairs((hist_data.cfrom, hist_data.cto))

    def update_available_pairs(self, newtuple=None):
        """Update internal list of pairs with available historical rate.

        :param newtuple: tuple (from_currency, to_currency);
            If supplied, updates existing list of pairs (built before)
            with pair supplied. Default (newtuple=None) will force
            rebuild of pairs list from scratch based on supplied
            historical data sets.

        """
        if not newtuple:
            # clear pairs list:
            self.pairs = {}
            to_add = self.hdict.keys()
        else:
            fcur, tcur = (c.upper() for c in newtuple)
            # check if newtuple provided is really available:
            if not (fcur, tcur) in self.hdict:
                if not (tcur, fcur) in self.hdict:
                    raise ValueError(
                        "Supplied new pair {} has no historical data. "
                        "Please provide it with `add_historic_data` first."
                        "".format(str((fcur, tcur))))
                else:
                    to_add = [(tcur, fcur)]
            else:
                to_add = [(fcur, tcur)]

        for new1, new2 in to_add:
            foundA = []
            foundB = []
            # first compare new pair with available pairs and try to add
            # new combined relations:
            for (cfrom, cto), (count, recipe) in self.pairs.items():
                if new2 == cfrom and new1 != cto:
                    # new pair can be added before other recipe
                    newp = [(new1, cto),
                            (count + 1, [(new1, new2, False)] + recipe)]
                    # reverse direction:
                    newr = [(cto, new1),
                            (count + 1, self.pairs[(cto, cfrom)][1]
                                        + [(new1, new2, True)]      )]
                    # in case it's already available, only add if
                    # new recipe is shorter:
                    if (newp[0] not in self.pairs
                        or self.pairs[newp[0]][0] > count + 1):
                            self.pairs[newp[0]] = newp[1]
                            # also add the reverse direction:
                            self.pairs[newr[0]] = newr[1]
                            # keep track of addition, will be needed later:
                            foundB.append((cfrom, cto, count, recipe))
                elif new1 == cto and new2 != cfrom:
                    # new pair can be added after other recipe:
                    newp = [(cfrom, new2),
                            (count + 1, recipe + [(new1, new2, False)])]
                    # reverse direction:
                    newr = [(new2, cfrom),
                            (count + 1, [(new1, new2, True)]
                                        + self.pairs[(cto, cfrom)][1])]
                    # in case it's already available, only add if
                    # new recipe is shorter:
                    if (newp[0] not in self.pairs
                        or self.pairs[newp[0]][0] > count + 1):
                            self.pairs[newp[0]] = newp[1]
                            # also add the reverse direction:
                            self.pairs[newr[0]] = newr[1]
                            # keep track of addition, will be needed later:
                            foundA.append((cfrom, cto, count, recipe))
            # If the new pair could be added to the beginning aswell as
            # to the end of existing recipes, there are also new recipes
            # where the new pair joins two old recipes together:
            for fa in foundA:
                for fb in foundB:
                    newp = [(fa[0], fb[1]),
                            (fa[2] + fb[2] + 1, fa[3]
                                                + [(new1, new2, False)]
                                                + fb[3])]
                    # reverse direction:
                    newr = [(fb[1], fa[0]),
                            (fa[2] + fb[2] + 1,
                                 self.pairs[(fb[1], fb[0])][1]
                                 + [(new1, new2, True)]
                                 + self.pairs[(fa[1], fa[0])][1])]
                    # in case it's already available, only add if
                    # new recipe is shorter:
                    if (newp[0] not in self.pairs
                        or self.pairs[newp[0]][0] > fa[2] + fb[2] + 1):
                            self.pairs[newp[0]] = newp[1]
                            # also add the reverse direction:
                            self.pairs[newr[0]] = newr[1]
            # And finally, don't forget to add the new pair by itself:
            newp = [(new1, new2), (1, [(new1, new2, False)])]
            # reverse direction:
            newr = [(new2, new1), (1, [(new1, new2, True)])]
            # in case it's already available, only add if
            # new recipe is shorter:
            if (newp[0] not in self.pairs
                or self.pairs[newp[0]][0] > 1):
                    self.pairs[newp[0]] = newp[1]
                    # also add the reverse direction:
                    self.pairs[newr[0]] = newr[1]

        return self.pairs



    def get_rate(self, time, from_currency, to_currency):
        """Return the rate for conversion of *from_currency* to
        *to_currency* at the datetime *time*.

        If data for the direct relation of the currency pair has not
        been added with `add_historic_data` before, an indirect route
        using multiple added pairs is tried. If this also fails, a
        ValueError is raised.

        """
        pass
