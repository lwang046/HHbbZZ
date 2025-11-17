import glob
import os
import correctionlib._core as core
import numpy as np

# ======================= 1. 定义 JSON 目录和确切的修正名称 (已更新为2023BPix) =======================
# 我们根据之前的调试结果，指向2023年BPix时期的JME目录
base_dir = "/cvmfs/cms.cern.ch/rsync/cms-nanoAOD/jsonpog-integration/POG/JME/2023_Summer23BPix"
# 这是该目录下JER对应的标准名称
sf_name  = "Summer23BPixPrompt23_RunD_JRV1_MC_ScaleFactor_AK4PFPuppi"
res_name = "Summer23BPixPrompt23_RunD_JRV1_MC_PtResolution_AK4PFPuppi"

# ======================= 2. 查找并加载修正的辅助函数 (无需修改) =======================
def find_and_load_corr(target_name):
    """在目录中查找包含特定名称的JSON文件，并返回修正对象"""
    for f_path in sorted(glob.glob(os.path.join(base_dir, "*.json.gz"))):
        try:
            cset = core.CorrectionSet.from_file(f_path)
            if target_name in cset:
                print(f"成功! 在文件 '{os.path.basename(f_path)}' 中找到 '{target_name}'。")
                return cset[target_name]
        except Exception:
            continue
    print(f"错误: 在 '{base_dir}' 目录下的任何JSON文件中都找不到 '{target_name}'。")
    return None

# ======================= 3. 定义要验证的喷注和事件信息 (已从您的日志中提取) =======================
# 数据来自 Event 89 的日志
jets_to_validate = [
    # --- Jet 0 ---
    {"name": "Jet 0", "JetPt": 73.00782754, "JetEta": -0.32824707, "GenPt": 67.33900452, "ExpectedPt": 73.24024928},
    # --- Jet 1 ---
    {"name": "Jet 1", "JetPt": 54.00312692, "JetEta": 0.40838623, "GenPt": 44.58179092, "ExpectedPt": 54.34229502},
    # --- Jet 2 ---
    {"name": "Jet 2", "JetPt": 41.11736051, "JetEta": -2.35644531, "GenPt": 37.00774765, "ExpectedPt": 41.35571806},
    # --- Jet 3 ---
    {"name": "Jet 3", "JetPt": 37.54931823, "JetEta": 0.97436523, "GenPt": 34.13050842, "ExpectedPt": 37.63136966},
    # --- Jet 4 ---
    {"name": "Jet 4", "JetPt": 18.52328103, "JetEta": 0.20919800, "GenPt": 16.35919571, "ExpectedPt": 18.60335218},
]

# 事件级别的通用信息
event_info = {
    "EventID": 89,
    "Rho": 24.83956528
}

# ======================= 4. 执行验证 (无需修改) =======================
print("\n开始批量验证...")

# 加载一次修正对象
corr_sf = find_and_load_corr(sf_name)
corr_res = find_and_load_corr(res_name)

if corr_sf is None or corr_res is None:
    print("错误：未能加载所有必要的修正，验证中止。")
else:
    # 遍历所有待验证的喷注
    for jet_data in jets_to_validate:
        print(f"\n\n--- Validating {jet_data['name']} (Event {event_info['EventID']}) ---")
        
        # 提取输入值 (注意：JetPt 使用的是 JEC 修正后的 pt_JEC)
        eta_val = float(jet_data['JetEta'])
        pt_val  = float(jet_data['JetPt'])
        gen_pt_val = float(jet_data['GenPt'])
        rho_val = float(event_info['Rho'])
        event_id = int(event_info['EventID'])
        
        # --- 步骤 A: 计算 ScaleFactor 和 PtResolution ---
        # CORRECTED: 根据 correction summary 的要求，为 SF 的计算加入了 pt_val
        sf_val = corr_sf.evaluate(eta_val, pt_val, "nom")
        res_val = corr_res.evaluate(eta_val, pt_val, rho_val)
        print(f"  [FACTORS] ScaleFactor: {sf_val:<10.4f}  PtResolution: {res_val:<10.8f}")

        # --- 步骤 B: 计算 Smear Factor (与 jetCorr.py 中的逻辑完全一致) ---
        smear_factor = 1.0
        if gen_pt_val > 0:
            print(f"  [SMEARING] Method: Stochastic (using GenJet match)")
            smear_factor = 1.0 + (sf_val - 1.0) * (pt_val - gen_pt_val) / pt_val
        elif sf_val > 1:
            # 注意：这个分支在这个测试中不会被走到，因为所有喷注都有GenJet匹配
            sigma = res_val * np.sqrt(max(0, sf_val**2 - 1))
            # 使用一个固定的随机种子来保证结果可复现
            np.random.seed(int(event_id + (eta_val + 5.0) * 10000 + (pt_val*100)))
            smear_factor = np.random.normal(1.0, sigma)
        
        # --- 步骤 C: 计算并验证最终的 Pt ---
        final_pt = pt_val * smear_factor
        expected_pt = jet_data['ExpectedPt']
        diff = final_pt - expected_pt
        
        print(f"\n  [OUTPUT] Calculated Pt: {final_pt:<10.8f}")
        print(f"           Expected Pt  : {expected_pt:<10.8f}")
        print(f"           Difference   : {diff:<.10f}")
        
        # 检查验证是否成功
        if abs(diff) < 1e-6:
            print("  [STATUS] ✅ VERIFICATION SUCCESSFUL")
        else:
            print("  [STATUS] ❌ VERIFICATION FAILED")

print("\n\n批量验证完成。")
