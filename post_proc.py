#!/usr/bin/env python3
import os
import sys
import argparse

from PhysicsTools.NanoAODTools.postprocessing.framework.postprocessor import PostProcessor
from PhysicsTools.NanoAODTools.postprocessing.framework.datamodel import Collection
from PhysicsTools.NanoAODTools.postprocessing.framework.eventloop import Module
from H4Lmodule import *
from H4LCppModule import *
# --- 核心修正：导入 btagSFProducer 类 ---
from btagSFProducer import btagSFProducer
from corrections_config import setup_corrections, add_correction_args

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="NanoAOD post-processor for Run 3.")
    parser.add_argument("-i", "--inputFile", required=True, type=str, help="Input file list (.txt) or single file (.root)")
    parser.add_argument("-n", "--entriesToRun", default=0, type=int, help="Set to 0 to run over all entries")
    parser.add_argument("-d", "--DownloadFileToLocalThenRun", default=True, type=bool, help="Download file to local then run")
    
    parser.add_argument("--isMC", action="store_true", help="Set if running on MC")
    parser.add_argument("--isFSR", action="store_true", help="Set if running with FSR")
    # --- 新增：添加 outputFile 参数 ---
    parser.add_argument("--outputFile", type=str, default="skimmed_nano.root", help="Name of the output file")
    
    add_correction_args(parser)
    
    args = parser.parse_args()

    return args

def getListFromFile(filename):
    """Read file list from a text file."""
    with open(filename, "r") as file:
        return ["root://cms-xrd-global.cern.ch/" + line.strip() for line in file if line.strip()]

def main():
    args = parse_arguments()

    # --- Determine list of files to process ---
    if args.inputFile.endswith(".txt"):
        testfilelist = getListFromFile(args.inputFile)
    else:
        # For single file input, add the remote prefix if not already present
        if not testfilelist[0].startswith("root://"):
            testfilelist = ["root://cms-xrd-global.cern.ch/" + testfilelist[0]]
        else:
            testfilelist = [args.inputFile]
    
    if not testfilelist:
        print(f"ERROR: No input files found from {args.inputFile}. Exiting.")
        sys.exit(1)

    # ======================= NEW: LOCAL CACHING LOGIC =======================
    files_to_process = testfilelist
    local_files_to_cleanup = []

    if args.DownloadFileToLocalThenRun:
        import subprocess
        print("INFO: Local caching is enabled. Downloading files before processing...")
        
        cached_files = []
        for remote_file in testfilelist:
            local_filename = os.path.basename(remote_file)
            # Check if file already exists locally to avoid re-downloading
            if os.path.exists(local_filename):
                print(f"  - Found local copy: {local_filename}")
                cached_files.append(local_filename)
                continue

            print(f"  - Downloading: {remote_file} -> {local_filename}")
            try:
                # Using xrdcp to copy the file to the current directory
                subprocess.run(["xrdcp", remote_file, local_filename], check=True, capture_output=True, text=True)
                cached_files.append(local_filename)
                local_files_to_cleanup.append(local_filename)
            except subprocess.CalledProcessError as e:
                print(f"ERROR: Failed to download {remote_file}. Error: {e.stderr}")
                # Decide if you want to exit or just skip the file
                print("Skipping this file and continuing...")
        
        files_to_process = cached_files
        if not files_to_process:
            print("ERROR: No files could be downloaded or found locally. Exiting.")
            sys.exit(1)
    # ========================================================================

    # --- Determine year and sample type from the first file ---
    # IMPORTANT: Use the original remote path for metadata, not the local copy
    first_file = testfilelist[0]
    isMC = "/data/" not in first_file
    isFSR = False # Set your FSR logic if needed

    year_map = {"Summer22": 2022, "Run2022": 2022, "Summer23": 2023, "Run2023": 2023}
    year = next((y for s, y in year_map.items() if s in first_file), None)
    if year is None:
        raise ValueError(f"Could not determine Run 3 year from first file: {first_file}")

    # --- CORE LOGIC: Get all correction modules and PU info from the config file ---
    modulesToRun, pu_params = setup_corrections(args, year, isMC, first_file)
    
    # --- Add analysis-specific modules that ALWAYS run ---
    cfgFile = f"Input_{year}.yml"
    
    # --- NEW: Check if b-tag SFs will be calculated ---
    btagSF_on = any(isinstance(m, btagSFProducer) for m in modulesToRun)
    
    # The HZZ C++ module needs the PU info, which we pass to it.
    # If corrections are disabled, pu_params will be an empty dict, and the module should handle it.
    modulesToRun.append(HZZAnalysisCppProducer(year, cfgFile, isMC, isFSR, btagSF_on=btagSF_on, **pu_params))
    
    # --- Setup PostProcessor ---
    jsonInput = None
    if not isMC:
        json_map = {2022: "golden_Json/Cert_Collisions2022_355100_362760_Golden.json", 2023: "golden_Json/Cert_Collisions2023_366442_370790_Golden.json"}
        jsonInput = json_map.get(year)

    output_drop_file = "keep_and_drop_data.txt" if not isMC else "keep_and_drop.txt"

    print(f"--- Running PostProcessor for Year: {year}, isMC: {isMC} ---")
    print(f"--- {len(modulesToRun)} modules will be run: ---")
    for m in modulesToRun:
        print(f"  - {m.__class__.__name__}")
    print("-------------------------------------------------")

    try:
        p = PostProcessor(".",
                          files_to_process, # <-- Use the (potentially local) file list
                          cut=None,
                          branchsel=None,
                          modules=modulesToRun,
                          provenance=True,
                          outputbranchsel=output_drop_file,
                          maxEntries=args.entriesToRun if args.entriesToRun > 0 else None,
                          haddFileName=args.outputFile
                          )
        p.run()
    finally:
        # --- NEW: Cleanup downloaded files ---
        if local_files_to_cleanup:
            print("INFO: Cleaning up downloaded temporary files...")
            for f in local_files_to_cleanup:
                os.remove(f)
                print(f"  - Removed {f}")

if __name__ == "__main__":
    main()
