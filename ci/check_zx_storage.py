"""Validate persisted storage inputs and the union independently of SR/CR.

Usage: uv run --managed-python --python 3.9 python ci/check_zx_storage.py skim.root
Run inside the pinned CMSSW runtime. No event is accepted merely by Events membership.
"""
import argparse
import collections
import json
import math


def expected_2p1f(event, config):
    """Rebuild the legacy, with-SIP 2P1F decision from persisted objects.

    This deliberately does not use passedZPlusLStorage or the C++ selector.
    A saved FR pass, no-SIP-only probe or event without two cleaned jets must
    not acquire the legacy fail-region flag merely because it was retained.
    """
    import ROOT
    if config['mode'] not in ('4l', '4l2j'):
        return False
    cuts = config['selection']
    leptons = []
    for collection in ('Electron', 'Muon'):
        for i in range(int(getattr(event, 'n' + collection))):
            value = lambda field: getattr(event, collection + '_' + field)[i]
            if not value('ZXLoose'):
                continue
            bare = ROOT.TLorentzVector()
            bare.SetPtEtaPhiM(value('pt'), value('eta'), value('phi'), value('mass'))
            dressed = ROOT.TLorentzVector(bare)
            photon_index = int(value('fsrPhotonIdxAnalysis'))
            if config['isFSR'] and photon_index >= 0:
                photon = ROOT.TLorentzVector()
                photon.SetPtEtaPhiM(event.FsrPhoton_pt[photon_index],
                    event.FsrPhoton_eta[photon_index], event.FsrPhoton_phi[photon_index], 0.)
                dressed += photon
            leptons.append((bare, dressed, int(value('pdgId')), bool(value('ZXTight'))))
    if len(leptons) != 3 or sum(l[3] for l in leptons) != 2:
        return False
    met = float(event.PuppiMET_pt)
    if not math.isfinite(met) or not 0 <= met < 25.:
        return False
    tags = [l for l in leptons if l[3]]
    if tags[0][2] + tags[1][2] != 0:
        return False
    mass = (tags[0][1] + tags[1][1]).M()
    if not (cuts['MZcut']['down'] < mass < cuts['MZcut']['up'] and
            abs(mass - cuts['Zmass']) < 7. and
            max(l[1].Pt() for l in tags) > 20. and min(l[1].Pt() for l in tags) > 10.):
        return False
    for i, first in enumerate(leptons):
        for second in leptons[i + 1:]:
            if first[0].DeltaR(second[0]) <= .02:
                return False
            if first[2] * second[2] < 0 and (first[0] + second[0]).M() < 4.:
                return False
    clean_jets = 0
    for i in range(event.nJet):
        if not (event.Jet_pt[i] > cuts['Jet']['pTcut'] and
                abs(event.Jet_eta[i]) < cuts['Jet']['Etacut'] and event.Jet_jetId[i] > 0):
            continue
        jet = ROOT.TLorentzVector()
        jet.SetPtEtaPhiM(event.Jet_pt[i], event.Jet_eta[i], event.Jet_phi[i], event.Jet_mass[i])
        clean_jets += int(all(jet.DeltaR(l[1]) >= .4 for l in leptons))
    return clean_jets >= max(2, cuts['Jet']['Ncut'])


def validate(path):
    import ROOT
    file = ROOT.TFile.Open(path)
    if not file or file.IsZombie() or file.TestBit(ROOT.TFile.kRecovered):
        raise RuntimeError("Invalid ROOT file: " + path)
    tree = file.Get("Events")
    metadata = file.Get("ZXStorageConfig")
    if not tree or not metadata:
        raise RuntimeError("Missing Events/ZXStorageConfig")
    configs = [json.loads(str(row.configJSON)) for row in metadata]
    if not configs or any(row['schemaVersion'] != 3 for row in configs):
        raise RuntimeError("Expected three-layer storage schemaVersion 3")
    enabled = {row['enabled'] for row in configs}
    profiles = {row.get('profile', 'wide') for row in configs}
    if len(enabled) != 1 or len(profiles) != 1:
        raise RuntimeError("Mixed storage modes in one output")
    names = {branch.GetName() for branch in tree.GetListOfBranches()}
    expected = {'passedZPlusLStorage', 'passedZXNoSIPCRStorage', 'nElectron', 'nMuon', 'nJet',
                'passedZXCR2P1FSelection', 'passedZXCR2P2FSelection',
                'passedZXCR3P1FSelection', 'Sel_CRtype', 'nZXCRFailedLeptons',
                'Sel_isSR', 'Sel_isZXCR', 'Sel_goodJetIdx', 'nFsrPhoton',
                'FsrPhoton_pt', 'FsrPhoton_eta', 'FsrPhoton_phi',
                'FsrPhoton_relIso03', 'FsrPhoton_dROverEt2',
                'Muon_pfRelIso03FsrCorr'}
    for collection in ('Electron', 'Muon'):
        expected.update(collection + suffix for suffix in
                        ('_ZXLooseNoSIP', '_ZXLoose', '_ZXTight', '_pt', '_eta', '_phi',
                         '_sip3d', '_dxy', '_dz', '_fsrPhotonIdxAnalysis'))
    for config in configs:
        expected.update(config['inputBranches'])
        expected.update(config.get('objectBranches', []))
        if config['isMC']:
            expected.update(('nGenPart', 'GenPart_pdgId', 'GenPart_statusFlags',
                             'GenPart_genPartIdxMother', 'Electron_genPartIdx',
                             'Muon_genPartIdx', 'genWeight'))
    if expected - names:
        raise RuntimeError("Dropped storage inputs: " + str(sorted(expected - names)))
    counts = collections.Counter()
    for event in tree:
        sr, cr = bool(event.passedFullSelection), bool(event.isZXCR)
        stored = bool(event.passedZPlusLStorage)
        no_sip_cr = bool(event.passedZXNoSIPCRStorage)
        shifted = any(event.Sel_isSR) or any(event.Sel_isZXCR)
        if sr and cr or not (shifted or stored or no_sip_cr):
            raise RuntimeError("Invalid SR/CR/storage union")
        if bool(event.Sel_isSR[0]) != sr or bool(event.Sel_isZXCR[0]) != cr:
            raise RuntimeError("Nominal view disagrees with legacy flags")
        flags = [bool(getattr(event, 'passedZXCR' + region + 'Selection'))
                 for region in ('2P1F', '2P2F', '3P1F')]
        if sum(flags) != int(cr):
            raise RuntimeError("Legacy CR flags are not exclusive or disagree with isZXCR")
        region = flags.index(True) + 1 if cr else 0
        if int(event.Sel_CRtype[0]) != region:
            raise RuntimeError("Nominal Sel_CRtype disagrees with legacy CR flags")
        if flags[0] != expected_2p1f(event, configs[0]):
            raise RuntimeError("2P1F flag disagrees with independent with-SIP object/jet selection: " +
                               str((int(event.run), int(event.luminosityBlock), int(event.event))))
        if flags[0] and (event.nZXCRFailedLeptons != 1 or event.ngoodJets < 2):
            raise RuntimeError("2P1F requires one failing probe and two cleaned jets")
        counts['2P1F'] += int(flags[0])
        counts['2P1F_independent_checks'] += 1
        if (stored or no_sip_cr) and not next(iter(enabled)):
            raise RuntimeError("Storage event with feature disabled")
        for collection in ('Electron', 'Muon'):
            size = int(getattr(event, 'n' + collection))
            loose = list(getattr(event, collection + '_ZXLoose'))
            no_sip = list(getattr(event, collection + '_ZXLooseNoSIP'))
            tight = list(getattr(event, collection + '_ZXTight'))
            if (len(loose) != size or len(tight) != size or len(no_sip) != size or
                    any(t and not l or l and not n for n, l, t in zip(no_sip, loose, tight))):
                raise RuntimeError("Invalid original-collection ZX masks")
            # Reconstruct the two loose layers directly from persisted objects,
            # independently of the C++ list builder and its Python masks.
            cuts = configs[0]['selection'][collection]
            for i in range(size):
                value = lambda field: getattr(event, collection + '_' + field)[i]
                expected_no_sip = (value('pt') > cuts['pTcut'] and
                    abs(value('eta')) < cuts['Etacut'] and
                    abs(value('dxy')) < cuts['Loosedxycut'] and
                    abs(value('dz')) < cuts['Loosedzcut'])
                if collection == 'Muon':
                    expected_no_sip = expected_no_sip and (value('isGlobal') or value('isTracker'))
                if configs[0]['mode'] not in ('4l', '4l2j'):
                    expected_no_sip = False
                expected_sip = expected_no_sip and abs(value('sip3d')) < cuts['Sip3dcut']
                if no_sip[i] != expected_no_sip or loose[i] != expected_sip:
                    raise RuntimeError("Loose layers disagree with input objects: " + collection)
        if len(event.Jet_pt) != event.nJet:
            raise RuntimeError("Incomplete Jet collection")
        if not configs[0]['isMC'] and list(event.GENlep_Hindex) != [-1] * 4:
            raise RuntimeError("Data GENlep_Hindex must contain four explicit unavailable indices")
        counts['events'] += 1
        counts['SR' if sr else 'CR' if cr else 'VariationOnly' if shifted else 'StorageOnly'] += 1
        counts['storage'] += int(stored)
        counts['noSIP_application_storage'] += int(no_sip_cr)
        no_sip_count = sum(event.Electron_ZXLooseNoSIP) + sum(event.Muon_ZXLooseNoSIP)
        if no_sip_cr and no_sip_count < 4:
            raise RuntimeError("Invalid no-SIP application storage multiplicity")
        if stored:
            loose_count = sum(event.Electron_ZXLoose) + sum(event.Muon_ZXLoose)
            tight_count = sum(event.Electron_ZXTight) + sum(event.Muon_ZXTight)
            if next(iter(profiles)) == 'fr' and (3 not in (loose_count, no_sip_count) or
                                                not 0 <= event.PuppiMET_pt < 25):
                raise RuntimeError("Event outside the configured FR storage envelope")
            if loose_count == 3:
                counts['stored_3loose_pass' if tight_count == 3 else 'stored_3loose_fail'] += 1
            if no_sip_count == 3:
                counts['stored_3looseNoSIP_pass' if tight_count == 3 else 'stored_3looseNoSIP_fail'] += 1
            counts['stored_SIP_fail_objects'] += no_sip_count - loose_count
            counts['stored_raw_jets_0or1'] += int(event.nJet < 2)
    result = dict(counts=counts, storage_enabled=next(iter(enabled)),
                  storage_profile=next(iter(profiles)),
                  branch_count=len(names), input_metadata_rows=len(configs))
    file.Close()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('path')
    args = parser.parse_args()
    print(json.dumps(validate(args.path), sort_keys=True))
