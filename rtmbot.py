#!/usr/bin/env python

# This code is mostly from the rtmbot project; it handles the lower-level
# details of interacting with the Slack socket API, and imports the bot
# logic from teambot.py. It is also the application entry point.

import sys
sys.dont_write_bytecode = True

import glob
import yaml
import json
import os
import sys
import time
import logging
import importlib
import functools
import pprint
from argparse import ArgumentParser

from slackclient import SlackClient

import teambot

def dbg(debug_string):
    if debug:
        logging.info(debug_string)

class RtmBot(object):
    def __init__(self, token):
        self.last_ping = 0
        self.token = token
        self.bot_plugins = []
        self.slack_client = None

    def connect(self):
        """Convenience method that creates Server instance"""
        self.slack_client = SlackClient(self.token)
        self.slack_client.rtm_connect()

    def start(self):
        self.connect()
        self.load_plugins()
        while True:
            for reply in self.slack_client.rtm_read():
                self.input(reply)
            self.output()
            self.autoping()
            time.sleep(.1)

    def autoping(self):
        #hardcode the interval to 3 seconds
        now = int(time.time())
        if now > self.last_ping + 3:
            self.slack_client.server.ping()
            self.last_ping = now

    def input(self, data):
        if "type" in data:
            function_name = "process_" + data["type"]
            dbg("got {}".format(function_name))
            for plugin in self.bot_plugins:
                plugin.do(function_name, data)

    def output(self):
        for plugin in self.bot_plugins:
            limiter = False
            for output in plugin.do_output():
                channel = self.slack_client.server.channels.find(output[0])
                if channel != None and output[1] != None:
                    if limiter == True:
                        time.sleep(.1)
                        limiter = False
                    message = output[1].encode('ascii','ignore')
                    channel.send_message("{}".format(message))
                    limiter = True

    def load_plugins(self):
        self.bot_plugins.append(Plugin(teambot, self))

class Plugin(object):
    def __init__(self, module, bot):
        self.module = module
        name = module.__name__
        self.name = name

        self.outputs = []
        if name in config:
            logging.info("config found for: " + name)
            self.module.config = config[name]
        if 'setup' in dir(self.module):
            self.module.setup(bot)

    def do(self, function_name, data):
        if function_name in dir(self.module):
            #this makes the plugin fail with stack trace in debug mode
            if not debug:
                try:
                    eval("self.module."+function_name)(data)
                except:
                    dbg("problem in module {} {}".format(function_name, data))
            else:
                eval("self.module."+function_name)(data)

        if "catch_all" in dir(self.module):
            try:
                self.module.catch_all(data)
            except:
                dbg("problem in catch all")

    def do_output(self):
        output = []
        while True:
            if 'outputs' in dir(self.module):
                if len(self.module.outputs) > 0:
                    logging.info("output from {}".format(self.module))
                    output.append(self.module.outputs.pop(0))
                else:
                    break
            else:
                self.module.outputs = []
        return output

class UnknownChannel(Exception):
    pass


def main_loop():
    logging_conf = {
        'level': logging.INFO,
        'format': '%(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        'handlers': [logging.StreamHandler()],
    }
    if "LOGFILE" in config:
        logging_conf.update({
            'filename': config["LOGFILE"],
        })
    logging.basicConfig(**logging_conf)
    logging.info(directory)
    try:
        bot.start()
    except KeyboardInterrupt:
        sys.exit(0)
    except:
        logging.exception('OOPS')


def parse_args(args=None, namespace=None):
    """
    >>> from test.test_support import EnvironmentVarGuard
    >>> env = EnvironmentVarGuard()
    >>> # Without TEAMBOT_SETTINGS_MODULE
    >>> env.unset('TEAMBOT_SETTINGS_MODULE')
    >>> parse_args([])
    Namespace(config='rtmbot.conf', diffsettings=False, settings=None)
    >>> parse_args(["--diffsettings"])
    Namespace(config='rtmbot.conf', diffsettings=True, settings=None)
    >>> parse_args(["--config", 'teambotconfig.conf'])
    Namespace(config='teambotconfig.conf', diffsettings=False, settings=None)
    >>> # With TEAMBOT_SETTINGS_MODULE=settings
    >>> env.set('TEAMBOT_SETTINGS_MODULE', 'settings')
    >>> parse_args([])
    Namespace(config=None, diffsettings=False, settings='settings')
    >>> parse_args(["--diffsettings"])
    Namespace(config=None, diffsettings=True, settings='settings')
    >>> parse_args(["--settings", 'teambotconfig'])
    Namespace(config=None, diffsettings=False, settings='teambotconfig')
    """
    parser = ArgumentParser()

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '-c',
        '--config',
        help='Full path to config file.',
        metavar='path'
    )
    group.add_argument(
        '-s',
        '--settings',
        help='Python path to settings module.',
        metavar='module'
    )

    parser.add_argument(
        '--diffsettings',
        help='Displays the current settings and exits.',
        action='store_true'
    )

    # Allows the bot to be run with zero arguments and use a Python module
    # instead of a YAML file.
    if os.getenv('TEAMBOT_SETTINGS_MODULE') is not None:
        parser.set_defaults(settings=os.getenv('TEAMBOT_SETTINGS_MODULE'))
    else:
        parser.set_defaults(config='rtmbot.conf')

    return parser.parse_args(args, namespace)

def get_config(args):
    if args.config:
        config = yaml.load(file(args.config, 'r'))
    elif args.settings:
        s = importlib.import_module(args.settings)
        get_s = functools.partial(getattr, s)
        config = {
            'DAEMON': get_s('DAEMON', False),
            'DEBUG': get_s('DEBUG', False),
            'SLACK_TOKEN': get_s('SLACK_TOKEN', None),
        }
    return config

if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    directory = os.path.dirname(sys.argv[0])
    if not directory.startswith('/'):
        directory = os.path.abspath("{}/{}".format(os.getcwd(),
                                directory
                                ))

    config = get_config(args)

    if args.diffsettings:
        pprint.pprint(config)
        sys.exit()

    debug = config["DEBUG"]
    bot = RtmBot(config["SLACK_TOKEN"])
    site_plugins = []
    files_currently_downloading = []
    job_hash = {}

    if config.has_key("DAEMON"):
        if config["DAEMON"]:
            import daemon
            with daemon.DaemonContext():
                main_loop()
    main_loop()
