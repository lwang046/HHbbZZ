"""ROOT/NanoAODTools integration check; run inside the configured CMSSW runtime."""
from array import array
from pathlib import Path
import subprocess
import sys
import tempfile
import ROOT


def main():
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='inclusive4l_jets_') as tmp:
        base = Path(tmp)
        input_path = base / 'fixture.root'
        f = ROOT.TFile(str(input_path), 'RECREATE')
        tree = ROOT.TTree('Events', 'synthetic already-selected 4l events')
        buffers = {}
        for name in ('nJet', 'nElectron', 'nMuon', 'event'):
            buffers[name] = array('i', [0])
            tree.Branch(name, buffers[name], name + '/I')
        for name in ('Jet_pt', 'Jet_mass', 'Jet_eta', 'Jet_phi', 'Jet_btagUParTAK4B',
                     'Jet_smearUp_pt', 'Jet_smearUp_mass', 'Jet_jetId',
                     'Electron_eta', 'Electron_phi', 'Electron_jetCleaning',
                     'Muon_eta', 'Muon_phi', 'Muon_jetCleaning'):
            count = 'n' + name.split('_')[0]
            kind = 'i' if name.endswith(('jetId', 'jetCleaning')) else 'f'
            buffers[name] = array(kind, [0]*8)
            tree.Branch(name, buffers[name], '%s[%s]/%s' % (name, count, kind.upper()))
        for number, pts in enumerate(([], [30.], [19., 40.], [30., 40., 50.])):
            buffers['event'][0] = number
            buffers['nJet'][0] = len(pts)
            buffers['nElectron'][0] = 1
            buffers['nMuon'][0] = 0
            buffers['Electron_eta'][0] = 0.
            buffers['Electron_phi'][0] = 0.
            buffers['Electron_jetCleaning'][0] = 1
            for i, pt in enumerate(pts):
                for name, value in {'pt': pt, 'mass': 5., 'eta': 1., 'phi': i,
                                    'btagUParTAK4B': i/10., 'jetId': 2,
                                    'smearUp_pt': pt+2., 'smearUp_mass': 5.5}.items():
                    buffers['Jet_' + name][i] = value
            if number == 3:
                buffers['Jet_eta'][0] = 0.  # First jet overlaps the cleaning electron.
            tree.Fill()
        tree.Write()
        f.Close()
        for variation, extra, expected in (
            ('nominal', [], [False, False, False, True]),
            ('up', ['--pt-field', 'smearUp_pt', '--mass-field', 'smearUp_mass'],
             [False, False, True, True]),
        ):
            output = base / variation
            subprocess.run([sys.executable, str(repo/'scripts/jet_selection.py'),
                            str(input_path), '--year', '2024', '-o', str(output)] + extra,
                           check=True)
            result = ROOT.TFile.Open(str(output/'fixture_jets.root'))
            events = result.Get('Events')
            assert events.GetEntries() == 4
            assert [bool(e.JetStudy_pass2j) for e in events] == expected
            assert [int(e.event) for e in events] == [0, 1, 2, 3]
            assert [int(e.nJet) for e in events] == [0, 1, 2, 3]
            events.GetEntry(3)
            assert list(events.JetStudy_idx) == [1, 2]
            assert (events.JetStudy_j1Idx, events.JetStudy_j2Idx) == (2, 1)
            assert events.JetStudy_mjj > 0
            result.Close()
        print('ROOT_INTEGRATION_PASS: counts, cleaning, indices, pairing, JER migration')


if __name__ == '__main__':
    main()
