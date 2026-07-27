from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .errors import invalid
from .models import list_value, object_value, string_value


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"proposal-{digest}"


def _condition_matches(condition: dict[str, Any], values: dict[str, Any]) -> bool:
    return all(
        values.get(key, "unknown") == expected for key, expected in condition.items()
    )


class PlanningRules:
    """Deterministic expansion of semantic graph differences into plan drafts."""

    def __init__(self, rules_path: str | Path) -> None:
        self.rules_path = Path(rules_path)
        try:
            document = yaml.safe_load(self.rules_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise invalid(f"无法加载规划规则: {error}") from error
        self.document = object_value(document, "rules document")
        self.version = string_value(self.document.get("version"), "rules.version")
        self.rule_set = string_value(self.document.get("ruleSet"), "rules.ruleSet")
        self.defaults = object_value(
            self.document.get("defaults", {}), "rules.defaults"
        )
        self.rules = list_value(
            self.document.get("rules"), "rules.rules", nonempty=True
        )
        self._validate_rules()

    def _validate_rules(self) -> None:
        seen: set[str] = set()
        for index, rule_value in enumerate(self.rules):
            rule = object_value(rule_value, f"rules.rules[{index}]")
            rule_id = string_value(rule.get("id"), f"rules.rules[{index}].id")
            if rule_id in seen:
                raise invalid(f"规划规则 ID 重复: {rule_id}")
            seen.add(rule_id)
            object_value(rule.get("when"), f"rules.rules[{index}].when")
            object_value(rule.get("then"), f"rules.rules[{index}].then")

    def expand(
        self,
        difference_value: Any,
        context_value: Any | None = None,
    ) -> dict[str, Any]:
        difference = object_value(difference_value, "difference")
        if not difference:
            raise invalid("difference 不能为空")
        context = (
            object_value(context_value, "context") if context_value is not None else {}
        )
        values = {**context, **difference}
        difference_id = str(
            difference.get("differenceId")
            or difference.get("id")
            or hashlib.sha256(
                json.dumps(
                    difference,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()[:16]
        )
        evidence_refs = difference.get("evidenceRefs", [])
        if not isinstance(evidence_refs, list):
            raise invalid("difference.evidenceRefs 必须是数组")

        matched_rules: list[str] = []
        proposals: list[dict[str, Any]] = []
        assessments: list[str] = []
        alignment_searches: list[dict[str, Any]] = []
        unresolved_questions: list[dict[str, Any]] = []
        review_reasons: list[dict[str, Any]] = []
        missing_properties: list[str] = []

        for rule_value in self.rules:
            rule = dict(rule_value)
            when = object_value(rule["when"], f"rule {rule['id']}.when")
            if not all(values.get(key) == expected for key, expected in when.items()):
                continue

            rule_id = str(rule["id"])
            matched_rules.append(rule_id)
            then = object_value(rule["then"], f"rule {rule_id}.then")
            for index, proposal_value in enumerate(then.get("proposals", [])):
                proposal = object_value(
                    proposal_value, f"rule {rule_id}.then.proposals[{index}]"
                )
                change_type = string_value(
                    proposal.get("type"),
                    f"rule {rule_id}.then.proposals[{index}].type",
                )
                role = string_value(
                    proposal.get("role"),
                    f"rule {rule_id}.then.proposals[{index}].role",
                )
                proposals.append(
                    {
                        "proposalId": _stable_id(
                            self.version, rule_id, difference_id, str(index)
                        ),
                        "category": "Required",
                        "changeType": change_type,
                        "role": role,
                        "targetCurrentEntityId": difference.get("currentEntityId"),
                        "desiredEntityId": difference.get("desiredEntityId"),
                        "reason": rule.get("description", rule_id),
                        "evidenceRefs": evidence_refs,
                        "derivedByRule": rule_id,
                        "dependsOn": [],
                        "humanGate": None,
                    }
                )
            for assessment in then.get("assessments", []):
                if assessment not in assessments:
                    assessments.append(str(assessment))
            if "alignmentSearch" in then:
                alignment_searches.append(
                    {
                        "ruleId": rule_id,
                        **object_value(
                            then["alignmentSearch"],
                            f"rule {rule_id}.then.alignmentSearch",
                        ),
                    }
                )
            for decision_value in then.get("decisions", []):
                decision = object_value(
                    decision_value, f"rule {rule_id}.then.decisions"
                )
                conditions = decision.get("requiredWhen", [])
                if not conditions or any(
                    _condition_matches(object_value(item, "requiredWhen"), values)
                    for item in conditions
                ):
                    unresolved_questions.append(
                        {
                            "ruleId": rule_id,
                            "question": string_value(
                                decision.get("question"), "decision.question"
                            ),
                        }
                    )

            for property_name in then.get("requiredDesignProperties", []):
                if (
                    values.get(property_name) is None or values.get(property_name) == ""
                ) and property_name not in missing_properties:
                    missing_properties.append(str(property_name))

            review_policy = then.get("reviewPolicy", {})
            if review_policy:
                conditions = object_value(
                    review_policy, f"rule {rule_id}.then.reviewPolicy"
                ).get("requiredWhen", [])
                for condition_value in conditions:
                    condition = object_value(
                        condition_value, "reviewPolicy.requiredWhen"
                    )
                    if _condition_matches(condition, values):
                        review_reasons.append(
                            {"ruleId": rule_id, "condition": condition}
                        )

        if missing_properties:
            unresolved_questions.append(
                {
                    "ruleId": "REQUIRED-DESIGN-PROPERTIES",
                    "question": "补全规划所需设计属性",
                    "missingProperties": missing_properties,
                }
            )

        human_review_required = bool(review_reasons or unresolved_questions)
        if human_review_required:
            for proposal in proposals:
                proposal["humanGate"] = "ArchitectureReview"

        return {
            "ruleSet": self.rule_set,
            "ruleSetVersion": self.version,
            "differenceId": difference_id,
            "matchedRules": matched_rules,
            "proposals": proposals,
            "assessments": assessments,
            "alignmentSearches": alignment_searches,
            "humanReviewRequired": human_review_required,
            "reviewReasons": review_reasons,
            "missingDesignProperties": missing_properties,
            "unresolvedQuestions": unresolved_questions,
        }
