import requests
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from supybot.commands import wrap, optional
import supybot.utils as utils
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks

class Bitcoin(callbacks.Plugin):
    """Responds with the current Bitcoin price and percentage change over a given timeframe."""
    threaded = True

    def bitcoin(self, irc, msg, args, timeframe=None):
        """[timeframe]

        Fetches the current Bitcoin price and the percentage change over the specified timeframe (e.g., 1d, 1w, 1m, 1y).
        If no timeframe is provided, defaults to 1 day (1d)."""

        # Fetch current price
        url_current = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        try:
            response = requests.get(url_current)
            response.raise_for_status()
            current_price = response.json()["bitcoin"]["usd"]
        except requests.RequestException:
            irc.reply("Error fetching current Bitcoin price.")
            return

        # Determine timeframe
        if not timeframe:
            timeframe = "1d"
            start_date = datetime.today() - timedelta(days=1)
        else:
            try:
                if timeframe.endswith("d"):
                    days = int(timeframe[:-1])
                    start_date = datetime.today() - timedelta(days=days)
                elif timeframe.endswith("w"):
                    weeks = int(timeframe[:-1])
                    start_date = datetime.today() - timedelta(weeks=weeks)
                elif timeframe.endswith("m"):
                    months = int(timeframe[:-1])
                    # Calculate the first day of the current month, then subtract the months
                    start_date = datetime.today().replace(day=1) - relativedelta(months=months)
                elif timeframe.endswith("y"):
                    years = int(timeframe[:-1])
                    # Calculate the first day of the current year, then subtract the years
                    start_date = datetime.today().replace(month=1, day=1) - relativedelta(years=years)
                else:
                    raise ValueError
            except ValueError:
                irc.reply("Invalid timeframe format. Use formats like '1d', '1w', '1m', or '1y'.")
                return

        # Fetch historical price
        url_historical = f"https://api.coingecko.com/api/v3/coins/bitcoin/history?date={start_date.strftime('%d-%m-%Y')}"
        try:
            response = requests.get(url_historical)
            response.raise_for_status()
            historical_data = response.json()
            start_price = historical_data['market_data']['current_price']['usd']
        except requests.RequestException:
            irc.reply("Error fetching historical Bitcoin price.")
            return
        except KeyError:
            irc.reply("Historical data unavailable for the specified timeframe.")
            return

        # Calculate percentage difference
        try:
            percentage_diff = ((current_price - start_price) / start_price) * 100
        except ZeroDivisionError:
            irc.reply("Start price is zero, cannot calculate percentage difference.")
            return

        percentage_diff_formatted = (
            ircutils.mircColor(f"{percentage_diff:.2f}%", "red") if percentage_diff < 0
            else ircutils.mircColor(f"{percentage_diff:.2f}%", "green")
        )

        # Format response without decimals
        current_price_bold = ircutils.bold(f"${current_price:.0f}")
        start_price_bold = ircutils.bold(f"${start_price:.0f}")
        # Broadcast the response to the channel
        irc.reply(f"Current Price: {current_price_bold} ({percentage_diff_formatted}) – {start_price_bold} {timeframe} ago.", to=msg.args[0])


    # Make 'timeframe' optional
    bitcoin = wrap(bitcoin, [optional("text")])
    btc = bitcoin

Class = Bitcoin
