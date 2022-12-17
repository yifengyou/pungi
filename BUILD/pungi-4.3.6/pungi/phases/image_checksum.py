# -*- coding: utf-8 -*-

import os
from kobo import shortcuts
from collections import defaultdict
import threading

from .base import PhaseBase
from ..util import get_format_substs, get_file_size


MULTIPLE_CHECKSUMS_ERROR = (
    'Config option "media_checksum_one_file" requires only one checksum'
    ' to be configured in "media_checksums".'
)


class ImageChecksumPhase(PhaseBase):
    """Go through images specified in image manifest and generate their
    checksums. The manifest will be updated with the checksums.
    """

    name = "image_checksum"

    def __init__(self, compose):
        super(ImageChecksumPhase, self).__init__(compose)
        self.checksums = self.compose.conf["media_checksums"]
        self.one_file = self.compose.conf["media_checksum_one_file"]

    def skip(self):
        # Skipping this phase does not make sense:
        #  * if there are no images, it doesn't do anything and is quick
        #  * if there are images, they must have checksums computed or else
        #    writing metadata will fail
        return False

    def validate(self):
        errors = []

        if self.one_file and len(self.checksums) != 1:
            errors.append(MULTIPLE_CHECKSUMS_ERROR)

        if errors:
            raise ValueError("\n".join(errors))

    def _get_images(self):
        """Returns a mapping from directories to sets of ``Image``s.

        The paths to dirs are absolute.
        """
        top_dir = self.compose.paths.compose.topdir()
        images = {}
        for variant in self.compose.im.images:
            for arch in self.compose.im.images[variant]:
                for image in self.compose.im.images[variant][arch]:
                    path = os.path.dirname(os.path.join(top_dir, image.path))
                    images.setdefault((variant, arch, path), set()).add(image)
        return images

    def _get_base_filename(self, variant, arch, **kwargs):
        base_checksum_name = self.compose.conf["media_checksum_base_filename"]
        if base_checksum_name:
            substs = get_format_substs(
                self.compose, variant=variant, arch=arch, **kwargs
            )
            base_checksum_name = (base_checksum_name % substs).format(**substs)
            base_checksum_name += "-"
        return base_checksum_name

    def run(self):
        topdir = self.compose.paths.compose.topdir()

        make_checksums(
            topdir,
            self.compose.im,
            self.checksums,
            self.one_file,
            self._get_base_filename,
        )


def _compute_checksums(
    results,
    cache,
    variant,
    arch,
    path,
    images,
    checksum_types,
    base_checksum_name_gen,
    one_file,
    results_lock,
    cache_lock,
):
    for image in images:
        filename = os.path.basename(image.path)
        full_path = os.path.join(path, filename)
        if not os.path.exists(full_path):
            continue

        filesize = image.size or get_file_size(full_path)

        cache_lock.acquire()
        if full_path not in cache:
            cache_lock.release()
            # Source ISO is listed under each binary architecture. There's no
            # point in checksumming it twice, so we can just remember the
            # digest from first run..
            checksum_value = shortcuts.compute_file_checksums(full_path, checksum_types)
            with cache_lock:
                cache[full_path] = checksum_value
        else:
            cache_lock.release()

        with cache_lock:
            digests = cache[full_path]

        for checksum, digest in digests.items():
            # Update metadata with the checksum
            image.add_checksum(None, checksum, digest)
            # If not turned of, create the file-specific checksum file
            if not one_file:
                checksum_filename = os.path.join(
                    path, "%s.%sSUM" % (filename, checksum.upper())
                )
                with results_lock:
                    results[checksum_filename].add(
                        (filename, filesize, checksum, digest)
                    )

            if one_file:
                dirname = os.path.basename(path)
                base_checksum_name = base_checksum_name_gen(
                    variant, arch, dirname=dirname
                )
                checksum_filename = base_checksum_name + "CHECKSUM"
            else:
                base_checksum_name = base_checksum_name_gen(variant, arch)
                checksum_filename = "%s%sSUM" % (base_checksum_name, checksum.upper())
            checksum_path = os.path.join(path, checksum_filename)

            with results_lock:
                results[checksum_path].add((filename, filesize, checksum, digest))


def make_checksums(topdir, im, checksum_types, one_file, base_checksum_name_gen):
    results = defaultdict(set)
    cache = {}
    threads = []
    results_lock = threading.Lock()  # lock to synchronize access to the results dict.
    cache_lock = threading.Lock()  # lock to synchronize access to the cache dict.

    # create all worker threads
    for (variant, arch, path), images in get_images(topdir, im).items():
        threads.append(
            threading.Thread(
                target=_compute_checksums,
                args=[
                    results,
                    cache,
                    variant,
                    arch,
                    path,
                    images,
                    checksum_types,
                    base_checksum_name_gen,
                    one_file,
                    results_lock,
                    cache_lock,
                ],
            )
        )
        threads[-1].start()

    # wait for all worker threads to finish
    for thread in threads:
        thread.join()

    for file in results:
        dump_checksums(file, results[file])


def dump_checksums(checksum_file, data):
    """Write checksums to file.

    :param checksum_file: where to write the checksums
    :param data: an iterable of tuples (filename, filesize, checksum_type, hash)
    """
    with open(checksum_file, "w") as f:
        for filename, filesize, alg, checksum in sorted(data):
            f.write("# %s: %s bytes\n" % (filename, filesize))
            f.write("%s (%s) = %s\n" % (alg.upper(), filename, checksum))


def get_images(top_dir, manifest):
    """Returns a mapping from directories to sets of ``Image``s.

    The paths to dirs are absolute.
    """
    images = {}
    for variant in manifest.images:
        for arch in manifest.images[variant]:
            for image in manifest.images[variant][arch]:
                path = os.path.dirname(os.path.join(top_dir, image.path))
                images.setdefault((variant, arch, path), []).append(image)
    return images
