#!/usr/bin/env python3
# "chmod +x add_jetid_v15.py" to make it executable

"""
Add Jet_jetId branch for NanoAODv15 samples.

This script is intended as a preprocessing step:

    original NanoAODv15.root
        -> add_jetid_v15.py
        -> originalNanoAODv15_jetId.root

Then use the *_jetId.root files as input to post_proc.py.
"""

import os
from argparse import ArgumentParser

from PhysicsTools.NanoAODTools.postprocessing.framework.postprocessor import PostProcessor
from PhysicsTools.NATModules.modules.jetId import jetId


def main():
    parser = ArgumentParser(description="Add Jet_jetId branch to NanoAODv15 samples")

    parser.add_argument(
        "-i", "--infiles",
        nargs="+",
        required=True,
        help="Input NanoAOD root file(s). Can be local, /eos path, or root:// path."
    )

    parser.add_argument(
        "-o", "--outdir",
        default=".",
        help="Output directory. For Condor use '.', then copy output in the wrapper."
    )

    parser.add_argument(
        "-m", "--maxevts",
        type=int,
        default=-1,
        help="Maximum number of events. Use -1 to process all events."
    )

    args = parser.parse_args()

    # 2024 NanoAODv15 jet ID JSON.
    # This is the same type of path used in the official example.
    json_jetid = (
        "/cvmfs/cms-griddata.cern.ch/cat/metadata/JME/"
        "Run3-24CDEReprocessingFGHIPrompt-Summer24-NanoAODv15/"
        "latest/jetid.json.gz"
    )

    if not os.path.exists(json_jetid):
        raise RuntimeError(f"JetID JSON does not exist: {json_jetid}")

    print("[add_jetid_2024] Input files:")
    for f in args.infiles:
        print("  ", f)

    print("[add_jetid_2024] Output directory:", args.outdir)
    print("[add_jetid_2024] JetID JSON:", json_jetid)
    print("[add_jetid_2024] jetType: AK4PUPPI")

    max_entries = args.maxevts if args.maxevts > 0 else None

    modules = [
        jetId(json_jetid, jetType="AK4PUPPI")
    ]

    # Important:
    # cut=None means do not drop any event.
    # This preprocessing step should only add Jet_jetId, not skim events.
    p = PostProcessor(
        args.outdir,
        args.infiles,
        cut=None,
        branchsel=None,
        modules=modules,
        maxEntries=max_entries,
        postfix="_jetId",
        outputbranchsel=None,
        provenance=True,
        prefetch=True,
        longTermCache=True
    )

    p.run()


if __name__ == "__main__":
    main()