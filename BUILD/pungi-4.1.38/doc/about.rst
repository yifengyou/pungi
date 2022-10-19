=============
 About Pungi
=============

.. figure:: _static/pungi_snake-sm-dark.png
    :align: right
    :alt: Pungi Logo

*Pungi* is a distribution compose tool.

Composes are release snapshots that contain release deliverables such as:

- installation trees

  - RPMs
  - repodata
  - comps

- (bootable) ISOs
- kickstart trees

  - anaconda images
  - images for PXE boot


Tool overview
=============

*Pungi* consists of multiple separate executables backed by a common library.

The main entry-point is the ``pungi-koji`` script. It loads the compose
configuration and kicks off the process. Composing itself is done in phases.
Each phase is responsible for generating some artifacts on disk and updating
the ``compose`` object that is threaded through all the phases.

*Pungi* itself does not actually do that much. Most of the actual work is
delegated to separate executables. *Pungi* just makes sure that all the
commands are invoked in the appropriate order and with correct arguments. It
also moves the artifacts to correct locations.


Links
=====
- Upstream GIT: https://pagure.io/pungi/
- Issue tracker: https://pagure.io/pungi/issues
- Questions can be asked on *#fedora-releng* IRC channel on FreeNode


Origin of name
==============

The name *Pungi* comes from the instrument used to charm snakes. *Anaconda*
being the software Pungi was manipulating, and anaconda being a snake, led to
the referential naming.

The first name, which was suggested by Seth Vidal, was *FIST*, *Fedora
Installation <Something> Tool*. That name was quickly discarded and replaced
with Pungi.

There was also a bit of an inside joke that when said aloud, it could sound
like punji, which is `a sharpened stick at the bottom of a
trap <https://en.wikipedia.org/wiki/Punji_stick>`_. Kind of like software…
