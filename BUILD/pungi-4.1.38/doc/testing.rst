===============
 Testing Pungi
===============


Test Data
=========
Tests require test data and not all of it is available in git.
You must create test repositories before running the tests::

    make test-data

Requirements: createrepo_c, rpmbuild


Unit Tests
==========
Unit tests cover functionality of Pungi python modules.
You can run all of them at once::

    make test

which is shortcut to::

    python2 setup.py test
    python3 setup.py test

You can alternatively run individual tests::

    cd tests
    ./<test>.py [<class>[.<test>]]


Functional Tests
================
Because compose is quite complex process and not everything is covered with
unit tests yet, the easiest way how to test if your changes did not break
anything badly is to start a compose on a relatively small and well defined
package set::

    cd tests
    ./test_compose.sh
