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
    """
    將 '€1200M' 或 '1,200' 轉為 float 數字以便計算
    """
    if not val_str or val_str == 'N/A': return 0
    try:
        clean = str(val_str).replace('€', '').replace('M', '').replace(',', '').strip()
        return float(clean)
    except:
        return 0

# ================= 輔助：計算近況分數 =================
def calculate_form_score(form_str):
    """
    將 WWDLW 轉換為分數: W=3, D=1, L=0
    回傳平均分 (0~3)
    """
    if not form_str or form_str == 'N/A': return 1.5 # 預設中立
    
    score = 0
    count = 0
    # 取最後 5 場
    relevant_form = form_str.replace(',', '').strip()[-5:]
    
    for char in relevant_form:
        if char.upper() == 'W': score += 3
        elif char.upper() == 'D': score += 1
        else: score += 0
        count += 1
        
    if count == 0: return 1.5
    return score / count # 平均分

# ================= 獲取聯賽詳細數據 (攻防能力) =================
def get_all_standings_with_stats():
    print("📊 正在獲取各聯賽實時排名與攻防數據...")
    standings_map = {}
    headers = {'X-Auth-Token': API_KEY}
    
    for comp in COMPETITIONS:
        try:
            url = f"{BASE_URL}/competitions/{comp}/standings"
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                for table in data.get('standings', []):
                    if table['type'] == 'TOTAL':
                        for entry in table['table']:
                            team_id = entry['team']['id']
                            raw_form = entry.get('form')
                            if raw_form is None: raw_form = "N/A"
                            
                            # === 關鍵：獲取進球與失球數據 ===
                            played = entry['playedGames']
                            goals_for = entry['goalsFor']
                            goals_against = entry['goalsAgainst']
                            
                            # 計算場均數據 (避免除以0)
                            avg_gf = goals_for / played if played > 0 else 1.2
                            avg_ga = goals_against / played if played > 0 else 1.2

                            standings_map[team_id] = {
                                'rank': entry['position'],
                                'form': raw_form,
                                'points': entry['points'],
                                'avg_gf': avg_gf, # 場均進球 (攻擊力)
                                'avg_ga': avg_ga  # 場均失球 (防守弱點)
                            }
            time.sleep(1.5) 
        except Exception as e:
            print(f"⚠️ 無法獲取 {comp} 排名: {e}")
    return standings_map

# ================= 核心算法：真實預測模型 =================
def predict_match_outcome(home_stats, away_stats, home_val_str, away_val_str):
    """
    基於真實數據計算預期進球 (Expected Goals)
    """
    # 1. 基礎攻防模型
    # 主隊預期入球 = (主隊攻擊 + 客隊防守) / 2
    raw_h_exp = (home_stats['avg_gf'] + away_stats['avg_ga']) / 2
    # 客隊預期入球 = (客隊攻擊 + 主隊防守) / 2
    raw_a_exp = (away_stats['avg_gf'] + home_stats['avg_ga']) / 2
    
    # 2. 加入主場優勢 (通常主隊有 +0.2 ~ +0.3 的優勢)
    raw_h_exp *= 1.15
    
    # 3. 身價修正 (Market Value Adjustment)
    h_val = parse_market_value(home_val_str)
    a_val = parse_market_value(away_val_str)
    
    if h_val > 0 and a_val > 0:
        ratio = h_val / a_val
        if ratio > 5.0: # 身價懸殊 (主隊強)
            raw_h_exp *= 1.25
            raw_a_exp *= 0.8
        elif ratio > 2.0:
            raw_h_exp *= 1.1
            raw_a_exp *= 0.9
        elif ratio < 0.2: # 身價懸殊 (客隊強)
            raw_h_exp *= 0.8
            raw_a_exp *= 1.25
        elif ratio < 0.5:
            raw_h_exp *= 0.9
            raw_a_exp *= 1.1

    # 4. 近況修正 (Form Adjustment)
    h_form_score = calculate_form_score(home_stats['form']) # 0~3
    a_form_score = calculate_form_score(away_stats['form']) # 0~3
    
    form_diff = h_form_score - a_form_score
    # 如果主隊近況好很多 (例如差 2 分以上)
    if form_diff > 1.5:
        raw_h_exp *= 1.1
    elif form_diff < -1.5:
        raw_a_exp *= 1.1

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
    # 1. 獲取帶有攻防數據的排名表
    standings = get_all_standings_with_stats()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 數據引擎啟動...")
    
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
            
            # 獲取球隊數據 (如果沒有數據，給予預設值)
            default_stats = {'rank': '-', 'form': 'N/A', 'avg_gf': 1.3, 'avg_ga': 1.3}
            home_info = standings.get(home_id, default_stats)
            away_info = standings.get(away_id, default_stats)

            home_value = market_value_map.get(home_name, "N/A")
            away_value = market_value_map.get(away_name, "N/A")
            
            # --- API 限制保護 ---
            if status != '完場':
                print(f"   🤖 計算中: {home_name} vs {away_name} ...")
                h2h_str, ou_stats_str = get_h2h_and_ou_stats(match['id'], home_id, away_id)
                time.sleep(6.1) # 避免 API 封鎖
            else:
                h2h_str = "N/A"
                ou_stats_str = "N/A"

            # === AI 核心預測 (不再是 Random) ===
            pred_h_goals, pred_a_goals = predict_match_outcome(home_info, away_info, home_value, away_value)

            # 計算主攻/客攻指數 (UI用)
            att_h = round(pred_h_goals * 1.3, 1) # 攻擊指數通常比預期進球高一點
            att_a = round(pred_a_goals * 1.3, 1)

            match_info = {
                '時間': time_str,
                '聯賽': match['competition']['name'],
                '主隊': home_name,
                '客隊': away_name,
                '主排名': home_info['rank'], 
                '客排名': away_info['rank'],
                '主近況': home_info['form'],
                '客近況': away_info['form'],
                '主預測': pred_h_goals,   # 真實計算結果
                '客預測': pred_a_goals,   # 真實計算結果
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
