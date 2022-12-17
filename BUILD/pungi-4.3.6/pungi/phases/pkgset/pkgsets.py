# -*- coding: utf-8 -*-


# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <https://gnu.org/licenses/>.


"""
The KojiPackageSet object obtains the latest RPMs from a Koji tag.
It automatically finds a signed copies according to *sigkey_ordering*.
"""

import itertools
import json
import os
import time
from six.moves import cPickle as pickle

import kobo.log
import kobo.pkgset
import kobo.rpmlib

from kobo.threads import WorkerThread, ThreadPool

from pungi.util import pkg_is_srpm, copy_all
from pungi.arch import get_valid_arches, is_excluded
from pungi.errors import UnsignedPackagesError


class ExtendedRpmWrapper(kobo.pkgset.SimpleRpmWrapper):
    """
    ExtendedRpmWrapper extracts only certain RPM fields instead of
    keeping the whole RPM header in memory.
    """

    def __init__(self, file_path, ts=None, **kwargs):
        kobo.pkgset.SimpleRpmWrapper.__init__(self, file_path, ts=ts)
        header = kobo.rpmlib.get_rpm_header(file_path, ts=ts)
        self.requires = set(kobo.rpmlib.get_header_field(header, "requires"))
        self.provides = set(kobo.rpmlib.get_header_field(header, "provides"))


class ReaderPool(ThreadPool):
    def __init__(self, package_set, logger=None):
        ThreadPool.__init__(self, logger)
        self.package_set = package_set


class ReaderThread(WorkerThread):
    def process(self, item, num):
        # rpm_info, build_info = item

        if (num % 100 == 0) or (num == self.pool.queue_total):
            self.pool.package_set.log_debug(
                "Processed %s out of %s packages" % (num, self.pool.queue_total)
            )

        rpm_path = self.pool.package_set.get_package_path(item)
        if rpm_path is None:
            return

        # In case we have old file cache data, try to reuse it.
        if self.pool.package_set.old_file_cache:
            # Try to find the RPM in old_file_cache and reuse it instead of
            # reading its headers again.
            try:
                rpm_obj = self.pool.package_set.old_file_cache[rpm_path]
            except KeyError:
                rpm_obj = None

            # Also reload rpm_obj if it's not ExtendedRpmWrapper object
            # to get the requires/provides data into the cache.
            if rpm_obj and isinstance(rpm_obj, ExtendedRpmWrapper):
                self.pool.package_set.file_cache[rpm_path] = rpm_obj
            else:
                rpm_obj = self.pool.package_set.file_cache.add(rpm_path)
        else:
            rpm_obj = self.pool.package_set.file_cache.add(rpm_path)
        self.pool.package_set.rpms_by_arch.setdefault(rpm_obj.arch, []).append(rpm_obj)

        if pkg_is_srpm(rpm_obj):
            self.pool.package_set.srpms_by_name[rpm_obj.file_name] = rpm_obj
        elif rpm_obj.arch == "noarch":
            srpm = self.pool.package_set.srpms_by_name.get(rpm_obj.sourcerpm, None)
            if srpm:
                # HACK: copy {EXCLUDE,EXCLUSIVE}ARCH from SRPM to noarch RPMs
                rpm_obj.excludearch = srpm.excludearch
                rpm_obj.exclusivearch = srpm.exclusivearch
            else:
                self.pool.log_warning("Can't find a SRPM for %s" % rpm_obj.file_name)


class PackageSetBase(kobo.log.LoggingBase):
    def __init__(
        self,
        name,
        sigkey_ordering,
        arches=None,
        logger=None,
        allow_invalid_sigkeys=False,
    ):
        super(PackageSetBase, self).__init__(logger=logger)
        self.name = name
        self.file_cache = kobo.pkgset.FileCache(ExtendedRpmWrapper)
        self.old_file_cache = None
        self.sigkey_ordering = tuple(sigkey_ordering or [None])
        self.arches = arches
        self.rpms_by_arch = {}
        self.srpms_by_name = {}
        # RPMs not found for specified sigkeys
        self._invalid_sigkey_rpms = []
        self._allow_invalid_sigkeys = allow_invalid_sigkeys

    @property
    def invalid_sigkey_rpms(self):
        return self._invalid_sigkey_rpms

    def __getitem__(self, name):
        return self.file_cache[name]

    def __len__(self):
        return len(self.file_cache)

    def __iter__(self):
        for i in self.file_cache:
            yield i

    def __getstate__(self):
        result = self.__dict__.copy()
        del result["_logger"]
        return result

    def __setstate__(self, data):
        self._logger = None
        self.__dict__.update(data)

    def raise_invalid_sigkeys_exception(self, rpminfos):
        """
        Raises UnsignedPackagesError containing details of RPMs with invalid
        sigkeys defined in `rpminfos`.
        """

        def nvr_formatter(package_info):
            # joins NVR parts of the package with '-' character.
            return "-".join(
                (package_info["name"], package_info["version"], package_info["release"])
            )

        def get_error(sigkeys, infos):
            return (
                "RPM(s) not found for sigs: %s. Check log for details. "
                "Unsigned packages:\n%s"
                % (
                    sigkeys,
                    "\n".join(sorted(set(nvr_formatter(rpminfo) for rpminfo in infos))),
                )
            )

        if not isinstance(rpminfos, dict):
            rpminfos = {self.sigkey_ordering: rpminfos}
        raise UnsignedPackagesError(
            "\n".join(get_error(k, v) for k, v in rpminfos.items())
        )

    def read_packages(self, rpms, srpms):
        srpm_pool = ReaderPool(self, self._logger)
        rpm_pool = ReaderPool(self, self._logger)

        for i in rpms:
            rpm_pool.queue_put(i)

        for i in srpms:
            srpm_pool.queue_put(i)

        thread_count = 10
        for i in range(thread_count):
            srpm_pool.add(ReaderThread(srpm_pool))
            rpm_pool.add(ReaderThread(rpm_pool))

        # process SRC and NOSRC packages first (see ReaderTread for the
        # EXCLUDEARCH/EXCLUSIVEARCH hack for noarch packages)
        self.log_debug("Package set: spawning %s worker threads (SRPMs)" % thread_count)
        srpm_pool.start()
        srpm_pool.stop()
        self.log_debug("Package set: worker threads stopped (SRPMs)")

        self.log_debug("Package set: spawning %s worker threads (RPMs)" % thread_count)
        rpm_pool.start()
        rpm_pool.stop()
        self.log_debug("Package set: worker threads stopped (RPMs)")

        if not self._allow_invalid_sigkeys and self._invalid_sigkey_rpms:
            self.raise_invalid_sigkeys_exception(self._invalid_sigkey_rpms)

        return self.rpms_by_arch

    def subset(self, primary_arch, arch_list, exclusive_noarch=True):
        """Create a subset of this package set that only includes
        packages compatible with"""
        pkgset = PackageSetBase(
            self.name, self.sigkey_ordering, logger=self._logger, arches=arch_list
        )
        pkgset.merge(self, primary_arch, arch_list, exclusive_noarch=exclusive_noarch)
        return pkgset

    def merge(self, other, primary_arch, arch_list, exclusive_noarch=True):
        """
        Merge ``other`` package set into this instance.
        """
        msg = "Merging package sets for %s: %s" % (primary_arch, arch_list)
        self.log_debug("[BEGIN] %s" % msg)

        # if "src" is present, make sure "nosrc" is included too
        if "src" in arch_list and "nosrc" not in arch_list:
            arch_list.append("nosrc")

        # make sure sources are processed last
        for i in ("nosrc", "src"):
            if i in arch_list:
                arch_list.remove(i)
                arch_list.append(i)

        seen_sourcerpms = set()
        # {Exclude,Exclusive}Arch must match *tree* arch + compatible native
        # arches (excluding multilib arches)
        if primary_arch:
            exclusivearch_list = get_valid_arches(
                primary_arch, multilib=False, add_noarch=False, add_src=False
            )
            # We don't want to consider noarch: if a package is true noarch
            # build (not just a subpackage), it has to have noarch in
            # ExclusiveArch otherwise rpm will refuse to build it.
            # This should eventually become a default, but it could have a big
            # impact and thus it's hidden behind an option.
            if not exclusive_noarch and "noarch" in exclusivearch_list:
                exclusivearch_list.remove("noarch")
        else:
            exclusivearch_list = None
        for arch in arch_list:
            self.rpms_by_arch.setdefault(arch, [])
            for i in other.rpms_by_arch.get(arch, []):
                if i.file_path in self.file_cache:
                    # TODO: test if it really works
                    continue
                if exclusivearch_list and arch == "noarch":
                    if is_excluded(i, exclusivearch_list, logger=self._logger):
                        continue

                if arch in ("nosrc", "src"):
                    # include only sources having binary packages
                    if i.name not in seen_sourcerpms:
                        continue
                else:
                    sourcerpm_name = kobo.rpmlib.parse_nvra(i.sourcerpm)["name"]
                    seen_sourcerpms.add(sourcerpm_name)

                self.file_cache.file_cache[i.file_path] = i
                self.rpms_by_arch[arch].append(i)

        self.log_debug("[DONE ] %s" % msg)

    def save_file_list(self, file_path, remove_path_prefix=None):
        with open(file_path, "w") as f:
            for arch in sorted(self.rpms_by_arch):
                for i in self.rpms_by_arch[arch]:
                    rpm_path = i.file_path
                    if remove_path_prefix and rpm_path.startswith(remove_path_prefix):
                        rpm_path = rpm_path[len(remove_path_prefix) :]
                    f.write("%s\n" % rpm_path)

    @staticmethod
    def load_old_file_cache(file_path):
        """
        Loads the cached FileCache stored in pickle format in `file_path`.
        """
        with open(file_path, "rb") as f:
            return pickle.load(f)

    def set_old_file_cache(self, old_file_cache):
        """Set cache of old files."""
        self.old_file_cache = old_file_cache

    def save_file_cache(self, file_path):
        """
        Saves the current FileCache using the pickle module to `file_path`.
        """
        with open(file_path, "wb") as f:
            pickle.dump(self.file_cache, f, protocol=pickle.HIGHEST_PROTOCOL)


class FilelistPackageSet(PackageSetBase):
    def get_package_path(self, queue_item):
        # TODO: sigkey checking
        rpm_path = os.path.abspath(queue_item)
        return rpm_path

    def populate(self, file_list):
        result_rpms = []
        result_srpms = []
        msg = "Getting RPMs from file list"
        self.log_info("[BEGIN] %s" % msg)
        for i in file_list:
            if i.endswith(".src.rpm") or i.endswith(".nosrc.rpm"):
                result_srpms.append(i)
            else:
                result_rpms.append(i)
        result = self.read_packages(result_rpms, result_srpms)
        self.log_info("[DONE ] %s" % msg)
        return result


class KojiPackageSet(PackageSetBase):
    def __init__(
        self,
        name,
        koji_wrapper,
        sigkey_ordering,
        arches=None,
        logger=None,
        packages=None,
        allow_invalid_sigkeys=False,
        populate_only_packages=False,
        cache_region=None,
        extra_builds=None,
        extra_tasks=None,
        signed_packages_retries=0,
        signed_packages_wait=30,
    ):
        """
        Creates new KojiPackageSet.

        :param list sigkey_ordering: Ordered list of sigkey strings. When
            getting package from Koji, KojiPackageSet tries to get the package
            signed by sigkey from this list. If None or "" appears in this
            list, unsigned package is used.
        :param list arches: List of arches to get the packages for.
        :param logging.Logger logger: Logger instance to use for logging.
        :param list packages: List of package names to be used when
            `allow_invalid_sigkeys` or `populate_only_packages` is set.
        :param bool allow_invalid_sigkeys: When True, packages *not* listed in
            the `packages` list are added to KojiPackageSet even if they have
            invalid sigkey. This is useful in case Koji tag contains some
            unsigned packages, but we know they won't appear in a compose.
            When False, all packages in Koji tag must have valid sigkey as
            defined in `sigkey_ordering`.
        :param bool populate_only_packages. When True, only packages in
            `packages` list are added to KojiPackageSet. This can save time
            when generating compose from predefined list of packages from big
            Koji tag.
            When False, all packages from Koji tag are added to KojiPackageSet.
        :param dogpile.cache.CacheRegion cache_region: If set, the CacheRegion
            will be used to cache the list of RPMs per Koji tag, so next calls
            of the KojiPackageSet.populate(...) method won't try fetching it
            again.
        :param list extra_builds: Extra builds NVRs to get from Koji and include
            in the package set.
        :param list extra_tasks: Extra RPMs defined as Koji task IDs to get from Koji
            and include in the package set. Useful when building testing compose
            with RPM scratch builds.
        :param int signed_packages_retries: How many times should a search for
            signed package be repeated.
        :param int signed_packages_wait: How long to wait between search attemts.
        """
        super(KojiPackageSet, self).__init__(
            name,
            sigkey_ordering=sigkey_ordering,
            arches=arches,
            logger=logger,
            allow_invalid_sigkeys=allow_invalid_sigkeys,
        )
        self.koji_wrapper = koji_wrapper
        # Names of packages to look for in the Koji tag.
        self.packages = set(packages or [])
        self.populate_only_packages = populate_only_packages
        self.cache_region = cache_region
        self.extra_builds = extra_builds or []
        self.extra_tasks = extra_tasks or []
        self.reuse = None
        self.signed_packages_retries = signed_packages_retries
        self.signed_packages_wait = signed_packages_wait

    def __getstate__(self):
        result = self.__dict__.copy()
        del result["koji_wrapper"]
        del result["_logger"]
        if "cache_region" in result:
            del result["cache_region"]
        return result

    def __setstate__(self, data):
        self._logger = None
        self.__dict__.update(data)

    @property
    def koji_proxy(self):
        return self.koji_wrapper.koji_proxy

    def get_extra_rpms(self):
        if not self.extra_builds:
            return [], []

        rpms = []
        builds = []

        builds = self.koji_wrapper.retrying_multicall_map(
            self.koji_proxy, self.koji_proxy.getBuild, list_of_args=self.extra_builds
        )
        rpms_in_builds = self.koji_wrapper.retrying_multicall_map(
            self.koji_proxy,
            self.koji_proxy.listBuildRPMs,
            list_of_args=self.extra_builds,
        )

        rpms = []
        for rpms_in_build in rpms_in_builds:
            rpms += rpms_in_build
        return rpms, builds

    def get_extra_rpms_from_tasks(self):
        """
        Returns manually constructed RPM infos from the Koji tasks defined
        in `self.extra_tasks`.

        :rtype: list
        :return: List with RPM infos defined as dicts with following keys:
            - name, version, release, arch, src - as returned by parse_nvra.
            - path_from_task - Full path to RPM on /mnt/koji.
            - build_id - Always set to None.
        """
        if not self.extra_tasks:
            return []

        # Get the IDs of children tasks - these are the tasks containing
        # the resulting RPMs.
        children_tasks = self.koji_wrapper.retrying_multicall_map(
            self.koji_proxy,
            self.koji_proxy.getTaskChildren,
            list_of_args=self.extra_tasks,
        )
        children_task_ids = []
        for tasks in children_tasks:
            children_task_ids += [t["id"] for t in tasks]

        # Get the results of these children tasks.
        results = self.koji_wrapper.retrying_multicall_map(
            self.koji_proxy,
            self.koji_proxy.getTaskResult,
            list_of_args=children_task_ids,
        )
        rpms = []
        for result in results:
            rpms += result.get("rpms", [])
            rpms += result.get("srpms", [])

        rpm_infos = []
        for rpm in rpms:
            rpm_info = kobo.rpmlib.parse_nvra(os.path.basename(rpm))
            rpm_info["path_from_task"] = os.path.join(
                self.koji_wrapper.koji_module.pathinfo.work(), rpm
            )
            rpm_info["build_id"] = None
            rpm_infos.append(rpm_info)

        return rpm_infos

    def get_latest_rpms(self, tag, event, inherit=True):
        if not tag:
            return [], []

        response = None
        if self.cache_region:
            cache_key = "KojiPackageSet.get_latest_rpms_%s_%s_%s" % (
                str(tag),
                str(event),
                str(inherit),
            )
            try:
                response = self.cache_region.get(cache_key)
            except Exception:
                pass

        if not response:
            response = self.koji_proxy.listTaggedRPMS(
                tag, event=event, inherit=inherit, latest=True
            )
            if self.cache_region:
                try:
                    self.cache_region.set(cache_key, response)
                except Exception:
                    pass

        return response

    def get_package_path(self, queue_item):
        rpm_info, build_info = queue_item

        # Check if this RPM is coming from scratch task. In this case, we already
        # know the path.
        if "path_from_task" in rpm_info:
            return rpm_info["path_from_task"]

        pathinfo = self.koji_wrapper.koji_module.pathinfo
        paths = []

        attempts_left = self.signed_packages_retries + 1
        while attempts_left > 0:
            for sigkey in self.sigkey_ordering:
                if not sigkey:
                    # we're looking for *signed* copies here
                    continue
                sigkey = sigkey.lower()
                rpm_path = os.path.join(
                    pathinfo.build(build_info), pathinfo.signed(rpm_info, sigkey)
                )
                if rpm_path not in paths:
                    paths.append(rpm_path)
                if os.path.isfile(rpm_path):
                    return rpm_path

            # No signed copy was found, wait a little and try again.
            attempts_left -= 1
            if attempts_left > 0:
                nvr = "%(name)s-%(version)s-%(release)s" % rpm_info
                self.log_debug("Waiting for signed package to appear for %s", nvr)
                time.sleep(self.signed_packages_wait)

        if None in self.sigkey_ordering or "" in self.sigkey_ordering:
            # use an unsigned copy (if allowed)
            rpm_path = os.path.join(pathinfo.build(build_info), pathinfo.rpm(rpm_info))
            paths.append(rpm_path)
            if os.path.isfile(rpm_path):
                return rpm_path

        if self._allow_invalid_sigkeys and rpm_info["name"] not in self.packages:
            # use an unsigned copy (if allowed)
            rpm_path = os.path.join(pathinfo.build(build_info), pathinfo.rpm(rpm_info))
            paths.append(rpm_path)
            if os.path.isfile(rpm_path):
                self._invalid_sigkey_rpms.append(rpm_info)
                return rpm_path

        self._invalid_sigkey_rpms.append(rpm_info)
        self.log_error(
            "RPM %s not found for sigs: %s. Paths checked: %s"
            % (rpm_info, self.sigkey_ordering, paths)
        )
        return None

    def populate(self, tag, event=None, inherit=True, include_packages=None):
        """Populate the package set with packages from given tag.

        :param event: the Koji event to query at (or latest if not given)
        :param inherit: whether to enable tag inheritance
        :param include_packages: an iterable of tuples (package name, arch) that should
                                 be included, all others are skipped.
        """
        result_rpms = []
        result_srpms = []
        include_packages = set(include_packages or [])

        if type(event) is dict:
            event = event["id"]

        msg = "Getting latest RPMs (tag: %s, event: %s, inherit: %s)" % (
            tag,
            event,
            inherit,
        )
        self.log_info("[BEGIN] %s" % msg)
        rpms, builds = self.get_latest_rpms(tag, event, inherit=inherit)
        extra_rpms, extra_builds = self.get_extra_rpms()
        rpms += extra_rpms
        builds += extra_builds

        extra_builds_by_name = {}
        for build_info in extra_builds:
            extra_builds_by_name[build_info["name"]] = build_info["build_id"]

        builds_by_id = {}
        exclude_build_id = []
        for build_info in builds:
            build_id, build_name = build_info["build_id"], build_info["name"]
            if (
                build_name in extra_builds_by_name
                and build_id != extra_builds_by_name[build_name]
            ):
                exclude_build_id.append(build_id)
            else:
                builds_by_id.setdefault(build_id, build_info)

        # Get extra RPMs from tasks.
        rpms += self.get_extra_rpms_from_tasks()

        skipped_arches = []
        skipped_packages_count = 0
        # We need to process binary packages first, and then source packages.
        # If we have a list of packages to use, we need to put all source rpms
        # names into it. Otherwise if the SRPM name does not occur on the list,
        # it would be missing from the package set. Even if it ultimately does
        # not end in the compose, we need it to extract ExcludeArch and
        # ExclusiveArch for noarch packages.
        for rpm_info in itertools.chain(
            (rpm for rpm in rpms if not _is_src(rpm)),
            (rpm for rpm in rpms if _is_src(rpm)),
        ):
            if rpm_info["build_id"] in exclude_build_id:
                continue

            if self.arches and rpm_info["arch"] not in self.arches:
                if rpm_info["arch"] not in skipped_arches:
                    self.log_debug("Skipping packages for arch: %s" % rpm_info["arch"])
                    skipped_arches.append(rpm_info["arch"])
                continue

            if (
                include_packages
                and (rpm_info["name"], rpm_info["arch"]) not in include_packages
                and rpm_info["arch"] != "src"
            ):
                self.log_debug(
                    "Skipping %(name)s-%(version)s-%(release)s.%(arch)s" % rpm_info
                )
                continue

            if (
                self.populate_only_packages
                and self.packages
                and rpm_info["name"] not in self.packages
            ):
                skipped_packages_count += 1
                continue

            build_info = builds_by_id.get(rpm_info["build_id"], None)
            if _is_src(rpm_info):
                result_srpms.append((rpm_info, build_info))
            else:
                result_rpms.append((rpm_info, build_info))
                if self.populate_only_packages and self.packages:
                    # Only add the package if we already have some whitelist.
                    if build_info:
                        self.packages.add(build_info["name"])
                    else:
                        # We have no build info and therefore no Koji package name,
                        # we can only guess that the Koji package name would be the same
                        # one as the RPM name.
                        self.packages.add(rpm_info["name"])

        if skipped_packages_count:
            self.log_debug(
                "Skipped %d packages, not marked as to be "
                "included in a compose." % skipped_packages_count
            )

        result = self.read_packages(result_rpms, result_srpms)

        # Check that after reading the packages, every package that is
        # included in a compose has the right sigkey.
        if self._invalid_sigkey_rpms:
            invalid_sigkey_rpms = [
                rpm for rpm in self._invalid_sigkey_rpms if rpm["name"] in self.packages
            ]
            if invalid_sigkey_rpms:
                self.raise_invalid_sigkeys_exception(invalid_sigkey_rpms)

        self.log_info("[DONE ] %s" % msg)
        return result

    def write_reuse_file(self, compose, include_packages):
        """Write data to files for reusing in future.

        :param compose: compose object
        :param include_packages: an iterable of tuples (package name, arch) that should
                                 be included.
        """
        reuse_file = compose.paths.work.pkgset_reuse_file(self.name)
        self.log_info("Writing pkgset reuse file: %s" % reuse_file)
        try:
            with open(reuse_file, "wb") as f:
                pickle.dump(
                    {
                        "name": self.name,
                        "allow_invalid_sigkeys": self._allow_invalid_sigkeys,
                        "arches": self.arches,
                        "sigkeys": self.sigkey_ordering,
                        "packages": self.packages,
                        "populate_only_packages": self.populate_only_packages,
                        "rpms_by_arch": self.rpms_by_arch,
                        "srpms_by_name": self.srpms_by_name,
                        "extra_builds": self.extra_builds,
                        "include_packages": include_packages,
                    },
                    f,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
        except Exception as e:
            self.log_warning("Writing pkgset reuse file failed: %s" % str(e))

    def _get_koji_event_from_file(self, event_file):
        with open(event_file, "r") as f:
            return json.load(f)["id"]

    def try_to_reuse(self, compose, tag, inherit=True, include_packages=None):
        """Try to reuse pkgset data of old compose.
        :param compose: compose object
        :param str tag: koji tag name
        :param inherit: whether to enable tag inheritance
        :param include_packages: an iterable of tuples (package name, arch) that should
                                 be included.
        """
        if not compose.conf["pkgset_allow_reuse"]:
            self.log_info("Reusing pkgset data from old compose is disabled.")
            return False

        self.log_info("Trying to reuse pkgset data of old compose")
        if not compose.paths.get_old_compose_topdir():
            self.log_debug("No old compose found. Nothing to reuse.")
            return False

        event_file = os.path.join(
            compose.paths.work.topdir(arch="global", create_dir=False), "koji-event"
        )
        old_event_file = compose.paths.old_compose_path(event_file)

        try:
            koji_event = self._get_koji_event_from_file(event_file)
            old_koji_event = self._get_koji_event_from_file(old_event_file)
        except Exception as e:
            self.log_debug("Can't read koji event from file: %s" % str(e))
            return False

        if koji_event != old_koji_event:
            self.log_debug(
                "Koji event doesn't match, querying changes between event %d and %d"
                % (old_koji_event, koji_event)
            )
            changed = self.koji_proxy.queryHistory(
                tables=["tag_listing", "tag_inheritance"],
                tag=tag,
                afterEvent=min(koji_event, old_koji_event),
                beforeEvent=max(koji_event, old_koji_event) + 1,
            )
            if changed["tag_listing"]:
                self.log_debug("Builds under tag %s changed. Can't reuse." % tag)
                return False
            if changed["tag_inheritance"]:
                self.log_debug("Tag inheritance %s changed. Can't reuse." % tag)
                return False

            if inherit:
                inherit_tags = self.koji_proxy.getFullInheritance(tag, koji_event)
                for t in inherit_tags:
                    changed = self.koji_proxy.queryHistory(
                        tables=["tag_listing", "tag_inheritance"],
                        tag=t["name"],
                        afterEvent=min(koji_event, old_koji_event),
                        beforeEvent=max(koji_event, old_koji_event) + 1,
                    )
                    if changed["tag_listing"]:
                        self.log_debug(
                            "Builds under inherited tag %s changed. Can't reuse."
                            % t["name"]
                        )
                        return False
                    if changed["tag_inheritance"]:
                        self.log_debug("Tag inheritance %s changed. Can't reuse." % tag)
                        return False

        repo_dir = compose.paths.work.pkgset_repo(tag, create_dir=False)
        old_repo_dir = compose.paths.old_compose_path(repo_dir)
        if not old_repo_dir:
            self.log_debug("Can't find old repo dir to reuse.")
            return False

        old_reuse_file = compose.paths.old_compose_path(
            compose.paths.work.pkgset_reuse_file(tag)
        )

        try:
            self.log_debug("Loading reuse file: %s" % old_reuse_file)
            reuse_data = self.load_old_file_cache(old_reuse_file)
        except Exception as e:
            self.log_debug("Failed to load reuse file: %s" % str(e))
            return False

        if (
            reuse_data["allow_invalid_sigkeys"] == self._allow_invalid_sigkeys
            and reuse_data["packages"] == self.packages
            and reuse_data["populate_only_packages"] == self.populate_only_packages
            and reuse_data["extra_builds"] == self.extra_builds
            and reuse_data["sigkeys"] == self.sigkey_ordering
            and reuse_data["include_packages"] == include_packages
        ):
            self.log_info("Copying repo data for reuse: %s" % old_repo_dir)
            copy_all(old_repo_dir, repo_dir)
            self.reuse = old_repo_dir
            self.rpms_by_arch = reuse_data["rpms_by_arch"]
            self.srpms_by_name = reuse_data["srpms_by_name"]
            if self.old_file_cache:
                self.file_cache = self.old_file_cache
            return True
        else:
            self.log_info("Criteria does not match. Nothing to reuse.")
            return False


def _is_src(rpm_info):
    """Check if rpm info object returned by Koji refers to source packages."""
    return rpm_info["arch"] in ("src", "nosrc")
