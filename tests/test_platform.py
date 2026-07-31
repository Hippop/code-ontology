from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from code_ontology_platform.errors import PlatformError
from code_ontology_platform.graph_baseline import (
    compare_graph_baseline,
    load_graph_baseline,
)
from code_ontology_platform.http_api import handler_for
from code_ontology_platform.models import GRAPH_SPACES
from code_ontology_platform.repository_scan import RepositoryScanner
from code_ontology_platform.semantic_validation import validate_semantic_assets
from code_ontology_platform.service import PlatformService
from code_ontology_platform.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "requirement-change-planning-rules.yaml"
JAVA_SAMPLE = ROOT / "examples" / "java-spring-sample"
DESIGN_SAMPLE = ROOT / "examples" / "designs" / "sdn-minimum-bandwidth.md"
EXPECTED_JAVA_GRAPH = (
    ROOT / "examples" / "expected-graphs" / "java-spring-sample.current.graph.json"
)


class PlatformServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        database = Path(self.temporary_directory.name) / "test.db"
        self.service = PlatformService(SQLiteStore(database), RULES)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_requirement_context_is_bound_to_exact_stage_and_revision(self) -> None:
        context = self.service.put_requirement_context(
            "REQ-1",
            "DESIGN-1",
            "plan",
            {
                "approvalState": "AlignmentConfirmed",
                "allowedActions": ["CreateDraft"],
                "requirementId": "REQ-ATTEMPTED-OVERRIDE",
                "stage": "implement",
                "contextHash": "untrusted",
            },
        )

        loaded = self.service.requirement_context("REQ-1", "DESIGN-1", "plan")
        self.assertEqual(context, loaded)
        self.assertEqual("REQ-1", loaded["requirementId"])
        self.assertEqual("plan", loaded["stage"])
        self.assertTrue(loaded["contextHash"].startswith("sha256:"))

        with self.assertRaises(PlatformError) as raised:
            self.service.requirement_context("REQ-1", "DESIGN-1", "implement")
        self.assertEqual(404, raised.exception.status)

    def test_graph_query_is_read_only_and_does_not_cross_graph_spaces(self) -> None:
        self.service.replace_graph(
            "current",
            "commit-abc",
            [
                {"id": "controller", "type": "Class"},
                {"id": "service", "type": "Class"},
                {"id": "repository", "type": "Class"},
            ],
            [
                {
                    "source": "controller",
                    "relation": "code:callsDirectly",
                    "target": "service",
                },
                {
                    "source": "service",
                    "relation": "code:callsDirectly",
                    "target": "repository",
                },
            ],
        )
        self.service.replace_graph(
            "desired",
            "design-1",
            [{"id": "desired-only", "type": "DesiredCodeRole"}],
            [],
        )

        result = self.service.graph_query(
            {
                "graphSpace": "current",
                "queryType": "CALL_PATH",
                "entityId": "controller",
                "targetEntityId": "repository",
                "revision": "commit-abc",
                "depth": 2,
                "limit": 20,
            }
        )

        self.assertEqual(
            ["controller", "repository", "service"],
            [node["id"] for node in result["nodes"]],
        )
        self.assertEqual([["controller", "service", "repository"]], result["paths"])
        self.assertNotIn("desired-only", json.dumps(result))
        overview = self.service.graph_query(
            {
                "graphSpace": "current",
                "queryType": "GRAPH_OVERVIEW",
                "revision": "commit-abc",
                "entityTypes": ["Class"],
                "search": "service",
                "limit": 20,
            }
        )
        self.assertEqual(["service"], [node["id"] for node in overview["nodes"]])
        self.assertEqual(3, overview["summary"]["totalNodes"])
        self.assertEqual(2, overview["summary"]["totalEdges"])
        self.assertEqual([], overview["paths"])

    def test_graph_publish_dual_writes_database_and_text_snapshot(self) -> None:
        nodes = [
            {"id": "service", "type": "Class", "label": "PolicyService"},
            {"id": "controller", "type": "Class", "label": "PolicyController"},
        ]
        edges = [
            {
                "source": "controller",
                "relation": "code:callsDirectly",
                "target": "service",
            }
        ]
        text_snapshot = self.service.replace_graph(
            "current",
            "commit:text/snapshot",
            list(reversed(nodes)),
            edges,
            metadata={"graphId": "urn:graph:current:text"},
        )

        self.assertIsNotNone(text_snapshot)
        self.assertEqual("application/json", text_snapshot["format"])
        self.assertTrue(text_snapshot["relativePath"].endswith(".graph.json"))
        document = self.service.store.read_graph_text_snapshot(
            "current", "commit:text/snapshot"
        )
        self.assertEqual(
            ["controller", "service"],
            [node["id"] for node in document["nodes"]],
        )
        self.assertEqual(2, document["summary"]["nodeCount"])
        self.assertEqual(1, document["summary"]["edgeCount"])
        database_nodes, database_edges = self.service.store.read_graph(
            "current", "commit:text/snapshot"
        )
        self.assertEqual(database_nodes, document["nodes"])
        self.assertEqual(database_edges, document["edges"])
        catalog = self.service.graph_catalog("current")
        self.assertEqual(
            text_snapshot,
            catalog["revisions"][0]["metadata"]["textSnapshot"],
        )

        path = self.service.store.graph_text_root / text_snapshot["relativePath"]
        first_bytes = path.read_bytes()
        self.service.replace_graph(
            "current",
            "commit:text/snapshot",
            nodes,
            edges,
            metadata={"graphId": "urn:graph:current:text"},
        )
        self.assertEqual(first_bytes, path.read_bytes())
        for graph_space in GRAPH_SPACES - {"current"}:
            other_snapshot = self.service.replace_graph(
                graph_space,
                f"{graph_space}-text-revision",
                [{"id": f"{graph_space}:entity", "type": "GraphEntity"}],
                [],
            )
            self.assertTrue(
                (
                    self.service.store.graph_text_root / other_snapshot["relativePath"]
                ).is_file()
            )

        tampered = json.loads(path.read_text(encoding="utf-8"))
        tampered["nodes"][0]["label"] = "Tampered"
        path.write_text(
            json.dumps(tampered, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with self.assertRaises(PlatformError) as raised:
            self.service.store.read_graph_text_snapshot(
                "current", "commit:text/snapshot"
            )
        self.assertEqual("GRAPH_TEXT_INTEGRITY_ERROR", raised.exception.code)

    def test_graph_compare_returns_entity_relation_and_field_differences(self) -> None:
        self.service.replace_graph(
            "current",
            "base-1",
            [
                {"id": "service", "type": "Class", "label": "Policy", "version": 1},
                {"id": "legacy", "type": "Class", "label": "Legacy"},
            ],
            [
                {
                    "source": "service",
                    "relation": "code:callsDirectly",
                    "target": "legacy",
                }
            ],
        )
        self.service.replace_graph(
            "actual",
            "target-1",
            [
                {"id": "service", "type": "Class", "label": "Policy", "version": 2},
                {"id": "replacement", "type": "Class", "label": "Replacement"},
            ],
            [
                {
                    "source": "service",
                    "relation": "code:callsDirectly",
                    "target": "replacement",
                }
            ],
        )

        result = self.service.graph_compare(
            {
                "base": {"graphSpace": "current", "revision": "base-1"},
                "target": {"graphSpace": "actual", "revision": "target-1"},
                "limit": 20,
            }
        )

        self.assertEqual(1, result["summary"]["nodeChanges"]["Added"])
        self.assertEqual(1, result["summary"]["nodeChanges"]["Removed"])
        self.assertEqual(1, result["summary"]["nodeChanges"]["Modified"])
        self.assertEqual(1, result["summary"]["edgeChanges"]["Added"])
        self.assertEqual(1, result["summary"]["edgeChanges"]["Removed"])
        self.assertEqual(
            ["version"],
            [
                change["field"]
                for change in result["fieldChanges"]
                if change["entityId"] == "service"
            ],
        )
        self.assertEqual(
            {"Added", "Removed", "Modified"},
            {node["changeStatus"] for node in result["nodes"]},
        )
        filtered = self.service.graph_compare(
            {
                "base": {"graphSpace": "current", "revision": "base-1"},
                "target": {"graphSpace": "actual", "revision": "target-1"},
                "changeStatuses": ["Modified"],
                "entityTypes": ["Class"],
                "search": "policy",
                "limit": 20,
            }
        )
        self.assertEqual(["service"], [node["id"] for node in filtered["nodes"]])
        self.assertEqual([], filtered["edges"])

        self.service.replace_graph(
            "current",
            "snapshot-base",
            [
                {
                    "id": "stable",
                    "type": "Class",
                    "revision": "commit-a",
                    "evidence": {
                        "source": "src/Stable.java",
                        "sourceHash": "sha256:same",
                        "revision": "commit-a",
                    },
                }
            ],
            [
                {
                    "source": "stable",
                    "relation": "code:declaredIn",
                    "target": "stable",
                    "revision": "commit-a",
                }
            ],
        )
        self.service.replace_graph(
            "actual",
            "snapshot-target",
            [
                {
                    "id": "stable",
                    "type": "Class",
                    "revision": "commit-a+workspace:patch",
                    "evidence": {
                        "source": "src/Stable.java",
                        "sourceHash": "sha256:same",
                        "revision": "commit-a+workspace:patch",
                    },
                }
            ],
            [
                {
                    "source": "stable",
                    "relation": "code:declaredIn",
                    "target": "stable",
                    "revision": "commit-a+workspace:patch",
                }
            ],
        )
        snapshot_only = self.service.graph_compare(
            {
                "base": {
                    "graphSpace": "current",
                    "revision": "snapshot-base",
                },
                "target": {
                    "graphSpace": "actual",
                    "revision": "snapshot-target",
                },
            }
        )
        self.assertEqual(1, snapshot_only["summary"]["nodeChanges"]["Unchanged"])
        self.assertEqual(1, snapshot_only["summary"]["edgeChanges"]["Unchanged"])
        self.assertEqual([], snapshot_only["fieldChanges"])

    def test_candidate_write_is_idempotent_and_conflicts_are_rejected(self) -> None:
        body = {
            "runId": "run-align-1",
            "requirementId": "REQ-1",
            "status": "Candidate",
            "payload": {
                "candidates": [
                    {
                        "desiredEntityId": "desired:Evaluator",
                        "currentEntityId": "current:Evaluator",
                        "alignmentType": "ExtendExisting",
                        "confidence": 0.93,
                        "evidenceRefs": ["evidence:4.2"],
                    }
                ]
            },
        }

        first, first_replay = self.service.record_alignment_candidates(
            body, "align-key-0001"
        )
        second, second_replay = self.service.record_alignment_candidates(
            body, "align-key-0001"
        )
        self.assertFalse(first_replay)
        self.assertTrue(second_replay)
        self.assertEqual(first["artifactId"], second["artifactId"])
        self.assertEqual(
            1, len(self.service.list_artifacts("run-align-1")["artifacts"])
        )

        conflicting = json.loads(json.dumps(body))
        conflicting["payload"]["candidates"][0]["confidence"] = 0.51
        with self.assertRaises(PlatformError) as raised:
            self.service.record_alignment_candidates(conflicting, "align-key-0001")
        self.assertEqual(409, raised.exception.status)

    def test_change_plan_endpoint_cannot_write_approved_state(self) -> None:
        body = {
            "runId": "run-plan-1",
            "requirementId": "REQ-1",
            "status": "Approved",
            "payload": {
                "proposals": [
                    {
                        "proposalId": "proposal-1",
                        "changeType": "ProposedBehaviorChange",
                        "evidenceRefs": ["evidence:4.2"],
                    }
                ]
            },
        }
        with self.assertRaises(PlatformError) as raised:
            self.service.record_change_plan_draft(body, "plan-key-0001")
        self.assertEqual(400, raised.exception.status)

    def test_rules_expand_api_field_change_and_raise_human_gate(self) -> None:
        result = self.service.expand_change_plan(
            {
                "difference": {
                    "differenceId": "diff-field-1",
                    "differenceType": "AddEntityDifference",
                    "desiredEntityType": "DesiredSchemaField",
                    "desiredEntityId": "desired:minimumBandwidthMbps",
                    "evidenceRefs": ["evidence:6.1"],
                },
                "context": {
                    "fieldRequired": True,
                    "defaultMissing": True,
                    "publicContract": True,
                },
            }
        )

        self.assertEqual(["PLAN-API-SCHEMA-FIELD-ADDED"], result["matchedRules"])
        self.assertEqual(4, len(result["proposals"]))
        self.assertIn("CompatibilityAssessment", result["assessments"])
        self.assertTrue(result["humanReviewRequired"])
        self.assertTrue(
            all(
                item["humanGate"] == "ArchitectureReview"
                for item in result["proposals"]
            )
        )

    def test_java_spring_repository_scan_publishes_versioned_current_graph(
        self,
    ) -> None:
        repository = self.service.register_repository(
            {
                "repositoryId": "repo-sdn-test",
                "name": "SDN Test Service",
                "path": str(JAVA_SAMPLE),
            }
        )
        snapshot = self.service.create_repository_snapshot(
            repository["repositoryId"], {"actor": "test"}
        )
        run = self.service.scan_repository(
            repository["repositoryId"],
            {
                "snapshotId": snapshot["snapshotId"],
                "includeGraph": True,
                "actor": "test",
            },
        )

        self.assertEqual("Completed", run["status"])
        self.assertEqual(9, run["coverage"]["parsedJavaFiles"])
        self.assertEqual(0, run["coverage"]["unresolvedCallCount"])
        self.assertEqual(7, run["coverage"]["externalCallCount"])
        self.assertTrue(run["revision"])
        self.assertIsNotNone(run["graphTextSnapshot"])
        sensitive = [
            node for node in run["graph"]["nodes"] if node.get("sensitive") is True
        ]
        self.assertEqual(1, len(sensitive))
        self.assertTrue(sensitive[0]["redacted"])
        self.assertIsNone(sensitive[0].get("value"))

        table_id = "db:repo-sdn-test:table:network_policy"
        result = self.service.graph_query(
            {
                "graphSpace": "current",
                "queryType": "IMPLEMENTATION_SLICE",
                "entityId": ("api:repo-sdn-test:POST:/network-policies/{id}/deploy"),
                "targetEntityId": table_id,
                "revision": run["revision"],
                "depth": 6,
                "limit": 200,
            }
        )
        self.assertTrue(result["paths"])
        repository_paths = [
            path
            for path in result["paths"]
            if any("PolicyRepository" in entity for entity in path)
        ]
        self.assertTrue(repository_paths)
        self.assertTrue(all(path[-1] == table_id for path in repository_paths))
        event_nodes = [
            node for node in run["graph"]["nodes"] if node.get("type") == "EventType"
        ]
        self.assertEqual("network-policy-rejected", event_nodes[0]["channel"])
        self.assertTrue(
            any(
                edge["relation"] == "code:consumesEvent"
                for edge in run["graph"]["edges"]
            )
        )
        revisions = self.service.repository_graph_revisions(repository["repositoryId"])
        self.assertEqual(run["runId"], revisions["revisions"][0]["runId"])

    def test_expected_example_graph_matches_fresh_scan_and_detects_drift(
        self,
    ) -> None:
        expected = load_graph_baseline(EXPECTED_JAVA_GRAPH)
        actual = RepositoryScanner().scan(
            JAVA_SAMPLE,
            str(expected["repositoryId"]),
        )["graph"]
        comparison = compare_graph_baseline(expected, actual)

        self.assertEqual("Matched", comparison["status"])
        self.assertEqual(0, comparison["summary"]["differenceCount"])
        serialized = json.dumps(expected, ensure_ascii=False)
        self.assertNotIn(str(JAVA_SAMPLE.resolve()), serialized)
        self.assertNotIn('"revision"', serialized)

        drifted = json.loads(json.dumps(actual))
        policy_service = next(
            node
            for node in drifted["nodes"]
            if node["id"].endswith("java:org.example.sdn.PolicyService")
        )
        policy_service["label"] = "ChangedPolicyService"
        drift = compare_graph_baseline(expected, drifted)
        self.assertEqual("Drifted", drift["status"])
        self.assertEqual(1, drift["summary"]["differenceCount"])
        self.assertEqual(
            ["label"],
            drift["nodeDifferences"][0]["changedFields"],
        )

    def test_design_document_to_confirmed_requirement_and_desired_graph(
        self,
    ) -> None:
        document = self.service.create_design_document(
            {
                "documentId": "DESIGN-SDN-BW-TEST",
                "title": "Minimum bandwidth design",
                "owner": "product",
            }
        )
        revision = self.service.create_design_revision(
            document["documentId"],
            {
                "revisionNumber": "1.0",
                "content": DESIGN_SAMPLE.read_text(encoding="utf-8"),
                "actor": "product",
            },
        )
        requirement = self.service.extract_design_revision(
            revision["revisionId"], {"actor": "requirement-analyst"}
        )

        self.assertEqual("Draft", requirement["status"])
        self.assertGreaterEqual(len(requirement["ir"]["desiredEntities"]), 10)
        self.assertEqual([], requirement["ir"]["unresolvedQuestions"])
        self.assertEqual(1, len(requirement["ir"]["implementationSuggestions"]))
        desired_types = {
            item["entityType"] for item in requirement["ir"]["desiredEntities"]
        }
        self.assertIn("BusinessRule", desired_types)
        self.assertIn("BusinessProcess", desired_types)
        self.assertIn("BusinessProcessStep", desired_types)
        self.assertIn("DesiredSchemaField", desired_types)
        self.assertIn("DesiredConfigurationKey", desired_types)
        self.assertIn("DesiredEventType", desired_types)
        self.assertIn("DesiredTestObligation", desired_types)

        review = self.service.review_requirement(
            "REQ-SDN-2026-001",
            {
                "decision": "Confirm",
                "actor": "architect",
                "rationale": "业务目标、规则、失败路径和验收条件已确认。",
            },
        )
        self.assertEqual("Confirmed", review["requirement"]["status"])
        context = self.service.requirement_context(
            "REQ-SDN-2026-001", revision["revisionId"], "align"
        )
        self.assertEqual("RequirementConfirmed", context["approvalState"])
        desired = self.service.graph_query(
            {
                "graphSpace": "desired",
                "queryType": "ENTITY_NEIGHBORHOOD",
                "entityId": "requirement:REQ-SDN-2026-001",
                "revision": revision["revisionId"],
                "depth": 1,
                "limit": 100,
            }
        )
        self.assertGreaterEqual(len(desired["nodes"]), 11)
        _, desired_edges = self.service.store.read_graph(
            "desired", revision["revisionId"]
        )
        process_edges = [
            edge
            for edge in desired_edges
            if edge["relation"] in {"business:containsStep", "business:nextStep"}
        ]
        self.assertEqual(5, len(process_edges))
        business_nodes, business_edges = self.service.store.read_graph(
            "business", revision["revisionId"]
        )
        business_types = {node["type"] for node in business_nodes}
        self.assertIn("BusinessProcess", business_types)
        self.assertIn("BusinessProcessStep", business_types)
        self.assertIn("BusinessRule", business_types)
        self.assertTrue(
            any(edge["relation"] == "business:nextStep" for edge in business_edges)
        )
        catalog = self.service.graph_catalog("business")
        self.assertEqual(1, catalog["count"])
        self.assertEqual("Published", catalog["revisions"][0]["metadata"]["status"])

    def test_alignment_diff_planning_and_approval_gates(self) -> None:
        repository = self.service.register_repository(
            {
                "repositoryId": "repo-full-flow",
                "path": str(JAVA_SAMPLE),
            }
        )
        scan = self.service.scan_repository(repository["repositoryId"], {})
        document = self.service.create_design_document(
            {"documentId": "DESIGN-FULL-FLOW", "title": "Full flow design"}
        )
        revision = self.service.create_design_revision(
            document["documentId"],
            {
                "revisionNumber": "1.0",
                "content": DESIGN_SAMPLE.read_text(encoding="utf-8"),
            },
        )
        self.service.extract_design_revision(revision["revisionId"], {})
        self.service.review_requirement(
            "REQ-SDN-2026-001",
            {
                "decision": "Confirm",
                "actor": "product-architect",
                "rationale": "Requirement semantics confirmed.",
            },
        )

        alignment = self.service.create_alignment_run(
            {
                "requirementId": "REQ-SDN-2026-001",
                "repositoryId": repository["repositoryId"],
                "currentRevision": scan["revision"],
            }
        )
        self.assertEqual("Draft", alignment["status"])
        self.assertTrue(all(item["candidates"] for item in alignment["alignments"]))
        self.assertTrue(
            all(
                item["candidates"][0]["evidenceRefs"]
                for item in alignment["alignments"]
            )
        )
        for item in list(alignment["alignments"]):
            alignment = self.service.review_alignment(
                item["candidates"][0]["candidateId"],
                {
                    "decision": "Confirm",
                    "actor": "developer",
                    "rationale": "Selected after source and graph review.",
                },
            )
        self.assertEqual("Confirmed", alignment["status"])
        self.assertEqual(
            len(alignment["alignments"]),
            len(alignment["implementationSlices"]),
        )

        plan = self.service.create_change_plan(
            {
                "alignmentRunId": alignment["runId"],
                "context": {"repositoryId": repository["repositoryId"]},
            }
        )
        self.assertEqual("Draft", plan["status"])
        self.assertTrue(plan["semanticDiff"]["differences"])
        change_types = {item["changeType"] for item in plan["proposals"]}
        self.assertIn("ProposedBehaviorChange", change_types)
        self.assertIn("ProposedContractChange", change_types)
        self.assertIn("ProposedConfigurationChange", change_types)
        self.assertNotIn("ProposedDataMigration", change_types)
        self.assertIn("ProposedTestChange", change_types)
        self.assertIn("ProposedDeploymentChange", change_types)
        self.assertTrue(
            any(item["role"] == "AddMessageSchema" for item in plan["proposals"])
        )
        self.assertTrue(
            all(
                item.get("desiredEntity", {}).get("label")
                for item in plan["proposals"]
            )
        )
        self.assertTrue(
            any(
                "不新增数据库表" in item
                for item in plan["requirementContext"]["scope"]
            )
        )
        self.assertEqual(len(plan["proposals"]), len(plan["implementationTasks"]))
        proposed_nodes, proposed_edges = self.service.store.read_graph(
            "proposed", plan["planId"]
        )
        self.assertTrue(
            any(node["type"] == "DesignChangeSet" for node in proposed_nodes)
        )
        self.assertTrue(
            any(
                edge["relation"] == "plan:containsProposedChange"
                for edge in proposed_edges
            )
        )

        with self.assertRaises(PlatformError):
            self.service.approve_change_plan(
                plan["planId"],
                {
                    "actor": "change-board",
                    "rationale": "Must not skip architecture review.",
                    "allowedFiles": ["src/**"],
                    "forbiddenFiles": [".git/**"],
                    "requiredTests": ["mvn test"],
                    "securityDataApproved": True,
                },
            )
        plan = self.service.review_change_plan(
            plan["planId"],
            {
                "decision": "Accept",
                "actor": "independent-architect",
                "rationale": "Architecture and compatibility reviewed.",
                "findings": [],
            },
        )
        self.assertEqual("ArchitectureReviewed", plan["status"])
        plan = self.service.approve_change_plan(
            plan["planId"],
            {
                "actor": "change-board",
                "rationale": "All mandatory gates are satisfied.",
                "allowedFiles": ["src/main/**", "src/test/**"],
                "forbiddenFiles": [".git/**", "deploy/prod/**"],
                "requiredTests": ["mvn test"],
                "securityDataApproved": True,
            },
        )
        self.assertEqual("Approved", plan["status"])
        self.assertTrue(
            all(
                task["allowedFiles"] and task["forbiddenFiles"]
                for task in plan["implementationTasks"]
            )
        )
        approved_nodes, _ = self.service.store.read_graph("approved", plan["planId"])
        self.assertGreater(len(approved_nodes), len(plan["proposals"]))


class SemanticAssetsTest(unittest.TestCase):
    def test_all_examples_conform_to_combined_shapes(self) -> None:
        result = validate_semantic_assets(
            ontology_files=sorted((ROOT / "ontology").glob("*.ttl")),
            shape_files=sorted((ROOT / "shapes").glob("*.ttl")),
            data_files=sorted((ROOT / "examples").glob("*.ttl")),
        )

        self.assertTrue(
            result["conforms"],
            "\n\n".join(item.get("report", "") for item in result["results"]),
        )
        self.assertEqual(4, len(result["ontologyFiles"]))
        self.assertEqual(2, len(result["shapeFiles"]))
        self.assertEqual(2, len(result["results"]))


class HttpContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        database = Path(self.temporary_directory.name) / "http.db"
        self.service = PlatformService(SQLiteStore(database), RULES)
        self.service.put_requirement_context(
            "REQ-HTTP",
            "DESIGN-HTTP-1",
            "align",
            {"approvalState": "RequirementConfirmed"},
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary_directory.cleanup()

    def test_opencode_requirement_context_contract(self) -> None:
        url = (
            f"{self.base_url}/api/agent-context/requirements/REQ-HTTP"
            "?designRevisionId=DESIGN-HTTP-1&stage=align"
        )
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.loads(response.read())
        self.assertEqual("REQ-HTTP", payload["requirementId"])
        self.assertEqual("align", payload["stage"])
        self.assertEqual("RequirementConfirmed", payload["approvalState"])

    def test_graph_catalog_contract_lists_all_supported_spaces(self) -> None:
        with urllib.request.urlopen(
            f"{self.base_url}/api/graphs", timeout=2
        ) as response:
            payload = json.loads(response.read())
        self.assertIn("current", payload["graphSpaces"])
        self.assertIn("business", payload["graphSpaces"])
        self.assertIn("proposed", payload["graphSpaces"])
        self.assertEqual([], payload["revisions"])

    def test_graph_compare_and_workflow_http_routes_are_supported(self) -> None:
        self.service.replace_graph(
            "current",
            "http-base",
            [{"id": "entity", "type": "Class", "version": 1}],
            [],
        )
        self.service.replace_graph(
            "actual",
            "http-target",
            [{"id": "entity", "type": "Class", "version": 2}],
            [],
        )
        compare_request = urllib.request.Request(
            f"{self.base_url}/api/graphs/compare",
            data=json.dumps(
                {
                    "base": {
                        "graphSpace": "current",
                        "revision": "http-base",
                    },
                    "target": {
                        "graphSpace": "actual",
                        "revision": "http-target",
                    },
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(compare_request, timeout=2) as response:
            compared = json.loads(response.read())
        self.assertEqual(1, compared["summary"]["nodeChanges"]["Modified"])

        with urllib.request.urlopen(
            f"{self.base_url}/api/requirement-workflows", timeout=2
        ) as response:
            workflows = json.loads(response.read())
        self.assertEqual(0, workflows["count"])
        with self.assertRaises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(
                f"{self.base_url}/api/requirement-workflows/missing", timeout=2
            )
        self.assertEqual(404, missing.exception.code)
        self.assertNotEqual(
            "ROUTE_NOT_FOUND",
            json.loads(missing.exception.read())["error"]["code"],
        )
        retry_request = urllib.request.Request(
            f"{self.base_url}/api/requirement-workflows/missing/retry",
            data=json.dumps(
                {"actor": "operator", "rationale": "Retry failed stage."}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as missing_retry:
            urllib.request.urlopen(retry_request, timeout=2)
        self.assertEqual(404, missing_retry.exception.code)
        self.assertNotEqual(
            "ROUTE_NOT_FOUND",
            json.loads(missing_retry.exception.read())["error"]["code"],
        )

    def test_impact_analysis_design_routes_are_supported(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as get_error:
            urllib.request.urlopen(
                f"{self.base_url}/api/impact-analyses/missing-run", timeout=2
            )
        self.assertEqual(404, get_error.exception.code)
        get_payload = json.loads(get_error.exception.read())
        self.assertNotEqual("ROUTE_NOT_FOUND", get_payload["error"]["code"])
        self.assertIn("Impact Run", get_payload["error"]["message"])

        request = urllib.request.Request(
            f"{self.base_url}/api/impact-analyses",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as post_error:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(400, post_error.exception.code)
        post_payload = json.loads(post_error.exception.read())
        self.assertNotEqual("ROUTE_NOT_FOUND", post_payload["error"]["code"])

    def test_optional_bearer_token_protects_api_routes(self) -> None:
        secure_server = ThreadingHTTPServer(
            ("127.0.0.1", 0), handler_for(self.service, "test-secret")
        )
        secure_thread = threading.Thread(
            target=secure_server.serve_forever, daemon=True
        )
        secure_thread.start()
        url = (
            f"http://127.0.0.1:{secure_server.server_port}"
            "/api/agent-context/requirements/REQ-HTTP"
            "?designRevisionId=DESIGN-HTTP-1&stage=align"
        )
        try:
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(url, timeout=2)
            self.assertEqual(401, raised.exception.code)

            request = urllib.request.Request(
                url, headers={"Authorization": "Bearer test-secret"}
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.loads(response.read())
            self.assertEqual("REQ-HTTP", payload["requirementId"])
        finally:
            secure_server.shutdown()
            secure_server.server_close()
            secure_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
