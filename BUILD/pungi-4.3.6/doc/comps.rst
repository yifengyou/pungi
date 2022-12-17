.. _comps:

Processing comps files
======================

The comps file that Pungi takes as input is not really pure comps as used by
tools like DNF. There are extensions used to customize how the file is processed.

The first step of Pungi processing is to retrieve the actual file. This can use
anything that :ref:`scm_support` supports.

Pungi extensions are ``arch`` attribute on ``packageref``, ``group`` and
``environment`` tags. The value of this attribute is a comma separated list of
architectures.

Second step Pungi performs is creating a file for each architecture. This is
done by removing all elements with incompatible ``arch`` attribute. No
additional clean up is performed on this file. The resulting file is only used
internally for the rest of the compose process.

Third and final step is to create comps file for each Variant.Arch combination.
This is the actual file that will be included in the compose. The start file is
the original input file, from which all elements with incompatible architecture
are removed. Then clean up is performed by removing all empty groups, removing
non-existing groups from environments and categories and finally removing empty
environments and categories. As a last step groups not listed in the variants
file are removed.
