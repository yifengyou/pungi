.. _scm_support:

Exporting files from SCM
========================

Multiple places in Pungi can use files from external storage. The configuration
is similar independently of the backend that is used, although some features
may be different.

The so-called ``scm_dict`` is always put into configuration as a dictionary,
which can contain following keys.

* ``scm`` -- indicates which SCM system is used. This is always required.
  Allowed values are:

  * ``file`` -- copies files from local filesystem
  * ``git`` -- copies files from a Git repository
  * ``cvs`` -- copies files from a CVS repository
  * ``rpm`` -- copies files from a package in the compose
  * ``koji`` -- downloads archives from a given build in Koji build system

* ``repo``

  * for Git and CVS backends this should be URL to the repository
  * for RPM backend this should be a shell style glob matching package names
    (or a list of such globs)
  * for file backend this should be empty
  * for Koji backend this should be an NVR or package name

* ``branch``

  * branch name for Git and CVS backends, with ``master`` and ``HEAD`` as defaults
  * Koji tag for koji backend if only package name is given
  * otherwise should not be specified

* ``file`` -- a list of files that should be exported.

* ``dir`` -- a directory that should be exported. All its contents will be
  exported. This option is mutually exclusive with ``file``.

* ``command`` -- defines a shell command to run after Git clone to generate the
  needed file (for example to run ``make``). Only supported in Git backend.


Koji examples
-------------

There are two different ways how to configure the Koji backend. ::

    {
        # Download all *.tar files from build my-image-1.0-1.
        "scm": "koji",
        "repo": "my-image-1.0-1",
        "file": "*.tar",
    }

    {
        # Find latest build of my-image in tag my-tag and take files from
        # there.
        "scm": "koji",
        "repo": "my-image",
        "branch": "my-tag",
        "file": "*.tar",
    }

Using both tag name and exact NVR will result in error: the NVR would be
interpreted as a package name, and would not match anything.


``file`` vs. ``dir``
--------------------

Exactly one of these two options has to be specified. Documentation for each
configuration option should specify whether it expects a file or a directory.

For ``extra_files`` phase either key is valid and should be chosen depending on
what the actual use case.


Caveats
-------

The ``rpm`` backend can only be used in phases that would extract the files
after ``pkgset`` phase finished. You can't get comps file from a package.

Depending on Git repository URL configuration Pungi can only export the
requested content using ``git archive``. When a command should run this is not
possible and a clone is always needed.

When using ``koji`` backend, it is required to provide configuration for Koji
profile to be used (``koji_profile``). It is not possible to contact multiple
different Koji instances.
