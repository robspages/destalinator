#! /usr/bin/env python

import datetime
import sys
import time

import requests

import slackbot
import util


class Destalinator(object):

    closure = "closure.txt"
    warning = "warning.txt"
    earliest_archive_date = "2016-01-28"  # Do not archive channels prior to this date

    ignore_users = ["USLACKBOT"]

    def __init__(self, slack_name, slackbot, api_token=None, api_token_file=None):
        """
        slack name is the short name of the slack (preceding '.slack.com')
        slackbot should be an initialized slackbot.Slackbot() object
        api_token should be a Slack API Token.  However, it can also
        be None, and api_token_file be the file name containing a
        Slack API Token instead
        """
        self.slack_name = slack_name
        self.api_token = util.get_token(api_token, api_token_file)
        self.url = self.api_url()
        self.channels = self.get_channels()
        self.closure_text = self.get_content(self.closure)
        self.warning_text = self.get_content(self.warning)
        self.slackbot = slackbot

    def get_content(self, fname):
        """
        read fname into text blob, return text blob
        """
        f = open(fname)
        ret = f.read().strip()
        f.close()
        return ret

    def api_url(self):
        return "https://{}.slack.com/api/".format(self.slack_name)

    def get_channels(self, exclude_archived=True):
        """
        return a {channel_name: channel_id} dictionary
        if exclude_arhived (default: True), only shows non-archived channels
        """

        url_template = self.url + "channels.list?exclude_archived={}&token={}"
        if exclude_archived:
            exclude_archived = 1
        else:
            exclude_archived = 0
        url = url_template.format(exclude_archived, self.api_token)
        request = requests.get(url)
        payload = request.json()
        assert 'channels' in payload
        channels = {x['name']: x['id'] for x in payload['channels']}
        return channels

    def get_channelid(self, channel_name):
        """
        Given a channel name, returns the ID of the channel
        """
        return self.channels[channel_name]

    def safe_archive(self, channel_name):
        """
        Arhives channel if today's date is after self.earliest_archive_date
        """
        today = datetime.date.today()
        year, month, day = [int(x) for x in self.earliest_archive_date.split("-")]
        earliest = datetime.date(year, month, day)
        if today > earliest:
            self.archive(channel_name)
        else:
            message = "Just FYI, I would have archived this channel but it's not yet "
            message += self.earliest_archive_date
            self.slackbot.say(channel_name, message)

    def archive(self, channel_name):
        """
        Archives the given channel name.  Returns the response content
        """
        url_template = self.url + "channels.archive?token={}&channel={}"
        cid = self.get_channelid(channel_name)
        url = url_template.format(self.api_token, cid)
        self.slackbot.say(channel_name, self.closure_text)
        request = requests.get(url)
        payload = request.json()
        return payload

    def get_messages(self, channel_name, days):
        """
        get 'all' messages for the given channel name in the slack
        name from the last DAYS days
        By default, Slack only returns 100 messages, so if more than 100
        messages were sent, we'll only get a subset of messages.  Since
        this code is used for stale channel handling, that's considered
        acceptable.
        """

        url_template = self.url + "channels.history?oldest={}&token={}&channel={}"
        cid = self.get_channelid(channel_name)
        ago = time.time() - (days * 86400)
        url = url_template.format(ago, self.api_token, cid)
        payload = requests.get(url).json()
        assert 'messages' in payload
        # Why filter out subtype? Because Slack marks *everything* as
        # messages, even when it's automated 'X has joined the channel'
        # notifications (which really should be marked as events, not messages)
        # The way to know whether or not such message is an event is to see
        # if it has a subtype -- someone just talking has no subtype, but
        # 'X has joined the channel' have a subtype, so we'll filter that out.
        return [x for x in payload['messages'] if x.get("subtype") is None]

    def stale(self, channel_name, days):
        """
        returns True/False whether the channel is stale.  Definition of stale is
        no messages in the last DAYS days which are not from self.ignore_users
        """
        messages = self.get_messages(channel_name, days)
        messages = [x for x in messages if x.get("user") not in self.ignore_users]
        if messages:
            return False
        else:
            return True

    def warn(self, channel_name, days):
        """
        send warning text to channel_name, if it has not been sent already
        in the last DAYS days
        """
        messages = self.get_messages(channel_name, days)
        texts = [x['text'].strip() for x in messages]
        if self.warning_text in texts:
            # nothing to do
            print "Not warning {} because we already have".format(channel_name)
            return
        self.slackbot.say(channel_name, self.warning_text)
        print "Warned {}".format(channel_name)

    def safe_archive_all(self, days):
        """
        Safe-archives all channels stale longer than DAYS days
        """
        for channel in sorted(self.channels.keys()):
            if self.stale(channel, days):
                print "Attempting to safe-archive {}".format(channel)
                self.safe_archive(channel)

    def warn_all(self, days):
        """
        warns all channels which are DAYS idle
        """
        for channel in sorted(self.channels.keys()):
            if self.stale(channel, days):
                self.warn(channel, days)
            else:
                print "{} is not stale".format(channel)

    def get_stale_channels(self, days):
        ret = []
        for channel in sorted(self.channels.keys()):
            if self.stale(channel, days):
                ret.append(channel)
        return ret
