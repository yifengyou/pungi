==================
Config file format
==================

The configuration file parser is provided by `kobo
<https://github.com/release-engineering/kobo>`_

The file follows a Python-like format. It consists of a sequence of variables
that have a value assigned to them. ::

    variable = value

The variable names must follow the same convention as Python code: start with a
letter and consist of letters, digits and underscores only.

The values can be either an integer, float, boolean (``True`` or ``False``), a
string or ``None``. Strings must be enclosed in either single or double quotes.

Complex types are supported as well.

A list is enclosed in square brackets and items are separated with commas.
There can be a comma after the last item as well. ::

   a_list = [1,
             2,
             3,
            ]

A tuple works like a list, but is enclosed in parenthesis. ::

    a_tuple = (1, "one")

A dictionary is wrapped in brackets, and consists of ``key: value`` pairs
separated by commas. The keys can only be formed from basic types (int, float,
string). ::

    a_dict = {
        'foo': 'bar',
        1: None
    }

The value assigned to a variable can also be taken from another variable. ::

    one = 1
    another = one

Anything on a line after a ``#`` symbol is ignored and functions as a comment.


Importing other files
=====================

It is possible to include another configuration file. The files are looked up
relative to the currently processed file.

The general structure of import is: ::

    from FILENAME import WHAT

The ``FILENAME`` should be just the base name of the file without extension
(which must be ``.conf``). ``WHAT`` can either be a comma separated list of
variables or ``*``. ::

    # Opens constants.conf and brings PI and E into current scope.
    from constants import PI, E

    # Opens common.conf and brings everything defined in that file into current
    # file as well.
    from common import *

.. note::
    Pungi will copy the configuration file given on command line into the
    ``logs/`` directory. Only this single file will be copied, not any included
    ones. (Copying included files requires a fix in kobo library.)

    The JSON-formatted dump of configuration is correct though.

Formatting strings
==================

String interpolation is available as well. It uses a ``%``-encoded format. See
Python documentation for more details. ::

    joined = "%s %s" % (var_a, var_b)

    a_dict = {
        "fst": 1,
        "snd": 2,
    }
    another = "%(fst)s %(snd)s" % a_dict
