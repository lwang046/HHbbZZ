"""Boundary and migration checks for downstream jet selection."""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as Object

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from jet_selection import select_jets, choose_pair, dijet_mass


def jet(pt=30., eta=0., phi=0., mass=0., jetId=2, score=0.5):
    return Object(pt=pt, eta=eta, phi=phi, mass=mass, jetId=jetId, score=score)


class JetSelectionTest(unittest.TestCase):
    def test_threshold_migration_and_zero_one_jet(self):
        jets = [jet(pt=20.), jet(pt=21.), jet(eta=2.4)]
        self.assertEqual(select_jets(jets, []), [1])
        self.assertEqual(select_jets(jets, [], pt_min=19., eta_max=2.5), [0, 1, 2])
        self.assertEqual(select_jets([], []), [])
        self.assertEqual(choose_pair(jets, [1]), [1])

    def test_cleaning_wraps_phi_and_can_change_radius(self):
        jets = [jet(phi=math.pi-0.1), jet(eta=0.4)]
        leptons = [Object(eta=0., phi=-math.pi+0.1), Object(eta=0., phi=0.)]
        self.assertEqual(select_jets(jets, leptons), [1])
        self.assertEqual(select_jets(jets, leptons, clean_dr=0.1), [0, 1])

    def test_id_and_btag_pairing(self):
        jets = [jet(jetId=0), jet(jetId=2, score=0.7),
                jet(jetId=6, score=0.9), jet(jetId=6, score=0.9)]
        self.assertEqual(select_jets(jets, [], id_mask=6), [2, 3])
        self.assertEqual(choose_pair(jets, select_jets(jets, [])), [2, 3])

    def test_mass_and_kinematic_variation(self):
        self.assertAlmostEqual(dijet_mass(jet(pt=40.), jet(pt=40., phi=math.pi)), 80.)
        nominal = [jet(pt=19.), jet(pt=40., phi=math.pi)]
        shifted = [jet(pt=21.), nominal[1]]
        self.assertEqual(len(select_jets(nominal, [])), 1)
        self.assertEqual(len(select_jets(shifted, [])), 2)


if __name__ == '__main__':
    unittest.main()
