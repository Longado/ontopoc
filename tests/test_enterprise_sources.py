import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.request import HTTPRedirectHandler


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "tests/fixtures/enterprise_sources/manifest.json"


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class EnterpriseSourcesTest(unittest.TestCase):
    def test_five_read_only_sources_produce_one_stable_snapshot(self) -> None:
        from ontology_poc_generator.enterprise_sources import (
            load_enterprise_source_bundle,
        )

        first = load_enterprise_source_bundle(MANIFEST)
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as directory:
            reversed_manifest = Path(directory) / "manifest.json"
            manifest["sources"] = list(reversed(manifest["sources"]))
            for item in manifest["sources"]:
                item["location"] = str(MANIFEST.parent / item["location"])
            reversed_manifest.write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            second = load_enterprise_source_bundle(reversed_manifest)

        self.assertEqual(first, second)
        self.assertEqual(first["schema"], "enterprise_source_bundle.v1")
        self.assertEqual(
            [item["system"] for item in first["sources"]],
            ["ERP", "MES", "PLM", "QMS", "WMS"],
        )
        self.assertEqual(first["source_snapshot"]["schema"], "quality_source_snapshot.v1")
        self.assertEqual(len(first["source_snapshot"]["records"]), 18)
        self.assertRegex(first["content_hash"], r"^[0-9a-f]{64}$")
        self.assertIn("[QMS:qms:quality-event-017]", first["source_text"])
        self.assertTrue(first["boundaries"]["read_only"])
        self.assertFalse(first["boundaries"]["external_write_executed"])

    def test_manifest_must_cover_each_authoritative_system_once(self) -> None:
        from ontology_poc_generator.enterprise_sources import (
            EnterpriseSourceError,
            load_enterprise_source_bundle,
        )

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest["sources"] = manifest["sources"][:-1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(EnterpriseSourceError, "ERP, MES, PLM, QMS, WMS"):
                load_enterprise_source_bundle(path)

    def test_current_connector_rejects_self_declared_production_evidence(self) -> None:
        from ontology_poc_generator.enterprise_sources import (
            EnterpriseSourceError,
            load_enterprise_source_bundle,
        )

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest["evidence_scope"] = "authorized_read_only"
        for item in manifest["sources"]:
            item["location"] = str(MANIFEST.parent / item["location"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(EnterpriseSourceError, "synthetic_demo"):
                load_enterprise_source_bundle(path)

    def test_duplicate_record_ids_across_systems_are_rejected(self) -> None:
        from ontology_poc_generator.enterprise_sources import (
            EnterpriseSourceError,
            load_enterprise_source_bundle,
        )

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in manifest["sources"]:
                source = json.loads(
                    (MANIFEST.parent / item["location"]).read_text(encoding="utf-8")
                )
                if item["system"] == "ERP":
                    source["records"][0]["source_record_id"] = "quality-event-017"
                location = root / item["location"]
                location.write_text(json.dumps(source), encoding="utf-8")
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(EnterpriseSourceError, "source_record_id"):
                load_enterprise_source_bundle(path)

    def test_each_system_can_only_assert_its_declared_fact_types(self) -> None:
        from ontology_poc_generator.enterprise_sources import (
            EnterpriseSourceError,
            load_enterprise_source_bundle,
        )

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in manifest["sources"]:
                source = json.loads(
                    (MANIFEST.parent / item["location"]).read_text(encoding="utf-8")
                )
                if item["system"] == "ERP":
                    source["records"][0]["predicate"] = "HAS_INSPECTION_OUTCOME"
                (root / item["location"]).write_text(json.dumps(source), encoding="utf-8")
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(EnterpriseSourceError, "ERP.*predicate"):
                load_enterprise_source_bundle(path)

    def test_http_transport_is_get_only_and_reads_token_from_environment(self) -> None:
        from ontology_poc_generator.enterprise_sources import (
            load_enterprise_source_bundle,
        )

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        erp_payload = json.loads((MANIFEST.parent / "erp.json").read_text(encoding="utf-8"))
        request_log: list[object] = []

        def opener(request, *, timeout):
            request_log.append((request, timeout))
            return FakeResponse(erp_payload)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in manifest["sources"]:
                if item["system"] == "ERP":
                    item.update(
                        {
                            "transport": "http_json",
                            "location": "https://erp.example/quality-records",
                            "token_env": "ERP_READ_TOKEN",
                        }
                    )
                else:
                    item["location"] = str(MANIFEST.parent / item["location"])
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            bundle = load_enterprise_source_bundle(
                path,
                environ={"ERP_READ_TOKEN": "secret-token"},
                opener=opener,
            )

        request, timeout = request_log[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        redirected = HTTPRedirectHandler().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://other.example/quality-records",
        )
        self.assertIsNone(redirected.get_header("Authorization"))
        self.assertEqual(timeout, 30)
        self.assertNotIn("secret-token", json.dumps(bundle))

    def test_http_transport_only_reads_the_system_specific_token(self) -> None:
        from ontology_poc_generator.enterprise_sources import (
            EnterpriseSourceError,
            load_enterprise_source_bundle,
        )

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for item in manifest["sources"]:
            if item["system"] == "ERP":
                item.update(
                    {
                        "transport": "http_json",
                        "location": "https://erp.example/quality-records",
                        "token_env": "UNRELATED_SECRET",
                    }
                )
            else:
                item["location"] = str(MANIFEST.parent / item["location"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(EnterpriseSourceError, "ERP_READ_TOKEN"):
                load_enterprise_source_bundle(
                    path,
                    environ={"UNRELATED_SECRET": "must-not-be-read"},
                    opener=lambda *_args, **_kwargs: None,
                )

    def test_record_order_does_not_change_source_or_bundle_hashes(self) -> None:
        from ontology_poc_generator.enterprise_sources import (
            load_enterprise_source_bundle,
        )

        first = load_enterprise_source_bundle(MANIFEST)
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in manifest["sources"]:
                source = json.loads(
                    (MANIFEST.parent / item["location"]).read_text(encoding="utf-8")
                )
                source["records"] = list(reversed(source["records"]))
                (root / item["location"]).write_text(
                    json.dumps(source), encoding="utf-8"
                )
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            second = load_enterprise_source_bundle(path)

        self.assertEqual(first["sources"], second["sources"])
        self.assertEqual(first["content_hash"], second["content_hash"])


if __name__ == "__main__":
    unittest.main()
