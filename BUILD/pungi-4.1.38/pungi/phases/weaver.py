# -*- coding: utf-8 -*-

from kobo import shortcuts
from kobo.threads import ThreadPool, WorkerThread


class WeaverPhase(object):
    """
    Special "phase" that manages other phases' run.
    It needs input-running schema where particular phases are composed
    sequentially and in parallel as well. A Sequential set of phases
    is named "pipeline".
    If any of the phases fail, we must ensure that others will stop correctly.
    Otherwise the whole process will hang.

    :param compose: it is needed for logging
    :param phases_schema: two-dimensional array of phases. Top dimension
        denotes particular pipelines. Second dimension contains phases.
    """
    name = "weaver"

    def __init__(self, compose, phases_schema):
        self.msg = "---------- PHASE: %s ----------" % self.name.upper()
        self.compose = compose
        self.finished = False
        self.pool = ThreadPool(logger=self.compose._logger)
        if not phases_schema:
            msg = "No running schema was set for WeaverPhase"
            self.pool.log_error(msg)
            raise ValueError(msg)
        self._phases_schema = phases_schema

    def start(self):
        if self.finished:
            msg = "Phase '%s' has already finished and can not be started twice" % self.name
            self.pool.log_error(msg)
            raise RuntimeError(msg)

        self.compose.log_info("[BEGIN] %s" % self.msg)
        self.run()

    def run(self):
        for pipeline in shortcuts.force_list(self._phases_schema):
            self.pool.add(PipelineThread(self.pool))
            self.pool.queue_put(shortcuts.force_list(pipeline))

        self.pool.start()

    def stop(self):
        if self.finished:
            return
        if hasattr(self, "pool"):
            self.pool.stop()
        self.finished = True
        self.compose.log_info("[DONE ] %s" % self.msg)


class PipelineThread(WorkerThread):
    """
    Launches phases in pipeline sequentially
    """
    def process(self, item, num):
        pipeline = shortcuts.force_list(item)
        phases_names = ", ".join(phase.name for phase in pipeline)
        msg = "Running pipeline (%d/%d). Phases: %s" % (num, self.pool.queue_total, phases_names)
        self.pool.log_info("[BEGIN] %s" % (msg,))

        for phase in pipeline:
            phase.start()
            phase.stop()

        self.pool.log_info("[DONE ] %s" % (msg,))
