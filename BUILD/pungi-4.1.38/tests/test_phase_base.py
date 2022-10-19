#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import mock
try:
    import unittest2 as unittest
except ImportError:
    import unittest
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.phases import weaver
from tests.helpers import DummyCompose, boom


class TestWeaver(unittest.TestCase):
    def setUp(self):
        # prepare 6 phase mock-objects.
        for test_phase_number in range(1, 7):
            # This is equvalent to:
            # self.pX = mock.Mock()
            # self.pX.name = "phase X"
            # self.pX.start = default_method
            test_phase_name = "p" + repr(test_phase_number)
            tmp = mock.Mock()
            tmp.name = "phase %d" % test_phase_number
            tmp.start.side_effect = self.method_regular
            setattr(self, test_phase_name, tmp)

        self.compose = DummyCompose(None, {})

    def method_regular(self):
        """
        It only have to cause some delay (tens of miliseconds).
        Delay is needed for threads that has enough time to start.
        """
        multiplier = random.sample(range(1, 10), 1)
        time.sleep(multiplier[0] * 0.01)

    def method_with_exception(self):
        self.method_regular()  # make some delay
        boom()  # throw exception

    def assertFinalized(self, p):
        self.assertEqual(p.mock_calls, [mock.call.start(), mock.call.stop()])

    def assertInterrupted(self, p):
        self.assertEqual(p.mock_calls, [mock.call.start()])

    def assertMissed(self, p):
        self.assertEqual(p.mock_calls, [])

    def test_parallel(self):
        phases_schema = (self.p1, self.p2)
        weaver_phase = weaver.WeaverPhase(self.compose, phases_schema)
        weaver_phase.start()
        weaver_phase.stop()

        self.assertFinalized(self.p1)
        self.assertFinalized(self.p2)

    def test_pipeline(self):
        phases_schema = ((self.p1, self.p2),)
        weaver_phase = weaver.WeaverPhase(self.compose, phases_schema)
        weaver_phase.start()
        weaver_phase.stop()

        self.assertFinalized(self.p1)
        self.assertFinalized(self.p2)

    def test_stop_on_failure(self):
        self.p2.start.side_effect = self.method_with_exception

        phases_schema = ((self.p1, self.p2, self.p3),)  # one pipeline
        weaver_phase = weaver.WeaverPhase(self.compose, phases_schema)
        with self.assertRaises(Exception) as ctx:
            weaver_phase.start()
            weaver_phase.stop()

        self.assertEqual('BOOM', str(ctx.exception))
        self.assertFinalized(self.p1)
        self.assertInterrupted(self.p2)
        self.assertMissed(self.p3)

    def test_parallel_stop_on_failure(self):
        self.p2.start.side_effect = self.method_with_exception

        phases_schema = (self.p1, self.p2, self.p3)  # one pipeline
        weaver_phase = weaver.WeaverPhase(self.compose, phases_schema)
        with self.assertRaises(Exception) as ctx:
            weaver_phase.start()
            weaver_phase.stop()

        self.assertEqual('BOOM', str(ctx.exception))
        self.assertFinalized(self.p1)
        self.assertInterrupted(self.p2)
        self.assertFinalized(self.p3)

    def test_multiple_fail(self):
        self.p2.start.side_effect = self.method_with_exception
        self.p3.start.side_effect = self.method_with_exception

        phases_schema = ((self.p1, self.p2, self.p3),)  # one pipeline
        weaver_phase = weaver.WeaverPhase(self.compose, phases_schema)
        with self.assertRaises(Exception) as ctx:
            weaver_phase.start()
            weaver_phase.stop()

        self.assertEqual('BOOM', str(ctx.exception))
        self.assertFinalized(self.p1)
        self.assertInterrupted(self.p2)
        self.assertMissed(self.p3)

    def test_multi_pipeline(self):
        self.p2.start.side_effect = self.method_with_exception
        phases_schema = (
            self.p1,
            (self.p2, self.p3, self.p4),
            (self.p5, self.p6),
        )

        weaver_phase = weaver.WeaverPhase(self.compose, phases_schema)
        with self.assertRaises(Exception) as ctx:
            weaver_phase.start()
            weaver_phase.stop()

        self.assertEqual('BOOM', str(ctx.exception))
        self.assertFinalized(self.p1)
        self.assertInterrupted(self.p2)
        self.assertMissed(self.p3)
        self.assertMissed(self.p4)
        self.assertFinalized(self.p5)
        self.assertFinalized(self.p6)


if __name__ == "__main__":
    unittest.main()
