#!/usr/bin/env python3
# 2026 월드컵 몬테카를로 시뮬레이터 — FIFA 랭킹·최근 폼·시장가치 합성 전력 점수 기반 (표준 라이브러리만 사용)
import json
import math
import os
import random
import time
from itertools import combinations

SEED = 42
ITERATIONS = 10_000

# 경기 모델 파라미터 — 경기당 평균 총득점 2.5~2.8골 목표로 캘리브레이션
# (1차 실행 BASE=1.26 → 2.778골: 범위 상단이라 1.22로 하향, 2차 실행 2.69골 — 최근 월드컵 실측 2.64~2.69골대에 수렴)
BASE_GOALS = 1.22
ALPHA = 1.15

# 합성 전력 점수 가중치 (근거는 JSON model.weights에 명시)
W_RANK = 0.55
W_FORM = 0.20
W_VALUE = 0.25

GENERATED_ON = "2026-06-07"
KOREA = "대한민국"

# ── 입력 데이터 (조사 결과 그대로, 수치 임의 생성 금지) ──────────────────────
# (한글명, 영문명, 조, FIFA랭킹, FIFA포인트) — FIFA/Coca-Cola 랭킹 2026-04-01 에디션
TEAMS_RAW = [
    ("멕시코", "Mexico", "A", 15, 1681.03),
    ("남아프리카공화국", "South Africa", "A", 60, 1429.73),
    ("대한민국", "South Korea", "A", 25, 1588.66),
    ("체코", "Czechia", "A", 41, 1501.38),
    ("캐나다", "Canada", "B", 30, 1556.48),
    ("스위스", "Switzerland", "B", 19, 1649.40),
    ("카타르", "Qatar", "B", 55, 1454.96),
    ("보스니아 헤르체고비나", "Bosnia and Herzegovina", "B", 65, 1385.84),
    ("브라질", "Brazil", "C", 6, 1761.16),
    ("모로코", "Morocco", "C", 8, 1755.87),
    ("스코틀랜드", "Scotland", "C", 43, 1498.35),
    ("아이티", "Haiti", "C", 83, 1291.71),
    ("미국", "United States", "D", 16, 1673.13),
    ("파라과이", "Paraguay", "D", 40, 1503.50),
    ("호주", "Australia", "D", 27, 1580.67),
    ("튀르키예", "Türkiye", "D", 22, 1599.04),
    ("독일", "Germany", "E", 10, 1730.37),
    ("에콰도르", "Ecuador", "E", 23, 1594.78),
    ("코트디부아르", "Ivory Coast", "E", 34, 1532.98),
    ("퀴라소", "Curaçao", "E", 82, 1294.65),
    ("네덜란드", "Netherlands", "F", 7, 1757.87),
    ("일본", "Japan", "F", 18, 1660.43),
    ("스웨덴", "Sweden", "F", 38, 1514.77),
    ("튀니지", "Tunisia", "F", 44, 1483.05),
    ("벨기에", "Belgium", "G", 9, 1734.71),
    ("이란", "Iran", "G", 21, 1615.30),
    ("이집트", "Egypt", "G", 29, 1563.24),
    ("뉴질랜드", "New Zealand", "G", 85, 1281.57),
    ("스페인", "Spain", "H", 2, 1876.40),
    ("우루과이", "Uruguay", "H", 17, 1673.07),
    ("사우디아라비아", "Saudi Arabia", "H", 61, 1421.43),
    ("카보베르데", "Cape Verde", "H", 69, 1366.13),
    ("프랑스", "France", "I", 1, 1877.32),
    ("세네갈", "Senegal", "I", 14, 1688.99),
    ("노르웨이", "Norway", "I", 31, 1550.94),
    ("이라크", "Iraq", "I", 57, 1447.14),
    ("아르헨티나", "Argentina", "J", 3, 1874.81),
    ("오스트리아", "Austria", "J", 24, 1593.45),
    ("알제리", "Algeria", "J", 28, 1564.26),
    ("요르단", "Jordan", "J", 63, 1391.45),
    ("포르투갈", "Portugal", "K", 5, 1763.83),
    ("콜롬비아", "Colombia", "K", 13, 1693.09),
    ("우즈베키스탄", "Uzbekistan", "K", 50, 1465.34),
    ("DR콩고", "DR Congo", "K", 46, 1478.35),
    ("잉글랜드", "England", "L", 4, 1825.97),
    ("크로아티아", "Croatia", "L", 11, 1717.07),
    ("가나", "Ghana", "L", 74, 1346.31),
    ("파나마", "Panama", "L", 33, 1540.64),
]

# 상위 8개국 상세 데이터 — 최근 10경기(승/무/패), 스쿼드 시장가치(MEUR), 부상 페널티
# valueMEUR=None: EUR 확정치 미확보(USD 2차 보도만 존재) → 상세 코호트 평균 norm 값으로 대체(imputed)
# injury: 확인된 주전 부상 보도가 있는 잉글랜드(Livramento·Colwill 제외 등)만 0.02, 나머지는 데이터 미확보라 0
DETAIL = {
    "France": {"w": 8, "d": 1, "l": 1, "valueMEUR": 1520.0, "injury": 0.0, "record": "8승 1무 1패"},
    "Spain": {"w": 7, "d": 3, "l": 0, "valueMEUR": None, "injury": 0.0, "record": "7승 3무"},
    "Argentina": {"w": 8, "d": 1, "l": 1, "valueMEUR": 817.0, "injury": 0.0, "record": "8승 1무 1패"},
    "England": {"w": 7, "d": 1, "l": 2, "valueMEUR": None, "injury": 0.02, "record": "7승 1무 2패"},
    "Portugal": {"w": 6, "d": 3, "l": 1, "valueMEUR": 1020.0, "injury": 0.0, "record": "6승 3무 1패"},
    "Brazil": {"w": 6, "d": 1, "l": 3, "valueMEUR": 912.2, "injury": 0.0, "record": "6승 1무 3패"},
    "Netherlands": {"w": 7, "d": 3, "l": 0, "valueMEUR": 837.2, "injury": 0.0, "record": "7승 3무"},
    "Morocco": {"w": 8, "d": 2, "l": 0, "valueMEUR": 488.2, "injury": 0.0, "record": "8승 2무"},
}

GROUP_LETTERS = "ABCDEFGHIJKL"
BY_KR = {t[0]: {"nameEn": t[1], "group": t[2], "fifaRank": t[3], "fifaPoints": t[4]} for t in TEAMS_RAW}
EN2KR = {t[1]: t[0] for t in TEAMS_RAW}
PTS_FIFA = {t[0]: t[4] for t in TEAMS_RAW}
GROUPS = {g: [t[0] for t in TEAMS_RAW if t[2] == g] for g in GROUP_LETTERS}
GROUP_FIXTURES = {g: list(combinations(GROUPS[g], 2)) for g in GROUP_LETTERS}

# ── 32강 대진 (조사 데이터 bracketNotes 매치 73~88 그대로) ───────────────────
# ("W", 조) = 조 1위, ("R", 조) = 조 2위, ("T", 매치번호) = 3위 진출팀 슬롯
R32_DEF = [
    (73, ("R", "A"), ("R", "B")),
    (74, ("W", "E"), ("T", 74)),
    (75, ("W", "F"), ("R", "C")),
    (76, ("W", "C"), ("R", "F")),
    (77, ("W", "I"), ("T", 77)),
    (78, ("R", "E"), ("R", "I")),
    (79, ("W", "A"), ("T", 79)),
    (80, ("W", "L"), ("T", 80)),
    (81, ("W", "D"), ("T", 81)),
    (82, ("W", "G"), ("T", 82)),
    (83, ("R", "K"), ("R", "L")),
    (84, ("W", "H"), ("R", "J")),
    (85, ("W", "B"), ("T", 85)),
    (86, ("W", "J"), ("R", "H")),
    (87, ("W", "K"), ("T", 87)),
    (88, ("R", "D"), ("R", "G")),
]
# 3위 슬롯별 허용 조 풀 (조사 데이터의 가능 후보 목록) — Annex C 495조합표의 근사
THIRD_POOLS = {
    74: set("ABCDF"),
    77: set("CDFGH"),
    79: set("CEFHI"),
    80: set("EHIJK"),
    81: set("BEFIJ"),
    82: set("AEHIJ"),
    85: set("EFGIJ"),
    87: set("DEIJL"),
}
# 16강 이후 대진은 조사 데이터에 없음 → 32강 승자를 매치 번호 순서대로 페어링하는 근사
R16_PAIRS = [(73, 74), (75, 76), (77, 78), (79, 80), (81, 82), (83, 84), (85, 86), (87, 88)]


# ── 합성 전력 점수 ───────────────────────────────────────────────────────────
def build_strengths():
    pts_all = [t[4] for t in TEAMS_RAW]
    pmin, pmax = min(pts_all), max(pts_all)
    norm_rank = {t[0]: (t[4] - pmin) / (pmax - pmin) for t in TEAMS_RAW}

    vals = [d["valueMEUR"] for d in DETAIL.values() if d["valueMEUR"] is not None]
    lmin, lmax = math.log(min(vals)), math.log(max(vals))
    vnorm = {}
    for en, d in DETAIL.items():
        if d["valueMEUR"] is not None:
            vnorm[en] = (math.log(d["valueMEUR"]) - lmin) / (lmax - lmin)
        else:
            vnorm[en] = None
    vmean = sum(v for v in vnorm.values() if v is not None) / len(vals)

    raw = {}
    comp = {}
    for en, d in DETAIL.items():
        kr = EN2KR[en]
        form = (3 * d["w"] + d["d"]) / 30.0
        v = vnorm[en] if vnorm[en] is not None else vmean
        raw[kr] = W_RANK * norm_rank[kr] + W_FORM * form + W_VALUE * v - d["injury"]
        comp[kr] = {"ranking": norm_rank[kr], "form": form, "marketValue": v, "injuryPenalty": d["injury"]}

    cohort = list(raw)
    # 커버리지 보정상수: 상세 8개국 평균 점수 = 같은 8개국 랭킹 단독 평균이 되도록 보정
    # (데이터가 있다는 이유로 코호트 전체가 랭킹 단독 40개국 대비 불리해지는 비대칭 제거)
    C = sum(norm_rank[k] for k in cohort) / len(cohort) - sum(raw.values()) / len(cohort)

    S = {}
    teams_out = []
    for kr, en, g, rank, fpts in TEAMS_RAW:
        if kr in raw:
            S[kr] = raw[kr] + C
            d = DETAIL[en]
            coverage = "full" if d["valueMEUR"] is not None else "detail-value-imputed"
            entry = {
                "name": kr, "nameEn": en, "group": g, "fifaRank": rank, "fifaPoints": fpts,
                "strengthScore": round(S[kr], 4),
                "components": {k: round(v, 4) for k, v in comp[kr].items()},
                "dataCoverage": coverage,
                "formRecord": d["record"],
                "marketValueMEUR": d["valueMEUR"],
            }
        else:
            S[kr] = norm_rank[kr]
            entry = {
                "name": kr, "nameEn": en, "group": g, "fifaRank": rank, "fifaPoints": fpts,
                "strengthScore": round(S[kr], 4),
                "components": {"ranking": round(norm_rank[kr], 4), "form": None, "marketValue": None, "injuryPenalty": 0.0},
                "dataCoverage": "ranking-only",
            }
        teams_out.append(entry)
    return S, teams_out, C, vmean


# ── 경기 모델 ────────────────────────────────────────────────────────────────
def poisson(lam):
    # Knuth 알고리즘
    L = math.exp(-lam)
    p = 1.0
    k = 0
    while True:
        p *= random.random()
        if p <= L:
            return k
        k += 1


def lambdas(sa, sb):
    return BASE_GOALS * math.exp(ALPHA * (sa - sb)), BASE_GOALS * math.exp(ALPHA * (sb - sa))


def knockout(a, b, S):
    # 반환: (승자, 정규 90분 총득점)
    la, lb = lambdas(S[a], S[b])
    ga, gb = poisson(la), poisson(lb)
    if ga != gb:
        return (a if ga > gb else b), ga + gb
    ea, eb = poisson(la / 3.0), poisson(lb / 3.0)  # 연장 30분 = 정규의 1/3
    if ea != eb:
        return (a if ea > eb else b), ga + gb
    pa = 0.5 + max(-0.15, min(0.15, 0.25 * (S[a] - S[b])))  # 승부차기: 전력차 소폭 반영
    return (a if random.random() < pa else b), ga + gb


def assign_third_slots(qualified):
    # 3위 8팀 → 8개 슬롯 이분 매칭 (Kuhn 증대경로). 매칭 불가 시 잔여 슬롯 임의 배정(폴백).
    slots = list(THIRD_POOLS)
    owner = {}

    def aug(g, seen):
        for sid in slots:
            if sid in seen or g not in THIRD_POOLS[sid]:
                continue
            seen.add(sid)
            if sid not in owner or aug(owner[sid], seen):
                owner[sid] = g
                return True
        return False

    unmatched = [g for g in sorted(qualified) if not aug(g, set())]
    if unmatched:
        free = [sid for sid in slots if sid not in owner]
        for g, sid in zip(unmatched, free):
            owner[sid] = g
    return owner, len(unmatched)


# ── 메인 시뮬레이션 ──────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    random.seed(SEED)
    S, teams_out, C, vmean = build_strengths()

    reach = {kr: {"r32": 0, "r16": 0, "qf": 0, "sf": 0, "final": 0, "champion": 0} for kr in S}
    pos = {g: {t: [0, 0] for t in GROUPS[g]} for g in GROUP_LETTERS}
    korea_exit = {"groupStage": 0, "r32": 0, "r16": 0, "qf": 0, "sf": 0, "runnerUp": 0, "champion": 0}
    korea_opps = [t for t in GROUPS["A"] if t != KOREA]
    korea_vs = {opp: {"win": 0, "draw": 0, "loss": 0} for opp in korea_opps}
    korea_finish = [0, 0, 0, 0]
    korea_third_adv = 0
    goals_total = 0
    match_total = 0
    fallback_iters = 0

    for _ in range(ITERATIONS):
        first, second, third = {}, {}, {}
        third_rows = []
        for g in GROUP_LETTERS:
            teams = GROUPS[g]
            pts = dict.fromkeys(teams, 0)
            gf = dict.fromkeys(teams, 0)
            ga = dict.fromkeys(teams, 0)
            for a, b in GROUP_FIXTURES[g]:
                la, lb = lambdas(S[a], S[b])
                x, y = poisson(la), poisson(lb)
                goals_total += x + y
                match_total += 1
                gf[a] += x; ga[a] += y
                gf[b] += y; ga[b] += x
                if x > y:
                    pts[a] += 3
                elif y > x:
                    pts[b] += 3
                else:
                    pts[a] += 1
                    pts[b] += 1
                if g == "A" and (a == KOREA or b == KOREA):
                    opp = b if a == KOREA else a
                    kg, og = (x, y) if a == KOREA else (y, x)
                    korea_vs[opp]["win" if kg > og else ("draw" if kg == og else "loss")] += 1
            # 조 순위: 승점→골득실→다득점→FIFA 포인트→난수 추첨 (컨덕트 스코어·헤드투헤드 미모델링)
            order = sorted(teams, key=lambda t: (pts[t], gf[t] - ga[t], gf[t], PTS_FIFA[t], random.random()), reverse=True)
            first[g], second[g] = order[0], order[1]
            t3 = order[2]
            third[g] = t3
            third_rows.append((pts[t3], gf[t3] - ga[t3], gf[t3], PTS_FIFA[t3], random.random(), g))
            pos[g][order[0]][0] += 1
            pos[g][order[1]][1] += 1
            if g == "A":
                korea_finish[order.index(KOREA)] += 1

        # 조 3위 상위 8팀: 승점→골득실→득점→FIFA 포인트(컨덕트 스코어 생략)→난수
        third_rows.sort(reverse=True)
        qualified = [r[5] for r in third_rows[:8]]
        if third["A"] == KOREA and "A" in qualified:
            korea_third_adv += 1

        owner, fb = assign_third_slots(qualified)
        if fb:
            fallback_iters += 1

        def slot_team(s):
            kind, key = s
            if kind == "W":
                return first[key]
            if kind == "R":
                return second[key]
            return third[owner[key]]

        # 32강
        w32 = {}
        in32 = set()
        for mid, sa, sb in R32_DEF:
            ta, tb = slot_team(sa), slot_team(sb)
            in32.add(ta)
            in32.add(tb)
            win, gls = knockout(ta, tb, S)
            goals_total += gls
            match_total += 1
            w32[mid] = win
        for t in in32:
            reach[t]["r32"] += 1
        l16 = [w32[mid] for mid, _, _ in R32_DEF]
        for t in l16:
            reach[t]["r16"] += 1

        # 16강 (32강 승자 순차 페어링 근사)
        l8 = []
        for m1, m2 in R16_PAIRS:
            win, gls = knockout(w32[m1], w32[m2], S)
            goals_total += gls
            match_total += 1
            l8.append(win)
        for t in l8:
            reach[t]["qf"] += 1

        # 8강
        l4 = []
        for i in range(0, 8, 2):
            win, gls = knockout(l8[i], l8[i + 1], S)
            goals_total += gls
            match_total += 1
            l4.append(win)
        for t in l4:
            reach[t]["sf"] += 1

        # 4강
        l2 = []
        sf_losers = []
        for i in range(0, 4, 2):
            a, b = l4[i], l4[i + 1]
            win, gls = knockout(a, b, S)
            goals_total += gls
            match_total += 1
            l2.append(win)
            sf_losers.append(b if win == a else a)
        for t in l2:
            reach[t]["final"] += 1

        # 3·4위전 (진출 확률에는 영향 없음 — 득점 통계 완결용)
        _, gls = knockout(sf_losers[0], sf_losers[1], S)
        goals_total += gls
        match_total += 1

        # 결승
        champ, gls = knockout(l2[0], l2[1], S)
        goals_total += gls
        match_total += 1
        reach[champ]["champion"] += 1

        # 한국 탈락 스테이지
        if KOREA not in in32:
            korea_exit["groupStage"] += 1
        elif KOREA not in set(l16):
            korea_exit["r32"] += 1
        elif KOREA not in set(l8):
            korea_exit["r16"] += 1
        elif KOREA not in set(l4):
            korea_exit["qf"] += 1
        elif KOREA not in set(l2):
            korea_exit["sf"] += 1
        elif KOREA != champ:
            korea_exit["runnerUp"] += 1
        else:
            korea_exit["champion"] += 1

    assert match_total == ITERATIONS * 104, match_total
    avg_goals = goals_total / match_total

    def p(c):
        return round(c / ITERATIONS, 4)

    round_probs = {kr: {k: p(v) for k, v in reach[kr].items()} for kr in S}
    champion_probs = sorted(
        [{"team": kr, "nameEn": BY_KR[kr]["nameEn"], "prob": p(reach[kr]["champion"])} for kr in S],
        key=lambda e: (-e["prob"], -PTS_FIFA[e["team"]]),
    )

    labels = {
        "groupStage": "조별리그 탈락", "r32": "32강 탈락", "r16": "16강 탈락",
        "qf": "8강 탈락", "sf": "4강 탈락(3·4위)", "runnerUp": "준우승", "champion": "우승",
    }
    best = max(korea_exit, key=korea_exit.get)
    korea = {
        "group": "A",
        "groupOpponents": korea_opps,
        "strengthScore": round(S[KOREA], 4),
        "advanceToR32Prob": p(reach[KOREA]["r32"]),
        "groupFinish": {
            "first": p(korea_finish[0]), "second": p(korea_finish[1]),
            "third": p(korea_finish[2]), "fourth": p(korea_finish[3]),
            "thirdAndAdvanced": p(korea_third_adv),
        },
        "groupMatches": [{"opponent": opp, **{k: p(v) for k, v in korea_vs[opp].items()}} for opp in korea_opps],
        "stageDistribution": {k: p(v) for k, v in korea_exit.items()},
        "mostLikelyOutcome": {"stage": best, "probability": p(korea_exit[best]), "label": labels[best]},
    }

    dh_cands = sorted((kr for kr in S if BY_KR[kr]["fifaRank"] >= 20 and kr != KOREA), key=lambda kr: -reach[kr]["qf"])
    dark_horses = {
        "criterion": "FIFA 랭킹 20위 밖(시드 상위권이 아닌) 팀 중 8강 진출 확률 상위 3팀 — 랭킹 시드 대비 토너먼트 진출 확률이 높은 팀 (한국은 별도 섹션이라 제외)",
        "teams": [
            {
                "team": kr, "nameEn": BY_KR[kr]["nameEn"], "group": BY_KR[kr]["group"],
                "fifaRank": BY_KR[kr]["fifaRank"], "strengthScore": round(S[kr], 4),
                "r32": p(reach[kr]["r32"]), "r16": p(reach[kr]["r16"]), "qf": p(reach[kr]["qf"]),
            }
            for kr in dh_cands[:3]
        ],
    }

    group_summaries = [
        {
            "group": g,
            "teams": sorted(
                [{"team": t, "first": p(pos[g][t][0]), "second": p(pos[g][t][1])} for t in GROUPS[g]],
                key=lambda e: -e["first"],
            ),
        }
        for g in GROUP_LETTERS
    ]

    model = {
        "strengthFormula": "S = 0.55·norm(fifaPoints) + 0.20·(최근 10경기 승점률) + 0.25·norm(log(시장가치 MEUR)) − 부상 페널티 + 커버리지 보정상수(상세 데이터 8개국에만 적용)",
        "weights": {
            "rank": {"value": W_RANK, "rationale": "FIFA 포인트는 수년치 공식 경기 결과를 누적 반영하는 가장 안정적인 단일 지표라 베이스로 최대 가중"},
            "form": {"value": W_FORM, "rationale": "최근 10경기는 현재 컨디션을 반영하지만 표본이 작고 친선전이 섞여 노이즈가 커서 보조 가중"},
            "value": {"value": W_VALUE, "rationale": "스쿼드 시장가치(로그 스케일)는 랭킹이 못 잡는 선수단 체급 차이의 대리 지표 — 랭킹 포인트가 거의 같은 1~3위(프랑스·스페인·아르헨티나)를 변별하는 핵심 항목"},
            "injuryPenalty": {"value": 0.02, "rationale": "확인된 주전 부상 보도가 있는 잉글랜드(Livramento·Colwill 제외, James·Spence 복귀 직후, Stones 피트니스 우려)에만 0.02 감점 — 타 팀은 부상 데이터 미확보라 0"},
            "coverageBiasCorrection": {"value": round(C, 4), "rationale": "상세 데이터 8개국의 평균 점수를 같은 8개국의 랭킹 단독 점수 평균과 일치시키는 상수 — 데이터가 있다는 이유로 코호트 전체가 랭킹 단독 40개국 대비 불리해지는 비대칭 제거 (코호트 내부 서열은 폼·시장가치·부상으로 결정)"},
        },
        "matchModel": f"lambda_A = {BASE_GOALS} × exp({ALPHA} × (S_A − S_B)) 양 팀 독립 Poisson(Knuth 샘플링), 동률 시 연장(λ×1/3 Poisson) → 승부차기(전력차 반영 0.5±0.15)",
        "limitations": [
            "폼·시장가치·부상은 FIFA 상위 8개국만 조사됨 — 나머지 40개국은 FIFA 랭킹 100%(dataCoverage: ranking-only). 9~16위권(독일·벨기에·크로아티아 등)의 폼·시장가치는 미반영이라 이들 점수는 상대적으로 보수적",
            f"스페인·잉글랜드 시장가치는 EUR 확정치 미확보(USD 2차 보도만) — 상세 코호트 평균 norm 값({round(vmean, 4)})으로 대체(imputed)",
            "부상 데이터는 잉글랜드만 확보 — 타 팀 페널티 0은 '부상 없음'이 아니라 '데이터 없음'",
            "팀 컨덕트 스코어(옐로·레드카드)는 데이터가 없어 조 순위·3위 비교 모두에서 모델링 불가 — 승점→골득실→다득점→FIFA 포인트→난수 추첨 순으로 대체. 조 내 동률 시 헤드투헤드 규정도 미적용",
            f"3위 8팀의 32강 슬롯 배정은 FIFA 규정 Annex C의 495가지 조합표 대신 '슬롯별 허용 조 풀 안 이분 매칭' 근사 — 매칭 실패 폴백 발생 {fallback_iters}/{ITERATIONS}회",
            "16강 이후 대진은 조사 데이터에 없어 32강 매치(73~88) 승자를 번호 순서대로 페어링(W73 vs W74, …)하는 근사 — 실제 FIFA 브래킷과 다를 수 있음",
            "미반영 변수: 감독 전술, 선수 컨디션·피로, 날씨·기온, 이동 거리, 홈 어드밴티지(개최 3국 미국·캐나다·멕시코 보정 없음), 승부차기 전문 능력",
            "프랑스 최근 10경기 중 코트디부아르전은 소스 상충(ESPN 1-2 패 vs 타 소스 0-0 무) — ESPN 표기(패) 채택",
            "avgGoalsPerMatch는 정규 90분 득점 기준(연장 득점 제외), 3·4위전 포함 104경기 전체 평균",
            "결과는 단정 예측이 아니라 시드 고정 몬테카를로의 확률 분포 — 모델 가정이 바뀌면 수치도 바뀜",
        ],
    }

    out = {
        "meta": {
            "seed": SEED,
            "iterations": ITERATIONS,
            "avgGoalsPerMatch": round(avg_goals, 3),
            "generatedOn": GENERATED_ON,
            "matchesPerIteration": 104,
            "baseGoals": BASE_GOALS,
            "alpha": ALPHA,
        },
        "model": model,
        "teams": teams_out,
        "championProbs": champion_probs,
        "roundProbs": round_probs,
        "korea": korea,
        "darkHorses": dark_horses,
        "groupSummaries": group_summaries,
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "worldcup-2026.json")
    out_path = os.path.normpath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    elapsed = time.time() - t0
    print(f"완료: {ITERATIONS}회, {elapsed:.1f}s, 출력 → {out_path}")
    print(f"경기당 평균 총득점(정규 90분): {avg_goals:.3f} (목표 2.5~2.8)")
    print("상위 8개국 전력 점수:")
    for e in sorted(teams_out, key=lambda x: -x["strengthScore"])[:10]:
        print(f"  {e['name']:<8} S={e['strengthScore']:.4f} coverage={e['dataCoverage']}")
    print("우승 확률 TOP5:")
    for e in champion_probs[:5]:
        print(f"  {e['team']:<8} {e['prob']*100:.1f}%")
    print("한국:", json.dumps(korea["stageDistribution"], ensure_ascii=False))
    print("한국 조별 경기:", json.dumps(korea["groupMatches"], ensure_ascii=False))
    print("다크호스:", json.dumps([t["team"] for t in dark_horses["teams"]], ensure_ascii=False))


if __name__ == "__main__":
    main()
