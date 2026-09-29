# Inclusive four-lepton skims and downstream jet studies

Run the existing entry point with `--mode 4l` (also pass this option to
`condor_setup_lxplus.py` for batch production). The default remains `4l2j` for
compatibility. For example, inside the configured CMSSW environment:

```bash
python3 post_proc.py -i INPUT_NANOAOD.root -n 0 --mode 4l
```

The skim keeps only events passing the existing trigger and four-lepton
selection. It does **not** require two jets. Jet corrections still run before
the analysis. Every retained event stores the complete NanoAOD `Jet` collection,
including jets failing the nominal jet selection, plus the nominal `goodJet`
subset. This does not recover jets absent from the original NanoAOD.

## Stored information

- `nJet`, `Jet*`: corrected nominal kinematics, available JES/JER variations,
  tagging scores, jet ID inputs and MC flavour/matching information.
- `ngoodJets`, `goodJet_*`: the existing nominal selection. New `goodJet_idx`
  maps each entry to the complete `Jet` array.
- Complete `Electron` and `Muon` collections and their counts. New boolean
  `Electron_jetCleaning` and `Muon_jetCleaning` arrays mark the exact leptons
  used by the framework for jet cleaning. These include leptons beyond the
  final four-lepton candidate, where applicable.
- `Flag_JetVetoed*`, `Rho_*`, `fixedGridRho*`, and the existing MC GenJet inputs.

The retention changes apply to data and simulation in all analysis modes.
They do not change any event acceptance, threshold, correction or weight.
No new b-tag SF prescription is introduced.

## Recompute jets without rerunning four-lepton reconstruction

The supplied helper runs in the same NanoAODTools/ROOT environment:

```bash
python3 scripts/jet_selection.py skim.root --year 2024 -o jet_nominal
python3 scripts/jet_selection.py skim.root --year 2024 -o jet_pt25 --pt-min 25
python3 scripts/jet_selection.py skim.root --year 2024 -o jet_wide --eta-max 4.7
python3 scripts/jet_selection.py skim.root --year 2024 -o jet_clean03 --clean-dr 0.3
python3 scripts/jet_selection.py skim.root --year 2024 -o jet_jer_up \
  --pt-field smearUp_pt --mass-field smearUp_mass
```

Use a new output directory for each study. `--id-mask 2` explicitly requires
the tight jet-ID bit; the default reproduces the framework's `jetId > 0` test.
The default kinematic cuts are `pt > 20`, `abs(eta) < 2.4`, with cleaning at
`DeltaR >= 0.4`. Each variation reselects from the **full** Jet collection so
migration across thresholds is included. Set the matching pt and mass fields
together. JES field names depend on the correction payload; inspect the
available `Jet_*Scale*` branches before specifying them. JER fields are MC-only.

The helper preserves all input events/branches and adds:

| Branch | Meaning |
| --- | --- |
| `nJetStudy`, `JetStudy_idx` | Selected jets, indexed in the original `Jet` array |
| `JetStudy_pass2j` | At least two jets pass the study selection |
| `JetStudy_j1Idx`, `JetStudy_j2Idx` | Two highest b-score jet indices, or -1 if fewer than two |
| `JetStudy_mjj` | Dijet mass in GeV, or -1 if fewer than two |

The default score is RobustParT for 2022/2023 and UParT for 2024. Override it
with `--btag-field`, for example `btagDeepFlavB`. Exact score ties use input
order; this is explicit and can differ from the legacy C++ pairing in
three-or-more-jet events with tied scores. No b-tag working point, dijet mass
window, veto-map rejection or weight multiplication is imposed by this helper.
Apply those downstream using the selected indices, scores, saved veto flag
and appropriate weights. Older `pTj1`, `pTj2`, `invjj` fields are not filled by
inclusive 4l reconstruction; use the new `JetStudy_*` results instead.

This helper expects the new cleaning flags. Earlier production skims remain
usable for studies using their existing `goodJet_*` arrays, but the helper
fails explicitly rather than inventing missing cleaning information. Do not
reskim old data solely to gain these flags without first defining the study.

Stored nominal and shifted jet momenta are already corrected; the helper must
not rerun JEC/JER. In the current NATModules implementation,
`Jet_uncorrected_pt/mass` hold **raw** momenta. A future recalibration should
start from those raw fields, not apply the old rawFactor to corrected Jet_pt.
Changing the four-lepton acceptance or constructing loose-lepton Z+X control
regions still requires appropriately selected inputs.

## Checks

```bash
python3 -m unittest discover -s tests -p test_jet_selection.py -v
```

Before production use, run data and MC pilots and check the persisted ROOT
schema, event counts and index alignment. For default jet settings,
`JetStudy_idx` should equal `goodJet_idx` event by event. Compare with a direct
`4l2j` run on the same NanoAOD inputs; treat exact b-score ties as noted above.
