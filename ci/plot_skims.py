#!/usr/bin/env python3
"""Overlay histograms of key distributions in the base-branch and PR skims.

Usage: plot_skims.py REF_DIR NEW_DIR [--tree Events] [--outdir plots] [--summary summary.md]
Writes one PNG per sample and variable, one multi-page PDF per sample, and a markdown
table of entries and means. Branches missing from both files are skipped.
"""
import argparse
from pathlib import Path

import awkward as ak
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import uproot
from matplotlib.backends.backend_pdf import PdfPages

# Analysis code fills these with -999 (or similar) when an object is missing.
SENTINEL = -900.0

# (name, x-axis label, bin edges); a tuple name is summed per event.
VARIABLES = [
    ("ngoodJets", "number of good jets", np.arange(-0.5, 10.5)),
    ("njets_pt30_eta4p7", "number of jets (pT>30, |eta|<4.7)", np.arange(-0.5, 10.5)),
    (("nTightEle", "nTightMu"), "number of tight leptons", np.arange(-0.5, 8.5)),
    ("nTightEle", "number of tight electrons", np.arange(-0.5, 8.5)),
    ("nTightMu", "number of tight muons", np.arange(-0.5, 8.5)),
    ("pTj1", "leading jet pT [GeV]", np.linspace(0, 300, 31)),
    ("pTj2", "subleading jet pT [GeV]", np.linspace(0, 200, 21)),
    ("goodJet_pt", "good jet pT, all jets [GeV]", np.linspace(0, 300, 31)),
    ("pTL1", "lepton 1 pT [GeV]", np.linspace(0, 200, 41)),
    ("pTL2", "lepton 2 pT [GeV]", np.linspace(0, 150, 31)),
    ("pTL3", "lepton 3 pT [GeV]", np.linspace(0, 120, 25)),
    ("pTL4", "lepton 4 pT [GeV]", np.linspace(0, 100, 21)),
    ("btagger1_PN", "jet 1 PNet b score", np.linspace(0, 1, 26)),
    ("btagger2_PN", "jet 2 PNet b score", np.linspace(0, 1, 26)),
    ("btagger1_UPT", "jet 1 UParT b score", np.linspace(0, 1, 26)),
    ("btagger2_UPT", "jet 2 UParT b score", np.linspace(0, 1, 26)),
    ("btagger1_RPT", "jet 1 RobustParT b score", np.linspace(0, 1, 26)),
    ("btagger2_RPT", "jet 2 RobustParT b score", np.linspace(0, 1, 26)),
    ("btagger1_DJ", "jet 1 DeepJet b score", np.linspace(0, 1, 26)),
    ("btagger2_DJ", "jet 2 DeepJet b score", np.linspace(0, 1, 26)),
    ("goodJet_btagRPT", "good jet RobustParT b score, all jets", np.linspace(0, 1, 26)),
    ("goodJet_btagUPT", "good jet UParT b score, all jets", np.linspace(0, 1, 26)),
    ("mass4l", "m4l [GeV]", np.linspace(70, 870, 41)),
    ("massZ1", "mZ1 [GeV]", np.linspace(40, 120, 41)),
    ("massZ2", "mZ2 [GeV]", np.linspace(0, 120, 31)),
    ("invjj", "mjj [GeV]", np.linspace(0, 400, 41)),
]


def var_key(name):
    return "+".join(name) if isinstance(name, tuple) else name


def values(tree, name):
    """Flat numpy array of the variable, sentinels removed; None if a branch is missing."""
    names = name if isinstance(name, tuple) else (name,)
    if any(n not in tree for n in names):
        return None
    arrs = [tree[n].array(library="ak") for n in names]
    arr = arrs[0] if len(arrs) == 1 else sum(arrs[1:], arrs[0])
    flat = ak.to_numpy(ak.flatten(arr, axis=None)).astype(np.float64)
    return flat[np.isfinite(flat) & (flat > SENTINEL)]


def plot_one(ref, new, label, edges, title):
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(6, 5.5), sharex=True, gridspec_kw={"height_ratios": [3, 1], "hspace": 0.05}
    )
    counts = {}
    for side, vals, color in (("base", ref, "black"), ("PR", new, "tab:red")):
        if vals is None:
            continue
        h, _ = np.histogram(np.clip(vals, edges[0], np.nextafter(edges[-1], edges[0])), bins=edges)
        counts[side] = h
        top.stairs(h, edges, color=color, linewidth=1.5,
                   label=f"{side}: {len(vals)} entries, mean {vals.mean():.3g}" if len(vals) else f"{side}: 0 entries")
    top.set_ylabel("entries (overflow in last bin)")
    top.set_title(title, fontsize=9)
    top.legend(fontsize=8)

    if "base" in counts and "PR" in counts:
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(counts["base"] > 0, counts["PR"] / counts["base"], np.nan)
            err = np.where(counts["base"] > 0, np.sqrt(counts["PR"]) / counts["base"], np.nan)
        centers = 0.5 * (edges[1:] + edges[:-1])
        bottom.errorbar(centers, ratio, yerr=err, fmt="o", color="tab:red", markersize=3)
    bottom.axhline(1, color="gray", linestyle="--", linewidth=1)
    bottom.set_ylim(0.5, 1.5)
    bottom.set_ylabel("PR / base")
    bottom.set_xlabel(label)
    return fig


def summarize(vals):
    if vals is None:
        return "missing"
    return f"{len(vals)} / {vals.mean():.4g}" if len(vals) else "0 / -"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ref_dir", type=Path)
    p.add_argument("new_dir", type=Path)
    p.add_argument("--tree", default="Events")
    p.add_argument("--outdir", type=Path, default=Path("plots"))
    p.add_argument("--summary", type=Path, default=Path("plots_summary.md"))
    args = p.parse_args()

    ref_files = sorted(args.ref_dir.glob("*.root"))
    if not ref_files:
        raise FileNotFoundError(f"no .root files in {args.ref_dir}")
    args.outdir.mkdir(parents=True, exist_ok=True)

    out = ["# Distributions: base vs PR", "",
           "Plots are in the `skim-comparison` artifact under `plots/`. Cells: entries / mean.", ""]
    for ref_path in ref_files:
        new_path = args.new_dir / ref_path.name
        if not new_path.exists():
            raise FileNotFoundError(f"missing new output {new_path}")
        sample = ref_path.stem
        sample_dir = args.outdir / sample
        sample_dir.mkdir(exist_ok=True)
        ref_tree, new_tree = uproot.open(ref_path)[args.tree], uproot.open(new_path)[args.tree]

        out += [f"## {sample}", "", "| variable | base | PR |", "|---|---|---|"]
        with PdfPages(args.outdir / f"{sample}.pdf") as pdf:
            for name, label, edges in VARIABLES:
                ref, new = values(ref_tree, name), values(new_tree, name)
                if ref is None and new is None:
                    continue
                key = var_key(name)
                fig = plot_one(ref, new, label, edges, f"{sample}: {key}")
                fig.savefig(sample_dir / f"{key}.png", dpi=110, bbox_inches="tight")
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
                out.append(f"| {key} | {summarize(ref)} | {summarize(new)} |")
        out.append("")

    text = "\n".join(out)
    args.summary.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
