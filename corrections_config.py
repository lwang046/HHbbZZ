import os
from PhysicsTools.NanoAODTools.postprocessing.modules.common.muonScaleResProducer import muonScaleResProducer
from jetCorr import jetJERC
from jetVetoMaps import JetVetoMap
# --- 新增：导入我们全新的btag模块 ---
from btagSFProducer import btagSFProducer

def add_correction_args(parser):
    """Adds mutually exclusive correction flags to the parser."""
    # Create a group where only one argument can be active at a time.
    # By default (if no flag is given), all corrections will be ON.
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--no-corrections", action="store_true", help="Run without ANY corrections (JEC/JER, VetoMap, PU, b-tag SF).")
    group.add_argument("--pu-only", action="store_true", help="Run with ONLY Pileup reweighting enabled.")
    return parser

def setup_corrections(args, year, isMC, first_file):
    """
    This function is the central hub for all Run 3 physics corrections.
    It returns a list of configured correction modules and a dictionary of PU parameters.
    - Default: All corrections are enabled.
    - --no-corrections: Disables all corrections.
    - --pu-only: Enables only Pileup reweighting.
    """
    
    modules = []
    pu_params = {}

    # Handle the --no-corrections flag first (total override)
    if args.no_corrections:
        print("INFO: All corrections are disabled by --no-corrections flag.")
        return [], {}

    # --- PU Reweighting Parameters (always configured for MC if not fully disabled) ---
    if isMC:
        pu_corr_key = f"{year}_mc"
        if year == 2022:
            is_postEE = "Summer22EE" in first_file or any(run in first_file for run in ["Run2022E", "Run2022F", "Run2022G"])
            pu_params["pu_json"] = "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/LUM/2022_Summer22EE/puWeights.json.gz" if is_postEE else "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/LUM/2022_Summer22/puWeights.json.gz"
            pu_params["pu_name"] = "Collisions2022_359022_362760_eraEFG_GoldenJson" if is_postEE else "Collisions2022_355100_357900_eraBCD_GoldenJson"
        elif year == 2023:
            is_postBPix = "BPix" in first_file or any(run in first_file for run in ["Run2023C", "Run2023D"])
            pu_params["pu_json"] = "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/LUM/2023_Summer23BPix/puWeights.json.gz" if is_postBPix else "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/LUM/2023_Summer23/puWeights.json.gz"
            pu_params["pu_name"] = "Collisions2023_369803_370790_eraD_GoldenJson" if is_postBPix else "Collisions2023_366403_369802_eraBC_GoldenJson"

    # If --pu-only is specified, we are done. Return only the PU parameters.
    if args.pu_only:
        print("INFO: Running in --pu-only mode. All other corrections are disabled.")
        return [], pu_params

    # --- DEFAULT BEHAVIOR: Enable all other corrections ---
    print("INFO: Enabling all baseline corrections (JEC/JER, Veto Map, b-tag SF).")

    # --- 2022/2022EE ---
    if year == 2022:
        is_postEE = "Summer22EE" in first_file or any(run in first_file for run in ["Run2022E", "Run2022F", "Run2022G"])
        
        # --- JEC/JER ---
        json_path = "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME/2022_Summer22EE/" if is_postEE else "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME/2022_Summer22/"
        jec_json = os.path.join(json_path, "jet_jerc.json.gz")
        era_tag = "Summer22EE_22Sep2023" if is_postEE else "Summer22_22Sep2023"
        
        if isMC:
            correct_jer_tag = era_tag.replace("22Sep2023", "22Sep2023_JRV1")
            jetCorr_module = jetJERC(
                json_JERC=jec_json, json_JERsmear=jec_json,
                L1Key=f"{era_tag}_V2_MC_L1FastJet_AK4PFPuppi", L2Key=f"{era_tag}_V2_MC_L2Relative_AK4PFPuppi",
                L3Key=f"{era_tag}_V2_MC_L3Absolute_AK4PFPuppi", L2L3Key=f"{era_tag}_V2_MC_L2L3Residual_AK4PFPuppi",
                scaleTotalKey=f"{era_tag}_V2_MC_Total_AK4PFPuppi",
                JERKey=f"{correct_jer_tag}_MC_PtResolution_AK4PFPuppi", JERsfKey=f"{correct_jer_tag}_MC_ScaleFactor_AK4PFPuppi",
                smearKey="JERSmear", overwritePt=True
            )
        else: # Data
            run_period = next((p for p in ["RunCD", "RunE", "RunF", "RunG"] if any(rp in first_file for rp in p.replace("Run","").split())), "RunCD")
            data_era_tag = f"{era_tag}_{run_period}_V2_DATA"
            jetCorr_module = jetJERC(
                json_JERC=jec_json, json_JERsmear=jec_json,
                L1Key=f"{data_era_tag}_L1FastJet_AK4PFPuppi", L2Key=f"{data_era_tag}_L2Relative_AK4PFPuppi",
                L3Key=f"{data_era_tag}_L3Absolute_AK4PFPuppi", L2L3Key=f"{data_era_tag}_L2L3Residual_AK4PFPuppi",
                smearKey=None, overwritePt=True
            )
        modules.insert(0, jetCorr_module)

        # --- Jet Veto Map ---
        veto_map_json = "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME/2022_Summer22EE/jetvetomaps.json.gz" if is_postEE else "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME/2022_Summer22/jetvetomaps.json.gz"
        modules.append(JetVetoMap(veto_map_json))

    # --- 2023 ---
    elif year == 2023:
        is_postBPix = "BPix" in first_file or any(run in first_file for run in ["Run2023C", "Run2023D"])
        
        # --- JEC/JER ---
        json_path = "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME/2023_Summer23BPix/" if is_postBPix else "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME/2023_Summer23/"
        jec_json = os.path.join(json_path, "jet_jerc.json.gz")
        base_era_name = "Summer23BPixPrompt23" if is_postBPix else "Summer23Prompt23"
        
        if isMC:
            jec_mc_tag = f"{base_era_name}_V3_MC"
            jer_mc_tag = f"{base_era_name}_RunD_JRV1_MC"
            jetCorr_module = jetJERC(
                json_JERC=jec_json, json_JERsmear=jec_json,
                L1Key=f"{jec_mc_tag}_L1FastJet_AK4PFPuppi", L2Key=f"{jec_mc_tag}_L2Relative_AK4PFPuppi",
                L3Key=f"{jec_mc_tag}_L3Absolute_AK4PFPuppi", L2L3Key=f"{jec_mc_tag}_L2L3Residual_AK4PFPuppi",
                scaleTotalKey=f"{jec_mc_tag}_Regrouped_Total_AK4PFPuppi",
                JERKey=f"{jer_mc_tag}_PtResolution_AK4PFPuppi", JERsfKey=f"{jer_mc_tag}_ScaleFactor_AK4PFPuppi",
                smearKey="JERSmear", overwritePt=True
            )
        else: # Data
            run_period = next((p for p in ["RunB", "RunCv4", "RunD"] if p in first_file), "RunB")
            data_era_tag = f"{base_era_name}_{run_period}_V2_DATA"
            jetCorr_module = jetJERC(
                json_JERC=jec_json, json_JERsmear=jec_json,
                L1Key=f"{data_era_tag}_L1FastJet_AK4PFPuppi", L2Key=f"{data_era_tag}_L2Relative_AK4PFPuppi",
                L3Key=f"{data_era_tag}_L3Absolute_AK4PFPuppi", L2L3Key=f"{data_era_tag}_L2L3Residual_AK4PFPuppi",
                smearKey=None, overwritePt=True
            )
        modules.insert(0, jetCorr_module)

        # --- Jet Veto Map ---
        veto_map_json = "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME/2023_Summer23BPix/jetvetomaps.json.gz" if is_postBPix else "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME/2023_Summer23/jetvetomaps.json.gz"
        modules.append(JetVetoMap(veto_map_json))

    # ==================================================================
    #  B-TAGGING SCALE FACTORS (MC-only, now enabled by default)
    # ==================================================================
    if isMC:
        print("INFO: Enabling b-tagging SF calculation for DeepJet, ParticleNet, and RPT.")
        btag_json = ""
        if year == 2022:
            btag_json = "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/BTV/2022_Summer22EE/btagging.json.gz"
        elif year == 2023:
            btag_json = "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/BTV/2023_Summer23BPix/btagging.json.gz"
        
        if btag_json:
            modules.append(btagSFProducer(btag_json))
        else:
            print(f"WARNING: No b-tagging SF file found for year {year}. Skipping.")

    return modules, pu_params