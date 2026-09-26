"""Unit and integration tests for the NOVA-VoV architecture."""

import unittest
from veritas.nova.certificate import (
    AsymmetricCertificateFalsifier,
    make_arithmetic_certificate,
    make_path_safety_certificate,
)
from veritas.nova.entropy_gate import EpistemicEntropyGate
from veritas.nova.rh_vov import RHVoVInputs, decide, position_aware_impact
from veritas.nova.nova_scheduler import NOVAVoVScheduler


class TestEpistemicEntropyGate(unittest.TestCase):
    def test_fallback_entropy_computation(self):
        # Force fallback by pointing to an unreachable endpoint
        eeg = EpistemicEntropyGate(tau_entropy=0.5, base_url="http://127.0.0.1:0")
        # Identical characters have zero entropy
        skip, h = eeg.should_skip_verification("aaaa")
        self.assertAlmostEqual(h, 0.0, places=4)
        self.assertTrue(skip)

        # Diverse characters have high entropy
        skip2, h2 = eeg.should_skip_verification("The quick brown fox jumps over 123456")
        self.assertGreater(h2, 0.5)
        self.assertFalse(skip2)


class TestRecedingHorizonVoV(unittest.TestCase):
    def test_position_aware_impact_weighting(self):
        # Step 0 of 5 has more cascade potential than step 4 of 5
        imp_early = position_aware_impact(base_impact=0.4, step_index=0, total_steps=5, beta=1.0)
        imp_late = position_aware_impact(base_impact=0.4, step_index=4, total_steps=5, beta=1.0)
        self.assertGreater(imp_early, imp_late)

    def test_hard_critical_decision(self):
        inp = RHVoVInputs(
            p_error=0.1,
            base_impact=0.1,
            detection_rate=0.9,
            false_positive_rate=0.05,
            residual_loss=0.2,
            verification_cost=0.03,
            hard_critical=True,
        )
        res = decide(inp)
        self.assertTrue(res.should_verify)


class TestAsymmetricCertificateFalsification(unittest.TestCase):
    def setUp(self):
        self.acf = AsymmetricCertificateFalsifier()

    def test_correct_arithmetic_produces_no_certificate(self):
        cert = make_arithmetic_certificate("48 / 2", 24.0)
        self.assertIsNone(cert)

    def test_faulty_arithmetic_proves_contradiction(self):
        cert = make_arithmetic_certificate("48 / 2 + 10", 24.0)
        self.assertIsNotNone(cert)
        res = self.acf.adjudicate(cert)
        self.assertTrue(res.proven)
        self.assertFalse(res.overruled)

    def test_path_traversal_certificate(self):
        cert = make_path_safety_certificate("../secret/keys.env")
        self.assertIsNotNone(cert)
        res = self.acf.adjudicate(cert)
        self.assertTrue(res.proven)


class TestNOVAVoVScheduler(unittest.TestCase):
    def test_scheduler_lifecycle(self):
        sched = NOVAVoVScheduler()
        # Normal step
        rec = {
            "action_id": "step_1",
            "action_class": "math.calc",
            "tool": "math.calc",
            "action_text": "math.calc.eval(48 / 2=24.0)",
            "impact": 0.2,
            "calibrated_error_probability": 0.05,
            "verification_cost": 0.03,
            "step_index": 0,
            "total_steps": 2,
            "expression": "48 / 2",
            "target": 24.0,
            "arguments": {"expression": "48 / 2", "target": 24.0},
        }
        dec = sched.select(rec, remaining_budget=0.24, total_budget=0.24)
        self.assertFalse(dec.selected)

        # Faulty step
        rec_fault = dict(rec)
        rec_fault["hard_critical"] = True
        rec_fault["expression"] = "48 / 2 + 10"
        rec_fault["arguments"] = {"expression": "48 / 2 + 10", "target": 24.0}
        dec_fault = sched.select(rec_fault, remaining_budget=0.24, total_budget=0.24)
        self.assertTrue(dec_fault.selected)
        self.assertTrue(sched.increment_replan())


if __name__ == "__main__":
    unittest.main()
