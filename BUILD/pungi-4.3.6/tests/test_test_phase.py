# -*- coding: utf-8 -*-

import mock
import os

import pungi.phases.test as test_phase
from tests.helpers import DummyCompose, PungiTestCase, touch, FIXTURE_DIR

try:
    import dnf  # noqa: F401

    HAS_DNF = True
except ImportError:
    HAS_DNF = False

try:
    import yum  # noqa: F401

    HAS_YUM = True
except ImportError:
    HAS_YUM = False


PAD = b"\0" * 100
UNBOOTABLE_ISO = (b"\0" * 0x8001) + b"CD001" + PAD
ISO_WITH_MBR = (b"\0" * 0x1FE) + b"\x55\xAA" + (b"\0" * 0x7E01) + b"CD001" + PAD
ISO_WITH_GPT = (b"\0" * 0x200) + b"EFI PART" + (b"\0" * 0x7DF9) + b"CD001" + PAD
ISO_WITH_MBR_AND_GPT = (
    (b"\0" * 0x1FE) + b"\x55\xAAEFI PART" + (b"\0" * 0x7DF9) + b"CD001" + PAD
)
ISO_WITH_TORITO = (
    (b"\0" * 0x8001)
    + b"CD001"
    + (b"\0" * 0x7FA)
    + b"\0CD001\1EL TORITO SPECIFICATION"
    + PAD
)


class TestCheckImageSanity(PungiTestCase):
    def test_missing_file_reports_error(self):
        compose = DummyCompose(self.topdir, {})

        with self.assertRaises(IOError):
            test_phase.check_image_sanity(compose)

    def test_missing_file_doesnt_report_if_failable(self):
        compose = DummyCompose(self.topdir, {})
        compose.image.deliverable = "iso"
        compose.image.can_fail = True

        try:
            test_phase.check_image_sanity(compose)
        except Exception:
            self.fail("Failable deliverable must not raise")

    def test_correct_iso_does_not_raise(self):
        compose = DummyCompose(self.topdir, {})
        compose.image.format = "iso"
        compose.image.bootable = False
        touch(os.path.join(self.topdir, "compose", compose.image.path), UNBOOTABLE_ISO)

        try:
            test_phase.check_image_sanity(compose)
        except Exception:
            self.fail("Correct unbootable image must not raise")

    def test_incorrect_iso_raises(self):
        compose = DummyCompose(self.topdir, {})
        compose.image.format = "iso"
        compose.image.bootable = False
        touch(os.path.join(self.topdir, "compose", compose.image.path), "Hey there")

        with self.assertRaises(RuntimeError) as ctx:
            test_phase.check_image_sanity(compose)

        self.assertIn("does not look like an ISO file", str(ctx.exception))

    def test_bootable_iso_without_mbr_or_gpt_raises_on_x86_64(self):
        compose = DummyCompose(self.topdir, {})
        compose.image.arch = "x86_64"
        compose.image.format = "iso"
        compose.image.bootable = True
        touch(os.path.join(self.topdir, "compose", compose.image.path), UNBOOTABLE_ISO)

        with self.assertRaises(RuntimeError) as ctx:
            test_phase.check_image_sanity(compose)

        self.assertIn(
            "is supposed to be bootable, but does not have MBR nor GPT",
            str(ctx.exception),
        )

    def test_bootable_iso_without_mbr_or_gpt_doesnt_raise_on_arm(self):
        compose = DummyCompose(self.topdir, {})
        compose.image.arch = "armhfp"
        compose.image.format = "iso"
        compose.image.bootable = True
        touch(os.path.join(self.topdir, "compose", compose.image.path), UNBOOTABLE_ISO)

        try:
            test_phase.check_image_sanity(compose)
        except Exception:
            self.fail("Failable deliverable must not raise")

    def test_failable_bootable_iso_without_mbr_gpt_doesnt_raise(self):
        compose = DummyCompose(self.topdir, {})
        compose.image.format = "iso"
        compose.image.bootable = True
        compose.image.deliverable = "iso"
        compose.image.can_fail = True
        touch(os.path.join(self.topdir, "compose", compose.image.path), UNBOOTABLE_ISO)

        try:
            test_phase.check_image_sanity(compose)
        except Exception:
            self.fail("Failable deliverable must not raise")

    def test_bootable_iso_with_mbr_does_not_raise(self):
        compose = DummyCompose(self.topdir, {})
        compose.image.format = "iso"
        compose.image.bootable = True
        touch(os.path.join(self.topdir, "compose", compose.image.path), ISO_WITH_MBR)

        try:
            test_phase.check_image_sanity(compose)
        except Exception:
            self.fail("Bootable image with MBR must not raise")

    def test_bootable_iso_with_gpt_does_not_raise(self):
        compose = DummyCompose(self.topdir, {})
        compose.image.format = "iso"
        compose.image.bootable = True
        touch(os.path.join(self.topdir, "compose", compose.image.path), ISO_WITH_GPT)

        try:
            test_phase.check_image_sanity(compose)
        except Exception:
            self.fail("Bootable image with GPT must not raise")

    def test_bootable_iso_with_mbr_and_gpt_does_not_raise(self):
        compose = DummyCompose(self.topdir, {})
        compose.image.format = "iso"
        compose.image.bootable = True
        touch(
            os.path.join(self.topdir, "compose", compose.image.path),
            ISO_WITH_MBR_AND_GPT,
        )

        try:
            test_phase.check_image_sanity(compose)
        except Exception:
            self.fail("Bootable image with MBR and GPT must not raise")

    def test_bootable_iso_with_el_torito_does_not_raise(self):
        compose = DummyCompose(self.topdir, {})
        compose.image.format = "iso"
        compose.image.bootable = True
        touch(os.path.join(self.topdir, "compose", compose.image.path), ISO_WITH_TORITO)

        try:
            test_phase.check_image_sanity(compose)
        except Exception:
            self.fail("Bootable image with El Torito must not raise")

    def test_checks_with_optional_variant(self):
        compose = DummyCompose(self.topdir, {})
        compose.variants["Server"].variants = {
            "optional": mock.Mock(
                uid="Server-optional",
                arches=["x86_64"],
                type="optional",
                is_empty=False,
            )
        }
        compose.image.format = "iso"
        compose.image.bootable = True
        touch(
            os.path.join(self.topdir, "compose", compose.image.path),
            ISO_WITH_MBR_AND_GPT,
        )

        image = mock.Mock(
            path="Server/i386/optional/iso/image.iso", format="iso", bootable=False
        )
        compose.im.images["Server-optional"] = {"i386": [image]}

        try:
            test_phase.check_image_sanity(compose)
        except Exception:
            self.fail("Checking optional variant must not raise")

    @mock.patch("pungi.phases.test.check_sanity", new=mock.Mock())
    def test_too_big_iso(self):
        compose = DummyCompose(self.topdir, {"createiso_max_size": [(".*", {"*": 10})]})
        compose.image.format = "iso"
        compose.image.bootable = False
        compose.image.size = 20

        test_phase.check_image_sanity(compose)

        warnings = [call[0][0] for call in compose.log_warning.call_args_list]
        self.assertIn(
            "ISO Client/i386/iso/image.iso is too big. Expected max 10B, got 20B",
            warnings,
        )

    @mock.patch("pungi.phases.test.check_sanity", new=mock.Mock())
    def test_too_big_iso_strict(self):
        compose = DummyCompose(
            self.topdir,
            {
                "createiso_max_size": [(".*", {"*": 10})],
                "createiso_max_size_is_strict": [(".*", {"*": True})],
            },
        )
        compose.image.format = "iso"
        compose.image.bootable = False
        compose.image.size = 20

        with self.assertRaises(RuntimeError) as ctx:
            test_phase.check_image_sanity(compose)

        self.assertEqual(
            str(ctx.exception),
            "ISO Client/i386/iso/image.iso is too big. Expected max 10B, got 20B",
        )

    @mock.patch("pungi.phases.test.check_sanity", new=mock.Mock())
    def test_too_big_iso_not_strict(self):
        compose = DummyCompose(
            self.topdir,
            {
                "createiso_max_size": [(".*", {"*": 10})],
                "createiso_max_size_is_strict": [(".*", {"*": False})],
            },
        )
        compose.image.format = "iso"
        compose.image.bootable = False
        compose.image.size = 20

        test_phase.check_image_sanity(compose)

        warnings = [call[0][0] for call in compose.log_warning.call_args_list]
        self.assertIn(
            "ISO Client/i386/iso/image.iso is too big. Expected max 10B, got 20B",
            warnings,
        )

    @mock.patch("pungi.phases.test.check_sanity", new=mock.Mock())
    def test_too_big_unified(self):
        compose = DummyCompose(self.topdir, {})
        compose.image.format = "iso"
        compose.image.bootable = False
        compose.image.size = 20
        compose.image.unified = True
        setattr(compose.image, "_max_size", 10)

        test_phase.check_image_sanity(compose)

        warnings = [call[0][0] for call in compose.log_warning.call_args_list]
        self.assertIn(
            "ISO Client/i386/iso/image.iso is too big. Expected max 10B, got 20B",
            warnings,
        )

    @mock.patch("pungi.phases.test.check_sanity", new=mock.Mock())
    def test_too_big_unified_strict(self):
        compose = DummyCompose(
            self.topdir,
            {"createiso_max_size_is_strict": [(".*", {"*": True})]},
        )
        compose.image.format = "iso"
        compose.image.bootable = False
        compose.image.size = 20
        compose.image.unified = True
        setattr(compose.image, "_max_size", 10)

        with self.assertRaises(RuntimeError) as ctx:
            test_phase.check_image_sanity(compose)

        self.assertEqual(
            str(ctx.exception),
            "ISO Client/i386/iso/image.iso is too big. Expected max 10B, got 20B",
        )

    @mock.patch("pungi.phases.test.check_sanity", new=mock.Mock())
    def test_fits_in_limit(self):
        compose = DummyCompose(self.topdir, {"createiso_max_size": [(".*", {"*": 20})]})
        compose.image.format = "iso"
        compose.image.bootable = False
        compose.image.size = 5

        test_phase.check_image_sanity(compose)

        self.assertEqual(compose.log_warning.call_args_list, [])

    @mock.patch("pungi.phases.test.check_sanity", new=mock.Mock())
    def test_non_iso(self):
        compose = DummyCompose(self.topdir, {"createiso_max_size": [(".*", {"*": 10})]})
        compose.image.format = "qcow2"
        compose.image.bootable = False
        compose.image.size = 20

        test_phase.check_image_sanity(compose)

        self.assertEqual(compose.log_warning.call_args_list, [])


class TestImageMetadataValidation(PungiTestCase):
    def test_valid_metadata(self):
        compose = mock.Mock()
        compose.im.images = {"Server": mock.Mock()}
        compose.paths.compose.topdir = lambda: os.path.join(
            FIXTURE_DIR, "basic-metadata"
        )

        test_phase.check_image_metadata(compose)

    def test_missing_metadata(self):
        compose = mock.Mock()
        compose.im.images = {}
        compose.paths.compose.topdir = lambda: self.topdir

        test_phase.check_image_metadata(compose)

    def test_invalid_metadata(self):
        compose = mock.Mock()
        compose.im.images = {"Server": mock.Mock()}
        compose.paths.compose.topdir = lambda: os.path.join(
            FIXTURE_DIR, "invalid-image-metadata"
        )

        with self.assertRaises(RuntimeError):
            test_phase.check_image_metadata(compose)
