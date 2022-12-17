# -*- coding: utf-8 -*-


from inspect import isclass

from pungi.phases.base import PhaseBase


def gather_phases_metadata(source_object):
    """
    Code gathers metadata from Phase classes.
    Metadata are 'name' attributes of the corresponding classes.
    Metadata are gathered without creating instances of Phase classes.
    """

    if not source_object:
        raise ValueError(
            "PhasesMetadata can not load any data - it got empty parameter"
        )

    phases = []
    for item in dir(source_object):
        cls = getattr(source_object, item)  # get all objects references
        if not isclass(cls):  # filter out non-classes
            continue
        if issubclass(cls, PhaseBase):
            try:
                name_attr = getattr(cls, "name")
                phases.append(name_attr)
            except AttributeError:
                raise AttributeError(
                    "Bad phase-class format: '%s' is missing attribute 'name'" % item
                )

    return phases
