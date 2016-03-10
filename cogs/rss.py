import discord
from discord.ext import commands
import feedparser
import os
import time
import aiohttp
import asyncio
import datetime
import string

import cogs.utils.checks as checks
from cogs.utils.dataIO import fileIO
from cogs.utils.chat_formatting import *
from __main__ import send_cmd_help

class Settings(object):
    pass

class Feeds(object):
    def __init__(self):
        self.check_folders()
        # {server:{channel:{name:,url:,last_scraped:,template:}}}
        self.feeds = fileIO("data/RSS/feeds.json","load")

    def save_feeds(self):
        fileIO("data/RSS/feeds.json","save",self.feeds)

    def check_folders(self):
        if not os.path.exists("data/RSS"):
            print("Creating data/RSS folder...")
            os.makedirs("data/RSS")
        self.check_files()

    def check_files(self):
        f = "data/RSS/feeds.json"
        if not fileIO(f, "check"):
            print("Creating empty feeds.json...")
            fileIO(f, "save", {})

    def update_time(self,server,channel,name,time):
        if server in self.feeds:
            if channel in self.feeds[server]:
                if name in self.feeds[server][channel]:
                    self.feeds[server][channel][name]['last'] = time
                    self.save_feeds()

    async def edit_template(self,ctx,name,template):
        server = ctx.message.server.id
        channel = ctx.message.channel.id
        if server not in self.feeds:
            return False
        if channel not in self.feeds[server]:
            return False
        if name not in self.feeds[server][channel]:
            return False
        self.feeds[server][channel][name]['template'] = template
        self.save_feeds()
        return True

    def add_feed(self, ctx, name, url):
        server = ctx.message.server.id
        channel = ctx.message.channel.id
        if server not in self.feeds:
            self.feeds[server] = {}
        self.feeds[server][channel] = {}
        self.feeds[server][channel][name] = {}
        self.feeds[server][channel][name]['url'] = url
        self.feeds[server][channel][name]['last'] = ()
        self.feeds[server][channel][name]['template'] = "$name:\n$title"
        self.save_feeds()

    async def delete_feed(self,ctx,name):
        server = ctx.message.server.id
        channel = ctx.message.channel.id
        if server not in self.feeds:
            return False
        if channel not in self.feeds[server]:
            return False
        if name not in self.feeds[server][channel]:
            return False
        del self.feeds[server][channel][name]
        self.save_feeds()
        return True

    def get_feed_names(self,server):
        pass

    def get_copy(self):
        return self.feeds.copy()

class RSS(object):
    def __init__(self, bot):
        self.bot = bot

        self.settings = Settings()
        self.feeds = Feeds()

    def get_channel_object(self, channel_id):
        return self.bot.get_channel(channel_id)

    async def _get_feed(self, url):
        text = None
        try:
            with aiohttp.ClientSession() as session:
                with aiohttp.Timeout(3):
                    async with session.get(url) as r:
                        text = await r.text()
        except:
            pass
        return text

    async def valid_url(self,url):
        text = await self._get_feed(url)
        rss = feedparser.parse(text)
        if rss.bozo:
            return False
        else:
            return True

    @commands.group(pass_context=True)
    async def rss(self,ctx):
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @rss.command(pass_context=True,name="add")
    async def _rss_add(self, ctx, name : str, url : str):
        valid_url = await self.valid_url(url)
        if valid_url:
            self.feeds.add_feed(ctx,name,url)
            await self.bot.say('Feed "{}" added. Modify the template using rss template'.format(name))
        else:
            await self.bot.say('Invalid or unavailable URL.')

    @rss.command(pass_context=True,name="template")
    async def _rss_template(self,ctx,feed_name : str,*, template : str):
        template = template.replace("\\t","\t")
        template = template.replace("\\n","\n")
        success = await self.feeds.edit_template(ctx,feed_name,template)
        if success:
            await self.bot.say("Template added successfully.")
        else:
            await self.bot.say('Feed not found!')

    @rss.command(pass_context=True,name="remove")
    async def _rss_remove(self, ctx, name : str):
        success = await self.feeds.delete_feed(ctx,name)
        if success:
            await self.bot.say('Feed deleted.')
        else:
            await self.bot.say('Feed not found!')

    async def read_feeds(self):
        await self.bot.wait_until_ready()
        while 'RSS' in self.bot.cogs:
            feeds = self.feeds.get_copy()
            for server in feeds:
                for chan_id in feeds[server]:
                    for name,items in feeds[server][chan_id].items():
                        url = items['url']
                        last_time = items['last']
                        template = items['template']
                        text = await self._get_feed(url)
                        rss = feedparser.parse(text)
                        if rss.bozo:
                            continue
                        curr_time = rss.entries[0].published_parsed[:5]
                        curr_datetime = datetime.datetime(*curr_time)
                        if len(last_time) == 0 or curr_datetime > datetime.datetime(*last_time):
                            channel = self.get_channel_object(chan_id)
                            latest = rss.entries[0]
                            to_fill = string.Template(template)
                            message = to_fill.safe_substitute(
                                name=bold(name),
                                **latest
                            )
                            self.feeds.update_time(server,chan_id,name,curr_time)
                            await self.bot.send_message(channel,message)
            await asyncio.sleep(60)

def setup(bot):
    n = RSS(bot)
    bot.add_cog(n)
    loop = asyncio.get_event_loop()
    loop.create_task(n.read_feeds())