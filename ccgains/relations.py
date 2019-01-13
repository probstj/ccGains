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
from typing import List, Tuple, Dict


class CurrencyPair(namedtuple("CurrencyPair", ['base', 'quote'])):
    """CurrencyPair(base, quote)"""

    def reversed(self):
        """Swap base(from) for quote(to) currencies"""
        return CurrencyPair(self.quote, self.base)

    def __add__(self, other):
        if isinstance(other, CurrencyPair):
            return CurrencyPair(self.base, other.quote)
        raise NotImplementedError

    def __radd__(self, other):
        if isinstance(other, CurrencyPair):
            return CurrencyPair(other.base, self.quote)

    def __str__(self):
        return "<CurrencyPair> ({0.base}, {0.quote})".format(self)


@total_ordering
class Recipe(namedtuple('Recipe', ['num_steps', 'recipe_steps'])):
    """A conversion recipe made up of `num_steps` steps which are
    given in `recipe_steps`, showing how to convert from
    `recipe_steps[0].base` to `recipe_steps[-1].quote`
    """

    def reversed(self):
        """A reversed recipe has RecipeSteps in the reversed order,
        and the opposite value for `reciprocal` for each step
        """

        reversed_steps = [step.reversed() for step in reversed(self.recipe_steps)]
        return Recipe(self.num_steps, reversed_steps)

    def __gt__(self, other):
        """One Recipe is 'greater than' another if it requires more steps"""
        if isinstance(other, self.__class__):
            return self.num_steps > other.num_steps
        raise NotImplementedError

    def __add__(self, other):
        """Adding an 'other' Recipe involves adding number of steps, and
        extending the list of recipe steps with the steps in 'other'

        Adding an 'other' Recipe step involves incrementing number of
        steps by 1, and extending recipe steps with the other RecipeStep
        """

        if isinstance(other, Recipe):
            return Recipe(
                self.num_steps + other.num_steps,
                self.recipe_steps + other.recipe_steps)
        elif isinstance(other, RecipeStep):
            return Recipe(self.num_steps + 1, self.recipe_steps + [other])
        raise NotImplementedError

    def __radd__(self, other):
        """Reverse add still increments number of steps, but adds the
        additional steps on the opposite of the list
        """

        if isinstance(other, Recipe):
            return Recipe(
                self.num_steps + other.num_steps,
                other.recipe_steps + self.recipe_steps)
        elif isinstance(other, RecipeStep):
            return Recipe(self.num_steps + 1, [other] + self.recipe_steps)
        raise NotImplementedError


class RecipeStep(namedtuple('RecipeStep', ['base', 'quote', 'reciprocal'])):
    """One step in a conversion recipe, indicating base (from) currency,
    quote (to) currency, and whether the reciprocal of the price should
    be used for this step.
    """

    def as_recipe(self):
        """Create a Recipe (with one step) from this RecipeStep"""
        return Recipe(1, [self])

    def reversed(self):
        """Return a copy of this recipe step with reciprocal set opposite"""
        return RecipeStep(self.base, self.quote, not self.reciprocal)

    def __add__(self, other):
        """Adding one RecipeStep to another creates a Recipe.

        Adding a Recipe to a RecipeStep creates a new Recipe with
        the 'other' Recipe's steps at the end of the new list of
        recipe steps
        """

        if type(other) == Recipe:
            return Recipe(other.num_steps + 1, [self] + other.recipe_steps)
        elif type(other) == self.__class__:
            return Recipe(2, [self, other])
        raise NotImplementedError

    def __radd__(self, other):
        if type(other) == Recipe:
            return Recipe(other.num_steps + 1, other.recipe_steps + [self])
        elif type(other) == self.__class__:
            return Recipe(2, [other, self])
        raise NotImplementedError


# Custom type for static type-checking in a meaningful way
RecipeDict = Dict[CurrencyPair, Recipe]


class CurrencyRelation(object):
    
    def __init__(self, *args):
        """Create a CurrencyRelation object. This object allows
        exchanging values between currencies, using historical
        exchange rates at specific times.

        :param args:
            Any number of HistoricData objects. If multiple HistoricData
            objects are given with the same unit, only the last one will
            be used. More/updated HistoricData objects can be supplied
            later with `add_historic_data` method.
        """

        self.historic_prices = {}
        for hist_data in args:
            key = CurrencyPair(hist_data.cfrom, hist_data.cto)
            self.historic_prices[key] = hist_data

        self.recipes = {}  # type: RecipeDict
        self.update_available_pairs()

    def add_historic_data(self, hist_data):
        """Add an HistoricData object. If a HistoricData object with
        the same unit has already been added, it will be updated.
        """

        key = CurrencyPair(hist_data.cfrom, hist_data.cto)
        self.historic_prices[key] = hist_data
        self.update_available_pairs(key)

    def update_available_pairs(self, update_pair=None):
        """Update internal list of pairs with available historical rate.

        :param update_pair: tuple (from_currency, to_currency);
            If supplied, updates existing recipes with pair supplied.
            Default (None) will force rebuild of pairs list from scratch
            based on supplied historical data sets.
        """

        if not update_pair:
            # Regenerate all recipes
            self.recipes = {}  # type: RecipeDict
            to_add = list(self.historic_prices.keys())
        else:
            if not isinstance(update_pair, CurrencyPair):
                update_pair = CurrencyPair(update_pair[0], update_pair[1])
            # check if update_pair provided is really available:
            if update_pair not in self.historic_prices:
                if update_pair.reversed() not in self.historic_prices:
                    raise ValueError(
                        "Supplied new pair {} has no historical data. "
                        "Please provide it with `add_historic_data` first."
                        "".format(update_pair))
                else:
                    to_add = [update_pair.reversed()]
            else:
                to_add = [update_pair]

        def can_add_before(new: CurrencyPair, existing: CurrencyPair) -> bool:
            return new.quote == existing.base and new != existing.reversed()

        def can_add_after(new: CurrencyPair, existing: CurrencyPair) -> bool:
            return new.base == existing.quote and new != existing.reversed()

        def update_if_shorter(pair: CurrencyPair, recipe: Recipe) -> bool:
            if pair not in self.recipes or recipe < self.recipes[pair]:
                self.recipes[pair] = recipe
                self.recipes[pair.reversed()] = recipe.reversed()
                return True
            return False

        # Loop through each HistoricPrice
        for root_base, root_quote in to_add:
            added_after = []  # type: List[Tuple[CurrencyPair, Recipe]]
            added_before = []  # type: List[Tuple[CurrencyPair, Recipe]]

            root_pair = CurrencyPair(root_base, root_quote)
            root_step = RecipeStep(root_pair.base, root_pair.quote, False)

            for known_pair, known_recipe in tuple(self.recipes.items()):

                if can_add_before(root_pair, known_pair):
                    before_pair = root_pair + known_pair
                    new_recipe = root_step + known_recipe

                    # If already known, only add if new recipe is shorter:
                    if update_if_shorter(before_pair, new_recipe):
                        # keep track of addition, will be needed later:
                        added_before.append((known_pair, known_recipe))

                elif can_add_after(root_pair, known_pair):
                    # New pair can be added after existing recipe steps:
                    after_pair = known_pair + root_pair
                    new_recipe = known_recipe + root_step

                    # If already known, only add if new recipe is shorter:
                    if update_if_shorter(after_pair, new_recipe):
                        # keep track of addition, will be needed later:
                        added_after.append((known_pair, known_recipe))

            # If the new pair could be added to the beginning as well as
            # to the end of existing recipes, there are also new recipes
            # where the new pair joins two old recipes together:
            for pair_a, recipe_a in added_after:
                for pair_b, recipe_b in added_before:

                    middle_pair = pair_a + pair_b
                    middle_recipe = recipe_a + root_step + recipe_b

                    # If already known, only add if new recipe is shorter:
                    update_if_shorter(middle_pair, middle_recipe)

            # And finally, don't forget to add the new pair by itself:
            update_if_shorter(root_pair, root_step.as_recipe())

        return self.recipes

    def get_rate(self, dtime, from_currency, to_currency):
        """Return the rate for conversion of *from_currency* to
        *to_currency* at the datetime *dtime*.

        If a direct relation of the currency pair has not been added with
        `add_historic_data` before, an indirect route using multiple
        added pairs is tried. If this also fails, a KeyError is raised.
        """

        key = CurrencyPair(from_currency.upper(), to_currency.upper())
        steps = self.recipes[key].recipe_steps
        result = 1
        for base_cur, quote_cur, inverse in steps:
            step_key = CurrencyPair(base_cur, quote_cur)
            if not inverse:
                result *= self.historic_prices[step_key].get_price(dtime)
            else:
                result /= self.historic_prices[step_key].get_price(dtime)
        return result
