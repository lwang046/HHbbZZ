#!/usr/bin/env python3
"""
B-tagging Scale Factor Producer for Run3 using correctionlib.
Supports shape correction (continuous b-tag score for ML training).
Based on official BTV POG recommendations.
"""
import ROOT
ROOT.PyConfig.IgnoreCommandLineOptions = True

import os
import correctionlib
import numpy as np
from PhysicsTools.NanoAODTools.postprocessing.framework.eventloop import Module
from PhysicsTools.NanoAODTools.postprocessing.framework.datamodel import Collection

class btagSFProducer(Module):
    """
    Calculate b-tagging scale factors for Run3.
    Supports both fixed WP (M) and shape_corr (for ML training).
    
    Shape correction provides SF as a function of the continuous b-tag score,
    which is essential for ML applications that use b-tag discriminator as input.
    """
    def __init__(self, json_path, algo='deepJet', selectedWPs=['M', 'shape_corr']):
        """
        Args:
            json_path: Path to BTV POG JSON file
            algo: Algorithm name ('deepJet', 'particleNet', 'robustParticleTransformer')
            selectedWPs: List of working points, can include:
                        - Fixed WPs: 'L', 'M', 'T'
                        - 'shape_corr': continuous score correction for ML
        """
        self.json_path = json_path
        self.algo = algo
        self.selectedWPs = selectedWPs
        self.max_abs_eta = 2.5
        
        if not os.path.exists(self.json_path):
            raise RuntimeError(f"B-tagging SF file not found at {self.json_path}")
        
        print(f"--- btagSFProducer Initialization ({algo}) ---")
        print(f"Loading from: {os.path.basename(self.json_path)}")
        
        # Load correctionlib evaluator
        self.cset = correctionlib.CorrectionSet.from_file(json_path)
        
        # Print available corrections for debugging
        available_corrs = list(self.cset.keys())
        print(f"Available corrections: {available_corrs}")
        
        # Map algorithm to correction names in JSON
        # Run3 JSON structure: 'deepJet_shape', 'deepJet_comb', etc.
        self.algo_map = {
            'deepJet': {
                'shape': 'deepJet_shape',
                'comb': 'deepJet_comb'
            },
            'particleNet': {
                'shape': 'particleNet_shape', 
                'comb': 'particleNet_comb'
            },
            'robustParticleTransformer': {
                'shape': 'robustParticleTransformer_shape',
                'comb': 'robustParticleTransformer_comb'
            }
        }
        
        # Get correction names for this algorithm
        if algo not in self.algo_map:
            raise ValueError(f"Unknown algorithm: {algo}. Must be one of {list(self.algo_map.keys())}")
        
        self.shape_corr_name = self.algo_map[algo]['shape']
        self.wp_corr_name = self.algo_map[algo]['comb']
        
        # Validate that required corrections exist
        if 'shape_corr' in selectedWPs and self.shape_corr_name not in available_corrs:
            raise RuntimeError(f"Shape correction '{self.shape_corr_name}' not found in JSON!")
        
        for wp in selectedWPs:
            if wp != 'shape_corr' and self.wp_corr_name not in available_corrs:
                raise RuntimeError(f"WP correction '{self.wp_corr_name}' not found in JSON!")
        
        # Get evaluators
        self.evaluators = {}
        if 'shape_corr' in selectedWPs:
            self.evaluators['shape'] = self.cset[self.shape_corr_name]
            print(f"  ✓ Loaded shape correction: {self.shape_corr_name}")
        
        if any(wp != 'shape_corr' for wp in selectedWPs):
            self.evaluators['wp'] = self.cset[self.wp_corr_name]
            print(f"  ✓ Loaded WP correction: {self.wp_corr_name}")
        
        # Define systematic variations (from official BTV recommendations)
        self.systs_shape = [
            'central',
            'up_hf', 'down_hf',           # heavy flavor
            'up_lf', 'down_lf',           # light flavor
            'up_hfstats1', 'down_hfstats1',
            'up_hfstats2', 'down_hfstats2',
            'up_lfstats1', 'down_lfstats1',
            'up_lfstats2', 'down_lfstats2',
            'up_cferr1', 'down_cferr1',   # c-quark
            'up_cferr2', 'down_cferr2'
        ]
        self.systs_wp = ['central', 'up', 'down']
        
        # Map discriminator branch names
        self.discr_branch_map = {
            'deepJet': 'btagDeepFlavB',
            'particleNet': 'btagPNetB',
            'robustParticleTransformer': 'btagRobustParTAK4B'
        }
        self.discr_branch = self.discr_branch_map.get(algo, 'btagDeepFlavB')
        print(f"  ✓ Using discriminator branch: {self.discr_branch}")
        
        # Define output branch names
        self.branches = {}
        for wp in selectedWPs:
            if wp == 'shape_corr':
                systs = self.systs_shape
                base = f'Jet_btagSF_{algo}_shape'
            else:
                systs = self.systs_wp
                base = f'Jet_btagSF_{algo}_{wp}'
            self.branches[wp] = {
                s: f"{base}_{s}" if s != 'central' else base 
                for s in systs
            }
        
        print(f"  ✓ Will create branches for WPs: {selectedWPs}")
        print("--------------------------------------------------")

    def beginJob(self):
        pass

    def endJob(self):
        pass

    def beginFile(self, inputFile, outputFile, inputTree, wrappedOutputTree):
        self.out = wrappedOutputTree
        # Create all output branches
        for wp_branches in self.branches.values():
            for branch in wp_branches.values():
                self.out.branch(branch, "F", lenVar="nJet")

    def endFile(self, inputFile, outputFile, inputTree, wrappedOutputTree):
        pass

    def getFlavorBTV(self, hadronFlavor):
        """
        Map hadronFlavor to BTV convention used in correctionlib.
        Returns: 0 (b-jet), 1 (c-jet), 2 (light-jet)
        """
        abs_flavor = abs(hadronFlavor)
        if abs_flavor == 5:
            return 0  # b-jet
        elif abs_flavor == 4:
            return 1  # c-jet
        else:
            return 2  # light-jet (including gluon)

    def getSF(self, pt, eta, flavor, discr, syst, wp=None):
        """
        Evaluate scale factor using correctionlib.
        
        Args:
            pt: Jet pT
            eta: Jet eta
            flavor: Flavor code (0=b, 1=c, 2=light)
            discr: B-tag discriminator score (only used for shape_corr)
            syst: Systematic variation name
            wp: Working point ('L', 'M', 'T', or 'shape_corr')
        
        Returns:
            Scale factor (float)
        """
        # Clip eta to valid range
        eta_clipped = np.clip(eta, -self.max_abs_eta + 1e-5, self.max_abs_eta - 1e-5)
        
        # Clip pT to avoid edge issues (typical range: 20-1000 GeV)
        pt_clipped = np.clip(pt, 20.1, 999.0)
        
        try:
            if wp == 'shape_corr':
                # Shape correction uses continuous discriminator score
                # Signature: evaluate(syst, working_point, flavor, abseta, pt, discriminator)
                evaluator = self.evaluators['shape']
                sf = evaluator.evaluate(
                    syst,              # 'central', 'up_hf', etc.
                    'shape',           # working point literal string
                    flavor,            # 0, 1, or 2
                    abs(eta_clipped),
                    pt_clipped,
                    discr              # continuous b-tag score (THIS IS THE KEY!)
                )
            else:
                # Fixed WP (L/M/T)
                # Signature: evaluate(syst, working_point, flavor, abseta, pt)
                evaluator = self.evaluators['wp']
                sf = evaluator.evaluate(
                    syst,              # 'central', 'up', 'down'
                    wp.upper(),        # 'L', 'M', or 'T'
                    flavor,
                    abs(eta_clipped),
                    pt_clipped
                )
            
            # Sanity check
            return sf if 0.01 < sf < 10.0 else 1.0
        
        except Exception as e:
            # Suppress repetitive warnings
            if not hasattr(self, '_error_cache'):
                self._error_cache = set()
            
            error_key = (wp, syst, flavor)
            if error_key not in self._error_cache:
                print(f"Warning: SF evaluation failed for wp={wp}, syst={syst}, "
                      f"flavor={flavor}, pt={pt:.1f}, eta={eta:.2f}, discr={discr:.3f}")
                print(f"  Error: {e}")
                self._error_cache.add(error_key)
            
            return 1.0

    def analyze(self, event):
        """Process one event"""
        jets = Collection(event, "Jet")
        
        # Preload jet data (pt, eta, flavor, discriminator)
        jet_data = []
        for jet in jets:
            discr = getattr(jet, self.discr_branch, -1.0)
            jet_data.append((
                jet.pt,
                jet.eta,
                self.getFlavorBTV(jet.hadronFlavour),
                discr
            ))
        
        # Calculate SFs for each WP and systematic
        for wp in self.selectedWPs:
            systs = self.systs_shape if wp == 'shape_corr' else self.systs_wp
            
            for syst in systs:
                sfs = [
                    self.getSF(pt, eta, flavor, discr, syst, wp)
                    for pt, eta, flavor, discr in jet_data
                ]
                self.out.fillBranch(self.branches[wp][syst], sfs)
        
        return True