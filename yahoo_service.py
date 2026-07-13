import os
import json
from datetime import datetime

# 引入 Yahoo Fantasy API 相關套件
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa

# ==================== 環境變數讀取與暫存檔處理 ====================
YAHOO_LEAGUE_ID = os.environ.get("YAHOO_LEAGUE_ID")
YAHOO_OAUTH_JSON_STR = os.environ.get("YAHOO_OAUTH_JSON")
YAHOO_SPORT = os.environ.get("YAHOO_SPORT", "mlb")

# 將 Yahoo OAuth JSON 寫入暫存檔，供 yahoo_oauth 套件讀取
OAUTH_FILE_PATH = "/tmp/oauth2.json"

def init_yahoo_oauth_file():
    if YAHOO_OAUTH_JSON_STR:
        try:
            # 驗證是否為合法 JSON，並寫入 /tmp/oauth2.json
            oauth_data = json.loads(YAHOO_OAUTH_JSON_STR)
            with open(OAUTH_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(oauth_data, f)
            print(f"✅ 成功將 YAHOO_OAUTH_JSON 寫入暫存路徑: {OAUTH_FILE_PATH}")
        except Exception as e:
            print(f"❌ 解析 YAHOO_OAUTH_JSON 失敗: {e}")
    else:
        print("⚠️ 未偵測到 YAHOO_OAUTH_JSON 環境變數")

# 啟動時立即執行一次
init_yahoo_oauth_file()

# ==================== Yahoo Fantasy API 抓取邏輯 ====================

def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _connect_league():
    """建立 Yahoo League 物件。成功回傳 (lg, None)，失敗回傳 (None, 錯誤訊息文字)。"""
    if not os.path.exists(OAUTH_FILE_PATH):
        return None, "錯誤：找不到 Yahoo OAuth 憑證檔，請確認環境變數 YAHOO_OAUTH_JSON 是否正確。"

    try:
        with open(OAUTH_FILE_PATH, "r", encoding="utf-8") as f:
            oauth_data = json.load(f)
        if not oauth_data.get("refresh_token"):
            return None, "❌ oauth2.json 缺少 refresh_token"
    except Exception as e:
        return None, f"❌ 讀取 oauth2.json 失敗: {str(e)}"

    try:
        sc = OAuth2(None, None, from_file=OAUTH_FILE_PATH, browser_callback=None)
        gm = yfa.Game(sc, YAHOO_SPORT)
        league_id = YAHOO_LEAGUE_ID
        if not league_id:
            leagues = gm.league_ids()
            if leagues:
                league_id = leagues[0]
            else:
                return None, "錯誤：此 Yahoo 帳號目前沒有任何聯盟資料。"
        if "." not in str(league_id):
            league_id = f"{gm.game_id()}.l.{league_id}"
        return gm.to_league(league_id), None
    except EOFError:
        return None, "❌ Yahoo OAuth Token 已過期且無法在伺服器環境中互動授權。請在本機重新執行授權流程，取得新的 oauth2.json（包含有效的 refresh_token）後更新 YAHOO_OAUTH_JSON 環境變數。"
    except Exception as e:
        return None, f"❌ 連線 Yahoo Fantasy 失敗: {str(e)}"


def _extract_team_meta(team_obj):
    """從 Yahoo team 陣列結構（[[meta dicts...], {...}, ...]）取出 team_key 與隊名。"""
    meta_list = team_obj[0] if team_obj else []
    team_key, name = None, None
    for item in meta_list:
        if isinstance(item, dict):
            if "team_key" in item:
                team_key = item["team_key"]
            if "name" in item:
                name = item["name"]
    return team_key, name or "未知隊伍"


def _parse_current_matchups(matchups_data):
    """解析 Yahoo 奇葩的 matchups 結構，回傳 [{t1_key, t1_name, t1_score, t2_key, t2_name, t2_score}, ...]。
    這裡的 score 是本週從週一累計到目前為止的總分，不是單日分數。"""
    results = []
    try:
        matchups_dict = matchups_data.get('fantasy_content', {}).get('league', [{}, {}])[1].get('scoreboard', {}).get('0', {}).get('matchups', {})
    except Exception as e:
        print(f"定位 matchups 節點失敗: {e}")
        return results

    for key, val in matchups_dict.items():
        if not key.isdigit():
            continue
        try:
            matchup = val.get('matchup', {})
            teams_data = matchup.get('0', {}).get('teams', {})
            t1_obj = teams_data.get('0', {}).get('team', [])
            t2_obj = teams_data.get('1', {}).get('team', [])
            if len(t1_obj) < 2 or len(t2_obj) < 2:
                continue

            t1_key, t1_name = _extract_team_meta(t1_obj)
            t2_key, t2_name = _extract_team_meta(t2_obj)
            t1_score = _to_float(t1_obj[1].get('team_points', {}).get('total', '0'))
            t2_score = _to_float(t2_obj[1].get('team_points', {}).get('total', '0'))

            results.append({
                "t1_key": t1_key, "t1_name": t1_name, "t1_score": t1_score,
                "t2_key": t2_key, "t2_name": t2_name, "t2_score": t2_score,
            })
        except Exception as e:
            print(f"解析對戰組合 {key} 失敗: {e}")
    return results


def _render_standings_section(standings):
    """Yahoo 官方正式排名（上週結算，不含本週即時戰況）。"""
    report = "📊 聯盟排名\n"
    report += "-" * 30 + "\n"

    medals = {1: "🥇", 2: "🥈", 3: "🥉", 8: "[豆汁組]🤮", 9: "[豆汁組]🤮", 10: "[豆汁組]🤢"}
    for team in standings:
        name = team.get("name", "未知隊伍")
        rank_raw = team.get("rank", "?")
        rank = int(rank_raw) if str(rank_raw).isdigit() else None
        medal = medals.get(rank, "　")

        outcome = team.get("outcome_totals", {})
        wins   = outcome.get("wins", "-")
        losses = outcome.get("losses", "-")
        ties   = outcome.get("ties", "0")
        pct    = outcome.get("percentage", "-")
        games_back = team.get("games_back", "-") or "-"

        record = f"{wins}-{losses}" + (f"-{ties}" if ties not in ("0", 0, None) else "")
        report += f"{medal} {rank_raw}. {name}\n"
        report += f"    戰績 {record}（勝率 {pct}）落後 {games_back} 場\n"
    return report


def _render_matchup_section(current_week, matchups):
    """本週對戰戰況（累計到目前為止的比分）。"""
    report = f"⚔️ Week {current_week} 對戰戰況\n"
    report += "-" * 30 + "\n"

    if not matchups:
        report += "（暫無本週對戰資料或格式解析失敗）\n"
        return report

    for idx, m in enumerate(matchups, start=1):
        t1_score, t2_score = m["t1_score"], m["t2_score"]
        diff = abs(t1_score - t2_score)
        if t1_score > t2_score:
            line = f"👑 {m['t1_name']} {t1_score}  -  {t2_score} {m['t2_name']}"
        elif t2_score > t1_score:
            line = f"{m['t1_name']} {t1_score}  -  {t2_score} 👑 {m['t2_name']}"
        else:
            line = f"🤝 {m['t1_name']} {t1_score}  -  {t2_score} {m['t2_name']}（平手）"
        report += f"Match {idx}：{line}\n"
        report += f"    分差 {diff:.1f} 分\n\n"
    return report


def fetch_yahoo_fantasy_data():
    """完整戰報：聯盟排名 + 本週對戰戰況（給 /send-report、/get-top3、/get-tail3 用，格式維持不變）。"""
    lg, err = _connect_league()
    if err:
        return err

    try:
        settings = lg.settings()
        standings = lg.standings()
        current_week = lg.current_week()
        matchups = _parse_current_matchups(lg.matchups())

        report = f"🏆 Yahoo Fantasy 聯盟戰報 ({YAHOO_SPORT.upper()})\n"
        report += "=" * 20 + "\n"
        report += f"聯盟名稱：{settings.get('name', '未知')}\n"
        report += f"目前週次：Week {current_week}\n"
        report += f"更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        report += _render_standings_section(standings) + "\n"
        report += _render_matchup_section(current_week, matchups)
        return report
    except Exception as e:
        return f"❌ 抓取 Yahoo Fantasy 資料時發生錯誤: {str(e)}"


def fetch_matchup_report():
    """戰報：只回傳本週目前對戰比分（累計到目前為止，不含排名）。"""
    lg, err = _connect_league()
    if err:
        return err

    try:
        current_week = lg.current_week()
        matchups = _parse_current_matchups(lg.matchups())
        report = _render_matchup_section(current_week, matchups)
        report += f"\n更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return report
    except Exception as e:
        return f"❌ 抓取本週對戰資料時發生錯誤: {str(e)}"


def fetch_standings_report():
    """排名：Yahoo 官方正式排名（固定值，上週結算，不含本週即時戰況）。"""
    lg, err = _connect_league()
    if err:
        return err

    try:
        settings = lg.settings()
        standings = lg.standings()
        report = f"🏆 Yahoo Fantasy 聯盟排名 ({YAHOO_SPORT.upper()})\n"
        report += "=" * 20 + "\n"
        report += f"聯盟名稱：{settings.get('name', '未知')}\n\n"
        report += _render_standings_section(standings)
        report += f"\n更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return report
    except Exception as e:
        return f"❌ 抓取聯盟排名時發生錯誤: {str(e)}"


def fetch_live_standings_report():
    """即時排名（Head-to-Head Categories 專用）：本聯盟排名是看全季累計「贏過的類別總數」，
    不是週對戰的勝負場次。team_points.total 在類別制聯盟裡代表「目前這週贏過的類別數」
    （不是連續分數），所以直接把它累加進季賽總類別勝場，其餘（總類別數 - 雙方贏的類別數）
    算平手類別，藉此推算「假設現在收官」的即時排名。"""
    lg, err = _connect_league()
    if err:
        return err

    try:
        standings = lg.standings()
        current_week = lg.current_week()
        matchups = _parse_current_matchups(lg.matchups())
        total_categories = len(STAT_CONFIG)  # 本聯盟共 12 個計分類別

        # 1. 用 team_key 建立可變戰績表（單位是「類別數」，不是「場次」）
        records = {}
        for team in standings:
            t_key = team.get("team_key") or team.get("name")
            outcome = team.get("outcome_totals", {})
            records[t_key] = {
                "name": team.get("name", "未知隊伍"),
                "wins": _to_float(outcome.get("wins", 0)),
                "losses": _to_float(outcome.get("losses", 0)),
                "ties": _to_float(outcome.get("ties", 0)),
                "live_score": None,
            }

        # 2. 套用本週即時戰況：雙方目前贏的類別數直接加進季賽累計，
        #    剩下的類別（尚未分出勝負或本來就平手）算進 ties
        for m in matchups:
            k1, k2 = m["t1_key"], m["t2_key"]
            if k1 not in records or k2 not in records:
                continue
            records[k1]["live_score"] = m["t1_score"]
            records[k2]["live_score"] = m["t2_score"]

            cats_tied = max(total_categories - m["t1_score"] - m["t2_score"], 0)
            records[k1]["wins"] += m["t1_score"]
            records[k1]["losses"] += m["t2_score"]
            records[k1]["ties"] += cats_tied
            records[k2]["wins"] += m["t2_score"]
            records[k2]["losses"] += m["t1_score"]
            records[k2]["ties"] += cats_tied

        # 3. 重新計算勝率、依勝率排序（跟 Yahoo 官方排名同一套邏輯，只是類別數多算了本週進行中的部分）
        for r in records.values():
            total = r["wins"] + r["losses"] + r["ties"]
            r["win_pct"] = (r["wins"] + 0.5 * r["ties"]) / total if total else 0.0
        ranked = sorted(records.values(), key=lambda r: r["win_pct"], reverse=True)

        medals = ["🥇", "🥈", "🥉"]
        report = f"🔴 即時排名（含 Week {current_week} 目前戰況推算）\n"
        report += "=" * 20 + "\n"
        report += "⚠️ 本週對戰尚未結束，以下為「假設現在收官」的推算排名，非 Yahoo 官方正式結果\n"
        report += "-" * 30 + "\n"

        for idx, r in enumerate(ranked, start=1):
            medal = medals[idx - 1] if idx <= 3 else "　"
            wins_i, losses_i, ties_i = int(r["wins"]), int(r["losses"]), int(r["ties"])
            record = f"{wins_i}-{losses_i}" + (f"-{ties_i}" if ties_i else "")
            score_note = f"[本週目前贏 {int(r['live_score'])}/{total_categories} 類]" if r["live_score"] is not None else ""
            report += f"{medal} {idx}. {r['name']}（{record}，勝率 {r['win_pct']:.3f}）{score_note}\n"

        report += f"\n更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return report
    except Exception as e:
        return f"❌ 抓取即時排名時發生錯誤: {str(e)}"


def filter_standings(full_report: str, mode: str) -> str:
    """
    輔助函式：從完整戰報中，過濾出前三名或後三名的純文字
    mode: "top3" 或 "tail3"
    """
    if "❌" in full_report or "錯誤" in full_report:
        return full_report

    lines = full_report.split("\n")
    output = []

    # 1. 根據模式直接設定新的標題，不保留舊標頭
    if mode == "top3":
        output.append("🥇 頒獎前三名 🥇")
    else:
        output.append("🤮 豆汁倒楣鬼 🤮")
    output.append("=" * 20) # 加一條分隔線，比較美觀

    # 2. 找出所有排名資料行（只抓有隊伍名稱的那一行）
    team_names = []
    start_collect = False
    for line in lines:
        if "📊 聯盟排名" in line:
            start_collect = True
            continue
        if start_collect:
            # 遇到下一個區塊就停止
            if "⚔️" in line or "Match" in line:
                break
            # 隊伍名稱那一行通常會帶有名次，例如 "🥇 1. 隊伍 A" 或 "　 4. 隊伍 B"
            # 我們可以用正則表達式或簡單的字元判斷：只要包含 ". "（名次標示）就判定是隊伍名稱行
            if ". " in line:
                team_names.append(line.strip())

    # 3. 根據需求篩選隊伍名稱
    if mode == "top3":
        selected_teams = team_names[:3]
    else:  # tail3
        selected_teams = team_names[-3:]

    # 4. 重新組合輸出
    for team in selected_teams:
        output.append(team)

    return "\n".join(output)


# 本聯盟計分指標（打擊 6 項 + 投球 6 項）與觸發用的口語化關鍵字
# reverse=True 代表數值越高越好（由大到小排序）；False 代表數值越低越好（例如 ERA、WHIP）
# keys：Yahoo player_stats() 實際回傳的欄位名稱。大多數指標欄位名稱跟指標本身同名，
# 但 Yahoo 沒有原生的 "SV+HLD" 欄位，只有分開的 SV 跟 HLD，所以這項要用兩個欄位加總。
STAT_CONFIG = {
    "R":      {"label": "得分王",     "position_type": "B", "reverse": True,  "keys": ["R"],       "keywords": ["得分", "r"]},
    "HR":     {"label": "全壘打王",   "position_type": "B", "reverse": True,  "keys": ["HR"],      "keywords": ["全壘打", "hr"]},
    "RBI":    {"label": "打點王",     "position_type": "B", "reverse": True,  "keys": ["RBI"],     "keywords": ["打點", "rbi"]},
    "SB":     {"label": "盜壘王",     "position_type": "B", "reverse": True,  "keys": ["SB"],      "keywords": ["盜壘", "sb"]},
    "OBP":    {"label": "上壘率王",   "position_type": "B", "reverse": True,  "keys": ["OBP"],     "keywords": ["上壘率", "obp"]},
    "OPS":    {"label": "OPS王",     "position_type": "B", "reverse": True,  "keys": ["OPS"],     "keywords": ["ops", "攻擊指數"]},
    "QS":     {"label": "優質先發王", "position_type": "P", "reverse": True,  "keys": ["QS"],      "keywords": ["優質先發", "qs"]},
    "SV+H": {"label": "中繼救援王", "position_type": "P", "reverse": True,  "keys": ["SV+H"], "keywords": ["中繼", "救援", "sv", "hld"]},
    "K":      {"label": "三振王",     "position_type": "P", "reverse": True,  "keys": ["K"],       "keywords": ["三振", "k"]},
    "ERA":    {"label": "防禦率王",   "position_type": "P", "reverse": False, "keys": ["ERA"],     "keywords": ["防禦率", "era"]},
    "WHIP":   {"label": "WHIP王",    "position_type": "P", "reverse": False, "keys": ["WHIP"],    "keywords": ["whip"]},
    "K/BB":   {"label": "控球王",     "position_type": "P", "reverse": True,  "keys": ["K/BB"],    "keywords": ["控球", "k/bb"]},
}

# 組合關鍵字：一次觸發多項指標的排行榜
COMBO_STAT_KEYWORDS = {
    "雙冠王": ["HR", "RBI"],
    "打擊王": ["HR", "RBI"],
}


def fetch_stat_leaders(keyword: str) -> str:
    """
    抓取目前聯盟中所有已被選走球員的數據，依關鍵字對應到 STAT_CONFIG 的指標排出前三名。
    """

    if not os.path.exists(OAUTH_FILE_PATH):
        return "錯誤：找不到 Yahoo OAuth 憑證檔。"
    try:
        sc = OAuth2(None, None, from_file=OAUTH_FILE_PATH, browser_callback=None)
        gm = yfa.Game(sc, YAHOO_SPORT)
        league_id = YAHOO_LEAGUE_ID
        if not league_id:
            leagues = gm.league_ids()
            if leagues:
                league_id = leagues[0]
            else:
                return "錯誤：找不到任何聯盟資料。"

        if "." not in str(league_id):
            league_id = f"{gm.game_id()}.l.{league_id}"
        lg = gm.to_league(league_id)

        # 1. 取得聯盟內所有被選走的球員名單
        taken_players = lg.taken_players()
        print(f"taken_players: {taken_players}")
        if not taken_players:
            return "⚠️ 目前聯盟中沒有已被選走的球員資料。"

        # 2. 依位置分成打者 / 投手兩組（打擊指標只在打者裡排，投球指標只在投手裡排）
        teams_data = lg.teams()
        teams_map = {t_key: t_info.get("name") for t_key, t_info in teams_data.items()}
        print(f"teams_map: {teams_map}")
        batter_ids, pitcher_ids = [], []
        player_to_team = {}

        for t_key, t_info in teams_data.items():
            team_name = t_info.get("name", "未知隊伍")
            try:
                # 取得該隊伍的球員名單
                team_obj = lg.to_team(t_key)
                roster = team_obj.roster()

                for p in roster:
                    if not p.get("player_id"):
                        continue
                    p_id = int(p["player_id"])
                    player_to_team[p_id] = team_name
                    if p.get("position_type") == "B":
                        batter_ids.append(p_id)
                    elif p.get("position_type") == "P":
                        pitcher_ids.append(p_id)
            except Exception as e:
                print(f"抓取隊伍 {team_name} 名單失敗: {e}")

        if not batter_ids and not pitcher_ids:
            return "⚠️ 未在名單中找到任何球員。"

        # 3. 分批跟 Yahoo 查詢數據 (Yahoo 一次限制最多查 25 人)
        def fetch_stats(player_ids):
            chunk_size = 25
            results = []
            for i in range(0, len(player_ids), chunk_size):
                chunk = player_ids[i:i + chunk_size]
                try:
                    results.extend(lg.player_stats(chunk, "season"))
                except Exception as e:
                    print(f"分批抓取球員數據失敗: {e}")
            return results

        batter_stats = fetch_stats(batter_ids)
        pitcher_stats = fetch_stats(pitcher_ids)

        # 4. 判斷想查哪些指標
        if keyword in COMBO_STAT_KEYWORDS:
            target_stats = COMBO_STAT_KEYWORDS[keyword]
        else:
            target_stats = [stat for stat, cfg in STAT_CONFIG.items() if keyword in cfg["keywords"]]

        if not target_stats:
            return "⚠️ 沒有找到對應的數據指標。"

        report = f"📊 Yahoo Fantasy 數據排行榜 ({YAHOO_SPORT.upper()})\n"
        medals = ["🥇", "🥈", "🥉"]

        for stat in target_stats:
            cfg = STAT_CONFIG[stat]
            pool = batter_stats if cfg["position_type"] == "B" else pitcher_stats

            def stat_value(player, cfg=cfg):
                return sum(_to_float(player.get(k, 0)) for k in cfg["keys"])

            leaders = sorted(pool, key=stat_value, reverse=cfg["reverse"])[:3]

            report += f"🔥 【{cfg['label']} ({stat})】\n"
            for idx, p in enumerate(leaders):
                p_id = p.get("player_id")
                team_name = player_to_team.get(p_id, "Free Agent 快搶💪")
                # 單一欄位直接顯示原始值 (保留 Yahoo 回傳格式，例如 ERA 的小數點)；
                # 多欄位加總的指標 顯示計算後的總和
                if len(cfg["keys"]) == 1:
                    value_display = p.get(cfg["keys"][0], 0)
                else:
                    value_display = f"{stat_value(p):.0f}"
                report += f"{medals[idx]} {p.get('name', '未知')} ({team_name}) — {value_display} {stat}\n"
            report += "\n"

        report += f"更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return report

    except Exception as e:
        return f"❌ 抓取數據排行榜失敗: {str(e)}"
