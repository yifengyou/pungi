===============
 Configuration
===============

Please read
`productmd documentation <http://release-engineering.github.io/productmd/index.html>`_
for
`terminology <http://release-engineering.github.io/productmd/terminology.html>`_
and other release and compose related details.


Minimal Config Example
======================
::

    # RELEASE
    release_name = "Fedora"
    release_short = "Fedora"
    release_version = "23"

    # GENERAL SETTINGS
    comps_file = "comps-f23.xml"
    variants_file = "variants-f23.xml"
    module_defaults_dir = "module_defaults"

    # KOJI
    koji_profile = "koji"
    runroot = False

    # PKGSET
    sigkeys = [None]
    pkgset_source = "koji"
    pkgset_koji_tag = "f23"

    # CREATEREPO
    createrepo_checksum = "sha256"

    # GATHER
    gather_method = "deps"
    greedy_method = "build"
    check_deps = False

    # BUILDINSTALL
    bootable = True
    buildinstall_method = "lorax"


Release
=======
Following **mandatory** options describe a release.


Options
-------

**release_name** [mandatory]
    (*str*) -- release name

**release_short** [mandatory]
    (*str*) -- release short name, without spaces and special characters

**release_version** [mandatory]
    (*str*) -- release version

**release_type** = "ga" (*str*) -- release type, for example ``ga``,
    ``updates`` or ``updates-testing``. See `list of all valid values
    <http://productmd.readthedocs.io/en/latest/common.html#productmd.common.RELEASE_TYPES>`_
    in productmd documentation.

**release_internal** = False
    (*bool*) -- whether the compose is meant for public consumption


Example
-------
::

    release_name = "Fedora"
    release_short = "Fedora"
    release_version = "23"
    # release_type = "ga"


Base Product
============
Base product options are **optional** and we need
to them only if we're composing a layered product
built on another (base) product.


Options
-------

**base_product_name**
    (*str*) -- base product name

**base_product_short**
    (*str*) -- base product short name, without spaces and special characters

**base_product_version**
    (*str*) -- base product **major** version

**base_product_type** = "ga"
    (*str*) -- base product type, "ga", "updates" etc., for full list see
    documentation of *productmd*.


Example
-------
::

    release_name = "RPM Fusion"
    release_short = "rf"
    release_version = "23.0"

    base_product_name = "Fedora"
    base_product_short = "Fedora"
    base_product_version = "23"

General Settings
================

Options
-------

**comps_file** [mandatory]
    (:ref:`scm_dict <scm_support>`, *str* or None) -- reference to comps XML
    file with installation groups

**variants_file** [mandatory]
    (:ref:`scm_dict <scm_support>` or *str*) -- reference to variants XML file
    that defines release variants and architectures

**module_defaults_dir** [optional]
    (:ref:`scm_dict <scm_support>` or *str*) -- reference the module defaults
    directory containing modulemd-defaults YAML documents

**failable_deliverables** [optional]
    (*list*) -- list which deliverables on which variant and architecture can
    fail and not abort the whole compose. This only applies to ``buildinstall``
    and ``iso`` parts. All other artifacts can be configured in their
    respective part of configuration.

    Please note that ``*`` as a wildcard matches all architectures but ``src``.

**comps_filter_environments** [optional]
    (*bool*) -- When set to ``False``, the comps files for variants will not
    have their environments filtered to match the variant.

**tree_arches**
    ([*str*]) -- list of architectures which should be included; if undefined,
    all architectures from variants.xml will be included

**tree_variants**
    ([*str*]) -- list of variants which should be included; if undefined, all
    variants from variants.xml will be included

**repoclosure_strictness**
    (*list*) -- variant/arch mapping describing how repoclosure should run.
    Possible values are

     * ``off`` -- do not run repoclosure
     * ``lenient`` -- (default) run repoclosure and write results to logs, but
       detected errors are only reported in logs
     * ``fatal`` -- abort compose when any issue is detected

    When multiple blocks in the mapping match a variant/arch combination, the
    last value will win.

**repoclosure_backend**
    (*str*) -- Select which tool should be used to run repoclosure over created
    repositories. By default ``yum`` is used, but you can switch to ``dnf``.
    Please note that when ``dnf`` is used, the build dependencies check is
    skipped. On Python 3, only ``dnf`` backend is available.

**compose_type**
    (*str*) -- Allows to set default compose type. Type set via a command-line
    option overwrites this.

Example
-------
::

    comps_file = {
        "scm": "git",
        "repo": "https://git.fedorahosted.org/git/comps.git",
        "branch": None,
        "file": "comps-f23.xml.in",
    }

    variants_file = {
        "scm": "git",
        "repo": "https://pagure.io/pungi-fedora.git ",
        "branch": None,
        "file": "variants-fedora.xml",
    }

    failable_deliverables = [
        ('^.*$', {
            # Buildinstall can fail on any variant and any arch
            '*': ['buildinstall'],
            'src': ['buildinstall'],
            # Nothing on i386 blocks the compose
            'i386': ['buildinstall', 'iso', 'live'],
        })
    ]

    tree_arches = ["x86_64"]
    tree_variants = ["Server"]

    repoclosure_strictness = [
        # Make repoclosure failures fatal for compose on all variants …
        ('^.*$', {'*': 'fatal'}),
        # … except for Everything where it should not run at all.
        ('^Everything$', {'*': 'off'})
    ]


Image Naming
============

Both image name and volume id are generated based on the configuration. Since
the volume id is limited to 32 characters, there are more settings available.
The process for generating volume id is to get a list of possible formats and
try them sequentially until one fits in the length limit. If substitutions are
configured, each attempted volume id will be modified by it.

For layered products, the candidate formats are first
``image_volid_layered_product_formats`` followed by ``image_volid_formats``.
Otherwise, only ``image_volid_formats`` are tried.

If no format matches the length limit, an error will be reported and compose
aborted.

Options
-------

There a couple common format specifiers available for both the options:
 * ``compose_id``
 * ``release_short``
 * ``version``
 * ``date``
 * ``respin``
 * ``type``
 * ``type_suffix``
 * ``label``
 * ``label_major_version``
 * ``variant``
 * ``arch``
 * ``disc_type``

**image_name_format** [optional]
    (*str|dict*) -- Python's format string to serve as template for image
    names. The value can also be a dict mapping variant UID regexes to the
    format string. The pattern should not overlap, otherwise it is undefined
    which one will be used.

    This format will be used for all phases generating images. Currently that
    means ``createiso``, ``live_images`` and ``buildinstall``.

    Available extra keys are:
     * ``disc_num``
     * ``suffix``

**image_volid_formats** [optional]
    (*list*) -- A list of format strings for generating volume id.

    The extra available keys are:
     * ``base_product_short``
     * ``base_product_version``

**image_volid_layered_product_formats** [optional]
    (*list*) -- A list of format strings for generating volume id for layered
    products. The keys available are the same as for ``image_volid_formats``.

**restricted_volid** = False
    (*bool*) -- New versions of lorax replace all non-alphanumerical characters
    with dashes (underscores are preserved). This option will mimic similar
    behaviour in Pungi.

**volume_id_substitutions** [optional]
    (*dict*) -- A mapping of string replacements to shorten the volume id.

**disc_types** [optional]
    (*dict*) -- A mapping for customizing ``disc_type`` used in image names.

    Available keys are:
     * ``boot`` -- for ``boot.iso`` images created in  *buildinstall* phase
     * ``live`` -- for images created by *live_images* phase
     * ``dvd`` -- for images created by *createiso* phase
     * ``ostree`` -- for ostree installer images

    Default values are the same as the keys.

Example
-------
::

    # Image name respecting Fedora's image naming policy
    image_name_format = "%(release_short)s-%(variant)s-%(disc_type)s-%(arch)s-%(version)s%(suffix)s"
    # Use the same format for volume id
    image_volid_formats = [
        "%(release_short)s-%(variant)s-%(disc_type)s-%(arch)s-%(version)s"
    ]
    # No special handling for layered products, use same format as for regular images
    image_volid_layered_product_formats = []
    # Replace "Cloud" with "C" in volume id etc.
    volume_id_substitutions = {
        'Cloud': 'C',
        'Alpha': 'A',
        'Beta': 'B',
        'TC': 'T',
    }

    disc_types = {
        'boot': 'netinst',
        'live': 'Live',
        'dvd': 'DVD',
    }


Signing
=======

If you want to sign deliverables generated during pungi run like RPM wrapped
images. You must provide few configuration options:

**signing_command** [optional]
    (*str*) -- Command that will be run with a koji build as a single
    argument. This command must not require any user interaction.
    If you need to pass a password for a signing key to the command,
    do this via command line option of the command and use string
    formatting syntax ``%(signing_key_password)s``.
    (See **signing_key_password_file**).

**signing_key_id** [optional]
    (*str*) -- ID of the key that will be used for the signing.
    This ID will be used when crafting koji paths to signed files
    (``kojipkgs.fedoraproject.org/packages/NAME/VER/REL/data/signed/KEYID/..``).

**signing_key_password_file** [optional]
    (*str*) -- Path to a file with password that will be formatted
    into **signing_command** string via ``%(signing_key_password)s``
    string format syntax (if used).
    Because pungi config is usualy stored in git and is part of compose
    logs we don't want password to be included directly in the config.
    Note: If ``-`` string is used instead of a filename, then you will be asked
    for the password interactivelly right after pungi starts.

Example
-------
::

        signing_command = '~/git/releng/scripts/sigulsign_unsigned.py -vv --password=%(signing_key_password)s fedora-24'
        signing_key_id = '81b46521'
        signing_key_password_file = '~/password_for_fedora-24_key'


.. _git-urls:

Git URLs
========

In multiple places the config requires URL of a Git repository to download some
file from. This URL is passed on to *Koji*. It is possible to specify which
commit to use using this syntax: ::

    git://git.example.com/git/repo-name.git?#<rev_spec>

The ``<rev_spec>`` pattern can be replaced with actual commit SHA, a tag name,
``HEAD`` to indicate that tip of default branch should be used or
``origin/<branch_name>`` to use tip of arbitrary branch.

If the URL specifies a branch or ``HEAD``, *Pungi* will replace it with the
actual commit SHA. This will later show up in *Koji* tasks and help with
tracing what particular inputs were used.

.. note::

    The ``origin`` must be specified because of the way *Koji* works with the
    repository. It will clone the repository then switch to requested state
    with ``git reset --hard REF``. Since no local branches are created, we need
    to use full specification including the name of the remote.



Createrepo Settings
===================


Options
-------

**createrepo_checksum**
    (*str*) -- specify checksum type for createrepo; expected values:
    ``sha512``, ``sha256``, ``sha``. Defaults to ``sha256``.

**createrepo_c** = True
    (*bool*) -- use createrepo_c (True) or legacy createrepo (False)

**createrepo_deltas** = False
    (*list*) -- generate delta RPMs against an older compose. This needs to be
    used together with ``--old-composes`` command line argument. The value
    should be a mapping of variants and architectures that should enable
    creating delta RPMs. Source and debuginfo repos never have deltas.

**createrepo_use_xz** = False
    (*bool*) -- whether to pass ``--xz`` to the createrepo command. This will
    cause the SQLite databases to be compressed with xz.

**createrepo_num_threads**
    (*int*) -- how many concurrent ``createrepo`` process to run. The default
    is to use one thread per CPU available on the machine.

**createrepo_num_workers**
    (*int*) -- how many concurrent ``createrepo`` workers to run. Value defaults to 3.

**createrepo_database**
    (*bool*) -- whether to create SQLite database as part of the repodata. This
    is only useful as an optimization for clients using Yum to consume to the
    repo. Default value depends on gather backend. For DNF it's turned off, for
    Yum the default is ``True``.

**createrepo_extra_args**
    (*[str]*) -- a list of extra arguments passed on to ``createrepo`` or
    ``createrepo_c`` executable. This could be useful for enabling zchunk
    generation and pointing it to correct dictionaries.

**product_id** = None
    (:ref:`scm_dict <scm_support>`) -- If specified, it should point to a
    directory with certificates ``<variant_uid>-<arch>-*.pem``. Pungi will
    copy each certificate file into the relevant Yum repositories as a
    ``productid`` file in the ``repodata`` directories. The purpose of these
    ``productid`` files is to expose the product data to `subscription-manager
    <https://github.com/candlepin/subscription-manager>`_.
    subscription-manager inclues a "product-id" Yum plugin that can read these
    ``productid`` certificate files from each Yum repository.

**product_id_allow_missing** = False
    (*bool*) -- When ``product_id`` is used and a certificate for some variant
    and architecture is missing, Pungi will exit with an error by default.
    When you set this option to ``True``, Pungi will ignore the missing
    certificate and simply log a warning message.


Example
-------
::

    createrepo_checksum = "sha"
    createrepo_deltas = [
        # All arches for Everything should have deltas.
        ('^Everything$', {'*': True}),
        # Also Server.x86_64 should have them (but not on other arches).
        ('^Server$', {'x86_64': True}),
    ]


Package Set Settings
====================


Options
-------

**sigkeys**
    ([*str* or None]) -- priority list of sigkeys; if the list includes an
    empty string or  *None*, unsigned packages will be allowed

**pkgset_source** [mandatory]
    (*str*) -- "koji" (any koji instance) or "repos" (arbitrary yum repositories)

**pkgset_koji_tag**
    (*str|[str]*) -- tag(s) to read package set from. This option can be
    omitted for modular composes.

**pkgset_koji_builds**
    (*str|[str]*) -- extra build(s) to include in a package set defined as NVRs.

**pkgset_koji_module_tag**
   (*str|[str]*) -- tags to read module from. This option works similarly to
   listing tags in variants XML. If tags are specified and variants XML
   specifies some modules via NSVC (or part of), only modules matching that
   list will be used (and taken from the tag). Inheritance is used
   automatically.

**pkgset_koji_inherit** = True
    (*bool*) -- inherit builds from parent tags; we can turn it off only if we
    have all builds tagged in a single tag

**pkgset_koji_inherit_modules** = False
    (*bool*) -- the same as above, but this only applies to modular tags. This
    option applies to the content tags that contain the RPMs.

**pkgset_repos**
    (*dict*) -- A mapping of architectures to repositories with RPMs: ``{arch:
    [repo]}``. Only use when ``pkgset_source = "repos"``.

**pkgset_exclusive_arch_considers_noarch** = True
    (*bool*) -- If a package includes ``noarch`` in its ``ExclusiveArch`` tag,
    it will be included in all architectures since ``noarch`` is compatible
    with everything. Set this option to ``False`` to ignore ``noarch`` in
    ``ExclusiveArch`` and always consider only binary architectures.


Example
-------
::

    sigkeys = [None]
    pkgset_source = "koji"
    pkgset_koji_tag = "f23"


Buildinstall Settings
=====================
Script or process that creates bootable images with
Anaconda installer is historically called
`buildinstall <https://git.fedorahosted.org/cgit/anaconda.git/tree/scripts/buildinstall?h=f15-branch>`_.

Options
-------

**bootable**
    (*bool*) -- whether to run the buildinstall phase
**buildinstall_method**
    (*str*) -- "lorax" (f16+, rhel7+) or "buildinstall" (older releases)
**lorax_options**
    (*list*) -- special options passed on to *lorax*.

    Format: ``[(variant_uid_regex, {arch|*: {option: name}})]``.

    Recognized options are:
      * ``bugurl`` -- *str* (default ``None``)
      * ``nomacboot`` -- *bool* (default ``True``)
      * ``noupgrade`` -- *bool* (default ``True``)
      * ``add_template`` -- *[str]* (default empty)
      * ``add_arch_template`` -- *[str]* (default empty)
      * ``add_template_var`` -- *[str]* (default empty)
      * ``add_arch_template_var`` -- *[str]* (default empty)
      * ``rootfs_size`` -- [*int*] (default empty)
      * ``version`` -- [*str*] (default from ``release_version``) -- used as
        ``--version`` and ``--release`` argument on the lorax command line
**lorax_extra_sources**
    (*list*) -- a variant/arch mapping with urls for extra source repositories
    added to Lorax command line. Either one repo or a list can be specified.
**buildinstall_kickstart**
    (:ref:`scm_dict <scm_support>`) -- If specified, this kickstart file will
    be copied into each file and pointed to in boot configuration.
**buildinstall_topdir**
    (*str*) -- Full path to top directory where the runroot buildinstall
    Koji tasks output should be stored. This is useful in situation when
    the Pungi compose is not generated on the same storage as the Koji task
    is running on. In this case, Pungi can provide input repository for runroot
    task using HTTP and set the output directory for this task to
    ``buildinstall_topdir``. Once the runroot task finishes, Pungi will copy
    the results of runroot tasks to the compose working directory.
**buildinstall_skip**
    (*list*) -- mapping that defines which variants and arches to skip during
    buildinstall; format: ``[(variant_uid_regex, {arch|*: True})]``. This is
    only supported for lorax.


Example
-------
::

    bootable = True
    buildinstall_method = "lorax"

    # Enables macboot on x86_64 for all variants and builds upgrade images
    # everywhere.
    lorax_options = [
        ("^.*$", {
            "x86_64": {
                "nomacboot": False
            }
            "*": {
                "noupgrade": False
            }
        })
    ]

    # Don't run buildinstall phase for Modular variant
    buildinstall_skip = [
        ('^Modular', {
            '*': True
        })
    ]

    # Add another repository for lorax to install packages from
    lorax_extra_sources = [
        ('^Simple$', {
            '*': 'https://example.com/repo/$basearch/',
        })
    ]


.. note::

    It is advised to run buildinstall (lorax) in koji,
    i.e. with **runroot enabled** for clean build environments, better logging, etc.


.. warning::

    Lorax installs RPMs into a chroot. This involves running %post scriptlets
    and they frequently run executables in the chroot.
    If we're composing for multiple architectures, we **must** use runroot for this reason.


Gather Settings
===============

Options
-------

**gather_method** [mandatory]
    (*str*|*dict*) -- Options are ``deps``, ``nodeps`` and ``hybrid``.
    Specifies whether and how package dependencies should be pulled in.
    Possible configuration can be one value for all variants, or if configured
    per-variant it can be a simple string ``hybrid`` or a a dictionary mapping
    source type to a value of ``deps`` or ``nodeps``. Make sure only one regex
    matches each variant, as there is no guarantee which value will be used if
    there are multiple matching ones. All used sources must have a configured
    method unless hybrid solving is used.

**gather_fulltree** = False
    (*bool*) -- When set to ``True`` all RPMs built from an SRPM will always be
    included. Only use when ``gather_method = "deps"``.

**gather_selfhosting** = False
    (*bool*) -- When set to ``True``, *Pungi* will build a self-hosting tree by
    following build dependencies. Only use when ``gather_method = "deps"``.

**greedy_method**
    (*str*) -- This option controls how package requirements are satisfied in
    case a particular ``Requires`` has multiple candidates.

    * ``none`` -- the best packages is selected to satisfy the dependency and
      only that one is pulled into the compose
    * ``all`` -- packages that provide the symbol are pulled in
    * ``build`` -- the best package is selected, and then all packages from the
      same build that provide the symbol are pulled in

    .. note::
        As an example let's work with this situation: a package in the compose
        has ``Requires: foo``. There are three packages with ``Provides: foo``:
        ``pkg-a``, ``pkg-b-provider-1`` and ``pkg-b-provider-2``. The
        ``pkg-b-*`` packages are build from the same source package. Best match
        determines ``pkg-b-provider-1`` as best matching package.

        * With ``greedy_method = "none"`` only ``pkg-b-provider-1`` will be
          pulled in.
        * With ``greedy_method = "all"`` all three packages will be
          pulled in.
        * With ``greedy_method = "build" ``pkg-b-provider-1`` and
          ``pkg-b-provider-2`` will be pulled in.

**gather_backend**
    (*str*) --This changes the entire codebase doing dependency solving, so it
    can change the result in unpredictable ways.

    On Python 2, the choice is between ``yum`` or ``dnf`` and defaults to
    ``yum``. On Python 3 ``dnf`` is the only option and default.

    Particularly the multilib work is performed differently by using
    ``python-multilib`` library. Please refer to ``multilib`` option to see the
    differences.

**multilib**
    (*list*) -- mapping of variant regexes and arches to list of multilib
    methods

    Available methods are:
     * ``none`` -- no package matches this method
     * ``all`` -- all packages match this method
     * ``runtime`` -- packages that install some shared object file
       (``*.so.*``) will match.
     * ``devel`` -- packages whose name ends with ``-devel`` or ``--static``
       suffix will be matched. When ``dnf`` is used, this method automatically
       enables ``runtime`` method as well. With ``yum`` backend this method
       also uses a hardcoded blacklist and whitelist.
     * ``kernel`` -- packages providing ``kernel`` or ``kernel-devel`` match
       this method (only in ``yum`` backend)
     * ``yaboot`` -- only ``yaboot`` package on ``ppc`` arch matches this (only
       in ``yum`` backend)

.. _additional_packages:

**additional_packages**
    (*list*) -- additional packages to be included in a variant and
    architecture; format: ``[(variant_uid_regex, {arch|*: [package_globs]})]``

    The packages specified here are matched against RPM names, not any other
    provides in the package not the name of source package. Shell globbing is
    used, so wildcards are possible. The package can be specified as name only
    or ``name.arch``.

**filter_packages**
    (*list*) -- packages to be excluded from a variant and architecture;
    format: ``[(variant_uid_regex, {arch|*: [package_globs]})]``

    See :ref:`additional_packages <additional_packages>` for details about
    package specification.

**filter_system_release_packages**
    (*bool*) -- for each variant, figure out the best system release package
    and filter out all others. This will not work if a variant needs more than
    one system release package. In such case, set this option to ``False``.

**gather_prepopulate** = None
    (:ref:`scm_dict <scm_support>`) -- If specified, you can use this to add
    additional packages. The format of the file pointed to by this option is a
    JSON mapping ``{variant_uid: {arch: {build: [package]}}}``. Packages added
    through this option can not be removed by ``filter_packages``.

**multilib_blacklist**
    (*dict*) -- multilib blacklist; format: ``{arch|*: [package_globs]}``.

    See :ref:`additional_packages <additional_packages>` for details about
    package specification.

**multilib_whitelist**
    (*dict*) -- multilib blacklist; format: ``{arch|*: [package_names]}``. The
    whitelist must contain exact package names; there are no wildcards or
    pattern matching.

**gather_lookaside_repos** = []
    (*list*) -- lookaside repositories used for package gathering; format:
    ``[(variant_uid_regex, {arch|*: [repo_urls]})]``

**hashed_directories** = False
    (*bool*) -- put packages into "hashed" directories, for example
    ``Packages/k/kernel-4.0.4-301.fc22.x86_64.rpm``

**check_deps** = True
    (*bool*) -- Set to ``False`` if you don't want the compose to abort when
    some package has broken dependencies.

**require_all_comps_packages** = False
    (*bool*) -- Set to ``True`` to abort compose when package mentioned in
    comps file can not be found in the package set. When disabled (the
    default), such cases are still reported as warnings in the log.

**gather_source_mapping**
    (*str*) -- JSON mapping with initial packages for the compose. The value
    should be a path to JSON file with following mapping: ``{variant: {arch:
    {rpm_name: [rpm_arch|None]}}}``.

**gather_profiler** = False
    (*bool*) -- When set to ``True`` the gather tool will produce additional
    performance profiling information at the end of its logs.  Only takes
    effect when ``gather_backend = "dnf"``.

**variant_as_lookaside**
    (*list*) -- a variant/variant mapping that tells one or more variants in compose
    has other variant(s) in compose as a lookaside. Only top level variants are
    supported (not addons/layered products). Format:
    ``[(variant_uid, variant_uid)]``


Example
-------
::

    gather_method = "deps"
    greedy_method = "build"
    check_deps = False
    hashed_directories = True

    gather_method = {
        "^Everything$": {
            "comps": "deps"     # traditional content defined by comps groups
        },
        "^Modular$": {
            "module": "nodeps"  # Modules do not need dependencies
        },
        "^Mixed$": {            # Mixed content in one variant
            "comps": "deps",
            "module": "nodeps"
        }
        "^OtherMixed$": "hybrid",   # Using hybrid depsolver
    }

    additional_packages = [
        # bz#123456
        ('^(Workstation|Server)$', {
            '*': [
                'grub2',
                'kernel',
            ],
        }),
    ]

    filter_packages = [
        # bz#111222
        ('^.*$', {
            '*': [
                'kernel-doc',
            ],
        }),
    ]

    multilib = [
        ('^Server$', {
            'x86_64': ['devel', 'runtime']
        })
    ]

    multilib_blacklist = {
        "*": [
            "gcc",
        ],
    }

    multilib_whitelist = {
        "*": [
            "alsa-plugins-*",
        ],
    }

    # gather_lookaside_repos = [
    #     ('^.*$', {
    #         'x86_64': [
    #             "https://dl.fedoraproject.org/pub/fedora/linux/releases/22/Everything/x86_64/os/",
    #             "https://dl.fedoraproject.org/pub/fedora/linux/releases/22/Everything/source/SRPMS/",
    #         ]
    #     }),
    # ]


.. note::

   It is a good practice to attach bug/ticket numbers
   to additional_packages, filter_packages, multilib_blacklist and multilib_whitelist
   to track decisions.


Koji Settings
=============


Options
-------

**koji_profile**
    (*str*) -- koji profile name. This tells Pungi how to communicate with
    your chosen Koji instance. See `Koji's documentation about profiles
    <https://docs.pagure.org/koji/profiles/>`_ for more information about how
    to set up your Koji client profile. In the examples, the profile name is
    "koji", which points to Fedora's koji.fedoraproject.org.

**runroot_method**
    (*str*) -- Runroot method to use. It can further specify the runroot method
    in case the ``runroot`` is set to True.

    Available methods are:
     * ``local`` -- runroot tasks are run locally
     * ``koji`` -- runroot tasks are run in Koji
     * ``openssh`` -- runroot tasks are run on remote machine connected using OpenSSH.
       The ``runroot_ssh_hostnames`` for each architecture must be set and the
       user under which Pungi runs must be configured to login as ``runroot_ssh_username``
       using the SSH key.

**runroot_channel**
    (*str*) -- name of koji channel

**runroot_tag**
    (*str*) -- name of koji **build** tag used for runroot

**runroot_weights**
    (*dict*) -- customize task weights for various runroot tasks. The values in
    the mapping should be integers, the keys can be selected from the following
    list. By default no weight is assigned and Koji picks the default one
    according to policy.

     * ``buildinstall``
     * ``createiso``
     * ``ostree``
     * ``ostree_installer``

Example
-------
::

    koji_profile = "koji"
    runroot_channel = "runroot"
    runroot_tag = "f23-build"

Runroot "openssh" method settings
=================================


Options
-------

**runroot_ssh_username**
    (*str*) -- For ``openssh`` runroot method, configures the username used to login
    the remote machine to run the runroot task. Defaults to "root".

**runroot_ssh_hostnames**
    (*dict*) -- For ``openssh`` runroot method, defines the hostname for each
    architecture on which the runroot task should be running. Format:
    ``{"x86_64": "runroot-x86-64.localhost.tld", ...}``

**runroot_ssh_init_template**
    (*str*) [optional] -- For ``openssh`` runroot method, defines the command
    to initializes the runroot task on the remote machine. This command is
    executed as first command for each runroot task executed.

    The command can print a string which is then available as ``{runroot_key}``
    for other SSH commands. This string might be used to keep the context
    across different SSH commands executed for single runroot task.

    The goal of this command is setting up the environment for real runroot
    commands. For example preparing the unique mock environment, mounting the
    desired file-systems, ...

    The command string can contain following variables which are replaced by
    the real values before executing the init command:

    * ``{runroot_tag}`` - Tag to initialize the runroot environment from.

    When not set, no init command is executed.

**runroot_ssh_install_packages_template**
    (*str*) [optional] -- For ``openssh`` runroot method, defines the template
    for command to install the packages requested to run the runroot task.

    The template string can contain following variables which are replaced by
    the real values before executing the install command:

    * ``{runroot_key}`` - Replaced with the string returned by
      ``runroot_ssh_init_template`` if used. This can be used to keep the track
      of context of SSH commands beloging to single runroot task.
    * ``{packages}`` - White-list separated list of packages to install.

    Example (The ``{runroot_key}`` is expected to be set to mock config file
    using the ``runroot_ssh_init_template`` command.):
    ``"mock -r {runroot_key} --install {packages}"``

    When not set, no command to install packages on remote machine is executed.

**runroot_ssh_run_template**
    (*str*) [optional] -- For ``openssh`` runroot method, defines the template
    for the main runroot command.

    The template string can contain following variables which are replaced by
    the real values before executing the install command:

    * ``{runroot_key}`` - Replaced with the string returned by
      ``runroot_ssh_init_template`` if used. This can be used to keep the track
      of context of SSH commands beloging to single runroot task.
    * ``{command}`` - Command to run.

    Example (The ``{runroot_key}`` is expected to be set to mock config file
    using the ``runroot_ssh_init_template`` command.):
    ``"mock -r {runroot_key} chroot -- {command}"``

    When not set, the runroot command is run directly.


Extra Files Settings
====================


Options
-------

**extra_files**
    (*list*) -- references to external files to be placed in os/ directory and
    media; format: ``[(variant_uid_regex, {arch|*: [scm_dict]})]``. See
    :ref:`scm_support` for details. If the dict specifies a ``target`` key, an
    additional subdirectory will be used.


Example
-------
::

    extra_files = [
        ('^.*$', {
            '*': [
                # GPG keys
                {
                    "scm": "rpm",
                    "repo": "fedora-repos",
                    "branch": None,
                    "file": [
                        "/etc/pki/rpm-gpg/RPM-GPG-KEY-22-fedora",
                    ],
                    "target": "",
                },
                # GPL
                {
                    "scm": "git",
                    "repo": "https://pagure.io/pungi-fedora",
                    "branch": None,
                    "file": [
                        "GPL",
                    ],
                    "target": "",
                },
            ],
        }),
    ]


Extra Files Metadata
--------------------
If extra files are specified a metadata file, ``extra_files.json``, is placed
in the ``os/`` directory and media. The checksums generated are determined by
``media_checksums`` option. This metadata file is in the format:

::

    {
      "header": {"version": "1.0},
      "data": [
        {
          "file": "GPL",
          "checksums": {
            "sha256": "8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643"
          },
          "size": 18092
        },
        {
          "file": "release-notes/notes.html",
          "checksums": {
            "sha256": "82b1ba8db522aadf101dca6404235fba179e559b95ea24ff39ee1e5d9a53bdcb"
          },
          "size": 1120
        }
      ]
    }


Productimg Settings
===================
Product images are placed on installation media and provide additional branding
and Anaconda changes specific to product variants.

Options
-------

**productimg** = False
    (*bool*) -- create product images; requires bootable=True

**productimg_install_class**
    (:ref:`scm_dict <scm_support>`, *str*) -- reference to install class **file**

**productimg_po_files**
    (:ref:`scm_dict <scm_support>`, *str*) -- reference to a **directory** with
    po files for install class translations


Example
-------
::

    productimg = True
    productimg_install_class = {
        "scm": "git",
        "repo": "http://git.example.com/productimg.git",
        "branch": None,
        "file": "fedora23/%(variant_id)s.py",
    }
    productimg_po_files = {
        "scm": "git",
        "repo": "http://git.example.com/productimg.git",
        "branch": None,
        "dir": "po",
    }


CreateISO Settings
==================

Options
-------

**createiso_skip** = False
    (*list*) -- mapping that defines which variants and arches to skip during createiso; format: [(variant_uid_regex, {arch|*: True})]

**createiso_max_size**
    (*list*) -- mapping that defines maximum expected size for each variant and
    arch. If the ISO is larger than the limit, a warning will be issued.

    Format: ``[(variant_uid_regex, {arch|*: number})]``

**create_jigdo** = True
    (*bool*) -- controls the creation of jigdo from ISO

**create_optional_isos** = False
    (*bool*) -- when set to ``True``, ISOs will be created even for
    ``optional`` variants. By default only variants with type ``variant`` or
    ``layered-product`` will get ISOs.

**createiso_break_hardlinks** = False
    (*bool*) -- when set to ``True``, all files that should go on the ISO and
    have a hardlink will be first copied into a staging directory. This should
    work around a bug in ``genisoimage`` including incorrect link count in the
    image, but it is at the cost of having to copy a potentially significant
    amount of data.

    The staging directory is deleted when ISO is successfully created. In that
    case the same task to create the ISO will not be re-runnable.

**iso_size** = 4700000000
    (*int|str*) -- size of ISO image. The value should either be an integer
    meaning size in bytes, or it can be a string with ``k``, ``M``, ``G``
    suffix (using multiples of 1024).

**split_iso_reserve** = 10MiB
    (*int|str*) -- how much free space should be left on each disk. The format
    is the same as for ``iso_size`` option.

**iso_hfs_ppc64le_compatible** = True
    (*bool*) -- when set to False, the Apple/HFS compatibility is turned off
    for ppc64le ISOs. This option only makes sense for bootable products, and
    affects images produced in *createiso* and *extra_isos* phases.

.. note::

    Source architecture needs to be listed explicitly.
    Excluding '*' applies only on binary arches.
    Jigdo causes significant increase of time to ISO creation.


Example
-------
::

    createiso_skip = [
        ('^Workstation$', {
            '*': True,
            'src': True
        }),
    ]


.. _auto-version:

Automatic generation of version and release
===========================================

Version and release values for certain artifacts can be generated automatically
based on release version, compose label, date, type and respin. This can be
used to shorten the config and keep it the same for multiple uses.

+----------------------------+-------------------+--------------+--------------+--------+------------------+
| Compose ID                 | Label             | Version      | Date         | Respin | Release          |
+============================+===================+==============+==============+========+==================+
| ``F-Rawhide-20170406.n.0`` | ``-``             | ``Rawhide``  | ``20170406`` | ``0``  | ``20170406.n.0`` |
+----------------------------+-------------------+--------------+--------------+--------+------------------+
| ``F-26-20170329.1``        | ``Alpha-1.6``     | ``26_Alpha`` | ``20170329`` | ``1``  | ``1.6``          |
+----------------------------+-------------------+--------------+--------------+--------+------------------+
| ``F-Atomic-25-20170407.0`` | ``RC-20170407.0`` | ``25``       | ``20170407`` | ``0``  | ``20170407.0``   |
+----------------------------+-------------------+--------------+--------------+--------+------------------+
| ``F-Atomic-25-20170407.0`` | ``-``             | ``25``       | ``20170407`` | ``0``  | ``20170407.0``   |
+----------------------------+-------------------+--------------+--------------+--------+------------------+

All non-``RC`` milestones from label get appended to the version. For release
either label is used or date, type and respin.


Common options for Live Images, Live Media and Image Build
==========================================================

All images can have ``ksurl``, ``version``, ``release`` and ``target``
specified. Since this can create a lot of duplication, there are global options
that can be used instead.

For each of the phases, if the option is not specified for a particular
deliverable, an option named ``<PHASE_NAME>_<OPTION>`` is checked. If that is
not specified either, the last fallback is ``global_<OPTION>``. If even that is
unset, the value is considered to not be specified.

The kickstart URL is configured by these options.

 * ``global_ksurl`` -- global fallback setting
 * ``live_media_ksurl``
 * ``image_build_ksurl``
 * ``live_images_ksurl``

Target is specified by these settings.

 * ``global_target`` -- global fallback setting
 * ``live_media_target``
 * ``image_build_target``
 * ``live_images_target``

Version is specified by these options. If no version is set, a default value
will be provided according to :ref:`automatic versioning <auto-version>`.

 * ``global_version`` -- global fallback setting
 * ``live_media_version``
 * ``image_build_version``
 * ``live_images_version``

Release is specified by these options. If set to a magic value to
``!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN``, a value will be generated according
to :ref:`automatic versioning <auto-version>`.

 * ``global_release`` -- global fallback setting
 * ``live_media_release``
 * ``image_build_release``
 * ``live_images_release``

Each configuration block can also optionally specify a ``failable`` key. For
live images it should have a boolean value. For live media and image build it
should be a list of strings containing architectures that are optional. If any
deliverable fails on an optional architecture, it will not abort the whole
compose. If the list contains only ``"*"``, all arches will be substituted.


Live Images Settings
====================

**live_images**
    (*list*) -- Configuration for the particular image. The elements of the
    list should be tuples ``(variant_uid_regex, {arch|*: config})``. The config
    should be a dict with these keys:

      * ``kickstart`` (*str*)
      * ``ksurl`` (*str*) [optional] -- where to get the kickstart from
      * ``name`` (*str*)
      * ``version`` (*str*)
      * ``target`` (*str*)
      * ``repo`` (*str|[str]*) -- repos specified by URL or variant UID
      * ``specfile`` (*str*) -- for images wrapped in RPM
      * ``scratch`` (*bool*) -- only RPM-wrapped images can use scratch builds,
        but by default this is turned off
      * ``type`` (*str*) -- what kind of task to start in Koji. Defaults to
        ``live`` meaning ``koji spin-livecd`` will be used. Alternative option
        is ``appliance`` corresponding to ``koji spin-appliance``.
      * ``sign`` (*bool*) -- only RPM-wrapped images can be signed

**live_images_no_rename**
    (*bool*) -- When set to ``True``, filenames generated by Koji will be used.
    When ``False``, filenames will be generated based on ``image_name_format``
    configuration option.


Live Media Settings
===================

**live_media**
    (*dict*) -- configuration for ``koji spin-livemedia``; format:
    ``{variant_uid_regex: [{opt:value}]}``

    Required options:

      * ``name`` (*str*)
      * ``version`` (*str*)
      * ``arches`` (*[str]*) -- what architectures to build the media for; by default uses
        all arches for the variant.
      * ``kickstart`` (*str*) -- name of the kickstart file

    Available options:

      * ``ksurl`` (*str*)
      * ``ksversion`` (*str*)
      * ``scratch`` (*bool*)
      * ``target`` (*str*)
      * ``release`` (*str*) -- a string with the release, or
        ``!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN`` to automatically generate a
        suitable value. See :ref:`automatic versioning <auto-version>` for
        details.
      * ``skip_tag`` (*bool*)
      * ``repo`` (*str|[str]*) -- repos specified by URL or variant UID
      * ``title`` (*str*)
      * ``install_tree_from`` (*str*) -- variant to take install tree from


Image Build Settings
====================

**image_build**
    (*dict*) -- config for ``koji image-build``; format: {variant_uid_regex: [{opt: value}]}

    By default, images will be built for each binary arch valid for the
    variant. The config can specify a list of arches to narrow this down.

.. note::
    Config can contain anything what is accepted by
    ``koji image-build --config configfile.ini``

    Repo can be specified either as a string or a list of strings. It will be
    automatically transformed into format suitable for ``koji``. A repo for the
    currently built variant will be added as well.

    If you explicitly set ``release`` to
    ``!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN``, it will be replaced with a value
    generated as described in :ref:`automatic versioning <auto-version>`.

    If you explicitly set ``release`` to
    ``!RELEASE_FROM_DATE_RESPIN``, it will be replaced with a value
    generated as described in :ref:`automatic versioning <auto-version>`.

    If you explicitly set ``version`` to
    ``!VERSION_FROM_VERSION``, it will be replaced with a value
    generated as described in :ref:`automatic versioning <auto-version>`.

    Please don't set ``install_tree``. This gets automatically set by *pungi*
    based on current variant. You can use ``install_tree_from`` key to use
    install tree from another variant.

    Both the install tree and repos can use one of following formats:

     * URL to the location
     * name of variant in the current compose
     * absolute path on local filesystem (which will be translated using
       configured mappings or used unchanged, in which case you have to ensure
       the koji builders can access it)

    You can set either a single format, or a list of formats. For available
    values see help output for ``koji image-build`` command.

    If ``ksurl`` ends with ``#HEAD``, Pungi will figure out the SHA1 hash of
    current HEAD and use that instead.

    Setting ``scratch`` to ``True`` will run the koji tasks as scratch builds.


Example
-------
::

    image_build = {
        '^Server$': [
            {
                'image-build': {
                    'format': ['docker', 'qcow2']
                    'name': 'fedora-qcow-and-docker-base',
                    'target': 'koji-target-name',
                    'ksversion': 'F23',     # value from pykickstart
                    'version': '23',
                    # correct SHA1 hash will be put into the URL below automatically
                    'ksurl': 'https://git.fedorahosted.org/git/spin-kickstarts.git?somedirectoryifany#HEAD',
                    'kickstart': "fedora-docker-base.ks",
                    'repo': ["http://someextrarepos.org/repo", "ftp://rekcod.oi/repo"],
                    'distro': 'Fedora-20',
                    'disk_size': 3,

                    # this is set automatically by pungi to os_dir for given variant
                    # 'install_tree': 'http://somepath',
                },
                'factory-parameters': {
                    'docker_cmd':  "[ '/bin/bash' ]",
                    'docker_env': "[ 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' ]",
                    'docker_labels': "{'Name': 'fedora-docker-base', 'License': u'GPLv2', 'RUN': 'docker run -it --rm ${OPT1} --privileged -v \`pwd\`:/atomicapp -v /run:/run -v /:/host --net=host --name ${NAME} -e NAME=${NAME} -e IMAGE=${IMAGE} ${IMAGE} -v ${OPT2} run ${OPT3} /atomicapp', 'Vendor': 'Fedora Project', 'Version': '23', 'Architecture': 'x86_64' }",
                }
            },
            {
                'image-build': {
                    'format': ['docker', 'qcow2']
                    'name': 'fedora-qcow-and-docker-base',
                    'target': 'koji-target-name',
                    'ksversion': 'F23',     # value from pykickstart
                    'version': '23',
                    # correct SHA1 hash will be put into the URL below automatically
                    'ksurl': 'https://git.fedorahosted.org/git/spin-kickstarts.git?somedirectoryifany#HEAD',
                    'kickstart': "fedora-docker-base.ks",
                    'repo': ["http://someextrarepos.org/repo", "ftp://rekcod.oi/repo"],
                    'distro': 'Fedora-20',
                    'disk_size': 3,

                    # this is set automatically by pungi to os_dir for given variant
                    # 'install_tree': 'http://somepath',
                }
            },
            {
                'image-build': {
                    'format': 'qcow2',
                    'name': 'fedora-qcow-base',
                    'target': 'koji-target-name',
                    'ksversion': 'F23',     # value from pykickstart
                    'version': '23',
                    'ksurl': 'https://git.fedorahosted.org/git/spin-kickstarts.git?somedirectoryifany#HEAD',
                    'kickstart': "fedora-docker-base.ks",
                    'distro': 'Fedora-23',

                    # only build this type of image on x86_64
                    'arches': ['x86_64']

                    # Use install tree and repo from Everything variant.
                    'install_tree_from': 'Everything',
                    'repo': ['Everything'],

                    # Set release automatically.
                    'release': '!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN',
                }
            }
        ]
    }


OSTree Settings
===============

The ``ostree`` phase of *Pungi* can create and update ostree repositories. This
is done by running ``rpm-ostree compose`` in a Koji runroot environment. The
ostree repository itself is not part of the compose and should be located in
another directory. Any new packages in the compose will be added to the
repository with a new commit.

**ostree**
    (*dict*) -- a mapping of configuration for each. The format should be
    ``{variant_uid_regex: config_dict}``. It is possible to use a list of
    configuration dicts as well.

    The configuration dict for each variant arch pair must have these keys:

    * ``treefile`` -- (*str*) Filename of configuration for ``rpm-ostree``.
    * ``config_url`` -- (*str*) URL for Git repository with the ``treefile``.
    * ``repo`` -- (*str|dict|[str|dict]*) repos specified by URL or variant UID
      or a dict of repo options, ``baseurl`` is required in the dict.
    * ``ostree_repo`` -- (*str*) Where to put the ostree repository

    These keys are optional:

    * ``keep_original_sources`` -- (*bool*) Keep the existing source repos in
      the tree config file. If not enabled, all the original source repos will
      be removed from the tree config file.
    * ``config_branch`` -- (*str*) Git branch of the repo to use. Defaults to
      ``master``.
    * ``arches`` -- (*[str]*) List of architectures for which to update ostree.
      There will be one task per architecture. By default all architectures in
      the variant are used.
    * ``failable`` -- (*[str]*) List of architectures for which this
      deliverable is not release blocking.
    * ``update_summary`` -- (*bool*) Update summary metadata after tree composing.
      Defaults to ``False``.
    * ``force_new_commit`` -- (*bool*) Do not use rpm-ostree's built-in change
      detection.
      Defaults to ``False``.
    * ``version`` -- (*str*) Version string to be added as versioning metadata.
      If this option is set to ``!OSTREE_VERSION_FROM_LABEL_DATE_TYPE_RESPIN``,
      a value will be generated automatically as ``$VERSION.$RELEASE``.
      If this option is set to ``!VERSION_FROM_VERSION_DATE_RESPIN``,
      a value will be generated automatically as ``$VERSION.$DATE.$RESPIN``.
      :ref:`See how those values are created <auto-version>`.
    * ``tag_ref`` -- (*bool*, default ``True``) If set to ``False``, a git
      reference will not be created.
    * ``ostree_ref`` -- (*str*) To override value ``ref`` from ``treefile``.


Example config
--------------
::

    ostree = {
        "^Atomic$": {
            "treefile": "fedora-atomic-docker-host.json",
            "config_url": "https://git.fedorahosted.org/git/fedora-atomic.git",
            "repo": [
                "Server",
                "http://example.com/repo/x86_64/os",
                {"baseurl": "Everything"},
                {"baseurl": "http://example.com/linux/repo", "exclude": "systemd-container"},
            ],
            "keep_original_sources": True,
            "ostree_repo": "/mnt/koji/compose/atomic/Rawhide/",
            "update_summary": True,
            # Automatically generate a reasonable version
            "version": "!OSTREE_VERSION_FROM_LABEL_DATE_TYPE_RESPIN",
            # Only run this for x86_64 even if Atomic has more arches
            "arches": ["x86_64"],
        }
    }


Ostree Installer Settings
=========================

The ``ostree_installer`` phase of *Pungi* can produce installer image bundling
an OSTree repository. This always runs in Koji as a ``runroot`` task.

**ostree_installer**
    (*dict*) -- a variant/arch mapping of configuration. The format should be
    ``[(variant_uid_regex, {arch|*: config_dict})]``.

    The configuration dict for each variant arch pair must have this key:

    These keys are optional:

    * ``repo`` -- (*str|[str]*) repos specified by URL or variant UID
    * ``release`` -- (*str*) Release value to set for the installer image. Set
      to ``!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN`` to generate the value
      :ref:`automatically <auto-version>`.
    * ``failable`` -- (*[str]*) List of architectures for which this
      deliverable is not release blocking.

    These optional keys are passed to ``lorax`` to customize the build.

    * ``installpkgs`` -- (*[str]*)
    * ``add_template`` -- (*[str]*)
    * ``add_arch_template`` -- (*[str]*)
    * ``add_template_var`` -- (*[str]*)
    * ``add_arch_template_var`` -- (*[str]*)
    * ``rootfs_size`` -- (*[str]*)
    * ``template_repo`` -- (*str*) Git repository with extra templates.
    * ``template_branch`` -- (*str*) Branch to use from ``template_repo``.

    The templates can either be absolute paths, in which case they will be used
    as configured; or they can be relative paths, in which case
    ``template_repo`` needs to point to a Git repository from which to take the
    templates.

**ostree_installer_overwrite** = False
    (*bool*) -- by default if a variant including OSTree installer also creates
    regular installer images in buildinstall phase, there will be conflicts (as
    the files are put in the same place) and Pungi will report an error and
    fail the compose.

    With this option it is possible to opt-in for the overwriting. The
    traditional ``boot.iso`` will be in the ``iso/`` subdirectory.


Example config
--------------
::

    ostree_installer = [
        ("^Atomic$", {
            "x86_64": {
                "repo": [
                    "Everything",
                    "https://example.com/extra-repo1.repo",
                    "https://example.com/extra-repo2.repo",
                ],
                "release": "!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN",
                "installpkgs": ["fedora-productimg-atomic"],
                "add_template": ["atomic-installer/lorax-configure-repo.tmpl"],
                "add_template_var": [
                    "ostree_osname=fedora-atomic",
                    "ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",
                ],
                "add_arch_template": ["atomic-installer/lorax-embed-repo.tmpl"],
                "add_arch_template_var": [
                    "ostree_repo=https://kojipkgs.fedoraproject.org/compose/atomic/Rawhide/",
                    "ostree_osname=fedora-atomic",
                    "ostree_ref=fedora-atomic/Rawhide/x86_64/docker-host",
                ]
                'template_repo': 'https://git.fedorahosted.org/git/spin-kickstarts.git',
                'template_branch': 'f24',
            }
        })
    ]


OSBS Settings
=============

*Pungi* can build container images in OSBS. The build is initiated through Koji
``container-build`` plugin. The base image will be using RPMs from the current
compose and a ``Dockerfile`` from specified Git repository.

Please note that the image is uploaded to a registry and not exported into
compose directory. There will be a metadata file in
``compose/metadata/osbs.json`` with details about the built images (assuming
they are not scratch builds).

**osbs**
    (*dict*) -- a mapping from variant regexes to configuration blocks. The
    format should be ``{variant_uid_regex: [config_dict]}``.

    The configuration for each image must have at least these keys:

    * ``url`` -- (*str*) URL pointing to a Git repository with ``Dockerfile``.
      Please see :ref:`git-urls` section for more details.
    * ``target`` -- (*str*) A Koji target to build the image for.
    * ``git_branch`` -- (*str*) A branch in SCM for the ``Dockerfile``. This is
      required by OSBS to avoid race conditions when multiple builds from the
      same repo are submitted at the same time. Please note that ``url`` should
      contain the branch or tag name as well, so that it can be resolved to a
      particular commit hash.

    Optionally you can specify ``failable``. If it has a truthy value, failure
    to create the image will not abort the whole compose.

    .. note::
        Once OSBS gains support for multiple architectures, the usage of this
        option will most likely change to list architectures that are allowed
        to fail.


    The configuration will pass other attributes directly to the Koji task.
    This includes ``name``, ``version``, ``scratch`` and ``priority``.

    A value for ``yum_repourls`` will be created automatically and point at a
    repository in the current compose. You can add extra repositories with
    ``repo`` key having a list of urls pointing to ``.repo`` files or just
    variant uid, Pungi will create the .repo file for that variant. ``gpgkey``
    can be specified to enable gpgcheck in repo files for variants.

**osbs_registries**
   (*dict*) -- It is possible to configure extra information about where to
   push the image (unless it is a scratch build). For each finished build,
   Pungi will try to match NVR against a key in this mapping (using shell-style
   globbing) and take the corresponding value and collect them across all built
   images. The data will be saved into ``logs/global/osbs-registries.json`` as
   a mapping from Koji NVR to the registry data. The same data is also sent to
   the message bus on ``osbs-request-push`` topic once the compose finishes
   successfully. Handling the message and performing the actual push is outside
   of scope for Pungi.


Example config
--------------
::

    osbs = {
        "^Server$": {
            # required
            "url": "git://example.com/dockerfiles.git?#HEAD",
            "target": "f24-docker-candidate",
            "git_branch": "f24-docker",

            # optional
            "name": "fedora-docker-base",
            "version": "24",
            "repo": ["Everything", "https://example.com/extra-repo.repo"],
            # This will result in three repo urls being passed to the task.
            # They will be in this order: Server, Everything, example.com/
            "gpgkey": 'file:///etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release',
        }
    }


Extra ISOs
==========

Create an ISO image that contains packages from multiple variants. Such ISO
always belongs to one variant, and will be stored in ISO directory of that
variant.

The ISO will be bootable if buildinstall phase runs for the parent variant. It
will reuse boot configuration from that variant.

**extra_isos**
    (*dict*) -- a mapping from variant UID regex to a list of configuration
    blocks.

    * ``include_variants`` -- (*list*) list of variant UIDs from which content
      should be added to the ISO; the variant of this image is added
      automatically.

    Rest of configuration keys is optional.

    * ``filename`` -- (*str*) template for naming the image. In addition to the
      regular placeholders ``filename`` is available with the name generated
      using ``image_name_format`` option.

    * ``volid`` -- (*str*) template for generating volume ID. Again ``volid``
      placeholder can be used similarly as for file name. This can also be a
      list of templates that will be tried sequentially until one generates a
      volume ID that fits into 32 character limit.

    * ``extra_files`` -- (*list*) a list of :ref:`scm_dict <scm_support>`
      objects. These files will be put in the top level directory of the image.

    * ``arches`` -- (*list*) a list of architectures for which to build this
      image. By default all arches from the variant will be used. This option
      can be used to limit them.

    * ``failable_arches`` -- (*list*) a list of architectures for which the
      image can fail to be generated and not fail the entire compose.

    * ``skip_src`` -- (*bool*) allows to disable creating an image with source
      packages.

    * ``inherit_extra_files`` -- (*bool*) by default extra files in variants
      are ignored. If you want to include them in the ISO, set this option to
      ``True``.

    * ``max_size`` -- (*int*) expected maximum size in bytes. If the final
      image is larger, a warning will be issued.

Example config
--------------
::

    extra_isos = {
        'Server': [{
            # Will generate foo-DP-1.0-20180510.t.43-Server-x86_64-dvd1.iso
            'filename': 'foo-{filename}',
            'volid': 'foo-{arch}',

            'extra_files': [{
                'scm': 'git',
                'repo': 'https://pagure.io/pungi.git',
                'file': 'setup.py'
            }],

            'include_variants': ['Client']
        }]
    }
    # This should create image with the following layout:
    #  .
    #  ├── Client
    #  │   ├── Packages
    #  │   │   ├── a
    #  │   │   └── b
    #  │   └── repodata
    #  ├── Server
    #  │   ├── Packages
    #  │   │   ├── a
    #  │   │   └── b
    #  │   └── repodata
    #  └── setup.py



Media Checksums Settings
========================

**media_checksums**
    (*list*) -- list of checksum types to compute, allowed values are anything
    supported by Python's ``hashlib`` module (see `documentation for details
    <https://docs.python.org/2/library/hashlib.html>`_).

**media_checksum_one_file**
    (*bool*) -- when ``True``, only one ``CHECKSUM`` file will be created per
    directory; this option requires ``media_checksums`` to only specify one
    type

**media_checksum_base_filename**
    (*str*) -- when not set, all checksums will be save to a file named either
    ``CHECKSUM`` or based on the digest type; this option allows adding any
    prefix to that name

    It is possible to use format strings that will be replace by actual values.
    The allowed keys are:

      * ``arch``
      * ``compose_id``
      * ``date``
      * ``label``
      * ``label_major_version``
      * ``release_short``
      * ``respin``
      * ``type``
      * ``type_suffix``
      * ``version``
      * ``dirname`` (only if ``media_checksum_one_file`` is enabled)

    For example, for Fedora the prefix should be
    ``%(release_short)s-%(variant)s-%(version)s-%(date)s%(type_suffix)s.%(respin)s``.


Translate Paths Settings
========================

**translate_paths**
    (*list*) -- list of paths to translate; format: ``[(path, translated_path)]``

.. note::
    This feature becomes useful when you need to transform compose location
    into e.g. a HTTP repo which is can be passed to ``koji image-build``.
    The ``path`` part is normalized via ``os.path.normpath()``.


Example config
--------------
::

    translate_paths = [
        ("/mnt/a", "http://b/dir"),
    ]

Example usage
-------------
::

    >>> from pungi.util import translate_paths
    >>> print translate_paths(compose_object_with_mapping, "/mnt/a/c/somefile")
    http://b/dir/c/somefile


Miscellaneous Settings
======================

**paths_module**
    (*str*) -- Name of Python module implementing the same interface as
    ``pungi.paths``. This module can be used to override where things are
    placed.

**link_type** = ``hardlink-or-copy``
    (*str*) -- Method of putting packages into compose directory.

    Available options:

    * ``hardlink-or-copy``
    * ``hardlink``
    * ``copy``
    * ``symlink``
    * ``abspath-symlink``

**skip_phases**
    (*list*) -- List of phase names that should be skipped. The same
    functionality is available via a command line option.

**release_discinfo_description**
    (*str*) -- Override description in ``.discinfo`` files. The value is a
    format string accepting ``%(variant_name)s`` and ``%(arch)s`` placeholders.

**symlink_isos_to**
    (*str*) -- If set, the ISO files from ``buildinstall``, ``createiso`` and
    ``live_images`` phases will be put into this destination, and a symlink
    pointing to this location will be created in actual compose directory.

**dogpile_cache_backend**
    (*str*) -- If set, Pungi will use the configured Dogpile cache backend to
    cache various data between multiple Pungi calls. This can make Pungi
    faster in case more similar composes are running regularly in short time.

    For list of available backends, please see the
    https://dogpilecache.readthedocs.io documentation.

    Most typical configuration uses the ``dogpile.cache.dbm`` backend.

**dogpile_cache_arguments**
    (*dict*) -- Arguments to be used when creating the Dogpile cache backend.
    See the particular backend's configuration for the list of possible
    key/value pairs.

    For the ``dogpile.cache.dbm`` backend, the value can be for example
    following: ::

        {
            "filename": "/tmp/pungi_cache_file.dbm"
        }

**dogpile_cache_expiration_time**
    (*int*) -- Defines the default expiration time in seconds of data stored
    in the Dogpile cache. Defaults to 3600 seconds.
