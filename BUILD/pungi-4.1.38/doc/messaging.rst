.. _messaging:

Progress notification
=====================

*Pungi* has the ability to emit notification messages about progress and
general status of the compose. These can be used to e.g. send messages to
*fedmsg*. This is implemented by actually calling a separate script.

The script will be called with one argument describing action that just
happened. A JSON-encoded object will be passed to standard input to provide
more information about the event. At the very least, the object will contain a
``compose_id`` key.

The script is invoked in compose directory and can read other information
there.

Currently these messages are sent:

 * ``status-change`` -- when composing starts, finishes or fails; a ``status``
   key is provided to indicate details
 * ``phase-start`` -- on start of a phase
 * ``phase-stop`` -- when phase is finished
 * ``createiso-targets`` -- with a list of images to be created
 * ``createiso-imagedone`` -- when any single image is finished
 * ``createiso-imagefail`` -- when any single image fails to create
 * ``fail-to-start`` -- when there are incorrect CLI options or errors in
   configuration file; this message does not contain ``compose_id`` nor is it
   started in the compose directory (which does not exist yet)
 * ``ostree`` -- when a new commit is created, this message will announce its
   hash and the name of ref it is meant for.

For phase related messages ``phase_name`` key is provided as well.

A ``pungi-fedmsg-notification`` script is provided and understands this
interface.

Setting it up
-------------

The script should be provided as a command line argument
``--notification-script``. ::

    --notification-script=pungi-fedmsg-notification
