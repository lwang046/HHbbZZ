"""Exercise the real C++ 2P1F flag, its storage separation and event reset.

Run in CMSSW: python tests/check_zx_2p1f_root.py REPO
"""
import json
import math
from pathlib import Path
import sys

import ROOT

source = Path(sys.argv[1]).resolve()
ROOT.gROOT.ProcessLine('.L %s/src/H4LTools.cc+O' % source)
print('ZX_2P1F_WORKER_LOADED', flush=True)


def make_worker():
    w = ROOT.H4LTools(False)
    w.Initialize()
    w.SetAnalysisMode('4l')
    w.SetNanoVersion(15)
    w.isFSR = False
    w.InitializeElecut(5., 2.5, 4., .5, 1., 0., 0., 0., 0., 0., 0.)
    w.InitializeMucut(3., 2.4, 8., .5, 1.)
    w.InitializeFsrPhotonCut(2., 2.4, .8, .5, .012)
    w.InitializeJetcut(20., 2.4, 2)
    w.InitializeEvtCut(70., 105., 160., 91.1876, 40., 12., 120.)
    return w


def populate(w, jets=2, overlap=False, sip=1., tight=False, extra=False,
             same_sign=False, tag_pt=45.5):
    for pdg, phi in ((11, 0.), (11 if same_sign else -11, math.pi)):
        w.SetElectrons(tag_pt, 0., phi, .000511, .01, .02, 1., 0., 0., True, pdg)
    w.SetMuons(15., .5, 1., .105, True, True, .01, .02,
               sip, True, 0., True, 13, .1 if tight else .5)
    if extra:
        w.SetMuons(12., -.5, -1., .105, True, True, .01, .02,
                   1., True, 0., True, 13, .5)
    for i in range(jets):
        w.SetJets(35., .5 if overlap and i == 0 else 1.8,
                  1. if overlap and i == 0 else (1.8 if i == 0 else -1.8),
                  5., 2, .1, .1, .1, .1)
    w.BatchFsrRecovery_Run3()
    w.LeptonSelection()
    w.ZZSelection()


results = []
cases = [('fail_two_clean_jets', {}, 10., True),
         ('no_jets', {'jets': 0}, 10., False),
         ('one_jet', {'jets': 1}, 10., False),
         ('probe_jet_overlap', {'overlap': True}, 10., False),
         ('tight_probe', {'tight': True}, 10., False),
         ('sip_failing_probe', {'sip': 8.}, 10., False),
         ('four_loose_leptons', {'extra': True}, 10., False),
         ('same_sign_tags', {'same_sign': True}, 10., False),
         ('outside_narrow_z', {'tag_pt': 40.}, 10., False),
         ('met_zero', {}, 0., True),
         ('met_below_25', {}, 24.999, True),
         ('met_25', {}, 25., False),
         ('met_negative', {}, -1., False),
         ('met_nan', {}, float('nan'), False),
         ('met_infinite', {}, float('inf'), False)]
for name, options, met, expected in cases:
    print('ZX_2P1F_CASE', name, flush=True)
    w = make_worker()
    populate(w, **options)
    accepted = bool(w.ZXCRSelection(met))
    assert accepted == bool(w.passedZXCR2P1FSelection) == expected, name
    before = (bool(w.passedZXCR2P1FSelection), bool(w.passedZXCR2P2FSelection),
              bool(w.passedZXCR3P1FSelection), list(w.jetidx), list(w.lep_Hindex))
    w.BuildZXLooseNoSIP()
    w.ZXNoSIPCRStorage()
    after = (bool(w.passedZXCR2P1FSelection), bool(w.passedZXCR2P2FSelection),
             bool(w.passedZXCR3P1FSelection), list(w.jetidx), list(w.lep_Hindex))
    assert before == after, 'Storage mutated nominal state: ' + name
    if expected:
        assert w.nZXCRFailedLeptons == 1 and len(w.jetidx) >= 2
        assert list(w.ZXCRTight)[:3] == [True, True, False]
    results.append(dict(case=name, flag=accepted, expected=expected))

# Reuse the same worker: an accepted event must never contaminate the next one,
# including the Python fast path that skips ZXCRSelection without tight tags.
w = make_worker()
populate(w)
assert w.ZXCRSelection(10.) and w.passedZXCR2P1FSelection
w.Initialize()
assert not w.passedZXCR2P1FSelection and not w.passedZXCR2P2FSelection
assert not w.passedZXCR3P1FSelection and w.nZXCRFailedLeptons == 0
w.SetAnalysisMode('4l')
populate(w, tight=True)
assert not w.ZXCRSelection(10.) and not w.passedZXCR2P1FSelection
results.append(dict(case='same_worker_reset_and_reject', flag=False, expected=False))
print('ZX_2P1F_NATIVE_PASS ' + json.dumps(results))
