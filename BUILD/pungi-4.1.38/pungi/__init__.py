# -*- coding: utf-8 -*-

import os
import re


try:
    import gi
    gi.require_version('Modulemd', '1.0') # noqa
    from gi.repository import Modulemd
except:
    Modulemd = None


def get_full_version():
    """
    Find full version of Pungi: if running from git, this will return cleaned
    output of `git describe`, otherwise it will look for installed version.
    """
    location = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..')
    if os.path.isdir(os.path.join(location, '.git')):
        import subprocess
        proc = subprocess.Popen(['git', '--git-dir=%s/.git' % location, 'describe', '--tags'],
                                stdout=subprocess.PIPE, universal_newlines=True)
        output, _ = proc.communicate()
        return re.sub(r'-1.fc\d\d?', '', output.strip().replace('pungi-', ''))
    else:
        import subprocess
        proc = subprocess.Popen(
            ["rpm", "-q", "pungi"], stdout=subprocess.PIPE, universal_newlines=True
        )
        (output, err) = proc.communicate()
        if not err:
            return output.rstrip()
        else:
            return 'unknown'
