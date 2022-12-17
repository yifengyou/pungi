=====================
Contributing to Pungi
=====================


Set up development environment
==============================

In order to work on *Pungi*, you should install recent version of *Fedora*.

Python2
-------

Fedora 29 is recommended because some packages are not available in newer Fedora release, e.g. python2-libcomps.

Install required packages ::

    $ sudo dnf install -y krb5-devel gcc make libcurl-devel python2-devel python2-createrepo_c kobo-rpmlib yum python2-libcomps python2-libselinx

Python3
-------

Install required packages ::

    $ sudo dnf install -y krb5-devel gcc make libcurl-devel python3-devel python3-createrepo_c python3-libcomps

Developing
==========

Currently the development workflow for Pungi is on master branch:

- Make your own fork at https://pagure.io/pungi
- Clone your fork locally (replacing $USERNAME with your own)::

    git clone git@pagure.io:forks/$USERNAME/pungi.git

- cd into your local clone and add the remote upstream for rebasing::

    cd pungi
    git remote add upstream git@pagure.io:pungi.git

  .. note::
      This workflow assumes that you never ``git commit`` directly to the master
      branch of your fork. This will make more sense when we cover rebasing
      below.

- create a topic branch based on master::

    git branch my_topic_branch master
    git checkout my_topic_branch


- Make edits, changes, add new features, etc. and then make sure to pull
  from upstream master and rebase before submitting a pull request::

    # lets just say you edited setup.py for sake of argument
    git checkout my_topic_branch

    # make changes to setup.py
    black setup.py
    tox
    git add setup.py
    git commit -s -m "added awesome feature to setup.py"

    # now we rebase
    git checkout master
    git pull --rebase upstream master
    git push origin master
    git push origin --tags
    git checkout my_topic_branch
    git rebase master

    # resolve merge conflicts if any as a result of your development in
    # your topic branch
    git push origin my_topic_branch

  .. note::
      In order to for your commit to be merged:

      - you must sign-off on it. Use ``-s`` option when running ``git commit``.

      - The code must be well formatted via ``black`` and pass ``flake8`` checking. Run ``tox -e black,flake8`` to do the check.

- Create pull request in the pagure.io web UI

- For convenience, here is a bash shell function that can be placed in your
  ~/.bashrc and called such as ``pullupstream pungi-4-devel`` that will
  automate a large portion of the rebase steps from above::

    pullupstream () {
      if [[ -z "$1" ]]; then
        printf "Error: must specify a branch name (e.g. - master, devel)\n"
      else
        pullup_startbranch=$(git describe --contains --all HEAD)
        git checkout $1
        git pull --rebase upstream master
        git push origin $1
        git push origin --tags
        git checkout ${pullup_startbranch}
      fi
    }


Testing
=======

You must write unit tests for any new code (except for trivial changes). Any
code without sufficient test coverage may not be merged.

To run all existing tests, suggested method is to use *tox*. ::

    $ sudo dnf install python3-tox -y

    $ tox -e py3
    $ tox -e py27

Alternatively you could create a vitualenv, install deps and run tests
manually if you don't want to use tox. ::

    $ sudo dnf install python3-virtualenvwrapper -y
    $ mkvirtualenv --system-site-packages py3
    $ workon py3
    $ pip install -r requirements.txt -r test-requirements.txt
    $ make test

    # or with coverage
    $ make test-coverage

If you need to run specified tests, *pytest* is recommended. ::

    # Activate virtualenv first

    # Run tests
    $ pytest tests/test_config.py
    $ pytest tests/test_config.py -k test_pkgset_mismatch_repos

In the ``tests/`` directory there is a shell script ``test_compose.sh`` that
you can use to try and create a miniature compose on dummy data. The actual
data will be created by running ``make test-data`` in project root. ::

    $ sudo dnf -y install rpm-build createrepo_c isomd5sum genisoimage syslinux

    # Activate virtualenv (the one created by tox could be used)
    $ source .tox/py3/bin/activate

    $ python setup.py develop
    $ make test-data
    $ make test-compose

This testing compose does not actually use all phases that are available, and
there is no checking that the result is correct. It only tells you whether it
crashed or not.

.. note::
   Even when it finishes successfully, it may print errors about
   ``repoclosure`` on *Server-Gluster.x86_64* in *test* phase. This is not a
   bug.


Documenting
===========

You must write documentation for any new features and functional changes.
Any code without sufficient documentation may not be merged.

To generate the documentation, run ``make doc`` in project root.
