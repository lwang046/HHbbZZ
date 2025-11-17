import ROOT
import os
import correctionlib
from PhysicsTools.NanoAODTools.postprocessing.framework.eventloop import Module
from PhysicsTools.NanoAODTools.postprocessing.framework.datamodel import Collection

class btagSFProducer(Module):
    def __init__(self, json_path):
        """
        A comprehensive b-tagging SF producer that calculates SFs for multiple
        algorithms simultaneously for comparison purposes.
        
        Args:
            json_path (str): Path to the official BTV POG JSON file.
        """
        self.json_path = json_path
        
        # --- 我们要一次性处理的所有算法 ---
        self.algos_to_process = [
            "deepJet_shape",
            "particleNet_shape",
            "robustParticleTransformer_shape"
        ]
        
        if not os.path.exists(self.json_path):
            raise RuntimeError(f"B-tagging SF file not found at {self.json_path}")

        print("--- btagSFProducer Initialization ---")
        print(f"Loading b-tagging SFs from: {os.path.basename(self.json_path)}")

        cset = correctionlib.CorrectionSet.from_file(self.json_path)
        
        self.evaluators = {}
        self.output_branch_names = {}

        for algo in self.algos_to_process:
            if algo not in cset:
                print(f"WARNING: Algorithm '{algo}' not found in the JSON file. Skipping.")
                continue
            
            self.evaluators[algo] = cset[algo]
            branch_name = f"Jet_btagSF_{algo}"
            self.output_branch_names[algo] = branch_name
            print(f"  - Will calculate SFs for '{algo}' and create branch '{branch_name}'")
        
        print("------------------------------------")

    def beginFile(self, inputFile, outputFile, inputTree, wrappedOutputTree):
        self.out = wrappedOutputTree
        # 为每个算法创建对应的输出分支
        for algo, branch_name in self.output_branch_names.items():
            self.out.branch(branch_name, "F", lenVar="nJet")

    def analyze(self, event):
        jets = Collection(event, "Jet")
        
        # 为每个算法准备一个列表来存储当前event所有jet的SF值
        sf_values_map = {algo: [] for algo in self.evaluators}

        for jet in jets:
            # 对每个jet，计算所有算法的SF
            for algo, evaluator in self.evaluators.items():
                sf = 1.0  # 默认值为1.0
                try:
                    # 对于MC，根据hadronFlavour, eta, pt计算SF
                    # 对于Data，或超出范围的jet，correctionlib会自动处理或抛出异常
                    # 我们使用max(20.1, jet.pt)来避免在pT边界出现问题
                    eval_pt = max(20.1, jet.pt)
                    sf = evaluator.evaluate("central", jet.hadronFlavour, abs(jet.eta), eval_pt)
                except Exception:
                    # 如果jet在SF map的范围之外，sf将保持为1.0，这是正确的行为
                    pass
                
                sf_values_map[algo].append(sf)

        # 将计算出的所有SF值填充到对应的分支中
        for algo, branch_name in self.output_branch_names.items():
            self.out.fillBranch(branch_name, sf_values_map[algo])
            
        return True