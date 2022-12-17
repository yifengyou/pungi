.. _examples:

Big picture examples
====================

Actual Pungi configuration files can get very large. This pages brings two
examples of (almost) full configuration for two different composes.

Fedora Rawhide compose
----------------------

This is a shortened configuration for Fedora Radhide compose as of 2019-10-14.

::

    release_name = 'Fedora'
    release_short = 'Fedora'
    release_version = 'Rawhide'
    release_is_layered = False

    bootable = True
    comps_file = {
        'scm': 'git',
        'repo': 'https://pagure.io/fedora-comps.git',
        'branch': 'master',
        'file': 'comps-rawhide.xml',
        # Merge translations by running make. This command will generate the file.
        'command': 'make comps-rawhide.xml'
    }
    module_defaults_dir = {
        'scm': 'git',
        'repo': 'https://pagure.io/releng/fedora-module-defaults.git',
        'branch': 'main',
        'dir': '.'
    }
    # Optional module obsoletes configuration which is merged
    # into the module index and gets resolved
    module_obsoletes_dir = {
        'scm': 'git',
        'repo': 'https://pagure.io/releng/fedora-module-defaults.git',
        'branch': 'main',
        'dir': 'obsoletes'
    }

    variants_file='variants-fedora.xml'
    sigkeys = ['12C944D0']

    # Put packages into subdirectories hashed by their initial letter.
    hashed_directories = True

    # There is a special profile for use with compose. It makes Pungi
    # authenticate automatically as rel-eng user.
    koji_profile = 'compose_koji'

    # RUNROOT settings
    runroot = True
    runroot_channel = 'compose'
    runroot_tag = 'f32-build'

    # PKGSET
    pkgset_source = 'koji'
    pkgset_koji_tag = 'f32'
    pkgset_koji_inherit = False

    filter_system_release_packages = False

    # GATHER
    gather_method = {
        '^.*': {                # For all variants
            'comps': 'deps',    # resolve dependencies for packages from comps file
            'module': 'nodeps', # but not for packages from modules
        }
    }
    gather_backend = 'dnf'
    gather_profiler = True
    check_deps = False
    greedy_method = 'build'

    repoclosure_backend = 'dnf'

    # CREATEREPO
    createrepo_deltas = False
    createrepo_database = True
    createrepo_use_xz = True
    createrepo_extra_args = ['--zck', '--zck-dict-dir=/usr/share/fedora-repo-zdicts/rawhide']

    # CHECKSUMS
    media_checksums = ['sha256']
    media_checksum_one_file = True
    media_checksum_base_filename = '%(release_short)s-%(variant)s-%(version)s-%(arch)s-%(date)s%(type_suffix)s.%(respin)s'

    # CREATEISO
    iso_hfs_ppc64le_compatible = False

    # BUILDINSTALL
    buildinstall_method = 'lorax'
    buildinstall_skip = [
        # No installer for Modular variant
        ('^Modular$', {'*': True}),
        # No 32 bit installer for Everything.
        ('^Everything$', {'i386': True}),
    ]

    # Enables macboot on x86_64 for all variants and disables upgrade image building
    # everywhere.
    lorax_options = [
      ('^.*$', {
         'x86_64': {
             'nomacboot': False
         },
         'ppc64le': {
             # Use 3GB image size for ppc64le.
             'rootfs_size': 3
         },
         '*': {
             'noupgrade': True
         }
      })
    ]

    additional_packages = [
        ('^(Server|Everything)$', {
            '*': [
                # Add all architectures of dracut package.
                'dracut.*',
                # All all packages matching this pattern
                'autocorr-*',
            ],
        }),

        ('^Everything$', {
            # Everything should include all packages from the tag. This only
            # applies to the native arch. Multilib will still be pulled in
            # according to multilib rules.
            '*': ['*'],
        }),
    ]

    filter_packages = [
        ("^.*$", {"*": ["glibc32", "libgcc32"]}),
        ('(Server)$', {
            '*': [
                'kernel*debug*',
                'kernel-kdump*',
            ]
        }),
    ]

    multilib = [
        ('^Everything$', {
            'x86_64': ['devel', 'runtime'],
        })
    ]

    # These packages should never be multilib on any arch.
    multilib_blacklist = {
        '*': [
            'kernel', 'kernel-PAE*', 'kernel*debug*', 'java-*', 'php*', 'mod_*', 'ghc-*'
        ],
    }

    # These should be multilib even if they don't match the rules defined above.
    multilib_whitelist = {
        '*': ['wine', '*-static'],
    }

    createiso_skip = [
        # Keep binary ISOs for Server, but not source ones.
        ('^Server$', {'src': True}),

        # Remove all other ISOs.
        ('^Everything$', {'*': True, 'src': True}),
        ('^Modular$', {'*': True, 'src': True}),
    ]

    # Image name respecting Fedora's image naming policy
    image_name_format = '%(release_short)s-%(variant)s-%(disc_type)s-%(arch)s-%(version)s-%(date)s%(type_suffix)s.%(respin)s.iso'
    # Use the same format for volume id
    image_volid_formats = [
        '%(release_short)s-%(variant)s-%(disc_type)s-%(arch)s-%(version)s'
    ]
    # Used by Pungi to replace 'Cloud' with 'C' (etc.) in ISO volume IDs.
    # There is a hard 32-character limit on ISO volume IDs, so we use
    # these to try and produce short enough but legible IDs. Note this is
    # duplicated in Koji for live images, as livemedia-creator does not
    # allow Pungi to tell it what volume ID to use. Note:
    # https://fedoraproject.org/wiki/User:Adamwill/Draft_fedora_image_naming_policy
    volume_id_substitutions = {
                     'Beta': 'B',
                  'Rawhide': 'rawh',
               'Silverblue': 'SB',
                 'Cinnamon': 'Cinn',
                    'Cloud': 'C',
             'Design_suite': 'Dsgn',
           'Electronic_Lab': 'Elec',
               'Everything': 'E',
           'Scientific_KDE': 'SciK',
                 'Security': 'Sec',
                   'Server': 'S',
              'Workstation': 'WS',
    }

    disc_types = {
        'boot': 'netinst',
        'live': 'Live',
    }

    translate_paths = [
       ('/mnt/koji/compose/', 'https://kojipkgs.fedoraproject.org/compose/'),
    ]

    # These will be inherited by live_media, live_images and image_build
    global_ksurl = 'git+https://pagure.io/fedora-kickstarts.git?#HEAD'
    global_release = '!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN'
    global_version = 'Rawhide'
    # live_images ignores this in favor of live_target
    global_target = 'f32'

    image_build = {
        '^Container$': [
            {
                'image-build': {
                        'format': [('docker', 'tar.xz')],
                        'name': 'Fedora-Container-Base',
                        'kickstart': 'fedora-container-base.ks',
                        'distro': 'Fedora-22',
                        'disk_size': 5,
                        'arches': ['armhfp', 'aarch64', 'ppc64le', 's390x', 'x86_64'],
                        'repo': 'Everything',
                        'install_tree_from': 'Everything',
                        'subvariant': 'Container_Base',
                        'failable': ['*'],
                        },
                'factory-parameters': {
                    'dockerversion': "1.10.1",
                    'docker_cmd':  '[ "/bin/bash" ]',
                    'docker_env': '[ "DISTTAG=f32container", "FGC=f32", "container=oci" ]',
                    'docker_label': '{ "name": "fedora", "license": "MIT", "vendor": "Fedora Project", "version": "32"}',
                },
            },
        ],
    }

    live_media = {
        '^Workstation$': [
                {
                    'name': 'Fedora-Workstation-Live',
                    'kickstart': 'fedora-live-workstation.ks',
                    # Variants.xml also contains aarch64 and armhfp, but there
                    # should be no live media for those arches.
                    'arches': ['x86_64', 'ppc64le'],
                    'failable': ['ppc64le'],
                    # Take packages and install tree from Everything repo.
                    'repo': 'Everything',
                    'install_tree_from': 'Everything',
                }
            ],
        '^Spins': [
            # There are multiple media for Spins variant. They use subvariant
            # field so that they can be identified in the metadata.
            {
                'name': 'Fedora-KDE-Live',
                'kickstart': 'fedora-live-kde.ks',
                'arches': ['x86_64'],
                'repo': 'Everything',
                'install_tree_from': 'Everything',
                'subvariant': 'KDE'

            },
            {
                'name': 'Fedora-Xfce-Live',
                'kickstart': 'fedora-live-xfce.ks',
                'arches': ['x86_64'],
                'failable': ['*'],
                'repo': 'Everything',
                'install_tree_from': 'Everything',
                'subvariant': 'Xfce'
            },
        ],
    }

    failable_deliverables = [
        # Installer and ISOs for server failing do not abort the compose.
        ('^Server$', { 
            '*': ['buildinstall', 'iso'],
        }),
        ('^.*$', {
            # Buildinstall is not blocking
            'src': ['buildinstall'],
            # Nothing on i386, ppc64le blocks the compose
            'i386': ['buildinstall', 'iso'],
            'ppc64le': ['buildinstall', 'iso'],
            's390x': ['buildinstall', 'iso'],
        })
    ]

    live_target = 'f32'
    live_images_no_rename = True
    live_images = [
        ('^Workstation$', {
            'armhfp': {
                'kickstart': 'fedora-arm-workstation.ks',
                'name': 'Fedora-Workstation-armhfp',
                # Again workstation takes packages from Everything.
                'repo': 'Everything',
                'type': 'appliance',
                'failable': True,
            }
        }),
        ('^Server$', {
            # But Server has its own repo.
            'armhfp': {
                'kickstart': 'fedora-arm-server.ks',
                'name': 'Fedora-Server-armhfp',
                'type': 'appliance',
                'failable': True,
            }
        }),
    ]

    ostree = {
        "^Silverblue$": {
            "version": "!OSTREE_VERSION_FROM_LABEL_DATE_TYPE_RESPIN",
            # To get config, clone master branch from this repo and take
            # treefile from there.
            "treefile": "fedora-silverblue.yaml",
            "config_url": "https://pagure.io/workstation-ostree-config.git",
            "config_branch": "master",
            # Consume packages from Everything
            "repo": "Everything",
            # Don't create a reference in the ostree repo (signing automation does that).
            "tag_ref": False,
            # Don't use change detection in ostree.
            "force_new_commit": True,
            # Use unified core mode for rpm-ostree composes
            "unified_core": True,
            # This is the location for the repo where new commit will be
            # created. Note that this is outside of the compose dir.
            "ostree_repo": "/mnt/koji/compose/ostree/repo/",
            "ostree_ref": "fedora/rawhide/${basearch}/silverblue",
            "arches": ["x86_64", "ppc64le", "aarch64"],
            "failable": ['*'],
        }
    }

    ostree_installer = [
        ("^Silverblue$", {
            "x86_64": {
                "repo": "Everything",
                "release": None,
                "rootfs_size": "8",
                # Take templates from this repository.
                'template_repo': 'https://pagure.io/fedora-lorax-templates.git',
                'template_branch': 'master',
                # Use following templates.
                "add_template": ["ostree-based-installer/lorax-configure-repo.tmpl",
                                 "ostree-based-installer/lorax-embed-repo.tmpl",
                                 "ostree-based-installer/lorax-embed-flatpaks.tmpl"],
                # And add these variables for the templates.
                "add_template_var": [
                    "ostree_install_repo=https://kojipkgs.fedoraproject.org/compose/ostree/repo/",
                    "ostree_update_repo=https://ostree.fedoraproject.org",
                    "ostree_osname=fedora",
                    "ostree_oskey=fedora-32-primary",
                    "ostree_contenturl=mirrorlist=https://ostree.fedoraproject.org/mirrorlist",
                    "ostree_install_ref=fedora/rawhide/x86_64/silverblue",
                    "ostree_update_ref=fedora/rawhide/x86_64/silverblue",
                    "flatpak_remote_name=fedora",
                    "flatpak_remote_url=oci+https://registry.fedoraproject.org",
                    "flatpak_remote_refs=runtime/org.fedoraproject.Platform/x86_64/f30 app/org.gnome.Baobab/x86_64/stable",
                ],
                'failable': ['*'],
            },
        })
    ]


RCM Tools compose
-----------------

This is a small compose used to deliver packages to Red Hat internal users. The
configuration is split into two files.

::

    # rcmtools-common.conf 

    release_name = "RCM Tools"
    release_short = "RCMTOOLS"
    release_version = "2.0"
    release_type = "updates"
    release_is_layered = True
    createrepo_c = True
    createrepo_checksum = "sha256"

    # PKGSET
    pkgset_source = "koji"
    koji_profile = "brew"
    pkgset_koji_inherit = True


    # GENERAL SETTINGS
    bootable = False
    comps_file = "rcmtools-comps.xml"
    variants_file = "rcmtools-variants.xml"
    sigkeys = ["3A3A33A3"]


    # RUNROOT settings
    runroot = False


    # GATHER
    gather_method = "deps"
    check_deps = True

    additional_packages = [
        ('.*', {
            '*': ['puddle', 'rcm-nexus'],
            }
        ),
    ]

    # Set repoclosure_strictness to fatal to avoid installation dependency
    # issues in production composes
    repoclosure_strictness = [
        ("^.*$", {
            "*": "fatal"
        })
    ]


Configuration specific for different base products is split into separate files.

::

    # rcmtools-common.conf 
    from rcmtools-common import *

    # BASE PRODUCT
    base_product_name = "Red Hat Enterprise Linux"
    base_product_short = "RHEL"
    base_product_version = "7"

    # PKGSET
    pkgset_koji_tag = "rcmtools-rhel-7-compose"

    # remove i386 arch on rhel7
    tree_arches = ["aarch64", "ppc64le", "s390x", "x86_64"]

    check_deps = False

    # Packages in these repos are available to satisfy dependencies inside the
    # compose, but will not be pulled in.
    gather_lookaside_repos = [
        ("^Client|Client-optional$", {
            "x86_64": [
                "http://example.redhat.com/rhel/7/Client/x86_64/os/",
                "http://example.redhat.com/rhel/7/Client/x86_64/optional/os/",
            ],
        }),
         ("^Workstation|Workstation-optional$", {
            "x86_64": [
                "http://example.redhat.com/rhel/7/Workstation/x86_64/os/",
                "http://example.redhat.com/rhel/7/Workstation/x86_64/optional/os/",
            ],
        }),
        ("^Server|Server-optional$", {
            "aarch64": [
                "http://example.redhat.com/rhel/7/Server/aarch64/os/",
                "http://example.redhat.com/rhel/7/Server/aarch64/optional/os/",
            ],
            "ppc64": [
                "http://example.redhat.com/rhel/7/Server/ppc64/os/",
                "http://example.redhat.com/rhel/7/Server/ppc64/optional/os/",
            ],
            "ppc64le": [
                "http://example.redhat.com/rhel/7/Server/ppc64le/os/",
                "http://example.redhat.com/rhel/7/Server/ppc64le/optional/os/",
            ],
            "s390x": [
                "http://example.redhat.com/rhel/7/Server/s390x/os/",
                "http://example.redhat.com/rhel/7/Server/s390x/optional/os/",
            ],
            "x86_64": [
                "http://example.redhat.com/rhel/7/Server/x86_64/os/",
                "http://example.redhat.com/rhel/7/Server/x86_64/optional/os/",
            ],
        })
    ]
