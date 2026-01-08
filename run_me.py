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
    if not val_str or val_str == 'N/A': return 0
    try:
        clean = str(val_str).replace('€', '').replace('M', '').replace(',', '').strip()
        return float(clean)
    except:
        return 0

# ================= (新) 計算權重近況分數 =================
def calculate_weighted_form_score(form_str):
    if not form_str or form_str == 'N/A': return 1.5
    score = 0; total_weight = 0
    relevant_form = form_str.replace(',', '').strip()[-5:]
    weights = [1.0, 1.1, 1.2, 1.3, 1.5] # 最近一場權重最高
    start_idx = 5 - len(relevant_form)
    current_weights = weights[start_idx:]
    
    for i, char in enumerate(relevant_form):
        w = current_weights[i]
        s = 0
        if char.upper() == 'W': s = 3
        elif char.upper() == 'D': s = 1
        score += s * w
        total_weight += w
    if total_weight == 0: return 1.5
    return score / total_weight 

# ================= 獲取聯賽詳細數據 & 動態計算聯賽平均值 =================
def get_all_standings_with_stats():
    print("📊 正在計算各聯賽 [真實平均入球數據]...")
    standings_map = {}
    league_stats = {} # 儲存每個聯賽的平均值
    headers = {'X-Auth-Token': API_KEY}
    
    for comp in COMPETITIONS:
        try:
            url = f"{BASE_URL}/competitions/{comp}/standings"
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                
                # 初始化該聯賽統計
                total_home_goals = 0
                total_away_goals = 0
                total_matches_played = 0
                
                # 第一次遍歷：收集球隊數據並計算聯賽總入球
                for table in data.get('standings', []):
                    table_type = table['type']
                    
                    for entry in table['table']:
                        team_id = entry['team']['id']
                        if team_id not in standings_map:
                            standings_map[team_id] = {
                                'rank': 0, 'form': 'N/A', 
                                'home_att': 1.2, 'home_def': 1.2,
                                'away_att': 1.0, 'away_def': 1.0,
                                'volatility': 2.5
                            }
                        
                        played = entry['playedGames']
                        gf = entry['goalsFor']
                        ga = entry['goalsAgainst']
                        
                        avg_gf = gf / played if played > 0 else 0
                        avg_ga = ga / played if played > 0 else 0

                        if table_type == 'TOTAL':
                            standings_map[team_id]['rank'] = entry['position']
                            standings_map[team_id]['form'] = entry.get('form', 'N/A')
                            if played > 0:
                                standings_map[team_id]['volatility'] = (gf + ga) / played
                                
                        elif table_type == 'HOME':
                            standings_map[team_id]['home_att'] = avg_gf if avg_gf > 0 else 1.0
                            standings_map[team_id]['home_def'] = avg_ga if avg_ga > 0 else 1.0
                            total_home_goals += gf
                            if played > 0: total_matches_played += played # 這裡累加的是主場場次
                            
                        elif table_type == 'AWAY':
                            standings_map[team_id]['away_att'] = avg_gf if avg_gf > 0 else 1.0
                            standings_map[team_id]['away_def'] = avg_ga if avg_ga > 0 else 1.0
                            total_away_goals += gf

                # 計算該聯賽的平均值
                if total_matches_played > 10:
                    avg_home = total_home_goals / total_matches_played
                    avg_away = total_away_goals / total_matches_played
                else:
                    # 賽季剛開始的默認值
                    avg_home = 1.5
                    avg_away = 1.2
                
                league_stats[data['competition']['code']] = {
                    'avg_home': avg_home,
                    'avg_away': avg_away
                }
                print(f"   👉 {comp}: 主場均{avg_home:.2f}球 | 客場均{avg_away:.2f}球")

            time.sleep(1.2) 
        except Exception as e:
            print(f"⚠️ 無法獲取 {comp} 排名: {e}")
            
    return standings_map, league_stats

# ================= 核心算法：真實統計模型 (Statistical Model) =================
def predict_match_outcome(home_stats, away_stats, home_val_str, away_val_str, h2h_summary, league_avg):
    """
    使用標準泊松分佈模型 (Poisson Distribution Model)
    Exp = (Team Attack / League Avg Attack) * (Opponent Def / League Avg Def) * League Avg
    """
    
    # 獲取聯賽基準值 (不再靠估，而是用 API 算出來的真實平均)
    lg_avg_home = league_avg.get('avg_home', 1.5)
    lg_avg_away = league_avg.get('avg_away', 1.2)
    
    # 防止除以零
    if lg_avg_home < 0.1: lg_avg_home = 1.5
    if lg_avg_away < 0.1: lg_avg_away = 1.2

    # 1. 計算攻防強度 (Attack/Defense Strength)
    # 主隊攻擊強度 = 主隊主場入球 / 聯賽主場平均入球
    home_att_str = home_stats['home_att'] / lg_avg_home
    # 客隊防守強度 = 客隊客場失球 / 聯賽主場平均入球 (注意：客隊失球是相對於主場入球)
    away_def_str = away_stats['away_def'] / lg_avg_home
    
    # 客隊攻擊強度 = 客隊客場入球 / 聯賽客場平均入球
    away_att_str = away_stats['away_att'] / lg_avg_away
    # 主隊防守強度 = 主隊主場失球 / 聯賽客場平均入球
    home_def_str = home_stats['home_def'] / lg_avg_away
    
    # 2. 計算基礎預期入球
    raw_h_exp = home_att_str * away_def_str * lg_avg_home
    raw_a_exp = away_att_str * home_def_str * lg_avg_away
    
    # 3. 身價修正 (Market Value Adjustment) - 這是「質素」修正
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

    # 4. 權重近況修正 (Weighted Form Adjustment) - 這是「狀態」修正
    h_form = calculate_weighted_form_score(home_stats['form'])
    a_form = calculate_weighted_form_score(away_stats['form'])
    
    form_diff = h_form - a_form
    if form_diff > 1.0: raw_h_exp *= 1.15
    elif form_diff > 0.5: raw_h_exp *= 1.05
    elif form_diff < -1.0: raw_a_exp *= 1.15
    elif form_diff < -0.5: raw_a_exp *= 1.05

    # 5. H2H 歷史權重 (心理剋星)
    try:
        if "主" in h2h_summary and "勝" in h2h_summary:
            parts = h2h_summary.split('|')
            h_wins = int(parts[0].split('主')[1].split('勝')[0])
            a_wins = int(parts[2].split('客')[1].split('勝')[0])
            total = h_wins + a_wins + int(parts[1].split('和')[1])
            if total > 0:
                h_win_rate = h_wins / total
                a_win_rate = a_wins / total
                if h_win_rate > 0.6: raw_h_exp *= 1.1
                elif a_win_rate > 0.6: raw_a_exp *= 1.1
    except: pass

    # 6. 波動值修正 (風格修正)
    vol_h = home_stats.get('volatility', 2.5)
    vol_a = away_stats.get('volatility', 2.5)
    avg_volatility = (vol_h + vol_a) / 2
    
    if avg_volatility > 3.0: # 開放大戰
        raw_h_exp *= 1.05
        raw_a_exp *= 1.05
    elif avg_volatility < 2.3: # 死守悶戰
        raw_h_exp *= 0.95
        raw_a_exp *= 0.95

    return round(raw_h_exp, 2), round(raw_a_exp, 2), round(avg_volatility, 1)

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
    # 改為同時獲取 球隊數據 和 聯賽平均數據
    standings, league_stats = get_all_standings_with_stats()
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 數據引擎啟動 (使用動態聯賽平均值)...")
    
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
        print(f"🔍 發現 {len(matches)} 場賽事，正在進行運算...")

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
            league_code = match['competition']['code']
            
            home_info = standings.get(home_id, {'rank': '-', 'form': 'N/A', 'home_att': 1.2, 'home_def': 1.2, 'volatility': 2.5})
            away_info = standings.get(away_id, {'rank': '-', 'form': 'N/A', 'away_att': 1.0, 'away_def': 1.0, 'volatility': 2.5})

            home_value = market_value_map.get(home_name, "N/A")
            away_value = market_value_map.get(away_name, "N/A")
            
            print(f"   🤖 深度運算 [{index+1}/{len(matches)}]: {home_name} vs {away_name} ({status})...")
            h2h_str, ou_stats_str = get_h2h_and_ou_stats(match['id'], home_id, away_id)
            time.sleep(6.1) 

            # === AI 核心預測 (傳入真實聯賽平均值) ===
            league_avg = league_stats.get(league_code, {'avg_home': 1.5, 'avg_away': 1.2})
            pred_h_goals, pred_a_goals, game_volatility = predict_match_outcome(
                home_info, away_info, home_value, away_value, h2h_str, league_avg
            )

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
                '客隊身價': away_value,
                '賽事風格': game_volatility
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
                '主預測', '客預測', '總球數', '主攻(H)', '客攻(A)', '狀態', '主分', '客分', 'H2H', '大小球統計', '主隊身價', '客隊身價', '賽事風格']
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
