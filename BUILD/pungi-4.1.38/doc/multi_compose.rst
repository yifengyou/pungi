.. _multi_compose:

Managing compose from multiple parts
====================================

There may be cases where it makes sense to split a big compose into separate
parts, but create a compose output that links all output into one familiar
structure.

The `pungi-orchestrate` tools allows that.

It works with an INI-style configuration file. The ``[general]`` section
contains information about identity of the main compose. Other sections define
individual parts.

The parts are scheduled to run in parallel, with the minimal amount of
serialization. The final compose directory will contain hard-links to the
files.


General settings
----------------

**target**
   Path to directory where the final compose should be created.
**compose_type**
   Type of compose to make.
**release_name**
   Name of the product for the final compose.
**release_short**
   Short name of the product for the final compose.
**release_version**
   Version of the product for the final compose.
**release_type**
   Type of the product for the final compose.
**extra_args**
   Additional arguments that wil be passed to the child Pungi processes.
**koji_profile**
   If specified, a current event will be retrieved from the Koji instance and
   used for all parts.

**kerberos**
   If set to yes, a kerberos ticket will be automatically created at the start.
   Set keytab and principal as well.
**kerberos_keytab**
   Path to keytab file used to create the kerberos ticket.
**kerberos_principal**
   Kerberos principal for the ticket

**pre_compose_script**
   Commands to execute before first part is started. Can contain multiple
   commands on separate lines.
**post_compose_script**
   Commands to execute after the last part finishes and final status is
   updated. Can contain multiple commands on separate lines. ::

      post_compose_script =
          compose-latest-symlink $COMPOSE_PATH
          custom-post-compose-script.sh

   Multiple environment variables are defined for the scripts:

    * ``COMPOSE_PATH``
    * ``COMPOSE_ID``
    * ``COMPOSE_DATE``
    * ``COMPOSE_TYPE``
    * ``COMPOSE_RESPIN``
    * ``COMPOSE_LABEL``
    * ``RELEASE_ID``
    * ``RELEASE_NAME``
    * ``RELEASE_SHORT``
    * ``RELEASE_VERSION``
    * ``RELEASE_TYPE``
    * ``RELEASE_IS_LAYERED`` – ``YES`` for layered products, empty otherwise
    * ``BASE_PRODUCT_NAME`` – only set for layered products
    * ``BASE_PRODUCT_SHORT`` – only set for layered products
    * ``BASE_PRODUCT_VERSION`` – only set for layered products
    * ``BASE_PRODUCT_TYPE`` – only set for layered products

**notification_script**
   Executable name (or path to a script) that will be used to send a message
   once the compose is finished. In order for a valid URL to be included in the
   message, at least one part must configure path translation that would apply
   to location of main compose.

   Only two messages will be sent, one for start and one for finish (either
   successful or not).


Partial compose settings
------------------------

Each part should have a separate section in the config file.

It can specify these options:

**config**
   Path to configuration file that describes this part. If relative, it is
   resolved relative to the file with parts configuration.
**just_phase**, **skip_phase**
   Customize which phases should run for this part.
**depends_on**
   A comma separated list of other parts that must be finished before this part
   starts.
**failable**
   A boolean toggle to mark a part as failable. A failure in such part will
   mark the final compose as incomplete, but still successful.
