###
# [Your existing license and copyright]
###

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.ircmsgs as ircmsgs
import supybot.callbacks as callbacks
import supybot.log as log
from string import Template
import datetime
import json
import re
import time

try:
    from supybot.i18n import PluginInternationalization

    _ = PluginInternationalization("YouTube")
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x


class YouTube(callbacks.Plugin):
    """Queries YouTube API for information about YouTube videos"""

    threaded = True

    # Regular expression to detect YouTube URLs
    YOUTUBE_URL_REGEX = re.compile(
        r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)(?P<id>[A-Za-z0-9_-]{11})'
    )

    def __init__(self, irc):
        super().__init__(irc)
        # Initialize cache dictionary and cache duration (in seconds)
        self.cache = {}
        self.cache_duration = 300  # 5 minutes
        # Initialize rate limiting structures
        self.last_response = {}
        self.rate_limit_interval = 5  # seconds

    def dosearch(self, query, channel):
        apikey = self.registryValue("developerKey")
        safe_search = self.registryValue("safeSearch", channel)
        sort_order = self.registryValue("sortOrder", channel)
        video_id = None
        opts = {
            "q": query,
            "part": "snippet",
            "maxResults": "1",
            "order": sort_order,
            "key": apikey,
            "safeSearch": safe_search,
            "type": "video",
        }
        api_url = "https://www.googleapis.com/youtube/v3/search?{0}".format(
            utils.web.urlencode(opts)
        )
        try:
            log.debug("YouTube: requesting %s" % (api_url))
            request = utils.web.getUrl(api_url).decode()
            response = json.loads(request)
            video_id = response["items"][0]["id"]["videoId"]
        except Exception as e:
            log.error("YouTube: Error retrieving data from API: %s" % (str(e)))
        return video_id

    def get_duration_from_seconds(self, duration_seconds):
        m, s = divmod(duration_seconds, 60)
        h, m = divmod(m, 60)
        duration = "%02d:%02d" % (m, s)
        """ Only include hour if the video is at least 1 hour long """
        if h > 0:
            duration = "%02d:%s" % (h, duration)
        return duration

    def get_total_seconds_from_duration(self, input_duration):
        """
        Converts YouTube duration format (e.g., PT4M41S) to total seconds.
        """
        regex = re.compile(
            r"""
                   (?P<sign>    -?) P
                (?:(?P<years>  \d+) Y)?
                (?:(?P<months> \d+) M)?
                (?:(?P<days>   \d+) D)?
            (?:                     T
                (?:(?P<hours>  \d+) H)?
                (?:(?P<minutes>\d+) M)?
                (?:(?P<seconds>\d+) S)?
            )?
            """,
            re.VERBOSE,
        )
        match = regex.match(input_duration)
        if not match:
            return 0
        duration = match.groupdict()
        # Safely convert duration components, defaulting to 0 if None
        hours = int(duration.get("hours") or 0)
        minutes = int(duration.get("minutes") or 0)
        seconds = int(duration.get("seconds") or 0)
        total_seconds = hours * 3600 + minutes * 60 + seconds
        return total_seconds

    def get_youtube_logo(self, channel):
        use_bold = self.registryValue("useBold", channel)
        if use_bold:
            yt_logo = "{0}\x0F\x02".format(self.registryValue("logo", channel))
        else:
            yt_logo = "{0}\x0F".format(self.registryValue("logo", channel))
        return yt_logo

    def yt(self, irc, msg, args, query):
        """<search term>
        Search for YouTube videos
        """
        apikey = self.registryValue("developerKey")
        if not apikey:
            irc.reply("Error: You need to set an API key to use this plugin.")
            return
        template = self.registryValue("template", msg.channel)
        template = template.replace("{{", "$").replace("}}", "")
        template = Template(template)
        response = None
        title = None
        video_id = self.dosearch(query, msg.channel)
        if video_id:
            log.debug("YouTube: got video id: %s" % video_id)
            opts = {
                "part": "snippet,statistics,contentDetails",
                "maxResults": 1,
                "key": apikey,
                "id": video_id,
            }
            api_url = "https://www.googleapis.com/youtube/v3/videos?%s" % (utils.web.urlencode(opts))
            log.debug("YouTube: requesting %s" % (api_url))
            try:
                request = utils.web.getUrl(api_url).decode()
                response = json.loads(request)
                if response["pageInfo"]["totalResults"] > 0:
                    items = response["items"]
                    video = items[0]
                    snippet = video["snippet"]
                    statistics = video["statistics"]
                    view_count = 0
                    like_count = 0
                    dislike_count = 0
                    comment_count = 0
                    favorite_count = 0
                    if "viewCount" in statistics:
                        view_count = "{:,}".format(int(statistics["viewCount"]))
                    if "likeCount" in statistics:
                        like_count = "{:,}".format(int(statistics["likeCount"]))
                    if "dislikeCount" in statistics:
                        dislike_count = "{:,}".format(int(statistics["dislikeCount"]))
                    if "favoriteCount" in statistics:
                        favorite_count = "{:,}".format(int(statistics["favoriteCount"]))
                    if "commentCount" in statistics:
                        comment_count = "{:,}".format(int(statistics["commentCount"]))
                    channel_title = snippet["channelTitle"]
                    video_duration = video["contentDetails"]["duration"]
                    duration_seconds = self.get_total_seconds_from_duration(video_duration)
                    if duration_seconds > 0:
                        duration = self.get_duration_from_seconds(duration_seconds)
                    else:
                        duration = "LIVE"
                    results = {
                        "title": snippet["title"],
                        "duration": duration,
                        "views": view_count,
                        "likes": like_count,
                        "dislikes": dislike_count,
                        "comments": comment_count,
                        "favorites": favorite_count,
                        "uploader": channel_title,
                        "link": "https://youtu.be/%s" % (video_id),
                        "published": snippet["publishedAt"].split("T")[0],
                        "logo": self.get_youtube_logo(msg.channel),
                    }
                    title = template.safe_substitute(results)
                else:
                    log.debug("YouTube: video appears to be private; no results!")
            except Exception as e:
                log.error("YouTube: Error parsing Youtube API JSON response: %s" % (str(e)))
        else:
            irc.reply("No results found for: %s" % query)
            return
        if title:
            use_bold = self.registryValue("useBold", msg.channel)
            if use_bold:
                title = ircutils.bold(title)
            irc.reply(title, prefixNick=False)

    yt = wrap(yt, ["text"])

    ### New Functionality Starts Here ###

    def doPrivmsg(self, irc, msg):
        """
        Overrides the default doPrivmsg to detect YouTube links in messages.
        """
        self.doYouTubeLink(irc, msg)
        # Do not call super().doPrivmsg to avoid AttributeError

    def doYouTubeLink(self, irc, msg):
        """
        Automatically detects YouTube links in messages and responds with video info.
        """
        # Find all unique video IDs in the message
        video_ids = set(match.group('id') for match in self.YOUTUBE_URL_REGEX.finditer(msg.args[1]))
        for video_id in video_ids:
            if video_id:
                # Check cache to prevent duplicate API calls
                cached = self.cache.get(video_id)
                current_time = time.time()
                if cached:
                    cached_time, cached_response = cached
                    if current_time - cached_time < self.cache_duration:
                        # Use cached response
                        irc.reply(cached_response, prefixNick=False)
                        continue  # Skip to next video_id
                # Fetch and reply with video info
                response_text = self.fetch_and_format_video_info(irc, msg, video_id)
                if response_text:
                    irc.reply(response_text, prefixNick=False)
                    # Cache the response
                    self.cache[video_id] = (current_time, response_text)
                # Optional: Break after first link to prevent multiple replies
                # Uncomment the following line if desired
                # break

    def fetch_and_format_video_info(self, irc, msg, video_id):
        """
        Fetches video info using video_id and returns the formatted response text.
        Implements rate limiting to prevent spam.
        """
        try:
            # Rate limiting: Ensure only one response per channel within interval
            channel = msg.args[0]
            current_time = time.time()
            last_time = self.last_response.get(channel, 0)
            if current_time - last_time < self.rate_limit_interval:
                log.debug("YouTube: Rate limit exceeded for channel %s" % channel)
                return None  # Do not respond to prevent spam
            self.last_response[channel] = current_time

            apikey = self.registryValue("developerKey")
            if not apikey:
                irc.reply("Error: API key not set.", private=True)
                return None

            opts = {
                "part": "snippet,statistics,contentDetails",
                "id": video_id,
                "key": apikey,
            }
            api_url = "https://www.googleapis.com/youtube/v3/videos?{0}".format(
                utils.web.urlencode(opts)
            )
            log.debug("YouTube: requesting %s" % (api_url))
            request = utils.web.getUrl(api_url).decode()
            response = json.loads(request)

            if response["pageInfo"]["totalResults"] > 0:
                items = response["items"]
                video = items[0]
                snippet = video["snippet"]
                statistics = video["statistics"]
                view_count = "{:,}".format(int(statistics.get("viewCount", 0)))
                like_count = "{:,}".format(int(statistics.get("likeCount", 0)))
                dislike_count = "{:,}".format(int(statistics.get("dislikeCount", 0)))
                comment_count = "{:,}".format(int(statistics.get("commentCount", 0)))
                favorite_count = "{:,}".format(int(statistics.get("favoriteCount", 0)))
                channel_title = snippet["channelTitle"]
                video_duration = video["contentDetails"]["duration"]
                duration_seconds = self.get_total_seconds_from_duration(video_duration)
                duration = self.get_duration_from_seconds(duration_seconds) if duration_seconds > 0 else "LIVE"

                results = {
                    "title": snippet["title"],
                    "duration": duration,
                    "views": view_count,
                    "likes": like_count,
                    "dislikes": dislike_count,
                    "comments": comment_count,
                    "favorites": favorite_count,
                    "uploader": channel_title,
                    "link": f"https://youtu.be/{video_id}",
                    "published": snippet["publishedAt"].split("T")[0],
                    "logo": self.get_youtube_logo(msg.channel),
                }

                template = self.registryValue("template", msg.channel)
                template = template.replace("{{", "$").replace("}}", "")
                template = Template(template)
                title = template.safe_substitute(results)

                if self.registryValue("useBold", msg.channel):
                    title = ircutils.bold(title)

                return title
            else:
                log.debug("YouTube: No results found for video ID: %s" % video_id)
                return "No results found for video ID: {}".format(video_id)

        except Exception as e:
            log.error("YouTube: Error processing video ID %s: %s" % (video_id, str(e)))
            return "Error retrieving information for video ID: {}".format(video_id)


Class = YouTube

# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
