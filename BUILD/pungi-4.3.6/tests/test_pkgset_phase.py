# -*- coding: utf-8 -*-
from pungi.phases import pkgset
from tests import helpers


class TestPkgsetPhase(helpers.PungiTestCase):
    def test_validates_pkgset_koji_scratch_tasks_only_signed(self):
        cfg = {"pkgset_koji_scratch_tasks": ["123"], "sigkeys": ["sigkey"]}
        compose = helpers.DummyCompose(self.topdir, cfg)
        phase = pkgset.PkgsetPhase(compose)

        with self.assertRaises(ValueError) as ctx:
            phase.validate()
        self.assertIn("Unsigned packages must be allowed", str(ctx.exception))

    def test_validates_pkgset_koji_scratch_tasks_unsigned(self):
        for unsigned_obj in ["", None]:
            cfg = {
                "pkgset_koji_scratch_tasks": ["123"],
                "sigkeys": ["sigkey", unsigned_obj],
            }
            compose = helpers.DummyCompose(self.topdir, cfg)
            phase = pkgset.PkgsetPhase(compose)
            phase.validate()
