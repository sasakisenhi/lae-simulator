from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lae_simulator.cli import main
from lae_simulator.provenance import ProvenanceValidationError, verify_provenance_bundle

FIXTURE = Path("fixtures/g1")


class ProvenanceTests(unittest.TestCase):
    def _manifest(self, target: Path) -> tuple[Path, dict[str, object]]:
        manifest_path = target / "manifest.json"
        return manifest_path, json.loads(manifest_path.read_text(encoding="utf-8"))

    def _write_manifest(self, path: Path, manifest: dict[str, object]) -> None:
        path.write_text(
            json.dumps(manifest, ensure_ascii=False),
            encoding="utf-8",
        )

    def _codes(self, manifest_path: Path) -> set[str]:
        with self.assertRaises(ProvenanceValidationError) as caught:
            verify_provenance_bundle(manifest_path)
        return {issue.code for issue in caught.exception.issues}

    def test_fixed_bundle_validates_offline(self) -> None:
        report = verify_provenance_bundle(FIXTURE / "manifest.json")
        self.assertEqual("valid", report["status"])
        self.assertEqual(25, report["files_verified"])
        self.assertEqual(11, report["references_verified"])

    def test_digest_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "g1"
            shutil.copytree(FIXTURE, target)
            path = target / "sources/issue/issue-1955.md"
            path.write_text(path.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
            with self.assertRaises(ProvenanceValidationError) as caught:
                verify_provenance_bundle(target / "manifest.json")
            self.assertIn("digest-mismatch", {issue.code for issue in caught.exception.issues})

    def test_missing_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "g1"
            shutil.copytree(FIXTURE, target)
            (target / "raw/h0/index.js.b64").unlink()
            with self.assertRaises(ProvenanceValidationError) as caught:
                verify_provenance_bundle(target / "manifest.json")
            self.assertIn("missing-file", {issue.code for issue in caught.exception.issues})

    def test_invalid_version_and_reference_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "g1"
            shutil.copytree(FIXTURE, target)
            manifest_path = target / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["schema_version"] = "2.0.0"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            seed_path = target / "reference-seed.json"
            seed = json.loads(seed_path.read_text(encoding="utf-8"))
            seed["references"].append(seed["references"][0])
            seed_path.write_text(json.dumps(seed), encoding="utf-8")
            with self.assertRaises(ProvenanceValidationError) as caught:
                verify_provenance_bundle(manifest_path)
            codes = {issue.code for issue in caught.exception.issues}
            self.assertIn("unsupported-version", codes)
            self.assertIn("duplicate-reference", codes)

    def test_unknown_source_reference_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "g1"
            shutil.copytree(FIXTURE, target)
            seed_path = target / "reference-seed.json"
            seed = json.loads(seed_path.read_text(encoding="utf-8"))
            seed["references"][0]["source_id"] = "missing"
            seed_path.write_text(json.dumps(seed), encoding="utf-8")
            with self.assertRaises(ProvenanceValidationError) as caught:
                verify_provenance_bundle(target / "manifest.json")
            self.assertIn(
                "unknown-source-reference",
                {issue.code for issue in caught.exception.issues},
            )

    def test_file_symlink_outside_bundle_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "g1"
            shutil.copytree(FIXTURE, target)
            bundled = target / "raw/h0/index.js.b64"
            outside = root / "outside.b64"
            outside.write_bytes(bundled.read_bytes())
            bundled.unlink()
            bundled.symlink_to(outside)
            self.assertIn(
                "path-outside-bundle",
                self._codes(target / "manifest.json"),
            )

    def test_intermediate_directory_symlink_outside_bundle_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "g1"
            shutil.copytree(FIXTURE, target)
            bundled = target / "raw/h0"
            outside = root / "outside-h0"
            shutil.copytree(bundled, outside)
            shutil.rmtree(bundled)
            bundled.symlink_to(outside, target_is_directory=True)
            self.assertIn(
                "path-outside-bundle",
                self._codes(target / "manifest.json"),
            )

    def test_invalid_utf8_link_payload_is_structured_input_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "g1"
            shutil.copytree(FIXTURE, target)
            manifest_path, manifest = self._manifest(target)
            sources = manifest["sources"]
            assert isinstance(sources, list)
            b0 = sources[0]
            assert isinstance(b0, dict)
            files = b0["files"]
            assert isinstance(files, list)
            link = files[8]
            assert isinstance(link, dict)
            content = b"\xff"
            raw_path = target / str(link["path"])
            raw_path.write_bytes(base64.b64encode(content) + b"\n")
            link["sha256"] = hashlib.sha256(content).hexdigest()
            link["git_blob"] = hashlib.sha1(
                b"blob 1\0" + content,
                usedforsecurity=False,
            ).hexdigest()
            self._write_manifest(manifest_path, manifest)

            self.assertIn(
                "invalid-link-target-content",
                self._codes(manifest_path),
            )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["validate-materials", str(manifest_path)])
            self.assertEqual(2, exit_code)
            report = json.loads(stderr.getvalue())
            self.assertEqual("invalid", report["status"])
            self.assertIn(
                "invalid-link-target-content",
                {issue["code"] for issue in report["issues"]},
            )

    def test_base64_allows_only_declared_ascii_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "g1"
            shutil.copytree(FIXTURE, target)
            path = target / "raw/h0/index.js.b64"
            encoded = b"".join(path.read_bytes().split())
            path.write_bytes(b" \t" + encoded[:20] + b"\r\n" + encoded[20:] + b"\n")
            self.assertEqual(
                "valid",
                verify_provenance_bundle(target / "manifest.json")["status"],
            )

    def test_invalid_base64_character_padding_and_truncation_are_rejected(self) -> None:
        mutations: dict[str, Callable[[bytes], bytes]] = {
            "character": lambda value: b"%" + value,
            "padding": lambda value: value.rstrip() + b"=\n",
            "truncation": lambda value: value.rstrip()[:-1] + b"\n",
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "g1"
                shutil.copytree(FIXTURE, target)
                path = target / "raw/h0/index.js.b64"
                path.write_bytes(mutate(path.read_bytes()))
                self.assertIn(
                    "invalid-base64",
                    self._codes(target / "manifest.json"),
                )

    def test_manifest_required_fields_types_formats_and_unknown_keys(self) -> None:
        cases: tuple[tuple[str, Callable[[dict[str, Any]], object], str], ...] = (
            ("missing-retrieved", lambda value: value.pop("retrieved_at"), "missing-field"),
            ("bad-retrieved", lambda value: value.__setitem__("retrieved_at", "2026-11-07"), "invalid-datetime"),
            ("unknown-top", lambda value: value.__setitem__("surprise", True), "unknown-field"),
            (
                "bad-commit",
                lambda value: value["sources"][0].__setitem__("revision", "main"),
                "invalid-revision",
            ),
            (
                "bad-digest",
                lambda value: value["sources"][0]["files"][0].__setitem__("sha256", "A" * 64),
                "invalid-digest",
            ),
            (
                "unknown-file-key",
                lambda value: value["sources"][0]["files"][0].__setitem__("extra", "x"),
                "unknown-field",
            ),
        )
        for name, mutate, expected in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "g1"
                shutil.copytree(FIXTURE, target)
                manifest_path, manifest = self._manifest(target)
                mutate(manifest)
                self._write_manifest(manifest_path, manifest)
                self.assertIn(expected, self._codes(manifest_path))

    def test_reference_seed_contract_rejects_missing_duplicate_and_unknown_fields(self) -> None:
        mutations: dict[str, Callable[[dict[str, Any]], object]] = {
            "missing": lambda item: item.pop("target"),
            "unknown": lambda item: item.__setitem__("extra", "x"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "g1"
                shutil.copytree(FIXTURE, target)
                seed_path = target / "reference-seed.json"
                seed = json.loads(seed_path.read_text(encoding="utf-8"))
                mutate(seed["references"][0])
                seed_path.write_text(json.dumps(seed), encoding="utf-8")
                codes = self._codes(target / "manifest.json")
                self.assertIn(
                    "missing-field" if name == "missing" else "unknown-field",
                    codes,
                )

    def test_duplicate_bundle_path_and_drive_identifiers_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "g1"
            shutil.copytree(FIXTURE, target)
            manifest_path, manifest = self._manifest(target)
            sources = manifest["sources"]
            assert isinstance(sources, list)
            lae = sources[-1]
            assert isinstance(lae, dict)
            files = lae["files"]
            assert isinstance(files, list)
            first = files[0]
            second = files[1]
            assert isinstance(first, dict) and isinstance(second, dict)
            second["path"] = first["path"]
            second["drive_file_id"] = first["drive_file_id"]
            second["reference_id"] = first["reference_id"]
            self._write_manifest(manifest_path, manifest)
            codes = self._codes(manifest_path)
            self.assertIn("duplicate-path", codes)
            self.assertIn("duplicate-drive-file-id", codes)
            self.assertIn("duplicate-reference-id", codes)


if __name__ == "__main__":
    unittest.main()
