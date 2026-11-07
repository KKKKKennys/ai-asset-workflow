"""SYNTHETIC coordinator tests only: no actual generation, Blender or 3D QA.

All inputs and outputs live in TemporaryDirectory, never repository runs/.
PNG fixtures are real, tiny RGB PNGs built with stdlib struct/zlib. BLEND
fixtures deliberately contain only a plausible header and dummy bytes; GLBs
contain an empty JSON scene. Passing tests establish coordinator/state/hash
behavior, NOT Blender readability, GLB importability, geometry, or appearance.
Known invariant violations remain ordinary failures, not expectedFailure.
"""
import contextlib
import copy
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib

sys.dont_write_bytecode = True

from workflow import cli
from workflow.concepts import ingest
from workflow.core import Project, WorkflowError, contained, identifier


SYNTHETIC_NOTE = "SYNTHETIC human decision fixture; no real asset reviewed"


def png_bytes(color=(31, 97, 173)):
    """A valid 2x2 RGB PNG, including chunk CRCs and compressed scanlines."""
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))
    scanlines = (b"\x00" + bytes(color) * 2) * 2
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(scanlines))
            + chunk(b"IEND", b""))


def glb_bytes():
    """An empty synthetic glTF 2 JSON scene; no real mesh or import test."""
    payload = json.dumps(
        {"asset": {"version": "2.0", "generator": "SYNTHETIC unittest"},
         "scene": 0, "scenes": [{"nodes": []}]},
        separators=(",", ":"),
    ).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    return (struct.pack("<4sII", b"glTF", 2, 20 + len(payload))
            + struct.pack("<I4s", len(payload), b"JSON") + payload)


def put_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def get_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class SyntheticProjectCase(unittest.TestCase):
    """Every subclass/test is SYNTHETIC, with subprocess execution prohibited."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-workflow-test-")
        self.addCleanup(temporary.cleanup)
        self.sandbox = Path(temporary.name).resolve()
        self.root = self.sandbox / "project"
        self.project = Project(self.root / "project.json")
        self.brief = {
            "name": "SYNTHETIC coordinator fixtures",
            "style": "Approved theme only; this does not approve any asset image",
            "assets": [
                {"id": key, "name": "Synthetic " + key, "brief": "No real 3D work"}
                for key in ("case", "lamp")
            ],
        }
        self.project.init(copy.deepcopy(self.brief))
        self.input = self.sandbox / "input.png"
        self.input.write_bytes(png_bytes())
        guard = mock.patch(
            "subprocess.Popen",
            side_effect=AssertionError("SYNTHETIC tests must not spawn subprocesses"),
        )
        self.addCleanup(guard.stop)
        guard.start()

    def asset(self, key="case"):
        return self.project.asset(self.project.load(), key)

    def candidate(self, key="case", color=None):
        path = self.input
        if color is not None:
            path = self.sandbox / ("input-" + key + "-" + bytes(color).hex() + ".png")
            path.write_bytes(png_bytes(color))
        return self.project.register(key, path, "SYNTHETIC stdlib fixture", "Synthetic")

    def approved(self, key="case"):
        candidate = self.candidate(key)
        self.project.approve(key, candidate["id"], SYNTHETIC_NOTE)
        return candidate

    def assert_rejected(self, operation):
        """Rejected operations must preserve manifest bytes and file inventory."""
        before = self.project.path.read_bytes()
        paths = {p.relative_to(self.root) for p in self.root.rglob("*")}
        with self.assertRaises((WorkflowError, ValueError, OSError)):
            operation()
        self.assertEqual(before, self.project.path.read_bytes())
        self.assertEqual(paths, {p.relative_to(self.root) for p in self.root.rglob("*")})

    def receipt(self, packet, *, status="produced", marker=b"original"):
        job = Path(packet["receipt_path"]).parent
        output = Path(packet["output_dir"])
        kind = "blend" if packet["stage"] == "model" else "glb"
        name = "asset." + kind
        payload = (b"BLENDER-v300" + b"SYNTHETIC NOT A BLEND FILE " + marker
                   if kind == "blend" else glb_bytes())
        (output / name).write_bytes(payload)
        (output / "preview.png").write_bytes(png_bytes())
        receipt = {
            "schema_version": 1, "job_id": packet["job_id"],
            "asset_id": packet["asset_id"], "stage": packet["stage"],
            "reference_sha256": packet["reference_sha256"], "status": status,
            "artifacts": [
                {"kind": kind, "path": "outputs/" + name},
                {"kind": "preview", "path": "outputs/preview.png"},
            ],
            "checks": [{"name": "synthetic worker claim", "status": "passed",
                        "evidence": "SYNTHETIC claim, never independent 3D evidence"}],
            "limitations": ["SYNTHETIC files; no Blender, geometry or visual QA"],
        }
        if status == "failed":
            receipt["reason"] = "Synthetic worker failure"
        put_json(job / "result.json", receipt)
        return job / "result.json"

    def model(self, marker=b"original"):
        if self.asset()["approval"] is None:
            self.approved()
        packet = self.project.packet("case", "model")
        path = self.receipt(packet, marker=marker)
        self.project.record("case", "model", path)
        return packet, path

    def delivery(self):
        self.model()
        packet = self.project.packet("case", "deliver")
        path = self.receipt(packet)
        self.project.record("case", "deliver", path)
        return packet, path

    def symlink(self, target, link, directory=False):
        try:
            os.symlink(target, link, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            if os.name == "nt" and directory and getattr(exc, "winerror", None) == 1314:
                # Directory junctions exercise resolve()/containment without
                # administrator rights, shell commands, or external packages.
                import _winapi
                create_junction = getattr(_winapi, "CreateJunction", None)
                if create_junction is not None:
                    Path(target).resolve().relative_to(self.sandbox)
                    Path(link).parent.resolve().relative_to(self.sandbox)
                    create_junction(str(target), str(link))
                    return
            if (isinstance(exc, NotImplementedError)
                    or getattr(exc, "winerror", None) == 1314
                    or getattr(exc, "errno", None) in
                    (errno.EPERM, errno.EACCES, errno.ENOSYS, errno.ENOTSUP)):
                self.skipTest("SYNTHETIC symlink fixture unavailable: " + str(exc))
            raise


class SyntheticApprovalTests(SyntheticProjectCase):
    def test_no_model_before_explicit_image_approval(self):
        self.assert_rejected(lambda: self.project.packet("case", "model"))
        self.candidate()
        self.assert_rejected(lambda: self.project.packet("case", "model"))
        self.assertIsNone(self.asset()["approval"])
        self.assertFalse((self.root / "jobs").exists())

    def test_theme_and_another_asset_approval_are_not_asset_approval(self):
        self.approved("lamp")
        self.candidate("case")
        self.assert_rejected(lambda: self.project.packet("case", "model"))
        self.assertIsNone(self.asset()["approval"])

    def test_approval_requires_full_known_candidate_and_nonempty_note(self):
        candidate = self.candidate()
        for key, note in ((candidate["id"], ""), (candidate["id"], " \n\t"),
                          (candidate["id"][:16], SYNTHETIC_NOTE),
                          ("0" * 64, SYNTHETIC_NOTE)):
            with self.subTest(candidate=key, note=note):
                self.assert_rejected(lambda: self.project.approve("case", key, note))

    def test_same_bytes_registration_is_idempotent_even_after_approval(self):
        candidate = self.approved()
        before = self.project.path.read_bytes()
        other = self.sandbox / "same-content.other-extension"
        other.write_bytes(self.input.read_bytes())
        result = self.project.register("case", other, "Different source", "Different prompt")
        self.assertEqual(candidate, result)
        self.assertEqual(before, self.project.path.read_bytes())
        self.assertEqual(1, len(self.asset()["candidates"]))
        self.assertEqual(candidate["sha256"], self.asset()["approval"]["sha256"])

    def test_source_mutation_does_not_change_copied_approved_reference(self):
        candidate = self.approved()
        self.input.write_bytes(png_bytes((255, 0, 0)))
        packet = self.project.packet("case", "model")
        self.assertEqual(candidate["sha256"], packet["reference_sha256"])
        self.assertEqual(candidate["sha256"], sha256(packet["reference_path"]))

    def test_candidate_mutation_before_approval_is_rejected(self):
        candidate = self.candidate()
        (self.root / candidate["path"]).write_bytes(png_bytes((255, 0, 0)))
        self.assert_rejected(
            lambda: self.project.approve("case", candidate["id"], SYNTHETIC_NOTE))

    def test_approved_image_mutation_blocks_packet_record_and_acceptance(self):
        packet, receipt = self.delivery()
        candidate = self.asset()["candidates"][0]
        (self.root / candidate["path"]).write_bytes(png_bytes((255, 0, 0)))
        for operation in (
            lambda: self.project.packet("case", "model"),
            lambda: self.project.record("case", "deliver", receipt),
            lambda: self.project.accept_delivery("case", SYNTHETIC_NOTE),
        ):
            with self.subTest(operation=operation):
                self.assert_rejected(operation)

    def test_new_reference_clears_downstream_results_and_acceptance(self):
        self.delivery()
        self.project.accept_delivery("case", SYNTHETIC_NOTE)
        candidate = self.candidate(color=(255, 0, 0))
        result = self.project.approve("case", candidate["id"], SYNTHETIC_NOTE)
        self.assertEqual({}, result["results"])
        self.assertEqual("approved", result["status"])
        self.assertFalse(result.get("delivery_acceptance"),
                         "Old delivery acceptance survives a new reference approval")
        self.assert_rejected(lambda: self.project.accept_delivery("case", SYNTHETIC_NOTE))

    def test_safe_id_validation_and_duplicate_initialization(self):
        for value in ("../escape", "a/b", r"a\b", "..", ".", "/absolute",
                      "C:escape", "UPPER", "a b", "a\x00b", "", "a" * 65, None, 7):
            with self.subTest(value=value):
                with self.assertRaises(WorkflowError):
                    identifier(value)
        for value in ("a", "case-01", "case_01", "a" * 64):
            self.assertEqual(value, identifier(value))
        brief = copy.deepcopy(self.brief)
        brief["assets"].append(copy.deepcopy(brief["assets"][0]))
        project = Project(self.sandbox / "duplicate" / "project.json")
        with self.assertRaises(WorkflowError):
            project.init(brief)
        self.assertFalse(project.path.exists())

    @unittest.skipUnless(os.name == "nt", "Windows device-name safety")
    def test_windows_reserved_device_ids_are_rejected(self):
        for value in ("con", "prn", "aux", "nul", "com1", "lpt9"):
            with self.subTest(value=value):
                with self.assertRaises(WorkflowError):
                    identifier(value)

    def test_empty_unknown_and_short_image_inputs_are_rejected(self):
        for index, payload in enumerate((b"", b"not an image" * 20,
                                         b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
            with self.subTest(index=index):
                path = self.sandbox / ("invalid-" + str(index) + ".png")
                path.write_bytes(payload)
                self.assert_rejected(
                    lambda: self.project.register("case", path, "SYNTHETIC invalid"))

    def test_magic_with_junk_is_not_a_valid_image(self):
        # Passing this is a rejection check, not a claim of full format decoding.
        for index, magic in enumerate((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff",
                                       b"RIFF" + b"\x00" * 4 + b"WEBP")):
            with self.subTest(index=index):
                path = self.sandbox / ("forged-" + str(index) + ".bin")
                path.write_bytes(magic + b"\x00" * 96)
                self.assert_rejected(
                    lambda: self.project.register("case", path, "SYNTHETIC forged"))


class SyntheticStageTests(SyntheticProjectCase):
    def test_packet_stage_constraints_and_model_dependency(self):
        self.approved()
        for stage in ("", "concept", "complete", "../model", "deliver"):
            with self.subTest(stage=stage):
                self.assert_rejected(lambda: self.project.packet("case", stage))
        packet, _ = self.model()
        delivery = self.project.packet("case", "deliver")
        self.assertEqual(packet["job_id"], delivery["prior_model"]["job_id"])

    def test_running_or_failed_state_blocks_dispatch(self):
        self.approved()
        for status in ("running", "failed"):
            with self.subTest(status=status):
                data = self.project.load()
                self.project.asset(data, "case")["status"] = status
                put_json(self.project.path, data)  # Synthetic persisted-state fixture.
                self.assert_rejected(lambda: self.project.packet("case", "model"))

    def test_task_identity_must_match_receipt_and_current_reference(self):
        self.approved()
        packet = self.project.packet("case", "model")
        receipt = self.receipt(packet)
        task_path = receipt.parent / "task.json"
        original = get_json(task_path)
        for field, value in (("asset_id", "lamp"), ("stage", "deliver"),
                             ("reference_sha256", "0" * 64), ("schema_version", 2)):
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed[field] = value
                put_json(task_path, changed)
                self.assert_rejected(lambda: self.project.record("case", "model", receipt))
                put_json(task_path, original)

    def test_receipt_identity_must_match_issued_task(self):
        self.approved()
        packet = self.project.packet("case", "model")
        receipt = self.receipt(packet)
        original = get_json(receipt)
        for field, value in (("asset_id", "lamp"), ("stage", "deliver"),
                             ("reference_sha256", "0" * 64),
                             ("job_id", "model-not-issued"), ("schema_version", 2)):
            with self.subTest(field=field):
                changed = copy.deepcopy(original)
                changed[field] = value
                put_json(receipt, changed)
                self.assert_rejected(lambda: self.project.record("case", "model", receipt))
                put_json(receipt, original)

    def test_record_rejects_unknown_stage_even_if_task_and_receipt_agree(self):
        self.approved()
        packet = self.project.packet("case", "model")
        receipt = self.receipt(packet)
        for path in (receipt, receipt.parent / "task.json"):
            changed = get_json(path)
            changed["stage"] = "not-a-stage"
            if path == receipt:
                (Path(packet["output_dir"]) / "asset.glb").write_bytes(glb_bytes())
                changed["artifacts"][0] = {"kind": "glb", "path": "outputs/asset.glb"}
            put_json(path, changed)
        self.assert_rejected(lambda: self.project.record("case", "not-a-stage", receipt))

    def test_delivery_dispatch_rejects_modified_or_missing_prior_model_files(self):
        self.model()
        for artifact in self.asset()["results"]["model"]["artifacts"]:
            path = self.root / artifact["path"]
            original = path.read_bytes()
            for change in ("modified", "missing"):
                with self.subTest(kind=artifact["kind"], change=change):
                    if change == "modified":
                        path.write_bytes(original + b"SYNTHETIC change")
                    else:
                        path.unlink()
                    self.assert_rejected(lambda: self.project.packet("case", "deliver"))
                    path.write_bytes(original)

    def test_replacing_model_invalidates_existing_delivery_and_acceptance(self):
        self.delivery()
        self.project.accept_delivery("case", SYNTHETIC_NOTE)
        self.model(marker=b"replacement")
        asset = self.asset()
        self.assertNotIn("deliver", asset["results"])
        self.assertFalse(asset.get("delivery_acceptance"))
        self.assertNotEqual("completed", asset["status"])
        self.assert_rejected(lambda: self.project.accept_delivery("case", SYNTHETIC_NOTE))

    def test_stale_delivery_receipt_rejected_after_model_replacement(self):
        self.model()
        old = self.project.packet("case", "deliver")
        stale_receipt = self.receipt(old)
        self.model(marker=b"replacement")
        self.assert_rejected(
            lambda: self.project.record("case", "deliver", stale_receipt))

    def test_delivery_receipt_rejected_if_model_mutated_after_dispatch(self):
        self.model()
        packet = self.project.packet("case", "deliver")
        receipt = self.receipt(packet)
        artifact = self.asset()["results"]["model"]["artifacts"][0]
        (self.root / artifact["path"]).write_bytes(b"BLENDER SYNTHETIC modified")
        self.assert_rejected(lambda: self.project.record("case", "deliver", receipt))


class SyntheticReceiptTests(SyntheticProjectCase):
    def test_failed_receipt_never_completes_or_allows_acceptance(self):
        packet, receipt = self.delivery()
        failed = get_json(receipt)
        failed["status"] = "failed"
        failed["reason"] = "SYNTHETIC failure despite files being present"
        put_json(receipt, failed)
        result = self.project.record("case", "deliver", receipt)
        self.assertEqual("failed", result["status"])
        self.assert_rejected(lambda: self.project.accept_delivery("case", SYNTHETIC_NOTE))
        self.assert_rejected(lambda: self.project.packet("case", "deliver"))
        self.assertNotEqual("completed", self.asset()["status"])

    def test_receipt_cannot_claim_final_acceptance(self):
        self.approved()
        packet = self.project.packet("case", "model")
        receipt = self.receipt(packet)
        for status in ("complete", "completed", "accepted", "", None):
            with self.subTest(status=status):
                value = get_json(receipt)
                value["status"] = status
                put_json(receipt, value)
                self.assert_rejected(lambda: self.project.record("case", "model", receipt))

    def test_missing_empty_or_omitted_required_artifacts_rejected(self):
        self.approved()
        packet = self.project.packet("case", "model")
        receipt = self.receipt(packet)
        original_receipt = get_json(receipt)
        for entry in original_receipt["artifacts"]:
            path = receipt.parent / entry["path"]
            original_bytes = path.read_bytes()
            for defect in ("missing", "empty", "omitted"):
                with self.subTest(kind=entry["kind"], defect=defect):
                    changed = copy.deepcopy(original_receipt)
                    if defect == "missing":
                        path.unlink()
                    elif defect == "empty":
                        path.write_bytes(b"")
                    else:
                        changed["artifacts"].remove(entry)
                    put_json(receipt, changed)
                    self.assert_rejected(lambda: self.project.record("case", "model", receipt))
                    path.write_bytes(original_bytes)
                    put_json(receipt, original_receipt)

    def test_glb_magic_version_and_declared_length_validation(self):
        self.model()
        packet = self.project.packet("case", "deliver")
        receipt = self.receipt(packet)
        path = Path(packet["output_dir"]) / "asset.glb"
        good = path.read_bytes()
        bad_files = {
            "magic": b"BAD!" + good[4:],
            "version": good[:4] + struct.pack("<I", 1) + good[8:],
            "length_short": good[:8] + struct.pack("<I", len(good) - 1) + good[12:],
            "length_long": good[:8] + struct.pack("<I", len(good) + 1) + good[12:],
            "truncated": good[:9],
        }
        for defect, payload in bad_files.items():
            with self.subTest(defect=defect):
                path.write_bytes(payload)
                self.assert_rejected(lambda: self.project.record("case", "deliver", receipt))

    def test_file_receipt_preserves_unverified_geometry_and_worker_claim_boundary(self):
        self.model()
        asset = self.asset()
        result = asset["results"]["model"]
        self.assertTrue(result["file_integrity_checked"])
        self.assertIs(result["geometry_and_appearance_independently_verified"], False)
        self.assertEqual("passed", result["worker_checks"][0]["status"])
        self.assertTrue(result["limitations"])
        self.assertNotEqual("completed", asset["status"])
        self.assertFalse(asset.get("delivery_acceptance"))
        self.assert_rejected(lambda: self.project.accept_delivery("case", SYNTHETIC_NOTE))

    def test_recorded_deliver_outputs_hashes_and_explicit_decision_allow_acceptance(self):
        self.delivery()
        self.assertEqual("delivery_review", self.asset()["status"])
        self.assert_rejected(lambda: self.project.accept_delivery("case", " \n"))
        for result in self.asset()["results"].values():
            for artifact in result["artifacts"]:
                self.assertEqual(sha256(self.root / artifact["path"]), artifact["sha256"])
        result = self.project.accept_delivery("case", SYNTHETIC_NOTE)
        self.assertEqual("completed", result["status"])
        self.assertEqual(SYNTHETIC_NOTE, result["delivery_acceptance"]["decision_note"])
        for stage in result["results"].values():
            self.assertIs(stage["geometry_and_appearance_independently_verified"], False)

    def test_acceptance_rechecks_every_model_and_delivery_artifact(self):
        self.delivery()
        for stage, result in self.asset()["results"].items():
            for artifact in result["artifacts"]:
                path = self.root / artifact["path"]
                original = path.read_bytes()
                for defect in ("mutated", "missing"):
                    with self.subTest(stage=stage, kind=artifact["kind"], defect=defect):
                        if defect == "mutated":
                            path.write_bytes(original + b"SYNTHETIC mutation")
                        else:
                            path.unlink()
                        self.assert_rejected(
                            lambda: self.project.accept_delivery("case", SYNTHETIC_NOTE))
                        path.write_bytes(original)

    def test_delivery_review_status_alone_without_recorded_deliver_is_insufficient(self):
        self.model()
        data = self.project.load()
        self.project.asset(data, "case")["status"] = "delivery_review"
        put_json(self.project.path, data)  # Corrupt/incomplete persisted-state fixture.
        self.assert_rejected(lambda: self.project.accept_delivery("case", SYNTHETIC_NOTE))

    def test_empty_deliver_artifact_list_cannot_be_accepted(self):
        self.delivery()
        data = self.project.load()
        self.project.asset(data, "case")["results"]["deliver"]["artifacts"] = []
        put_json(self.project.path, data)  # Corrupt persisted-state fixture.
        self.assert_rejected(lambda: self.project.accept_delivery("case", SYNTHETIC_NOTE))


class SyntheticPathAndLockTests(SyntheticProjectCase):
    def test_containment_rejects_root_traversal_and_absolute_escape(self):
        root = self.root / "outputs"
        root.mkdir()
        for value in (".", "..", "../escape", "nested/../../escape",
                      str(self.sandbox / "outside.png")):
            with self.subTest(value=value):
                with self.assertRaises(WorkflowError):
                    contained(root, value)
        self.assertEqual(root / "inside.png", contained(root, "inside.png"))

    def test_receipt_must_be_within_current_asset_jobs(self):
        self.approved()
        packet = self.project.packet("case", "model")
        original = self.receipt(packet)
        for destination in (
            self.sandbox / "outside.json",
            self.root / "result.json",
            self.root / "jobs" / "lamp" / "wrong" / "result.json",
        ):
            with self.subTest(destination=destination):
                put_json(destination, get_json(original))
                self.assert_rejected(
                    lambda: self.project.record("case", "model", destination))

    def test_artifact_traversal_absolute_and_sibling_paths_rejected(self):
        self.approved()
        packet = self.project.packet("case", "model")
        receipt = self.receipt(packet)
        original = get_json(receipt)
        outside = receipt.parent / "outside.blend"
        outside.write_bytes(b"BLENDER SYNTHETIC")
        for value in ("outputs/../outside.blend",
                      "outputs/../../sibling/outputs/asset.blend",
                      str(outside), "../outside.blend"):
            with self.subTest(value=value):
                changed = copy.deepcopy(original)
                changed["artifacts"][0]["path"] = value
                put_json(receipt, changed)
                self.assert_rejected(lambda: self.project.record("case", "model", receipt))

    def test_output_file_symlink_cannot_escape_output_directory(self):
        self.approved()
        packet = self.project.packet("case", "model")
        receipt = self.receipt(packet)
        file = Path(packet["output_dir"]) / "asset.blend"
        external = self.root / "outside-output.blend"
        external.write_bytes(file.read_bytes())
        file.unlink()
        self.symlink(external, file)
        self.assert_rejected(lambda: self.project.record("case", "model", receipt))

    def test_output_directory_symlink_cannot_redirect_to_other_project_directory(self):
        self.approved()
        packet = self.project.packet("case", "model")
        outputs = Path(packet["output_dir"])
        outputs.rmdir()
        redirected = self.root / "unrelated-output"
        redirected.mkdir()
        self.symlink(redirected, outputs, directory=True)
        receipt = self.receipt(packet)
        self.assert_rejected(lambda: self.project.record("case", "model", receipt))

    def test_asset_jobs_symlink_cannot_escape_jobs_root_even_inside_project(self):
        self.approved()
        jobs = self.root / "jobs"
        jobs.mkdir()
        redirected = self.root / "unrelated-jobs"
        redirected.mkdir()
        self.symlink(redirected, jobs / "case", directory=True)
        self.assert_rejected(lambda: self.project.packet("case", "model"))

    def test_jobs_symlink_cannot_escape_project(self):
        self.approved()
        redirected = self.sandbox / "external-jobs"
        redirected.mkdir()
        self.symlink(redirected, self.root / "jobs", directory=True)
        self.assert_rejected(lambda: self.project.packet("case", "model"))
        self.assertEqual([], list(redirected.iterdir()))

    def test_project_lock_rejects_conflicting_mutations_without_deleting_lock(self):
        packet, receipt = self.delivery()
        candidate = self.asset()["candidates"][0]
        lock = self.project.path.with_suffix(".json.lock")
        operations = {
            "init": lambda: self.project.init(self.brief),
            "register": lambda: self.candidate(color=(1, 2, 3)),
            "approve": lambda: self.project.approve("case", candidate["id"], SYNTHETIC_NOTE),
            "packet": lambda: self.project.packet("case", "model"),
            "record": lambda: self.project.record("case", "deliver", receipt),
            "retry": lambda: self.project.retry("case"),
            "accept": lambda: self.project.accept_delivery("case", SYNTHETIC_NOTE),
        }
        with self.project.transaction():
            lock_bytes = lock.read_bytes()
            for name, operation in operations.items():
                with self.subTest(operation=name):
                    self.assert_rejected(operation)
                    self.assertEqual(lock_bytes, lock.read_bytes())
        self.assertFalse(lock.exists())

    def test_lock_released_after_exception(self):
        lock = self.project.path.with_suffix(".json.lock")
        with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
            with self.project.transaction():
                raise RuntimeError("synthetic failure")
        self.assertFalse(lock.exists())
        with self.project.transaction():
            self.assertTrue(lock.is_file())


class SyntheticConceptIngestTests(SyntheticProjectCase):
    def concept_receipt(self):
        directory = self.root / "concept-jobs" / "synthetic-job"
        outputs = directory / "outputs"
        outputs.mkdir(parents=True, exist_ok=True)
        image = outputs / "case.png"
        image.write_bytes(png_bytes())
        path = directory / "result.json"
        put_json(path, {
            "schema_version": 1, "approved": False,
            "generation_tool": "SYNTHETIC stdlib fixture, not imagegen",
            "assets": [{
                "asset_id": "case", "image_path": "outputs/case.png",
                "sha256": sha256(image), "status": "generated", "approved": False,
                "prompt": "SYNTHETIC", "image_model": None,
            }],
        })
        return path

    def test_valid_ingest_binds_bytes_and_receipt_but_never_approves(self):
        receipt = self.concept_receipt()
        result = ingest(self.project, receipt)
        self.assertEqual(1, len(result))
        candidate = result[0]
        self.assertEqual(get_json(receipt)["assets"][0]["sha256"], candidate["sha256"])
        self.assertEqual(candidate["sha256"], sha256(self.root / candidate["path"]))
        self.assertEqual(receipt.relative_to(self.root).as_posix(),
                         candidate["generation_receipt"])
        self.assertIsNone(self.asset()["approval"])
        self.assertIsNone(candidate["reported_image_model"])
        self.assert_rejected(lambda: self.project.packet("case", "model"))

    def test_ingest_rejects_hash_mismatch_and_changed_image(self):
        receipt = self.concept_receipt()
        original = get_json(receipt)
        bad = copy.deepcopy(original)
        bad["assets"][0]["sha256"] = "0" * 64
        put_json(receipt, bad)
        self.assert_rejected(lambda: ingest(self.project, receipt))
        put_json(receipt, original)
        (receipt.parent / "outputs" / "case.png").write_bytes(png_bytes((255, 0, 0)))
        self.assert_rejected(lambda: ingest(self.project, receipt))

    def test_ingest_requires_nonempty_recorded_image_hash(self):
        receipt = self.concept_receipt()
        original = get_json(receipt)
        for value in (None, ""):
            with self.subTest(sha256=value):
                changed = copy.deepcopy(original)
                if value is None:
                    changed["assets"][0].pop("sha256")
                else:
                    changed["assets"][0]["sha256"] = value
                put_json(receipt, changed)
                self.assert_rejected(lambda: ingest(self.project, receipt))

    def test_ingest_rejects_unknown_duplicate_and_empty_asset_batches_atomically(self):
        receipt = self.concept_receipt()
        original = get_json(receipt)
        entry = original["assets"][0]
        unknown = dict(entry, asset_id="unknown")
        for entries in ([entry, unknown], [entry, entry], []):
            with self.subTest(assets=[e["asset_id"] for e in entries]):
                changed = copy.deepcopy(original)
                changed["assets"] = entries
                put_json(receipt, changed)
                self.assert_rejected(lambda: ingest(self.project, receipt))
                self.assertEqual([], self.asset()["candidates"])
                self.assertFalse((self.root / "references").exists())

    def test_ingest_rejects_worker_approval_at_receipt_or_asset_level(self):
        receipt = self.concept_receipt()
        original = get_json(receipt)
        for level in ("receipt", "asset"):
            with self.subTest(level=level):
                changed = copy.deepcopy(original)
                target = changed if level == "receipt" else changed["assets"][0]
                target["approved"] = True
                put_json(receipt, changed)
                self.assert_rejected(lambda: ingest(self.project, receipt))
                self.assertIsNone(self.asset()["approval"])

    def test_ingest_receipt_cannot_be_outside_project(self):
        receipt = self.concept_receipt()
        outside = self.sandbox / "outside-concept-receipt.json"
        put_json(outside, get_json(receipt))
        self.assert_rejected(lambda: ingest(self.project, outside))

    def test_ingest_image_path_cannot_escape_receipt_directory(self):
        receipt = self.concept_receipt()
        external = self.root / "outside-concept.png"
        external.write_bytes(png_bytes())
        original = get_json(receipt)
        for value in ("../../outside-concept.png", str(external)):
            with self.subTest(path=value):
                changed = copy.deepcopy(original)
                changed["assets"][0]["image_path"] = value
                put_json(receipt, changed)
                self.assert_rejected(lambda: ingest(self.project, receipt))

    def test_ingest_image_symlink_cannot_escape_receipt_directory(self):
        receipt = self.concept_receipt()
        external = self.root / "outside-concept.png"
        external.write_bytes(png_bytes())
        image = receipt.parent / "outputs" / "case.png"
        image.unlink()
        self.symlink(external, image)
        self.assert_rejected(lambda: ingest(self.project, receipt))

    def test_ingest_honors_project_mutation_lock(self):
        receipt = self.concept_receipt()
        with self.project.transaction():
            self.assert_rejected(lambda: ingest(self.project, receipt))


class SyntheticCliTests(SyntheticProjectCase):
    def test_invalid_tasks_return_nonzero_without_subprocesses(self):
        cases = [
            ["packet", "--asset", "case", "--stage", "model"],
            ["packet", "--asset", "../escape", "--stage", "model"],
            ["packet", "--asset", "unknown", "--stage", "deliver"],
            ["packet", "--asset", "case", "--stage", "invalid"],
            ["accept-delivery", "--asset", "case", "--decision-note", SYNTHETIC_NOTE],
            ["ingest-concepts", "--receipt", str(self.sandbox / "missing.json")],
        ]
        for args in cases:
            with self.subTest(args=args):
                stdout, stderr = io.StringIO(), io.StringIO()
                before = self.project.path.read_bytes()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    try:
                        code = cli.main(args + ["--project", str(self.project.path)])
                    except SystemExit as exc:  # argparse rejects invalid choices.
                        code = exc.code
                self.assertIsInstance(code, int)
                self.assertNotEqual(0, code)
                self.assertTrue(stderr.getvalue())
                self.assertEqual(before, self.project.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
