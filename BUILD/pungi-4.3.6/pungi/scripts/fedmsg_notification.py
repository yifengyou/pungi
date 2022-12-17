# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import fedora_messaging.api
import fedora_messaging.config
import fedora_messaging.exceptions
import json
import sys


def send(cmd, data):
    topic = "compose.%s" % cmd.replace("-", ".").lower()
    try:
        msg = fedora_messaging.api.Message(topic="pungi.{}".format(topic), body=data)
        fedora_messaging.api.publish(msg)
    except fedora_messaging.exceptions.PublishReturned as e:
        print("Fedora Messaging broker rejected message %s: %s" % (msg.id, e))
        sys.exit(1)
    except fedora_messaging.exceptions.ConnectionException as e:
        print("Error sending message %s: %s" % (msg.id, e))
        sys.exit(1)
    except Exception as e:
        print("Error sending fedora-messaging message: %s" % (e))
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd")
    parser.add_argument(
        "--config",
        dest="config",
        help="fedora-messaging configuration file to use. "
        "This allows overriding the default "
        "/etc/fedora-messaging/config.toml.",
    )
    opts = parser.parse_args()

    if opts.config:
        fedora_messaging.config.conf.load_config(opts.config)

    data = json.load(sys.stdin)
    send(opts.cmd, data)
