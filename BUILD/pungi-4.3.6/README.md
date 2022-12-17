# Pungi

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


## Tool overview

*Pungi* consists of multiple separate executables backed by a common library.

The main entry-point is the `pungi-koji` script. It loads the compose
configuration and kicks off the process. Composing itself is done in phases.
Each phase is responsible for generating some artifacts on disk and updating
the `compose` object that is threaded through all the phases.

*Pungi* itself does not actually do that much. Most of the actual work is
delegated to separate executables. *Pungi* just makes sure that all the
commands are invoked in the appropriate order and with correct arguments. It
also moves the artifacts to correct locations.


## Links

- Documentation: https://docs.pagure.org/pungi/
- Upstream GIT: https://pagure.io/pungi/
- Issue tracker: https://pagure.io/pungi/issues
- Questions can be asked in the *#fedora-releng* IRC channel on irc.libera.chat
  or in the matrix room
  [`#releng:fedoraproject.org`](https://matrix.to/#/#releng:fedoraproject.org)
