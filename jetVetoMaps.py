import ROOT
import os
from PhysicsTools.NanoAODTools.postprocessing.framework.eventloop import Module
from PhysicsTools.NanoAODTools.postprocessing.framework.datamodel import Collection
import correctionlib

class JetVetoMap(Module):
    # --- 修正1：构造函数不再需要 map_name 参数 ---
    def __init__(self, json_path):
        """
        Initializes the Jet Veto Map module.
        It will automatically find and load the map from the provided JSON file.
        """
        self.json_path = json_path
        
        if not os.path.exists(self.json_path):
            raise RuntimeError(f"Jet Veto Map file not found at {self.json_path}")
        
        cset = correctionlib.CorrectionSet.from_file(self.json_path)
        
        # --- 修正2：自动检索可用的map名称 ---
        available_maps = list(cset.keys())
        if not available_maps:
            raise RuntimeError(f"FATAL: No maps found in Jet Veto Map file: {self.json_path}")
        
        # 使用找到的第一个map名称
        self.map_name = available_maps[0]
        self.evaluator = cset[self.map_name]
        
        print(f"INFO: Automatically detected and loaded Jet Veto Map '{self.map_name}' from '{os.path.basename(self.json_path)}'")

        # --- 调试代码已完成使命，可以移除 ---

    def beginFile(self, inputFile, outputFile, inputTree, wrappedOutputTree):
        pass

    def analyze(self, event):
        """
        Analyzes each event. Returns False if the event should be vetoed, True otherwise.
        """
        jets = Collection(event, "Jet")
        
        for jet in jets:
            # Apply pre-selection before checking the veto map
            if not (jet.pt > 15):
                continue
            if not (hasattr(jet, 'jetId') and jet.jetId >= 3):
                continue
            if not ((jet.chEmEF + jet.neEmEF) < 0.9):
                continue

            # --- 最终修正：根据调试信息，使用 "jetvetomap" 作为第一个参数 ---
            is_vetoed = self.evaluator.evaluate("jetvetomap", jet.eta, jet.phi)
            
            if is_vetoed == 1:
                return False # Veto the event
        
        return True # Keep the event