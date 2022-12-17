# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import atexit
import errno
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import threading
from collections import namedtuple

import kobo.conf
import kobo.log
import productmd
from kobo import shortcuts
from six.moves import configparser, shlex_quote

import pungi.util
from pungi.compose import get_compose_dir
from pungi.linker import linker_pool
from pungi.phases.pkgset.sources.source_koji import get_koji_event_raw
from pungi.util import find_old_compose, parse_koji_event, temp_dir
from pungi.wrappers.kojiwrapper import KojiWrapper


Config = namedtuple(
    "Config",
    [
        # Path to directory with the compose
        "target",
        "compose_type",
        "label",
        # Path to the selected old compose that will be reused
        "old_compose",
        # Path to directory with config file copies
        "config_dir",
        # Which koji event to use (if any)
        "event",
        # Additional arguments to pungi-koji executable
        "extra_args",
    ],
)

log = logging.getLogger(__name__)


class Status(object):
    # Ready to start
    READY = "READY"
    # Waiting for dependencies to finish.
    WAITING = "WAITING"
    # Part is currently running
    STARTED = "STARTED"
    # A dependency failed, this one will never start.
    BLOCKED = "BLOCKED"


class ComposePart(object):
    def __init__(self, name, config, just_phase=[], skip_phase=[], dependencies=[]):
        self.name = name
        self.config = config
        self.status = Status.WAITING if dependencies else Status.READY
        self.just_phase = just_phase
        self.skip_phase = skip_phase
        self.blocked_on = set(dependencies)
        self.depends_on = set(dependencies)
        self.path = None
        self.log_file = None
        self.failable = False

    def __str__(self):
        return self.name

    def __repr__(self):
        return (
            "ComposePart({0.name!r},"
            " {0.config!r},"
            " {0.status!r},"
            " just_phase={0.just_phase!r},"
            " skip_phase={0.skip_phase!r},"
            " dependencies={0.depends_on!r})"
        ).format(self)

    def refresh_status(self):
        """Refresh status of this part with the result of the compose. This
        should only be called once the compose finished.
        """
        try:
            with open(os.path.join(self.path, "STATUS")) as fh:
                self.status = fh.read().strip()
        except IOError as exc:
            log.error("Failed to update status of %s: %s", self.name, exc)
            log.error("Assuming %s is DOOMED", self.name)
            self.status = "DOOMED"

    def is_finished(self):
        return "FINISHED" in self.status

    def unblock_on(self, finished_part):
        """Update set of blockers for this part. If it's empty, mark us as ready."""
        self.blocked_on.discard(finished_part)
        if self.status == Status.WAITING and not self.blocked_on:
            log.debug("%s is ready to start", self)
            self.status = Status.READY

    def setup_start(self, global_config, parts):
        substitutions = dict(
            ("part-%s" % name, p.path) for name, p in parts.items() if p.is_finished()
        )
        substitutions["configdir"] = global_config.config_dir

        config = pungi.util.load_config(self.config)

        for f in config.opened_files:
            # apply substitutions
            fill_in_config_file(f, substitutions)

        self.status = Status.STARTED
        self.path = get_compose_dir(
            os.path.join(global_config.target, "parts"),
            config,
            compose_type=global_config.compose_type,
            compose_label=global_config.label,
        )
        self.log_file = os.path.join(global_config.target, "logs", "%s.log" % self.name)
        log.info("Starting %s in %s", self.name, self.path)

    def get_cmd(self, global_config):
        cmd = ["pungi-koji", "--config", self.config, "--compose-dir", self.path]
        cmd.append("--%s" % global_config.compose_type)
        if global_config.label:
            cmd.extend(["--label", global_config.label])
        for phase in self.just_phase:
            cmd.extend(["--just-phase", phase])
        for phase in self.skip_phase:
            cmd.extend(["--skip-phase", phase])
        if global_config.old_compose:
            cmd.extend(
                ["--old-compose", os.path.join(global_config.old_compose, "parts")]
            )
        if global_config.event:
            cmd.extend(["--koji-event", str(global_config.event)])
        if global_config.extra_args:
            cmd.extend(global_config.extra_args)
        cmd.extend(["--no-latest-link"])
        return cmd

    @classmethod
    def from_config(cls, config, section, config_dir):
        part = cls(
            name=section,
            config=os.path.join(config_dir, config.get(section, "config")),
            just_phase=_safe_get_list(config, section, "just_phase", []),
            skip_phase=_safe_get_list(config, section, "skip_phase", []),
            dependencies=_safe_get_list(config, section, "depends_on", []),
        )
        if config.has_option(section, "failable"):
            part.failable = config.getboolean(section, "failable")
        return part


def _safe_get_list(config, section, option, default=None):
    """Get a value from config parser. The result is split into a list on
    commas or spaces, and `default` is returned if the key does not exist.
    """
    if config.has_option(section, option):
        value = config.get(section, option)
        return [x.strip() for x in re.split(r"[, ]+", value) if x]
    return default


def fill_in_config_file(fp, substs):
    """Templating function. It works with Jinja2 style placeholders such as
    {{foo}}. Whitespace around the key name is fine. The file is modified in place.

    :param fp string: path to the file to process
    :param substs dict: a mapping for values to put into the file
    """

    def repl(match):
        try:
            return substs[match.group(1)]
        except KeyError as exc:
            raise RuntimeError(
                "Unknown placeholder %s in %s" % (exc, os.path.basename(fp))
            )

    with open(fp, "r") as f:
        contents = re.sub(r"{{ *([a-zA-Z-_]+) *}}", repl, f.read())
    with open(fp, "w") as f:
        f.write(contents)


def start_part(global_config, parts, part):
    part.setup_start(global_config, parts)
    fh = open(part.log_file, "w")
    cmd = part.get_cmd(global_config)
    log.debug("Running command %r", " ".join(shlex_quote(x) for x in cmd))
    return subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)


def handle_finished(global_config, linker, parts, proc, finished_part):
    finished_part.refresh_status()
    log.info("%s finished with status %s", finished_part, finished_part.status)
    if proc.returncode == 0:
        # Success, unblock other parts...
        for part in parts.values():
            part.unblock_on(finished_part.name)
        # ...and link the results into final destination.
        copy_part(global_config, linker, finished_part)
        update_metadata(global_config, finished_part)
    else:
        # Failure, other stuff may be blocked.
        log.info("See details in %s", finished_part.log_file)
        block_on(parts, finished_part.name)


def copy_part(global_config, linker, part):
    c = productmd.Compose(part.path)
    for variant in c.info.variants:
        data_path = os.path.join(part.path, "compose", variant)
        link = os.path.join(global_config.target, "compose", variant)
        log.info("Hardlinking content %s -> %s", data_path, link)
        hardlink_dir(linker, data_path, link)


def hardlink_dir(linker, srcdir, dstdir):
    for root, dirs, files in os.walk(srcdir):
        root = os.path.relpath(root, srcdir)
        for f in files:
            src = os.path.normpath(os.path.join(srcdir, root, f))
            dst = os.path.normpath(os.path.join(dstdir, root, f))
            linker.queue_put((src, dst))


def update_metadata(global_config, part):
    part_metadata_dir = os.path.join(part.path, "compose", "metadata")
    final_metadata_dir = os.path.join(global_config.target, "compose", "metadata")
    for f in os.listdir(part_metadata_dir):
        # Load the metadata
        with open(os.path.join(part_metadata_dir, f)) as fh:
            part_metadata = json.load(fh)
        final_metadata = os.path.join(final_metadata_dir, f)
        if os.path.exists(final_metadata):
            # We already have this file, will need to merge.
            merge_metadata(final_metadata, part_metadata)
        else:
            # A new file, just copy it.
            copy_metadata(global_config, final_metadata, part_metadata)


def copy_metadata(global_config, final_metadata, source):
    """Copy file to final location, but update compose information."""
    with open(
        os.path.join(global_config.target, "compose/metadata/composeinfo.json")
    ) as f:
        composeinfo = json.load(f)
    try:
        source["payload"]["compose"].update(composeinfo["payload"]["compose"])
    except KeyError:
        # No [payload][compose], probably OSBS metadata
        pass
    with open(final_metadata, "w") as f:
        json.dump(source, f, indent=2, sort_keys=True)


def merge_metadata(final_metadata, source):
    with open(final_metadata) as f:
        metadata = json.load(f)

    try:
        key = {
            "productmd.composeinfo": "variants",
            "productmd.modules": "modules",
            "productmd.images": "images",
            "productmd.rpms": "rpms",
        }[source["header"]["type"]]
        # TODO what if multiple parts create images for the same variant
        metadata["payload"][key].update(source["payload"][key])
    except KeyError:
        # OSBS metadata, merge whole file
        metadata.update(source)
    with open(final_metadata, "w") as f:
        json.dump(metadata, f, indent=2, sort_keys=True)


def block_on(parts, name):
    """Part ``name`` failed, mark everything depending on it as blocked."""
    for part in parts.values():
        if name in part.blocked_on:
            log.warning("%s is blocked now and will not run", part)
            part.status = Status.BLOCKED
            block_on(parts, part.name)


def check_finished_processes(processes):
    """Walk through all active processes and check if something finished."""
    for proc in processes.keys():
        proc.poll()
        if proc.returncode is not None:
            yield proc, processes[proc]


def run_all(global_config, parts):
    # Mapping subprocess.Popen -> ComposePart
    processes = dict()
    remaining = set(p.name for p in parts.values() if not p.is_finished())

    with linker_pool("hardlink") as linker:
        while remaining or processes:
            update_status(global_config, parts)

            for proc, part in check_finished_processes(processes):
                del processes[proc]
                handle_finished(global_config, linker, parts, proc, part)

            # Start new available processes.
            for name in list(remaining):
                part = parts[name]
                # Start all ready parts
                if part.status == Status.READY:
                    remaining.remove(name)
                    processes[start_part(global_config, parts, part)] = part
                # Remove blocked parts from todo list
                elif part.status == Status.BLOCKED:
                    remaining.remove(part.name)

            # Wait for any child process to finish if there is any.
            if processes:
                pid, reason = os.wait()
                for proc in processes.keys():
                    # Set the return code for process that we caught by os.wait().
                    # Calling poll() on it would not set the return code properly
                    # since the value was already consumed by os.wait().
                    if proc.pid == pid:
                        proc.returncode = (reason >> 8) & 0xFF

        log.info("Waiting for linking to finish...")
    return update_status(global_config, parts)


def get_target_dir(config, compose_info, label, reldir=""):
    """Find directory where this compose will be.

    @param reldir: if target path in config is relative, it will be resolved
                   against this directory
    """
    dir = os.path.realpath(os.path.join(reldir, config.get("general", "target")))
    target_dir = get_compose_dir(
        dir,
        compose_info,
        compose_type=config.get("general", "compose_type"),
        compose_label=label,
    )
    return target_dir


def setup_logging(debug=False):
    FORMAT = "%(asctime)s: %(levelname)s: %(message)s"
    level = logging.DEBUG if debug else logging.INFO
    kobo.log.add_stderr_logger(log, log_level=level, format=FORMAT)
    log.setLevel(level)


def compute_status(statuses):
    if any(map(lambda x: x[0] in ("STARTED", "WAITING"), statuses)):
        # If there is anything still running or waiting to start, the whole is
        # still running.
        return "STARTED"
    elif any(map(lambda x: x[0] in ("DOOMED", "BLOCKED") and not x[1], statuses)):
        # If any required part is doomed or blocked, the whole is doomed
        return "DOOMED"
    elif all(map(lambda x: x[0] == "FINISHED", statuses)):
        # If all parts are complete, the whole is complete
        return "FINISHED"
    else:
        return "FINISHED_INCOMPLETE"


def update_status(global_config, parts):
    log.debug("Updating status metadata")
    metadata = {}
    statuses = set()
    for part in parts.values():
        metadata[part.name] = {"status": part.status, "path": part.path}
        statuses.add((part.status, part.failable))
    metadata_path = os.path.join(
        global_config.target, "compose", "metadata", "parts.json"
    )
    with open(metadata_path, "w") as fh:
        json.dump(metadata, fh, indent=2, sort_keys=True, separators=(",", ": "))

    status = compute_status(statuses)
    log.info("Overall status is %s", status)
    with open(os.path.join(global_config.target, "STATUS"), "w") as fh:
        fh.write(status)

    return status != "DOOMED"


def prepare_compose_dir(config, args, main_config_file, compose_info):
    if not hasattr(args, "compose_path"):
        # Creating a brand new compose
        target_dir = get_target_dir(
            config, compose_info, args.label, reldir=os.path.dirname(main_config_file)
        )
        for dir in ("logs", "parts", "compose/metadata", "work/global"):
            try:
                os.makedirs(os.path.join(target_dir, dir))
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    raise
        with open(os.path.join(target_dir, "STATUS"), "w") as fh:
            fh.write("STARTED")
        # Copy initial composeinfo for new compose
        shutil.copy(
            os.path.join(target_dir, "work/global/composeinfo-base.json"),
            os.path.join(target_dir, "compose/metadata/composeinfo.json"),
        )
    else:
        # Restarting a particular compose
        target_dir = args.compose_path

    return target_dir


def load_parts_metadata(global_config):
    parts_metadata = os.path.join(global_config.target, "compose/metadata/parts.json")
    with open(parts_metadata) as f:
        return json.load(f)


def setup_for_restart(global_config, parts, to_restart):
    has_stuff_to_do = False
    metadata = load_parts_metadata(global_config)
    for key in metadata:
        # Update state to match what is on disk
        log.debug(
            "Reusing %s (%s) from %s",
            key,
            metadata[key]["status"],
            metadata[key]["path"],
        )
        parts[key].status = metadata[key]["status"]
        parts[key].path = metadata[key]["path"]
    for key in to_restart:
        # Set restarted parts to run again
        parts[key].status = Status.WAITING
        parts[key].path = None

    for key in to_restart:
        # Remove blockers that are already finished
        for blocker in list(parts[key].blocked_on):
            if parts[blocker].is_finished():
                parts[key].blocked_on.discard(blocker)
        if not parts[key].blocked_on:
            log.debug("Part %s in not blocked", key)
            # Nothing blocks it; let's go
            parts[key].status = Status.READY
            has_stuff_to_do = True

    if not has_stuff_to_do:
        raise RuntimeError("All restarted parts are blocked. Nothing to do.")


def run_kinit(config):
    if not config.getboolean("general", "kerberos"):
        return

    keytab = config.get("general", "kerberos_keytab")
    principal = config.get("general", "kerberos_principal")

    fd, fname = tempfile.mkstemp(prefix="krb5cc_pungi-orchestrate_")
    os.close(fd)
    os.environ["KRB5CCNAME"] = fname
    shortcuts.run(["kinit", "-k", "-t", keytab, principal])
    log.debug("Created a kerberos ticket for %s", principal)

    atexit.register(os.remove, fname)


def get_compose_data(compose_path):
    try:
        compose = productmd.compose.Compose(compose_path)
        data = {
            "compose_id": compose.info.compose.id,
            "compose_date": compose.info.compose.date,
            "compose_type": compose.info.compose.type,
            "compose_respin": str(compose.info.compose.respin),
            "compose_label": compose.info.compose.label,
            "release_id": compose.info.release_id,
            "release_name": compose.info.release.name,
            "release_short": compose.info.release.short,
            "release_version": compose.info.release.version,
            "release_type": compose.info.release.type,
            "release_is_layered": compose.info.release.is_layered,
        }
        if compose.info.release.is_layered:
            data.update(
                {
                    "base_product_name": compose.info.base_product.name,
                    "base_product_short": compose.info.base_product.short,
                    "base_product_version": compose.info.base_product.version,
                    "base_product_type": compose.info.base_product.type,
                }
            )
        return data
    except Exception:
        return {}


def get_script_env(compose_path):
    env = os.environ.copy()
    env["COMPOSE_PATH"] = compose_path
    for key, value in get_compose_data(compose_path).items():
        if isinstance(value, bool):
            env[key.upper()] = "YES" if value else ""
        else:
            env[key.upper()] = str(value) if value else ""
    return env


def run_scripts(prefix, compose_dir, scripts):
    env = get_script_env(compose_dir)
    for idx, script in enumerate(scripts.strip().splitlines()):
        command = script.strip()
        logfile = os.path.join(compose_dir, "logs", "%s%s.log" % (prefix, idx))
        log.debug("Running command: %r", command)
        log.debug("See output in %s", logfile)
        shortcuts.run(command, env=env, logfile=logfile)


def try_translate_path(parts, path):
    translation = []
    for part in parts.values():
        conf = pungi.util.load_config(part.config)
        translation.extend(conf.get("translate_paths", []))
    return pungi.util.translate_path_raw(translation, path)


def send_notification(compose_dir, command, parts):
    if not command:
        return
    from pungi.notifier import PungiNotifier

    data = get_compose_data(compose_dir)
    data["location"] = try_translate_path(parts, compose_dir)
    notifier = PungiNotifier([command])
    with open(os.path.join(compose_dir, "STATUS")) as f:
        status = f.read().strip()
    notifier.send("status-change", workdir=compose_dir, status=status, **data)


def setup_progress_monitor(global_config, parts):
    """Update configuration so that each part send notifications about its
    progress to the orchestrator.

    There is a file to which the notification is written. The orchestrator is
    reading it and mapping the entries to particular parts. The path to this
    file is stored in an environment variable.
    """
    tmp_file = tempfile.NamedTemporaryFile(prefix="pungi-progress-monitor_")
    os.environ["_PUNGI_ORCHESTRATOR_PROGRESS_MONITOR"] = tmp_file.name
    atexit.register(os.remove, tmp_file.name)

    global_config.extra_args.append(
        "--notification-script=pungi-notification-report-progress"
    )

    def reader():
        while True:
            line = tmp_file.readline()
            if not line:
                time.sleep(0.1)
                continue
            path, msg = line.split(":", 1)
            for part in parts:
                if parts[part].path == os.path.dirname(path):
                    log.debug("%s: %s", part, msg.strip())
                    break

    monitor = threading.Thread(target=reader)
    monitor.daemon = True
    monitor.start()


def run(work_dir, main_config_file, args):
    config_dir = os.path.join(work_dir, "config")
    shutil.copytree(os.path.dirname(main_config_file), config_dir)

    # Read main config
    parser = configparser.RawConfigParser(
        defaults={
            "kerberos": "false",
            "pre_compose_script": "",
            "post_compose_script": "",
            "notification_script": "",
        }
    )
    parser.read(main_config_file)

    # Create kerberos ticket
    run_kinit(parser)

    compose_info = dict(parser.items("general"))
    compose_type = parser.get("general", "compose_type")

    target_dir = prepare_compose_dir(parser, args, main_config_file, compose_info)
    kobo.log.add_file_logger(log, os.path.join(target_dir, "logs", "orchestrator.log"))
    log.info("Composing %s", target_dir)

    run_scripts("pre_compose_", target_dir, parser.get("general", "pre_compose_script"))

    old_compose = find_old_compose(
        os.path.dirname(target_dir),
        compose_info["release_short"],
        compose_info["release_version"],
        "",
    )
    if old_compose:
        log.info("Reusing old compose %s", old_compose)

    global_config = Config(
        target=target_dir,
        compose_type=compose_type,
        label=args.label,
        old_compose=old_compose,
        config_dir=os.path.dirname(main_config_file),
        event=args.koji_event,
        extra_args=_safe_get_list(parser, "general", "extra_args"),
    )

    if not global_config.event and parser.has_option("general", "koji_profile"):
        koji_wrapper = KojiWrapper(parser.get("general", "koji_profile"))
        event_file = os.path.join(global_config.target, "work/global/koji-event")
        result = get_koji_event_raw(koji_wrapper, None, event_file)
        global_config = global_config._replace(event=result["id"])

    parts = {}
    for section in parser.sections():
        if section == "general":
            continue
        parts[section] = ComposePart.from_config(parser, section, config_dir)

    if hasattr(args, "part"):
        setup_for_restart(global_config, parts, args.part)

    setup_progress_monitor(global_config, parts)

    send_notification(target_dir, parser.get("general", "notification_script"), parts)

    retcode = run_all(global_config, parts)

    if retcode:
        # Only run the script if we are not doomed.
        run_scripts(
            "post_compose_", target_dir, parser.get("general", "post_compose_script")
        )

    send_notification(target_dir, parser.get("general", "notification_script"), parts)

    return retcode


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--koji-event", metavar="ID", type=parse_koji_event)
    subparsers = parser.add_subparsers()
    start = subparsers.add_parser("start")
    start.add_argument("config", metavar="CONFIG")
    start.add_argument("--label")

    restart = subparsers.add_parser("restart")
    restart.add_argument("config", metavar="CONFIG")
    restart.add_argument("compose_path", metavar="COMPOSE_PATH")
    restart.add_argument(
        "part", metavar="PART", nargs="*", help="which parts to restart"
    )
    restart.add_argument("--label")

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    setup_logging(args.debug)

    main_config_file = os.path.abspath(args.config)

    with temp_dir() as work_dir:
        try:
            if not run(work_dir, main_config_file, args):
                sys.exit(1)
        except Exception:
            log.exception("Unhandled exception!")
            sys.exit(1)
