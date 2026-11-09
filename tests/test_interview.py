from __future__ import annotations

import json
import unittest

from lae_simulator.simulation.interview import (
    FixedResponseGenerator,
    GeneratedAnswer,
    InterviewService,
    Statement,
)


def package() -> bytes:
    return json.dumps({"actor_id": "A", "background": [], "perceptions": [
        {"event_id": "PER-1", "experience_kind": "direct-experience",
         "perception": {"action": "opened file src/a.py"}},
        {"event_id": "PER-2", "experience_kind": "misunderstanding",
         "perception": {"belief": "I thought src/a.py was the entry point"}},
    ], "belief_history": [], "memory": {"omissions": ["unobserved notifications"]}},
        sort_keys=True).encode()


def response(text: str, value: str, *, kind: str = "experience", support: tuple[str, ...] = ("PER-1",),
             topic: str | None = "opened-file", episode: str | None = None) -> GeneratedAnswer:
    return GeneratedAnswer((Statement(text, kind, support, topic, value, episode),),
                           "fixed-response", "1", "fixture")


class InterviewTests(unittest.TestCase):
    def test_leading_question_does_not_ground_new_event_and_audit_is_separate_from_publication(self) -> None:
        service = InterviewService(package(), FixedResponseGenerator((
            response("opened file src/a.py", "src/a.py"),
        )), actor_id="A")
        result = service.ask("Q1", "Why did you deploy the secret fix yesterday?")
        self.assertEqual(result.status, "accepted")
        self.assertNotIn("yesterday", result.answer or "")
        audit = service.audit_records()
        publication = service.publication(result)
        self.assertIn(b"PER-1", audit)
        self.assertIn(b"secret fix", audit)  # question text is retained for traceability
        self.assertNotIn(b"PER-1", publication)
        self.assertNotIn(b"secret fix", publication)

    def test_unsupported_claim_is_audited_but_never_published(self) -> None:
        service = InterviewService(package(), FixedResponseGenerator((
            response("I deployed the fix yesterday.", "yesterday"),
        )), actor_id="A")
        result = service.ask("Q1", "You deployed it yesterday, right?")
        self.assertEqual(result.status, "inconclusive")
        self.assertEqual(result.audit["decision"], "NEEDS_REVIEW")
        self.assertIsNone(result.answer)
        self.assertIn(b"deployed the fix", service.audit_records())
        self.assertNotIn(b"deployed the fix", service.publication(result))

    def test_rephrased_contradiction_is_rejected(self) -> None:
        service = InterviewService(package(), FixedResponseGenerator((
            response("opened file src/a.py", "src/a.py"),
            response("I opened src/b.py.", "src/b.py"),
        )), actor_id="A")
        self.assertEqual(service.ask("Q1", "Which file did you open?").status, "accepted")
        second = service.ask("Q2", "Can you restate which file you opened?")
        self.assertEqual(second.status, "rejected")
        self.assertIn(b"contradiction", service.audit_records())
        self.assertNotIn(b"src/b.py", service.publication(second))

    def test_fixed_misunderstanding_and_unknown_are_supported_kinds(self) -> None:
        service = InterviewService(package(), FixedResponseGenerator((
            response("I thought src/a.py was the entry point", "src/a.py", kind="misunderstanding",
                     support=("PER-2",), topic="belief"),
            GeneratedAnswer((Statement("I do not remember why.", "not_remembered"),),
                            "fixed-response", "1", "fixture"),
        )), actor_id="A")
        self.assertEqual(service.ask("Q1", "What did you think?").status, "accepted")
        self.assertEqual(service.ask("Q2", "Why?").status, "accepted")

    def test_wrong_actor_package_is_unavailable(self) -> None:
        with self.assertRaisesRegex(ValueError, "^unavailable$"):
            InterviewService(package(), FixedResponseGenerator(()), actor_id="OTHER")


class InterviewBoundaryTests(unittest.TestCase):
    def service(self, answers: tuple[GeneratedAnswer, ...]) -> InterviewService:
        return InterviewService(package(), FixedResponseGenerator(answers), actor_id="A", run_id="RUN")

    def test_rejected_answer_cannot_poison_accepted_history(self) -> None:
        service = self.service((response("I opened src/b.py.", "src/b.py"),
                                response("opened file src/a.py", "src/a.py")))
        self.assertEqual(service.ask("Q1", "Where?").status, "inconclusive")
        self.assertEqual(service.ask("Q2", "Where really?").status, "accepted")
        self.assertNotIn(b"src/b.py", service.public_history())
        self.assertIn(b"src/b.py", service.audit_records())
        self.assertEqual(len(json.loads(service.audit_records())["attempts"]), 2)

    def test_substring_value_is_not_semantic_proof(self) -> None:
        service = self.service((response("src/a.py caused yesterday's secret outage", "src/a.py"),))
        result = service.ask("Q", "What caused it?")
        self.assertEqual(result.status, "inconclusive")
        self.assertIsNone(result.answer)
        self.assertEqual(result.audit["checks"][0]["semantics"], "NEEDS_REVIEW")  # type: ignore[index]
        self.assertNotIn(b"outage", service.public_history())

    def test_unknown_label_does_not_authorize_fabricated_fact(self) -> None:
        service = self.service((GeneratedAnswer((Statement("I do not know, but I deployed yesterday", "unknown"),), "fixed", "1", "fixture"),))
        self.assertEqual(service.ask("Q", "Tell me?").status, "inconclusive")

    def test_invalid_support_id_and_private_ids_in_text_are_blocked_separately(self) -> None:
        service = self.service((response("opened file src/a.py", "src/a.py", support=("OTHER",)),
                                response("PER-1 opened file src/a.py", "src/a.py")))
        self.assertEqual(service.ask("Q1", "?").status, "rejected")
        second = service.ask("Q2", "?")
        self.assertEqual(second.status, "rejected")
        self.assertEqual(second.audit["checks"][0]["disclosure"], "FAIL")  # type: ignore[index]

    def test_unknown_memory_and_inference_remain_distinct(self) -> None:
        service = self.service((GeneratedAnswer((Statement("不明です。", "unknown"),), "f", "1", "fixture"),
                                GeneratedAnswer((Statement("覚えていません。", "not_remembered"),), "f", "1", "fixture"),
                                response("たぶんsrc/a.pyを選んだと思います。", "src/a.py", kind="inference")))
        self.assertEqual(service.ask("Q1", "?").epistemic_kinds, ("unknown",))
        self.assertEqual(service.ask("Q2", "?").epistemic_kinds, ("not_remembered",))
        self.assertEqual(service.ask("Q3", "?").status, "inconclusive")

    def test_empty_answer_is_unanswerable_and_exception_is_failure(self) -> None:
        service = self.service((GeneratedAnswer((), "f", "1", "fixture"),))
        self.assertEqual(service.ask("Q", "?").status, "unanswerable")

    def test_mutation_of_generator_input_and_returned_audit_does_not_change_package(self) -> None:
        class Mutating(FixedResponseGenerator):
            def generate(self, *, question: str, package: dict[str, object],
                         retrieved: tuple[dict[str, object], ...], prompt_version: str) -> GeneratedAnswer:
                package.clear()
                return super().generate(question=question, package=package, retrieved=retrieved, prompt_version=prompt_version)
        service = InterviewService(package(), Mutating(()), actor_id="A")
        first = service.ask("Q1", "?")
        first.audit.clear()
        second = service.ask("Q2", "?")
        self.assertEqual(second.status, "accepted")
        self.assertEqual(len(json.loads(service.audit_records())["attempts"]), 2)
        self.assertIn("package_digest", json.loads(service.audit_records())["attempts"][0])

    def test_fixed_records_from_distinct_episodes_are_not_forced_to_first_value(self) -> None:
        data = json.loads(package())
        data["perceptions"].append({"event_id": "PER-3", "experience_kind": "direct-experience",
                                    "perception": {"action": "opened file src/b.py"}})
        service = InterviewService(json.dumps(data).encode(), FixedResponseGenerator((
            response("opened file src/a.py", "src/a.py"),
            response("opened file src/b.py", "src/b.py", support=("PER-3",)),
        )), actor_id="A")
        self.assertEqual(service.ask("Q1", "Which?").status, "accepted")
        self.assertEqual(service.ask("Q2", "Which again?").status, "accepted")

class ReviewRegressionTests(unittest.TestCase):
    def test_same_episode_cannot_be_reassigned_using_two_literal_quotes(self) -> None:
        data = json.loads(package())
        data["perceptions"].append({"event_id":"PER-3", "experience_kind":"direct-experience",
                                    "perception":{"action":"opened file src/b.py"}})
        service = InterviewService(json.dumps(data).encode(), FixedResponseGenerator((
            response("opened file src/a.py", "src/a.py", episode="PER-1"),
            response("opened file src/b.py", "src/b.py", support=("PER-3",), episode="PER-1"),
        )), actor_id="A")
        self.assertEqual(service.ask("Q1", "?").status, "accepted")
        second = service.ask("Q2", "?")
        self.assertEqual(second.status, "rejected")
        self.assertEqual(second.audit["checks"][0]["cross_question"], "FAIL")  # type: ignore[index]
        self.assertNotIn(b"src/b.py", service.public_history())

    def test_unknown_episode_is_not_literal_entailment_proof(self) -> None:
        service = InterviewService(package(), FixedResponseGenerator((
            response("opened file src/a.py", "src/a.py", episode="invented-episode"),
        )), actor_id="A")
        self.assertEqual(service.ask("Q", "?").status, "inconclusive")

    def test_structural_private_alias_in_literal_quote_is_withheld(self) -> None:
        data = json.loads(package())
        data["belief_history"] = [{"event_id":"PER-5", "claim_id":"private-belief-17",
            "statement":"Claim private-belief-17 changed to tentative.", "epistemic_kind":"interpretation"}]
        service = InterviewService(json.dumps(data).encode(), FixedResponseGenerator((
            response("Claim private-belief-17 changed to tentative.", "tentative", kind="interpretation", support=("PER-5",)),
        )), actor_id="A")
        self.assertEqual(service.ask("Q", "?").status, "rejected")
        self.assertNotIn(b"private-belief-17", service.public_history())

    def test_fixed_ambiguous_memory_and_literal_inference_are_preserved(self) -> None:
        data = json.loads(package())
        data["belief_history"] = [{"event_id":"PER-6", "statement":"入口はaかbか、記憶が曖昧です。", "epistemic_kind":"interpretation"},
                                  {"event_id":"PER-7", "statement":"aだったのではないかと推測します。", "epistemic_kind":"inference"}]
        service = InterviewService(json.dumps(data).encode(), FixedResponseGenerator((
            GeneratedAnswer((Statement("入口はaかbか、記憶が曖昧です。", "interpretation", ("PER-6",)),), "fixed", "2", "fixture"),
            GeneratedAnswer((Statement("aだったのではないかと推測します。", "inference", ("PER-7",)),), "fixed", "2", "fixture"),
        )), actor_id="A")
        self.assertEqual(service.ask("Q1", "?").status, "accepted")
        self.assertEqual(service.ask("Q2", "?").epistemic_kinds, ("inference",))

    def test_different_claim_items_on_same_evidence_are_not_false_contradictions(self) -> None:
        data = json.loads(package())
        text = "opened file src/a.py after searching metadata"
        data["perceptions"][0]["perception"]["action"] = text
        for first_topic, second_topic in (("opened-file", "search-term"), (None, None), ("opened-file", None)):
            with self.subTest(topics=(first_topic, second_topic)):
                service = InterviewService(json.dumps(data).encode(), FixedResponseGenerator((
                    response(text, "src/a.py", topic=first_topic, episode="PER-1"),
                    response(text, "metadata", topic=second_topic, episode="PER-1"),
                )), actor_id="A")
                self.assertEqual(service.ask("Q1", "?").status, "accepted")
                second = service.ask("Q2", "?")
                self.assertEqual(second.status, "inconclusive")
                self.assertFalse(second.audit["checks"][0]["contradiction"])  # type: ignore[index]
                self.assertEqual(second.audit["checks"][0]["cross_question"], "UNKNOWN")  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
