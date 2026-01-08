import requests
import pandas as pd
import time
import math
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials

# ================= 設定區 =================
API_KEY = '531bb40a089446bdae76a019f2af3beb'
BASE_URL = 'https://api.football-data.org/v4'
GOOGLE_SHEET_NAME = "數據上傳" 
MANUAL_TAB_NAME = "球隊身價表" 
COMPETITIONS = ['PL', 'PD', 'CL', 'SA', 'BL1', 'FL1'] 

# 新增：聯賽入球係數 (根據歷史數據微調 Poisson Lambda)
LEAGUE_WEIGHTS = {
    'BL1': 1.15, # 德甲通常大球多
    'PL': 1.05,  # 英超節奏快
    'PD': 0.95,  # 西甲技術流，有時入球少
    'SA': 0.95,  # 意甲防守強
    'FL1': 1.0,  # 法甲中規中矩
    'CL': 1.1    # 歐聯強隊多，入球率偏高
}

# ================= 連接 Google Sheet =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open(GOOGLE_SHEET_NAME)
        return spreadsheet
    except Exception as e:
        print(f"❌ Google Sheet 連線失敗: {e}")
        return None

# ================= 讀取「球隊身價表」 =================
def load_manual_market_values(spreadsheet):
    print(f"📖 正在讀取 '{MANUAL_TAB_NAME}' 分頁...")
    market_value_map = {}
    try:
        worksheet = spreadsheet.worksheet(MANUAL_TAB_NAME)
        records = worksheet.get_all_records()
        for row in records:
            team_name = str(row.get('球隊名稱', '')).strip()
            value = str(row.get('身價', '')).strip()
            if team_name and value:
                market_value_map[team_name] = value
        print(f"✅ 成功讀取 {len(market_value_map)} 支球隊的身價資料！")
        return market_value_map
    except Exception as e:
        print(f"⚠️ 無法讀取身價表 (使用預設值): {e}")
        return {}

# ================= 輔助：解析身價為數字 =================
def parse_market_value(val_str):
    if not val_str or val_str == 'N/A': return 0
    try:
        clean = str(val_str).replace('€', '').replace('M', '').replace(',', '').strip()
        return float(clean)
    except:
        return 0

# ================= 輔助：計算近況分數 =================
def calculate_form_score(form_str):
    if not form_str or form_str == 'N/A': return 1.5
    score = 0
    count = 0
    relevant_form = form_str.replace(',', '').strip()[-5:]
    for char in relevant_form:
        if char.upper() == 'W': score += 3
        elif char.upper() == 'D': score += 1
        else: score += 0
        count += 1
    if count == 0: return 1.5
    return score / count 

# ================= (升級版) 獲取聯賽詳細數據：區分主/客場 =================
def get_all_standings_with_stats():
    print("📊 正在獲取各聯賽 [主場/客場] 獨立數據...")
    standings_map = {}
    headers = {'X-Auth-Token': API_KEY}
    
    for comp in COMPETITIONS:
        try:
            url = f"{BASE_URL}/competitions/{comp}/standings"
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                
                # 我們需要遍歷不同的 table type: TOTAL, HOME, AWAY
                for table in data.get('standings', []):
                    table_type = table['type'] # 'TOTAL', 'HOME', 'AWAY'
                    
                    for entry in table['table']:
                        team_id = entry['team']['id']
                        if team_id not in standings_map:
                            standings_map[team_id] = {
                                'rank': 0, 'form': 'N/A', 
                                'home_att': 1.2, 'home_def': 1.2,
                                'away_att': 1.0, 'away_def': 1.0
                            }
                        
                        # 處理數據
                        played = entry['playedGames']
                        gf = entry['goalsFor']
                        ga = entry['goalsAgainst']
                        avg_gf = gf / played if played > 0 else 0
                        avg_ga = ga / played if played > 0 else 0

                        if table_type == 'TOTAL':
                            standings_map[team_id]['rank'] = entry['position']
                            standings_map[team_id]['form'] = entry.get('form', 'N/A')
                        elif table_type == 'HOME':
                            # 主場進攻力 (Home Attack) & 主場防守漏水度 (Home Defense)
                            standings_map[team_id]['home_att'] = avg_gf if avg_gf > 0 else 0.8
                            standings_map[team_id]['home_def'] = avg_ga if avg_ga > 0 else 0.8
                        elif table_type == 'AWAY':
                            # 客場進攻力 & 客場防守
                            standings_map[team_id]['away_att'] = avg_gf if avg_gf > 0 else 0.8
                            standings_map[team_id]['away_def'] = avg_ga if avg_ga > 0 else 0.8
                            
            time.sleep(1.5) 
        except Exception as e:
            print(f"⚠️ 無法獲取 {comp} 排名: {e}")
    return standings_map

# ================= 核心算法：真實預測模型 (升級版) =================
def predict_match_outcome(home_stats, away_stats, home_val_str, away_val_str, h2h_summary, league_code):
    """
    Inputs:
    - home_stats: 包含主場攻擊力
    - away_stats: 包含客場防守力
    - h2h_summary: H2H 統計字串 (例如 "近5場: 主3勝...")
    - league_code: 聯賽代碼 (例如 PL, BL1)
    """
    
    # 1. 主客場獨立運算 (最準確的基礎)
    # 主隊預期入球 = (主隊主場攻擊力 + 客隊客場防守力) / 2
    raw_h_exp = (home_stats['home_att'] + away_stats['away_def']) / 2
    
    # 客隊預期入球 = (客隊客場攻擊力 + 主隊主場防守力) / 2
    raw_a_exp = (away_stats['away_att'] + home_stats['home_def']) / 2
    
    # 2. 聯賽係數修正
    league_factor = LEAGUE_WEIGHTS.get(league_code, 1.0)
    raw_h_exp *= league_factor
    raw_a_exp *= league_factor
    
    # 3. 身價修正
    h_val = parse_market_value(home_val_str)
    a_val = parse_market_value(away_val_str)
    
    if h_val > 0 and a_val > 0:
        ratio = h_val / a_val
        if ratio > 5.0:
            raw_h_exp *= 1.25; raw_a_exp *= 0.8
        elif ratio > 2.5:
            raw_h_exp *= 1.15; raw_a_exp *= 0.9
        elif ratio < 0.2:
            raw_h_exp *= 0.8; raw_a_exp *= 1.25
        elif ratio < 0.4:
            raw_h_exp *= 0.9; raw_a_exp *= 1.15

    # 4. 近況修正
    h_form = calculate_form_score(home_stats['form'])
    a_form = calculate_form_score(away_stats['form'])
    if h_form - a_form > 1.0: raw_h_exp *= 1.1
    if a_form - h_form > 1.0: raw_a_exp *= 1.1

    # 5. (新增) H2H 歷史權重修正
    # 解析 "近10場: 主5勝 | 和2 | 客3勝"
    try:
        if "主" in h2h_summary and "勝" in h2h_summary:
            parts = h2h_summary.split('|')
            h_wins = int(parts[0].split('主')[1].split('勝')[0]) # 提取主勝場數
            a_wins = int(parts[2].split('客')[1].split('勝')[0]) # 提取客勝場數
            total = h_wins + a_wins + int(parts[1].split('和')[1])
            
            if total > 0:
                h_win_rate = h_wins / total
                a_win_rate = a_wins / total
                
                # 如果主隊剋死客隊 (勝率 > 60%)
                if h_win_rate > 0.6: raw_h_exp *= 1.1
                # 如果客隊反客為主
                elif a_win_rate > 0.6: raw_a_exp *= 1.1
    except:
        pass # 解析失敗就不修正

    return round(raw_h_exp, 2), round(raw_a_exp, 2)

# ================= H2H + 大小球統計 =================
def get_h2h_and_ou_stats(match_id, current_home_id, current_away_id):
    headers = {'X-Auth-Token': API_KEY}
    url = f"{BASE_URL}/matches/{match_id}/head2head"
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            matches = data.get('matches', []) 
            if not matches: return "無對賽記錄", "N/A"
            
            matches.sort(key=lambda x: x['utcDate'], reverse=True)
            recent_matches = matches[:10]
            total_games = 0
            h_wins = 0; a_wins = 0; draws = 0
            o15 = 0; o25 = 0; o35 = 0
            
            for m in recent_matches:
                if m['status'] != 'FINISHED': continue
                total_games += 1
                winner = m['score']['winner']
                if winner == 'DRAW': draws += 1
                elif winner == 'HOME_TEAM':
                    if m['homeTeam']['id'] == current_home_id: h_wins += 1
                    else: a_wins += 1
                elif winner == 'AWAY_TEAM':
                    if m['awayTeam']['id'] == current_home_id: h_wins += 1
                    else: a_wins += 1
                
                try:
                    goals = m['score']['fullTime']['home'] + m['score']['fullTime']['away']
                    if goals > 1.5: o15 += 1
                    if goals > 2.5: o25 += 1
                    if goals > 3.5: o35 += 1
                except: pass 
            
            if total_games == 0: return "無有效對賽", "N/A"
            p15 = round((o15 / total_games) * 100)
            p25 = round((o25 / total_games) * 100)
            p35 = round((o35 / total_games) * 100)

            h2h_str = f"近{total_games}場: 主{h_wins}勝 | 和{draws} | 客{a_wins}勝"
            ou_str = f"近{total_games}場大球率: 1.5球({p15}%) | 2.5球({p25}%) | 3.5球({p35}%)"
            return h2h_str, ou_str
        else: return "N/A", "N/A"
    except Exception as e:
        print(f"H2H Error: {e}")
        return "N/A", "N/A"

# ================= 主流程 =================
def get_real_data(market_value_map):
    standings = get_all_standings_with_stats() # 這裡現在包含了主客場獨立數據
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 數據引擎啟動 (主客分離模式)...")
    
    headers = {'X-Auth-Token': API_KEY}
    today = datetime.now()
    start_date = (today - timedelta(days=6)).strftime('%Y-%m-%d')
    end_date = (today + timedelta(days=3)).strftime('%Y-%m-%d')
    
    params = { 'dateFrom': start_date, 'dateTo': end_date, 'competitions': ",".join(COMPETITIONS) }

    try:
        response = requests.get(f"{BASE_URL}/matches", headers=headers, params=params)
        if response.status_code != 200:
            print(f"❌ API 請求失敗: {response.text}")
            return []

        matches = response.json().get('matches', [])
        if not matches:
            print(f"⚠️ 期間無賽事。")
            return []

        cleaned_data = []
        hk_tz = pytz.timezone('Asia/Hong_Kong')
        print(f"🔍 發現 {len(matches)} 場賽事，正在進行 AI 運算...")

        for index, match in enumerate(matches):
            utc_str = match['utcDate']
            utc_dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            hk_dt = utc_dt.astimezone(hk_tz)
            time_str = hk_dt.strftime('%Y-%m-%d %H:%M') 

            status_raw = match['status']
            status = '未開賽'
            if status_raw in ['IN_PLAY', 'PAUSED']: status = '進行中'
            elif status_raw == 'FINISHED': status = '完場'
            
            score_h = match['score']['fullTime']['home']
            score_a = match['score']['fullTime']['away']

            home_id = match['homeTeam']['id']
            away_id = match['awayTeam']['id']
            home_name = match['homeTeam']['shortName'] or match['homeTeam']['name']
            away_name = match['awayTeam']['shortName'] or match['awayTeam']['name']
            league_code = match['competition']['code'] # 例如 'PL'
            
            # 獲取球隊數據
            default_stats = {'rank': '-', 'form': 'N/A', 'home_att': 1.2, 'home_def': 1.2, 'away_att': 1.0, 'away_def': 1.0}
            home_info = standings.get(home_id, default_stats)
            away_info = standings.get(away_id, default_stats)

            home_value = market_value_map.get(home_name, "N/A")
            away_value = market_value_map.get(away_name, "N/A")
            
            # --- API 限制保護 & H2H 獲取 ---
            if status != '完場':
                print(f"   🤖 深度運算: {home_name} (主) vs {away_name} (客)...")
                h2h_str, ou_stats_str = get_h2h_and_ou_stats(match['id'], home_id, away_id)
                time.sleep(6.1) 
            else:
                h2h_str = "N/A"
                ou_stats_str = "N/A"

            # === AI 核心預測 (主客分離 + 聯賽係數 + H2H權重) ===
            pred_h_goals, pred_a_goals = predict_match_outcome(home_info, away_info, home_value, away_value, h2h_str, league_code)

            att_h = round(pred_h_goals * 1.2, 1)
            att_a = round(pred_a_goals * 1.2, 1)

            match_info = {
                '時間': time_str,
                '聯賽': match['competition']['name'],
                '主隊': home_name,
                '客隊': away_name,
                '主排名': home_info['rank'], 
                '客排名': away_info['rank'],
                '主近況': home_info['form'],
                '客近況': away_info['form'],
                '主預測': pred_h_goals,
                '客預測': pred_a_goals,
                '總球數': round(pred_h_goals + pred_a_goals, 1),
                '主攻(H)': att_h,
                '客攻(A)': att_a,
                '狀態': status,
                '主分': score_h if score_h is not None else '',
                '客分': score_a if score_a is not None else '',
                'H2H': h2h_str,
                '大小球統計': ou_stats_str,
                '主隊身價': home_value, 
                '客隊身價': away_value
            }
            cleaned_data.append(match_info)
            
        print(f"✅ 運算完成！共處理 {len(cleaned_data)} 場賽事。")
        return cleaned_data
    except Exception as e:
        print(f"⚠️ 執行錯誤: {e}")
        return []

def main():
    spreadsheet = get_google_spreadsheet()
    market_value_map = {}
    if spreadsheet:
        market_value_map = load_manual_market_values(spreadsheet)
    
    real_data = get_real_data(market_value_map)
    
    if real_data:
        df = pd.DataFrame(real_data)
        cols = ['時間', '聯賽', '主隊', '客隊', '主排名', '客排名', '主近況', '客近況', 
                '主預測', '客預測', '總球數', '主攻(H)', '客攻(A)', '狀態', '主分', '客分', 'H2H', '大小球統計', '主隊身價', '客隊身價']
        df = df.reindex(columns=cols, fill_value='')
        
        if spreadsheet:
            try:
                print(f"🚀 更新 Google Sheet...")
                upload_sheet = spreadsheet.sheet1 
                header = df.columns.values.tolist()
                values = df.astype(str).values.tolist()
                data_to_upload = [header] + values
                upload_sheet.clear()
                upload_sheet.update(range_name='A1', values=data_to_upload)
                print(f"☁️ 更新成功！")
            except Exception as e:
                print(f"❌ 上傳失敗: {e}")
    else:
        print("⚠️ 無數據可更新。")

if __name__ == "__main__":
    main()
