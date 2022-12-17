# -*- coding: utf-8 -*-

"""
Messaging hook to block compose progress until an ostree commit is signed.

The signing is implemented by robosignatory, which listens on the message bus
and reacts to messages about new commits. It will create a signature and then
update the ref in the repo to point to the new commit.

This script should not be used if Pungi is updating the reference on its own
(since that does not leave time for the signature).
"""

from __future__ import print_function

import argparse
import datetime
import json
import os
import sys
import time

import fedora_messaging.api
import fedora_messaging.exceptions


RESEND_INTERVAL = 300  # In seconds
SLEEP_TIME = 5


def is_ref_updated(ref_file, commit):
    """The ref is updated when the file points to the correct commit."""
    try:
        with open(ref_file) as f:
            return f.read().strip() == commit
    except IOError:
        # Failed to open the file, probably it does not exist, so let's just
        # wait more.
        return False


def ts_log(msg):
    print("%s: %s" % (datetime.datetime.utcnow(), msg))


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
        print("Error sending fedora-messaging message: %s" % e)
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

    if opts.cmd != "ostree":
        # Not an announcement of new ostree commit, nothing to do.
        sys.exit()

    if opts.config:
        fedora_messaging.config.conf.load_config(opts.config)

    try:
        data = json.load(sys.stdin)
    except ValueError:
        print("Failed to decode data", file=sys.stderr)
        sys.exit(1)

    repo = data["local_repo_path"]
    commit = data["commitid"]
    if not commit:
        print("No new commit was created, nothing will get signed.")
        sys.exit(0)

    path = "%s/objects/%s/%s.commitmeta" % (repo, commit[:2], commit[2:])

    def wait_for(msg, test, *args):
        time_slept = 0
        while not test(*args):
            ts_log(msg)
            time_slept += SLEEP_TIME
            if time_slept >= RESEND_INTERVAL:
                ts_log("Repeating notification")
                send(opts.cmd, data)
                time_slept = 0
            time.sleep(SLEEP_TIME)

    wait_for("Commit not signed yet", os.path.exists, path)
    ts_log("Found signature, waiting for ref to be updated.")
    ref_file = os.path.join(repo, "refs/heads", data["ref"])
    wait_for("Ref is not yet up-to-date", is_ref_updated, ref_file, commit)
    ts_log("Ref is up-to-date. All done!")
