"""Build court_crosswalk_notes.csv: statutory effective dates of court establishments and renamings
(hand-written notes keyed by court_id_h, in Korean and English).

Sources: Act on the Establishment and Jurisdictional Districts of Courts at All Levels (`각급 법원의 설치와 관할구역에 관한 법률`,
      law ID 001709), addenda of each amending act and the history of Annex 2; Court Organization Act (`법원조직법`, law ID 001710),
      addenda of Act No. 13522; city-establishment acts (Act Nos. 6280 and 6928). Original texts checked at the
      National Law Information Center (2026-11-18/19).
Columns:
  court_id_h            harmonized id from build_courts.py (Korean; corresponds to court_ko in the release courts.csv)
  legal_start           statutory effective date (YYYY-MM-DD)
  legal_event           `설치` (established) / `승격` (elevated) / `전환` (converted) / `명칭변경` (renamed) /
                        `관할변경` (jurisdiction change) / `폐지` (abolished) / `미확인` (unconfirmed)
  predecessor, predecessor_en      predecessor court or body
  legal_basis, legal_basis_en      act number, promulgation date, addenda provision
  data_note, data_note_en          caveats for interpreting the panel (partial years, restated labels, double counting, etc.)
English statute names: `법원조직법` = Court Organization Act (official KLRI English title). Other act names are the
author's translation (EST).
`부칙` = Addenda, `단서` = proviso, `별표` = Annex.
python make_crosswalk_notes.py  →  data/series/court_crosswalk_notes.csv (merged directly by make_release.py)
"""
from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent / "data" / "series"
L = "각급법원설치법"
EST = "Act on the Establishment and Jurisdictional Districts of Courts at All Levels"  # author's translation
COA = "Court Organization Act"

rows = []


def add(ids, start, event, pred, basis, note, pred_en="", basis_en="", note_en=""):
    for i in ([ids] if isinstance(ids, str) else ids):
        rows.append(dict(court_id_h=i, legal_start=start, legal_event=event, predecessor=pred, predecessor_en=pred_en,
                         legal_basis=basis, legal_basis_en=basis_en, data_note=note, data_note_en=note_en))


# ── branch courts established after 2002 ──
add("수원지방법원/안산지원", "2002-09-01", "설치", "수원지방법원 본원·안산시법원·광명시법원 관할 일부",
    f"{L} 법률 제5432호(1997.12.13) 부칙 ① 단서(2001.1.29 개정)",
    "2002년 값은 9–12월(4개월)분 → 부분 연도",
    "Parts of the jurisdictions of the Suwon District Court (main court), Ansan Si Court and Gwangmyeong Si Court",
    f"{EST}, Act No. 5432 (1997-12-13), Addenda para. 1, proviso (as amended 2001-01-29)",
    "2002 values cover September–December only (partial year)")
add("의정부지방법원/고양지원", "2003-03-01", "설치", "서울지방법원 의정부지원·고양시법원",
    f"{L} 법률 제5432호(1997.12.13) 부칙 ① 단서(2001.1.29 개정)",
    "설치 당시 명칭 '서울지방법원 고양지원'(2004.2.1 의정부지방법원 소속). 2003년 값은 3–12월분. 2002년 소액 5,790은 2006년판이 고양지원 행에 실은 값으로, 2002년판(2절 p8)의 '고양시법원' 2002년 값과 같음 = 전신 고양시법원 사건(설치 전 재게재). 2002년판의 파주시법원 2,195도 2006년판과 같음",
    "Uijeongbu Branch Court of the Seoul District Court; Goyang Si Court",
    f"{EST}, Act No. 5432 (1997-12-13), Addenda para. 1, proviso (as amended 2001-01-29)",
    "Established as the Goyang Branch Court of the Seoul District Court; under the Uijeongbu District Court from 2004-02-01. 2003 values cover March–December. "
    "The 2002 small-claims value (5,790) is printed under this branch in the 2006 edition and equals the 2002 edition's 'Goyang Si Court' row for 2002 "
    "(2002 ed., 2절 p8): the predecessor Goyang Si Court's caseload restated before establishment")
add("대구지방법원/서부지원", "2007-03-01", "설치", "대구지방법원 본원 관할 일부",
    f"{L} 법률 제6923호(2003.7.18) 부칙 ①", "2007년 값은 3–12월분",
    "Part of the jurisdiction of the Daegu District Court (main court)",
    f"{EST}, Act No. 6923 (2003-07-18), Addenda para. 1", "2007 values cover March–December")
add("수원지방법원/안양지원", "2009-03-01", "설치", "수원지방법원 본원 관할 일부",
    f"{L} 법률 제7082호(2004.1.20) 부칙 제1조 단서",
    "2009년 값은 3–12월분. 2007년 민사단독 '200'은 2016판 OCR 오류(원문 '-', 안산지원 5,948을 5,748+200으로 분할 판독) → 정정",
    "Part of the jurisdiction of the Suwon District Court (main court)",
    f"{EST}, Act No. 7082 (2004-01-20), Addenda Art. 1, proviso",
    "2009 values cover March–December. A 2007 civil single-judge value of 200 was an OCR error in the 2016 edition (printed '-'; Ansan's 5,948 had been split into 5,748 + 200) and was corrected")
add("부산지방법원/서부지원", "2017-03-01", "설치", "부산지방법원 본원 관할 일부",
    f"{L} 법률 제11151호(2012.1.17) 부칙 제1조 단서", "2017년 값은 3–12월분",
    "Part of the jurisdiction of the Busan District Court (main court)",
    f"{EST}, Act No. 11151 (2012-01-17), Addenda Art. 1, proviso", "2017 values cover March–December")
add("의정부지방법원/남양주지원", "2022-03-01", "설치", "의정부지방법원 본원·남양주시법원",
    f"{L} 법률 제11623호(2013.1.23) 부칙 제1조 단서(2017.12.19 개정)",
    "법정 설치 2022.3.1이나 자료상 소액 2018–2021 값 존재: 2022–25판 Excel이 전신 남양주시법원 값을 남양주지원 행에 승계 표기한 것"
    "(남양주시법원 행과 값 동일) → 2018–2021 소액은 남양주시법원 행과 합산 시 이중계산 주의. 2022년 값은 3–12월분",
    "Uijeongbu District Court (main court); Namyangju Si Court",
    f"{EST}, Act No. 11623 (2013-01-23), Addenda Art. 1, proviso (as amended 2017-12-19)",
    "Legally established 2022-03-01, but small-claims values exist for 2018–2021: the 2022–2025 Excel editions restate the predecessor Namyangju Si Court under this branch (identical values). Do not add these rows to the Namyangju Si Court rows (double counting; dup_flag). 2022 values cover March–December")

# ── bankruptcy courts and high courts ──
add("서울회생법원", "2017-03-01", "설치", "서울중앙지방법원 파산부",
    f"{L} 법률 제14469호(2016.12.27) 부칙 제1조",
    "2017년 값은 3–12월분(시행일 전날 서울중앙지법 계속 사건은 서울회생법원으로 이관)",
    "Bankruptcy divisions of the Seoul Central District Court",
    f"{EST}, Act No. 14469 (2016-12-27), Addenda Art. 1",
    "2017 values cover March–December (cases pending at the Seoul Central District Court were transferred on the effective date)")
add(["수원회생법원", "부산회생법원"], "2023-03-01", "설치", "수원지방법원·부산지방법원 본원 파산부",
    f"{L} 법률 제19149호(2022.12.27) 부칙 제1조", "2023년 값은 3–12월분",
    "Bankruptcy divisions of the Suwon and Busan District Courts (main courts)",
    f"{EST}, Act No. 19149 (2022-12-27), Addenda Art. 1", "2023 values cover March–December")
add("수원고등법원", "2019-03-01", "설치", "서울고등법원 관할 일부(경기 남부)",
    f"{L} 법률 제12419호(2014.3.18) 부칙 제1조", "2019년 값은 3–12월분",
    "Part of the jurisdiction of the Seoul High Court (southern Gyeonggi)",
    f"{EST}, Act No. 12419 (2014-03-18), Addenda Art. 1", "2019 values cover March–December")
add("특허법원", "1998-03-01", "관할변경(2016-01-01)", "",
    f"설치: {L} 법률 제4766호(1994.7.27) 부칙 ①. 민사 항소 관할: 법원조직법 법률 제13522호(2015.12.1) 제28조의4제2호·부칙 제1조(2016.1.1 시행)",
    "민사본안 항소심 표 등장(2016~)은 법원 신설이 아니라 지식재산권 침해 민사사건 항소심 전속관할 신설 때문",
    "",
    f"Establishment: {EST}, Act No. 4766 (1994-07-27), Addenda para. 1. Civil appellate jurisdiction: {COA}, Act No. 13522 (2015-12-01), Art. 28-4(2) and Addenda Art. 1 (effective 2016-01-01)",
    "Appears in the civil appeal table from 2016 because it acquired exclusive appellate jurisdiction over IP-infringement civil cases, not because it was newly established")

# ── reorganization of the Seoul and Uijeongbu district courts (2004-02-01) ──
for c, p, pen in [("서울중앙지방법원", "서울지방법원 본원", "Seoul District Court (main court)"),
                  ("서울동부지방법원", "서울지방법원 동부지원", "Eastern Branch Court of the Seoul District Court"),
                  ("서울남부지방법원", "서울지방법원 남부지원", "Southern Branch Court of the Seoul District Court"),
                  ("서울북부지방법원", "서울지방법원 북부지원", "Northern Branch Court of the Seoul District Court"),
                  ("서울서부지방법원", "서울지방법원 서부지원", "Western Branch Court of the Seoul District Court"),
                  ("의정부지방법원", "서울지방법원 의정부지원", "Uijeongbu Branch Court of the Seoul District Court")]:
    nb = c == "서울북부지방법원"
    add(c, "2004-02-01", "승격", p,
        f"{L} 법률 제7082호(2004.1.20) 부칙 제1조·제2조",
        "2002–2003 값은 전신 지원(동일 관할)의 실적을 현 명칭으로 소급 표기한 것"
        + ("; 2014.3.1 관할구역 조정(법률 제11623호, 서울중앙지법·서울가정법원 관할 일부가 북부로 이관) → 수준 변화 가능" if nb else ""),
        pen, f"{EST}, Act No. 7082 (2004-01-20), Addenda Arts. 1–2",
        "2002–2003 values are those of the predecessor (same jurisdiction) restated under the current name"
        + ("; jurisdiction enlarged 2014-03-01 (Act No. 11623: parts of the Seoul Central District Court and Seoul Family Court jurisdictions transferred) — possible level shift" if nb else ""))

# ── conversions to family courts ──
add("부산가정법원", "2011-04-11", "전환", "부산지방법원 가정지원(2001.3.1 설치, 법률 제6409호)",
    f"{L} 법률 제10536호(2011.4.5) 부칙 제1조 단서",
    "2002–2010 값은 전신 부산지방법원 가정지원 실적의 소급 표기",
    "Family Branch of the Busan District Court (established 2001-03-01, Act No. 6409)",
    f"{EST}, Act No. 10536 (2011-04-05), Addenda Art. 1, proviso",
    "2002–2010 values are those of the predecessor family branch restated under the current name")
G_EN = {"대전": "Daejeon", "대구": "Daegu", "광주": "Gwangju", "인천": "Incheon", "울산": "Ulsan", "수원": "Suwon"}
for g, pred, pen, start, basis, ben in [
    ("대전", "대전지방법원 가정지원(2007.2.1 설치, 법률 제7726호) 및 본원", "Family Branch of the Daejeon District Court (established 2007-02-01, Act No. 7726) and the main court",
     "2012-03-01", "법률 제10536호(2011.4.5) 부칙 제1조 단서", "Act No. 10536 (2011-04-05), Addenda Art. 1, proviso"),
    ("대구", "대구지방법원 가정지원(2001.3.1 설치, 법률 제6409호) 및 본원", "Family Branch of the Daegu District Court (established 2001-03-01, Act No. 6409) and the main court",
     "2012-03-01", "법률 제10536호(2011.4.5) 부칙 제1조 단서", "Act No. 10536 (2011-04-05), Addenda Art. 1, proviso"),
    ("광주", "광주지방법원 가정지원(2001.3.1 설치, 법률 제6409호) 및 본원", "Family Branch of the Gwangju District Court (established 2001-03-01, Act No. 6409) and the main court",
     "2012-03-01", "법률 제10536호(2011.4.5) 부칙 제1조 단서", "Act No. 10536 (2011-04-05), Addenda Art. 1, proviso"),
    ("인천", "인천지방법원 본원", "Incheon District Court (main court)",
     "2016-03-01", "법률 제11151호(2012.1.17) 부칙 제1조·제2조(2016.1.19 개정)", "Act No. 11151 (2012-01-17), Addenda Arts. 1–2 (as amended 2016-01-19)"),
    ("울산", "울산지방법원 본원", "Ulsan District Court (main court)",
     "2018-03-01", "법률 제12184호(2014.1.7) 부칙 제1조 단서", "Act No. 12184 (2014-01-07), Addenda Art. 1, proviso"),
    ("수원", "수원지방법원 본원", "Suwon District Court (main court)",
     "2019-03-01", "법률 제12419호(2014.3.18) 부칙 제1조", "Act No. 12419 (2014-03-18), Addenda Art. 1"),
]:
    y = start[:4]
    add(f"{g}가정법원", start, "전환", pred, f"{L} {basis}",
        f"가사 표에서 {y}년 이전 값은 '{g}지방법원(가정지원)' 행 → court_id_h로 통합. {y}년이 전환 연도",
        pen, f"{EST}, {ben}",
        f"In the family tables, values before {y} come from the '{G_EN[g]} District Court (family branch)' rows, harmonized into this unit; {y} is the conversion year")
for g, brs, start, basis, ben in [
    ("대전", ["공주", "논산", "서산", "천안", "홍성"], "2012-03-01", "법률 제10536호 부칙 제2조 ⑤", "Act No. 10536, Addenda Art. 2(5)"),
    ("대구", ["경주", "김천", "상주", "안동", "영덕", "의성", "포항"], "2012-03-01", "법률 제10536호 부칙 제2조 ⑥", "Act No. 10536, Addenda Art. 2(6)"),
    ("광주", ["목포", "순천", "장흥", "해남"], "2012-03-01", "법률 제10536호 부칙 제2조 ⑦", "Act No. 10536, Addenda Art. 2(7)"),
    ("인천", ["부천"], "2016-03-01", "법률 제11151호 부칙 제2조 ②", "Act No. 11151, Addenda Art. 2(2)"),
    ("수원", ["성남", "안산", "안양", "여주", "평택"], "2019-03-01", "법률 제12419호 부칙 제2조 ③", "Act No. 12419, Addenda Art. 2(3)"),
]:
    y = start[:4]
    add([f"{g}가정법원/{b}지원" for b in brs], start, "전환", f"{g}지방법원 같은 이름 지원(가사사건)",
        f"{L} {basis}",
        f"{y}년 이전 가사 값은 지방법원 지원 행 → court_id_h로 통합" + ("; 안양지원 자체가 2009.3.1 설치" if g == "수원" else ""),
        f"Same-named branch court of the {G_EN[g]} District Court (family cases)",
        f"{EST}, {ben}",
        f"Family values before {y} come from the district-court branch rows, harmonized into this unit"
        + ("; the Anyang branch itself was established 2009-03-01" if g == "수원" else ""))

# ── renamings of si/gun (city/county) courts ──
add("대전지방법원/세종특별자치시법원", "2013-04-05", "명칭변경", "대전지방법원 연기군법원",
    f"{L} 법률 제11726호(2013.4.5) 부칙 제2조",
    "2002–2011 '연기군법원' 행을 통합(SI_GUN_RENAMES). 2012년 값은 Excel의 현 명칭 소급 표기",
    "Yeongi Gun Court (Daejeon District Court)",
    f"{EST}, Act No. 11726 (2013-04-05), Addenda Art. 2",
    "2002–2011 'Yeongi Gun Court' rows harmonized into this unit; 2012 value restated under the current name in the Excel editions")
add("대전지방법원/당진시법원", "2013-07-30", "명칭변경", "대전지방법원 서산지원 당진군법원",
    f"{L} 법률 제11951호(2013.7.30) 부칙 제2조",
    "2002–2011 '당진군법원' 행을 통합. 2012년 값은 Excel의 현 명칭 소급 표기",
    "Dangjin Gun Court (Seosan Branch Court of the Daejeon District Court)",
    f"{EST}, Act No. 11951 (2013-07-30), Addenda Art. 2",
    "2002–2011 'Dangjin Gun Court' rows harmonized into this unit; 2012 value restated under the current name in the Excel editions")
for c, old, oen in [("인천지방법원/김포시법원", "인천지방법원 김포군법원", "Gimpo Gun Court (Incheon District Court)"),
                    ("수원지방법원/안성시법원", "수원지방법원 평택지원 안성군법원", "Anseong Gun Court (Pyeongtaek Branch Court of the Suwon District Court)")]:
    add(c, "1998-09-17", "명칭변경", old, f"{L} 법률 제5562호(1998.9.17) 부칙 ①·②",
        "2002–2006 값은 2006판 소액 표의 옛 명칭 '…군법원' 표기 → 통합. 법정 명칭 변경은 1998년이므로 2006판 표기는 구 명칭 잔존",
        oen, f"{EST}, Act No. 5562 (1998-09-17), Addenda paras. 1–2",
        "2002–2006 values are printed under the old 'Gun Court' name in the 2006 edition's small-claims table and are harmonized; the legal renaming dates from 1998, so the 2006 label is a residual old name")
add("수원지방법원/광주시법원", "2001-03-21", "명칭변경(군→시 승격)", "수원지방법원 성남지원 광주군법원",
    "경기도화성시등2개도농복합형태의시설치등에관한법률(법률 제6280호, 2000.12.20) 부칙 제1조(공포 후 3월, 2001.3.21 시행)",
    "시·군법원 명칭은 소재 시·군을 따름. 2002–2006 값은 2006판 소액 표의 구 명칭 '광주군법원' 표기 → 통합",
    "Gwangju Gun Court (Seongnam Branch Court of the Suwon District Court)",
    "Act on the Establishment of Hwaseong-si and One Other Urban-Rural Integrated City in Gyeonggi-do (author translation), Act No. 6280 (2000-12-20), Addenda Art. 1 (effective three months after promulgation, 2001-03-21)",
    "Si/gun court names follow the city/county; 2002–2006 values printed as 'Gwangju Gun Court' in the 2006 edition are harmonized")
add("의정부지방법원/포천시법원", "2003-10-19", "명칭변경(군→시 승격)", "의정부지방법원 포천군법원",
    "경기도양주시·포천시도농복합형태의시설치등에관한법률(법률 제6928호, 2003.7.18) 부칙 제1조(2003.10.19 시행); "
    "각급법원설치법 별표 2 <개정 2003.7.18> 소재지 '抱川市'",
    "2002–2006 값은 2006판 소액 표의 구 명칭 '포천군법원' 표기 → 통합(2002–03은 실제로도 포천군법원)",
    "Pocheon Gun Court (Uijeongbu District Court)",
    f"Act on the Establishment of Yangju-si and Pocheon-si as Urban-Rural Integrated Cities in Gyeonggi-do (author translation), Act No. 6928 (2003-07-18), Addenda Art. 1 (effective 2003-10-19); {EST}, Annex 2 (as amended 2003-07-18), seat 'Pocheon-si'",
    "2002–2006 values printed as 'Pocheon Gun Court' in the 2006 edition are harmonized (in 2002–2003 the court was in fact still a Gun Court)")
add("창원지방법원/창원남부시법원", "2011-04-05", "명칭변경", "창원지방법원 진해시법원",
    f"{L} 법률 제10536호(2011.4.5, 전문개정) 별표 2: '창원남부(창원시 진해구)'. 직전 별표 2<개정 2003.7.18>: '鎭海(鎭海市)'",
    "2002–2006 '진해시법원' 행을 통합(SI_GUN_RENAMES; 2006 1,644 → 2007 1,400으로 연속). 2007–2010 값은 2011판의 현 명칭 소급 표기. "
    "창원시 통합(2010.7.1) 후 진해구 관할",
    "Jinhae Si Court (Changwon District Court)",
    f"{EST}, Act No. 10536 (2011-04-05, wholly amended), Annex 2: 'Changwon-Nambu (Jinhae-gu, Changwon-si)'; preceding Annex 2 (as amended 2003-07-18): 'Jinhae (Jinhae-si)'",
    "2002–2006 'Jinhae Si Court' rows harmonized into this unit (continuous: 1,644 in 2006 → 1,400 in 2007); 2007–2010 values restated under the current name in the 2011 edition; serves Jinhae-gu after the 2010-07-01 Changwon merger")
add("창원지방법원/마산시법원", "2011-04-05", "폐지(마산지원으로 흡수)", "",
    f"{L} 법률 제10536호(2011.4.5) 별표 2에서 삭제(직전 별표 2: '馬山(馬山市)'); 마산지원 설치 2011.3.1(법률 제8318호)",
    "2002–2006만 별도 행. 2011판은 2007–2010 소액을 '마산지원' 행에 소급 표기(마산지원 2007–10 민사단독·합의는 0) → "
    "마산시법원 실적의 승계 표기로 판단. 단 2006 9,593 → 2007 20,540으로 수준 차이가 커 통합하지 않음(unit_type도 다름)",
    "",
    f"Deleted from Annex 2 of the {EST} by Act No. 10536 (2011-04-05) (preceding Annex 2: 'Masan (Masan-si)'); Masan Branch Court established 2011-03-01 (Act No. 8318)",
    "Separate rows for 2002–2006 only. The 2011 edition restates 2007–2010 small claims under the Masan Branch Court (whose 2007–2010 civil single-judge and collegiate values are zero), interpreted as the Masan Si Court's caseload; not harmonized because of the level jump (9,593 in 2006 → 20,540 in 2007) and the different unit type")
add("창원지방법원/마산지원", "2011-03-01", "설치", "창원지방법원 본원 관할 일부(구 마산·진해 지역)·마산시법원",
    f"{L} 법률 제8318호(2007.3.29) 부칙 ①",
    "2011년 값은 3–12월분. 소액 2007–2010 값은 2011판이 전신 마산시법원 실적을 소급 표기한 것(마산시법원 행 참고)",
    "Part of the Changwon District Court (main court) jurisdiction (former Masan/Jinhae area); Masan Si Court",
    f"{EST}, Act No. 8318 (2007-03-29), Addenda para. 1",
    "2011 values cover March–December. Small-claims values for 2007–2010 are the predecessor Masan Si Court's caseload restated by the 2011 edition (see the Masan Si Court row)")
add("의정부지방법원/남양주시법원", "", "폐지(지원으로 승계, 2022-03-01)", "",
    f"{L} 법률 제11623호 부칙 제2조 ②",
    "2022.2.28 계속 사건은 남양주지원으로 승계. 자료상 2021년이 마지막",
    "",
    f"{EST}, Act No. 11623, Addenda Art. 2(2)",
    "Cases pending on 2022-02-28 were transferred to the Namyangju Branch Court; last year in the data is 2021")

df = pd.DataFrame(rows)
cw = pd.read_csv(OUT / "court_crosswalk.csv")
missing = sorted(set(df.court_id_h) - set(cw.court_id_h))
assert not missing, f"crosswalk에 없는 id: {missing}"
assert df.court_id_h.is_unique, df[df.court_id_h.duplicated()]
for c in ("legal_basis_en", "data_note_en"):
    empty = df[df[c].eq("") & df[c.replace("_en", "")].ne("")]
    assert empty.empty, (c, empty.court_id_h.tolist())
df.to_csv(OUT / "court_crosswalk_notes.csv", index=False, encoding="utf-8-sig")
print(f"court_crosswalk_notes.csv: {len(df)}행 (영문 병기)")
