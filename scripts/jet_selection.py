"""Jet-only selection on an inclusive 4l skim; no corrections are rerun."""
import argparse
import math


def select_jets(jets, cleaning_leptons, pt_min=20., eta_max=2.4,
                clean_dr=0.4, id_mask=None):
    """Return input indices. None reproduces the framework's jetId > 0."""
    selected = []
    for i, jet in enumerate(jets):
        if not (jet.pt > pt_min and abs(jet.eta) < eta_max):
            continue
        if not (jet.jetId > 0 if id_mask is None else
                (jet.jetId & id_mask) == id_mask):
            continue
        if any(math.hypot(jet.eta - lep.eta,
                          math.atan2(math.sin(jet.phi - lep.phi),
                                     math.cos(jet.phi - lep.phi))) < clean_dr
               for lep in cleaning_leptons):
            continue
        selected.append(i)
    return selected


def choose_pair(jets, indices):
    """Two highest b scores, with input order breaking exact ties."""
    return sorted(indices, key=lambda i: jets[i].score, reverse=True)[:2]


def dijet_mass(first, second):
    def p4(jet):
        px, py = jet.pt * math.cos(jet.phi), jet.pt * math.sin(jet.phi)
        pz = jet.pt * math.sinh(jet.eta)
        return math.sqrt(px*px + py*py + pz*pz + jet.mass*jet.mass), px, py, pz
    e, px, py, pz = [a+b for a, b in zip(p4(first), p4(second))]
    return math.sqrt(max(0., e*e-px*px-py*py-pz*pz))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='+', help='inclusive 4l ROOT skims')
    parser.add_argument('-o', '--output', required=True, help='new output directory')
    parser.add_argument('--year', type=int, choices=[2022, 2023, 2024], required=True)
    parser.add_argument('--pt-min', type=float, default=20.)
    parser.add_argument('--eta-max', type=float, default=2.4)
    parser.add_argument('--clean-dr', type=float, default=0.4)
    parser.add_argument('--id-mask', type=int, help='e.g. 2 for tight; default jetId > 0')
    parser.add_argument('--pt-field', default='pt', help='Jet field, e.g. smearUp_pt')
    parser.add_argument('--mass-field', default='mass', help='matching field, e.g. smearUp_mass')
    parser.add_argument('--btag-field', help='Jet field; defaults to the year-specific ParT score')
    args = parser.parse_args()
    if args.pt_min < 0 or args.eta_max <= 0 or args.clean_dr < 0:
        parser.error('require pt-min >= 0, eta-max > 0 and clean-dr >= 0')
    if args.id_mask is not None and args.id_mask <= 0:
        parser.error('id-mask must be positive')
    if (args.pt_field == 'pt') != (args.mass_field == 'mass'):
        parser.error('vary pt and mass together')
    score_field = args.btag_field or (
        'btagUParTAK4B' if args.year == 2024 else 'btagRobustParTAK4B')

    # Import the CMSSW runtime only for ROOT processing, not for unit tests.
    from types import SimpleNamespace
    from pathlib import Path
    import ROOT
    ROOT.PyConfig.IgnoreCommandLineOptions = True
    from PhysicsTools.NanoAODTools.postprocessing.framework.eventloop import Module
    from PhysicsTools.NanoAODTools.postprocessing.framework.datamodel import Collection
    from PhysicsTools.NanoAODTools.postprocessing.framework.postprocessor import PostProcessor

    class JetStudy(Module):
        def beginFile(self, inputFile, outputFile, inputTree, wrappedOutputTree):
            self.out = wrappedOutputTree
            required = {'nJet', 'Jet_eta', 'Jet_phi', 'Jet_jetId',
                        'Jet_' + args.pt_field, 'Jet_' + args.mass_field,
                        'Jet_' + score_field, 'nElectron', 'nMuon',
                        'Electron_eta', 'Electron_phi', 'Muon_eta', 'Muon_phi',
                        'Electron_jetCleaning', 'Muon_jetCleaning'}
            branches = {b.GetName() for b in inputTree.GetListOfBranches()}
            missing = required - branches
            if missing:
                raise RuntimeError('Skim lacks jet-study inputs: ' + ', '.join(sorted(missing)))
            self.out.branch('JetStudy_idx', 'I', lenVar='nJetStudy')
            self.out.branch('JetStudy_pass2j', 'O')
            self.out.branch('JetStudy_j1Idx', 'I')
            self.out.branch('JetStudy_j2Idx', 'I')
            self.out.branch('JetStudy_mjj', 'F')

        def analyze(self, event):
            jets = [SimpleNamespace(pt=getattr(j, args.pt_field), eta=j.eta,
                                    phi=j.phi, mass=getattr(j, args.mass_field),
                                    jetId=j.jetId, score=getattr(j, score_field))
                    for j in Collection(event, 'Jet')]
            leptons = [lep for name in ('Electron', 'Muon')
                       for lep in Collection(event, name) if lep.jetCleaning]
            indices = select_jets(jets, leptons, args.pt_min, args.eta_max,
                                  args.clean_dr, args.id_mask)
            pair = choose_pair(jets, indices)
            passed = len(pair) == 2
            self.out.fillBranch('JetStudy_idx', indices)
            self.out.fillBranch('JetStudy_pass2j', passed)
            self.out.fillBranch('JetStudy_j1Idx', pair[0] if passed else -1)
            self.out.fillBranch('JetStudy_j2Idx', pair[1] if passed else -1)
            self.out.fillBranch('JetStudy_mjj', dijet_mass(jets[pair[0]], jets[pair[1]])
                                if passed else -1.)
            return True  # Keep every input 4l event, including 0/1-jet events.

    # Require a fresh destination so an earlier study is never overwritten.
    Path(args.output).mkdir(parents=True, exist_ok=False)
    PostProcessor(args.output, args.inputs, modules=[JetStudy()],
                  postfix='_jets').run()


if __name__ == '__main__':
    main()
