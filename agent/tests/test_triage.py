import unittest

from snapcal.triage_schema import TriageCandidate, validate


class TriageSchemaTests(unittest.TestCase):
    def test_review_without_quotes_is_downgraded(self):
        candidate = TriageCandidate.from_dict({"kind": "review", "confidence": .9})
        self.assertEqual(candidate.kind, "insufficient_context")

    def test_confidence_is_clamped(self):
        candidate = TriageCandidate.from_dict({"kind": "unrelated", "confidence": 9})
        self.assertEqual(candidate.confidence, 1.0)

    def test_keeps_verbatim_statement(self):
        candidate = TriageCandidate.from_dict({
            "kind": "review", "confidence": .7,
            "observable_statements": [{
                "category": "document_control", "quote": "They kept my passport",
                "explanation": "Direct statement",
            }],
        })
        self.assertEqual(candidate.observable_statements[0].quote, "They kept my passport")

    def test_protective_language_cannot_trigger_review(self):
        candidate = TriageCandidate.from_dict({
            "kind": "review", "confidence": .9,
            "observable_statements": [{
                "category": "document_control", "quote": "Your passport or ID stays with you.",
                "explanation": "Model chose the wrong category",
            }],
        })
        validate(candidate)
        self.assertEqual(candidate.kind, "unrelated")
        self.assertEqual(candidate.observable_statements, [])

    def test_adverse_direct_statement_survives_validation(self):
        candidate = TriageCandidate.from_dict({
            "kind": "review", "confidence": .8,
            "observable_statements": [{
                "category": "movement_restriction", "quote": "They say I cannot leave.",
                "explanation": "Direct first-person statement",
            }],
        })
        validate(candidate)
        self.assertEqual(candidate.kind, "review")
        self.assertEqual(len(candidate.observable_statements), 1)


if __name__ == "__main__":
    unittest.main()
