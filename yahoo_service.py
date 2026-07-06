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


def fetch_yahoo_fantasy_data():
    if not os.path.exists(OAUTH_FILE_PATH):
        return "錯誤：找不到 Yahoo OAuth 憑證檔，請確認環境變數 YAHOO_OAUTH_JSON 是否正確。"

    try:
        with open(OAUTH_FILE_PATH, "r", encoding="utf-8") as f:
            oauth_data = json.load(f)
        if not oauth_data.get("refresh_token"):
            return "❌ oauth2.json 缺少 refresh_token"
    except Exception as e:
        return f"❌ 讀取 oauth2.json 失敗: {str(e)}"

    try:
        sc = OAuth2(None, None, from_file=OAUTH_FILE_PATH, browser_callback=None)
        gm = yfa.Game(sc, YAHOO_SPORT)
        league_id = YAHOO_LEAGUE_ID
        if not league_id:
            leagues = gm.league_ids()
            if leagues:
                league_id = leagues[0]
            else:
                return "錯誤：此 Yahoo 帳號目前沒有任何聯盟資料。"
        if "." not in str(league_id):
            league_id = f"{gm.game_id()}.l.{league_id}"
        lg = gm.to_league(league_id)

        settings = lg.settings()
        standings = lg.standings()
        current_week = lg.current_week()
        matchups_data = lg.matchups()

        # 5. 格式化成戰報文字
        report = f"🏆 Yahoo Fantasy 聯盟戰報 ({YAHOO_SPORT.upper()})\n"
        report += "=" * 20 + "\n"
        report += f"聯盟名稱：{settings.get('name', '未知')}\n"
        report += f"目前週次：Week {current_week}\n"
        report += f"更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

        # --- A. 聯盟排名 (Standings) ---
        report += "📊 聯盟排名\n"
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
        report += "\n"

        # --- B. 本週對戰成績 (Matchups) ---
        report += f"⚔️ Week {current_week} 對戰戰況\n"
        report += "-" * 30 + "\n"

        # 解析 Yahoo 奇葩的 matchups 結構
        matchups_dict = {}
        try:
            # 依據你的 JSON 結構定位到 matchups 節點
            matchups_dict = matchups_data.get('fantasy_content', {}).get('league', [{}, {}])[1].get('scoreboard', {}).get('0', {}).get('matchups', {})
        except Exception as e:
            print(f"定位 matchups 節點失敗: {e}")

        if matchups_dict:
            match_idx = 1
            # 遍歷 "0", "1", "2", "3"... 等對戰組合
            for key, val in matchups_dict.items():
                if key.isdigit():
                    try:
                        matchup = val.get('matchup', {})
                        # 取得 teams 中的 "0" 與 "1" 兩隊
                        teams_data = matchup.get('0', {}).get('teams', {})

                        t1_obj = teams_data.get('0', {}).get('team', [])
                        t2_obj = teams_data.get('1', {}).get('team', [])

                        if len(t1_obj) >= 2 and len(t2_obj) >= 2:
                            # 1. 解析隊伍名稱 (在第一個陣列元素的 index 2 的 'name')
                            t1_name = t1_obj[0][2].get('name', '未知隊伍1')
                            t2_name = t2_obj[0][2].get('name', '未知隊伍2')

                            # 2. 解析當前比分 (在第二個元素 dictionary 的 'team_points' 裡)
                            t1_score = t1_obj[1].get('team_points', {}).get('total', '0')
                            t2_score = t2_obj[1].get('team_points', {}).get('total', '0')

                            t1_val, t2_val = _to_float(t1_score), _to_float(t2_score)
                            diff = abs(t1_val - t2_val)

                            if t1_val > t2_val:
                                line = f"👑 {t1_name} {t1_score}  -  {t2_score} {t2_name}"
                            elif t2_val > t1_val:
                                line = f"{t1_name} {t1_score}  -  {t2_score} 👑 {t2_name}"
                            else:
                                line = f"🤝 {t1_name} {t1_score}  -  {t2_score} {t2_name}（平手）"

                            report += f"Match {match_idx}：{line}\n"
                            report += f"    分差 {diff:.1f} 分\n\n"
                            match_idx += 1
                    except Exception as e:
                        print(f"解析對戰組合 {key} 失敗: {e}")
        else:
            report += "（暫無本週對戰資料或格式解析失敗）\n"
        return report

    except EOFError:
        return "❌ Yahoo OAuth Token 已過期且無法在伺服器環境中互動授權。請在本機重新執行授權流程，取得新的 oauth2.json（包含有效的 refresh_token）後更新 YAHOO_OAUTH_JSON 環境變數。"
    except Exception as e:
        return f"❌ 抓取 Yahoo Fantasy 資料時發生錯誤: {str(e)}"


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


def fetch_stat_leaders(keyword: str) -> str:
    """
    抓取目前聯盟中所有已被選走打者的數據，並排出全壘打(HR)或打點(RBI)的前三名。
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

        # 2. 過濾出打者 (Batter, 'B')
        teams_map = {t_key: t_info.get("name") for t_key, t_info in lg.teams().items()}
        print(f"teams_map: {teams_map}")
        batter_ids = []
        player_to_team = {}

        for t_key, t_info in teams_data.items():
            team_name = t_info.get("name", "未知隊伍")
            try:
                # 取得該隊伍的球員名單
                team_obj = lg.to_team(t_key)
                roster = team_obj.roster()

                for p in roster:
                    # 過濾出打者 (B)
                    if p.get("position_type") == "B" and p.get("player_id"):
                        p_id = int(p["player_id"])
                        batter_ids.append(p_id)
                        player_to_team[p_id] = team_name
            except Exception as e:
                print(f"抓取隊伍 {team_name} 名單失敗: {e}")

        if not batter_ids:
            return "⚠️ 未在名單中找到任何打者。"
        # 3. 分批跟 Yahoo 查詢數據 (Yahoo 一次限制最多查 25 人)
        chunk_size = 25
        all_player_stats = []
        for i in range(0, len(batter_ids), chunk_size):
            chunk = batter_ids[i:i + chunk_size]
            try:
                stats = lg.player_stats(chunk, "season")
                all_player_stats.extend(stats)
            except Exception as e:
                print(f"分批抓取球員數據失敗: {e}")

        # 4. 判斷想查哪種數據
        show_hr = "hr" in keyword or "全壘打" in keyword or "雙冠王" in keyword or "打擊王" in keyword
        show_rbi = "rbi" in keyword or "打點" in keyword or "雙冠王" in keyword or "打擊王" in keyword

        report = f"📊 Yahoo Fantasy 數據排行榜 ({YAHOO_SPORT.upper()})\n"
        report += "=" * 0 + "\n"
        if show_hr:
            hr_leaders = sorted(all_player_stats, key=lambda x: _to_float(x.get("HR", 0)), reverse=True)[:3]
            report += "🔥 【全壘打王排行榜 (HR)】\n"
            medals = ["🥇", "🥈", "🥉"]

            for idx, p in enumerate(hr_leaders):
                p_id = p.get("player_id")
                team_name = player_to_team.get(p_id, "Free Agent 快搶💪")
                report += f"{medals[idx]} {p.get('name', '未知')} ({team_name}) — {p.get('HR', 0)} HR\n"
            report += "\n"

        if show_rbi:
            rbi_leaders = sorted(all_player_stats, key=lambda x: _to_float(x.get("RBI", 0)), reverse=True)[:3]
            report += "💪 【打點王排行榜 (RBI)】\n"

            medals = ["🥇", "🥈", "🥉"]
            for idx, p in enumerate(rbi_leaders):
                p_id = p.get("player_id")
                team_name = player_to_team.get(p_id, "Free Agent 快搶💪")
                report += f"{medals[idx]} {p.get('name', '未知')} ({team_name}) — {p.get('RBI', 0)} RBI\n"

            report += "\n"

        report += f"更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return report

    except Exception as e:
        return f"❌ 抓取數據排行榜失敗: {str(e)}"
