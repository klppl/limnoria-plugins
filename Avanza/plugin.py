import json
import requests
from supybot import callbacks
from supybot.commands import wrap
from supybot.i18n import PluginInternationalization

_ = PluginInternationalization("Avanza")

class Avanza(callbacks.Plugin):
    """Fetch stock and index data from Avanza."""

    def aktie(self, irc, msg, args, stock_name):
        """<stock name>
        Fetches the current price and related info for a stock."""
        try:
            search_url = f"https://www.avanza.se/ab/component/orderbook_search/?query={stock_name}"
            find_stock = json.loads(requests.get(search_url).text)
            stock_id = find_stock[0]["id"]
        except (IndexError, KeyError):
            irc.reply("Hittade inget!", prefixNick=False)
            return

        try:
            data = json.loads(requests.get(f"https://www.avanza.se/_mobile/market/orderbooklist/{stock_id}").text)
            stock_data = data[0]

            name = stock_data["name"]
            last_price = stock_data["lastPrice"]
            currency = stock_data["currency"]
            change_in_number = stock_data["change"]
            change_in_percent = stock_data["changePercent"]
            price_three_months_ago = stock_data["priceThreeMonthsAgo"]
            change_in_months = round((float(last_price) - float(price_three_months_ago)) / float(price_three_months_ago) * 100, 1)
            highest_price = stock_data.get("highestPrice", "N/A")
            lowest_price = stock_data.get("lowestPrice", "N/A")
            volume = stock_data["totalVolumeTraded"]

            irc.reply(
                f"{name} | {last_price} {currency} | Idag: {change_in_percent}% ({change_in_number} {currency}) | "
                f"3 mån: {change_in_months}% ({price_three_months_ago} {currency}) | "
                f"Volla: {lowest_price} - {highest_price} {currency} | Volym: {volume}",
                prefixNick=False
            )
        except Exception as e:
            irc.reply(f"Fel vid hämtning av data: {e}", prefixNick=False)

    aktie = wrap(aktie, ["text"])

Class = Avanza
