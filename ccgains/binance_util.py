from decimal import Decimal
from typing import Union, List

QUOTE_ASSETS = ['BTC', 'ETH', 'USDT', 'TUSD', 'PAX', 'BNB']


def split_market_symbols(market: str) -> List[Union[str, None]]:
    # Binance trade csv provides a column called 'Market', which is
    # the non-separated trading pair (e.g. 'NEOBTC' or 'BNBUSDT')
    # Split this string to return [base, quote] assets
    for quote in QUOTE_ASSETS:
        quote_start = market.find(quote)
        if len(market) == quote_start + len(quote):  # This quote asset is right-most
            return [market[:quote_start], market[quote_start:]]
    raise KeyError("Couldn't find a quote symbol for %s" % market)


def currency_for(csv_line, side):
    market = split_market_symbols(csv_line[1])  # [base, quote]
    is_buy = csv_line[2].upper() == 'BUY'
    if side not in ['buy', 'sell']:
        return None
    if side == 'buy':
        return market[not is_buy]  # base if is_buy, quote if not is_buy
    else:
        return market[is_buy]  # quote if True, base if False


# Binance trade csv output has following columns:
# Date (UTC), Market, Type, Price, Amount, Total, Fee, Fee Coin
TPLOC_BINANCE_TRADES = {
    'kind': 'Trade', 'dtime': 0,
    'buy_currency': lambda cols: currency_for(cols, 'buy'),
    'buy_amount': lambda cols: [Decimal(cols[4]), Decimal(cols[5])][(cols[2].upper() == 'SELL')],
    'sell_currency': lambda cols: currency_for(cols, 'sell'),
    'sell_amount': lambda cols: [Decimal(cols[4]), Decimal(cols[5])][(cols[2].upper() == 'BUY')],
    'fee_currency': 7,
    'fee_amount': 6,
    'exchange': 'Binance',
}
