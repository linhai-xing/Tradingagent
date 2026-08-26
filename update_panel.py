"""Update panel.json with agent overrides and recalculate votes."""
import json, os, sys

CACHE = r"C:\Users\72955\.claude\plugins\cache\uzi-skill\stock-deep-analyzer\3.9.0\skills\deep-analysis\scripts\.cache\002436.SZ"

with open(os.path.join(CACHE, "panel.json"), encoding="utf-8") as f:
    panel = json.load(f)

# Agent overrides from 4-agent parallel analysis
overrides = {}
# Value + Growth
overrides["buffett"] = ("bearish", 5)
overrides["graham"] = ("bearish", 12)
overrides["fisher"] = ("bearish", 32)
overrides["munger"] = ("bearish", 10)
overrides["templeton"] = ("bearish", 16)
overrides["klarman"] = ("bearish", 0)
overrides["lynch"] = ("neutral", 38)
overrides["oneill"] = ("bullish", 78)
overrides["thiel"] = ("bearish", 3)
overrides["wood"] = ("bullish", 85)
overrides["andreessen"] = ("bearish", 2)
# Macro + Technical
overrides["ray_dalio"] = ("bearish", 18)
overrides["george_soros"] = ("bullish", 75)
overrides["stanley_druckenmiller"] = ("bullish", 68)
overrides["paul_tudor_jones"] = ("neutral", 52)
overrides["jim_simons"] = ("neutral", 55)
overrides["michael_burry"] = ("bearish", 10)
overrides["bill_ackman"] = ("neutral", 40)
overrides["mark_minervini"] = ("bullish", 72)
# China value + quant
overrides["duan_yongping"] = ("bearish", 15)
overrides["dan_bin"] = ("bearish", 12)
overrides["lin_yuan"] = ("bearish", 8)
overrides["li_lu"] = ("bearish", 18)
overrides["zhang_lei"] = ("neutral", 42)
overrides["qiu_guolu"] = ("bearish", 6)
overrides["feng_liu"] = ("bearish", 22)
overrides["simons_renaissance"] = ("bearish", 28)
overrides["ge_weidong"] = ("neutral", 40)
# Youzi
overrides["zhao_laoge"] = ("bullish", 72)
overrides["chaogu_yangjia"] = ("bearish", 28)
overrides["zuoshou_xinyi"] = ("neutral", 45)
overrides["xiao_eyu"] = ("bullish", 78)
overrides["fang_xinxia"] = ("bullish", 82)
overrides["niepan_zhongsheng"] = ("neutral", 50)
overrides["tuixue_chaogu"] = ("neutral", 40)
overrides["beijing_chaogu"] = ("bullish", 75)
overrides["guhai_zeiwang"] = ("bullish", 68)
overrides["zhang_mengzhu"] = ("bullish", 80)
overrides["xuxiang"] = ("bearish", 18)
overrides["zhuming_cike"] = ("bearish", 30)
overrides["rui_hexian"] = ("bearish", 25)
overrides["gerou_rong"] = ("bearish", 22)
overrides["huanle_hai"] = ("bullish", 75)
overrides["long_feihu"] = ("bullish", 70)
overrides["linghu_chong"] = ("bullish", 72)
overrides["sunge"] = ("neutral", 50)
overrides["zhiye_chaoshou"] = ("neutral", 48)
overrides["qiaobangzhu"] = ("neutral", 50)
overrides["chengdou_xi"] = ("neutral", 50)
overrides["ziyou_chaogu"] = ("neutral", 42)

# Create id mapping: rule engine might use different ids
id_map = {}
for inv in panel["investors"]:
    iid = inv["investor_id"]
    id_map[iid] = inv

# Apply overrides
applied = 0
for iid, (signal, score) in overrides.items():
    if iid in id_map:
        id_map[iid]["signal"] = signal
        id_map[iid]["score"] = score
        id_map[iid]["agent_reviewed"] = True
        applied += 1
    else:
        pass  # ID not found in panel, may use different naming

print(f"Applied {applied} overrides out of {len(overrides)} attempted")

# Recalculate distributions
signals = [inv.get("signal", "skip") for inv in panel["investors"]]
panel["signal_distribution"] = {
    "bullish": signals.count("bullish"),
    "neutral": signals.count("neutral"),
    "bearish": signals.count("bearish"),
    "skip": signals.count("skip"),
}

votes = []
for inv in panel["investors"]:
    s = inv.get("signal", "skip")
    score = inv.get("score", 0)
    if s == "skip":
        votes.append("skip")
    elif s == "bullish":
        if score >= 75:
            votes.append("strongly_buy")
        elif score >= 60:
            votes.append("buy")
        else:
            votes.append("watch")
    elif s == "bearish":
        if score <= 15:
            votes.append("avoid")
        else:
            votes.append("wait")
    else:
        votes.append("wait")

panel["vote_distribution"] = {
    "strongly_buy": votes.count("strongly_buy"),
    "buy": votes.count("buy"),
    "watch": votes.count("watch"),
    "wait": votes.count("wait"),
    "avoid": votes.count("avoid"),
    "n_a": 0,
    "skip": votes.count("skip"),
}

scored = [inv.get("score", 0) for inv in panel["investors"] if inv.get("signal", "skip") != "skip"]
panel["panel_consensus"] = round(sum(scored) / len(scored), 1) if scored else 0

with open(os.path.join(CACHE, "panel.json"), "w", encoding="utf-8") as f:
    json.dump(panel, f, ensure_ascii=False, indent=2)

print(f"Panel: {len(panel['investors'])} investors")
print(f"Consensus: {panel['panel_consensus']}")
print(f"Signals: {panel['signal_distribution']}")
print(f"Votes: {panel['vote_distribution']}")
