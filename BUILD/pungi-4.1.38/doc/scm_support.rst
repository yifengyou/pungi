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

* ``repo`` -- for Git and CVS backends URL to the repository, for RPM a shell
  glob for matching package names (or a list of such globs); for ``file``
  backend this option should be empty (or left out)

* ``branch`` -- branch name for Git and CVS backends, with ``master`` and
  ``HEAD`` as defaults. Ignored for other backends.

* ``file`` -- a list of files that should be exported.

* ``dir`` -- a directory that should be exported. All its contents will be
  exported. This option is mutually exclusive with ``file``.

* ``command`` -- defines a shell command to run after Git clone to generate the
  needed file (for example to run ``make``). Only supported in Git backend.


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
