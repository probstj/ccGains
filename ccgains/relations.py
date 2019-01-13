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

from collections import namedtuple
from functools import total_ordering
from typing import Dict, List, Tuple


class CurrencyPair(namedtuple("CurrencyPair", ['base', 'quote'])):
    """CurrencyPair(base, quote)"""

    def reversed(self):
        return CurrencyPair(self.quote, self.base)


class RecipeStep:
    def __init__(self, base, quote, reciprocal):
        self.base = base
        self.quote = quote
        self.reciprocal = reciprocal

    def as_recipe(self):
        return Recipe(1, [self])

    def reversed(self):
        """Return a copy of this recipe step with reciprocal set opposite"""
        return RecipeStep(self.base, self.quote, not self.reciprocal)

    def __getitem__(self, item):
        if item == 0:
            return self.base
        elif item == 1:
            return self.quote
        elif item == 2:
            return self.reciprocal
        else:
            raise IndexError

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        elif isinstance(other, tuple):
            return (self.base, self.quote, self.reciprocal) == other
        return NotImplemented

    def __add__(self, other):
        if isinstance(other, Recipe):
            return Recipe(other.num_steps + 1, [self] + other.recipe_steps)
        elif isinstance(other, self.__class__):
            return Recipe(2, [self, other])
        raise NotImplementedError


@total_ordering
class Recipe:
    def __init__(self, num_steps: int, recipe_steps: List[RecipeStep]):
        self.num_steps = num_steps
        self.recipe_steps = recipe_steps

    def reversed(self):
        reversed_steps = [step.reversed() for step in reversed(self.recipe_steps)]
        return Recipe(self.num_steps, reversed_steps)

    def __getitem__(self, item):
        if item == 0:
            return self.num_steps
        elif item == 1:
            return self.recipe_steps
        else:
            raise IndexError

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        elif isinstance(other, tuple):
            return (self.num_steps, self.recipe_steps) == other
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, self.__class__):
            return self.num_steps > other.num_steps
        raise NotImplementedError

    def __add__(self, other):
        if isinstance(other, self.__class__):
            return Recipe(self.num_steps + other.num_steps, self.recipe_steps + other.recipe_steps)
        elif isinstance(other, RecipeStep):
            return Recipe(self.num_steps + 1, self.recipe_steps + [other])
        raise NotImplementedError


RecipeDict = Dict[CurrencyPair, Recipe]


class CurrencyRelation(object):
    def __init__(self, *args):
        """Create a CurrencyRelation object. This object contains
        methods to exchange values between currencies, using
        historical exchange rates at specific times.

        :param args:
            Any number of HistoricData objects. If multiple HistoricData
            objects are given with the same unit, only the last one
            in the list will be used. More/updated HistoricData
            objects can be supplied later with `add_historic_data`
            method.

        """
        self.historic_prices = {}
        for hist_data in args:
            key = CurrencyPair(hist_data.cfrom, hist_data.cto)
            self.historic_prices[key] = hist_data

        # self.pairs is a dictionary with keys
        # `(from_currency, to_currency)` and values
        # `(num_tsteps, tsteps)` for all pairs of currencies whose
        # exchange rates can be calculated with the provided historical
        # data sets. `tsteps` in turn is a list (with length `num_tsteps`)
        # of `(from_cur, to_cur, reciprocal?)`-tuples with exchanges
        # directly available in self.hdict that must be applied in
        # turn (maybe reciprocal) to achieve the desired translation
        # from `from_currency` to `to_currency`.
        self.recipes = {}  # type: RecipeDict
        self.update_available_pairs()

    def add_historic_data(self, hist_data):
        """Add an HistoricData object. If a HistoricData object with
        the same unit has already been added, it will be updated.

        """
        self.historic_prices[CurrencyPair(hist_data.cfrom, hist_data.cto)] = hist_data
        self.update_available_pairs(CurrencyPair(hist_data.cfrom, hist_data.cto))

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
            self.recipes = {}  # type: RecipeDict
            to_add = list(self.historic_prices.keys())
        else:
            fcur, tcur = (c.upper() for c in newtuple)
            # check if newtuple provided is really available:
            if CurrencyPair(fcur, tcur) not in self.historic_prices:
                if CurrencyPair(tcur, fcur) not in self.historic_prices:
                    raise ValueError(
                        "Supplied new pair {} has no historical data. "
                        "Please provide it with `add_historic_data` first."
                        "".format(str((fcur, tcur))))
                else:
                    to_add = [CurrencyPair(tcur, fcur)]
            else:
                to_add = [CurrencyPair(fcur, tcur)]

        def is_symmetric(first: CurrencyPair, second: CurrencyPair) -> bool:
            return first.quote == second.base and second.quote == first.base

        def can_add_before(new: CurrencyPair, existing: CurrencyPair) -> bool:
            return new.quote == existing.base and not is_symmetric(new, existing)

        def can_add_after(new: CurrencyPair, existing: CurrencyPair) -> bool:
            return new.base == existing.quote and not is_symmetric(new, existing)

        def update_if_shorter(pair: CurrencyPair, recipe: Recipe) -> bool:
            if pair not in self.recipes or recipe < self.recipes[pair]:
                self.recipes[pair] = recipe
                self.recipes[pair.reversed()] = recipe.reversed()
                return True
            return False

        # Loop through each HistoricPrice
        for new_base, new_quote in to_add:
            new_after = []  # type: List[Tuple[CurrencyPair, Recipe]]
            new_before = []  # type: List[Tuple[CurrencyPair, Recipe]]

            single_pair = CurrencyPair(new_base, new_quote)
            single_step = RecipeStep(single_pair.base, single_pair.quote, False)

            for existing_pair, existing_recipe in tuple(self.recipes.items()):

                if can_add_before(single_pair, existing_pair):
                    before_pair = CurrencyPair(single_pair.base, existing_pair.quote)
                    new_recipe = single_step + existing_recipe

                    # If already known, only add if new recipe_steps is shorter:
                    if update_if_shorter(before_pair, new_recipe):
                        # keep track of addition, will be needed later:
                        new_before.append((existing_pair, existing_recipe))

                elif can_add_after(single_pair, existing_pair):
                    # New pair can be added after existing recipe steps:
                    new_pair = CurrencyPair(existing_pair.base, single_pair.quote)
                    new_recipe = existing_recipe + single_step

                    # If already known, only add if new recipe_steps is shorter:
                    if update_if_shorter(new_pair, new_recipe):
                        # keep track of addition, will be needed later:
                        new_after.append((existing_pair, existing_recipe))

            # If the new pair could be added to the beginning as well as
            # to the end of existing recipes, there are also new recipes
            # where the new pair joins two old recipes together:
            for pair_a, recipe_a in new_after:
                for pair_b, recipe_b in new_before:

                    new_pair = CurrencyPair(pair_a.base, pair_b.quote)
                    new_recipe = recipe_a + single_step + recipe_b

                    # If already known, only add if new recipe_steps is shorter:
                    update_if_shorter(new_pair, new_recipe)

            # And finally, don't forget to add the new pair by itself:
            base_recipe = single_step.as_recipe()

            # If already known, only add if new recipe_steps is shorter:
            update_if_shorter(single_pair, base_recipe)

        return self.recipes

    def get_rate(self, dtime, from_currency, to_currency):
        """Return the rate for conversion of *from_currency* to
        *to_currency* at the datetime *dtime*.

        If data for the direct relation of the currency pair has not
        been added with `add_historic_data` before, an indirect route
        using multiple added pairs is tried. If this also fails, a
        KeyError is raised.
        """

        recipe_pair = CurrencyPair(from_currency.upper(), to_currency.upper())
        steps = self.recipes[recipe_pair].recipe_steps
        result = 1
        for base_cur, quote_cur, inverse in steps:
            if not inverse:
                result *= self.historic_prices[CurrencyPair(base_cur, quote_cur)].get_price(dtime)
            else:
                result /= self.historic_prices[CurrencyPair(base_cur, quote_cur)].get_price(dtime)
        return result
