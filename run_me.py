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

# 完整支援的 11 個聯賽
COMPETITIONS = [
    'PL', 'PD', 'CL', 'SA', 'BL1', 'FL1', 
    'DED', 'PPL', 'ELC', 'BSA', 'CLI'
]

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
    except: return 0

# ================= 輔助：計算波膽 (Correct Score) =================
def calculate_correct_score_probs(home_exp, away_exp):
    """
    計算最可能的 3 個波膽
    """
    def poisson(k, lam):
        return (lam**k * math.exp(-lam)) / math.factorial(k)
    
    scores = []
    for h in range(6):
        for a in range(6):
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            scores.append({'score': f"{h}:{a}", 'prob': prob})
    
    scores.sort(key=lambda x: x['prob'], reverse=True)
    top_3 = [f"{s['score']} ({int(s['prob']*100)}%)" for s in scores[:3]]
    return " | ".join(top_3)

# ================= 計算權重近況 =================
def calculate_weighted_form_score(form_str):
    if not form_str or form_str == 'N/A': return 1.5 
    score = 0; total_weight = 0
    relevant_form = form_str.replace(',', '').strip()[-5:]
    weights = [1.0, 1.1, 1.2, 1.3, 1.5]
    start_idx = 5 - len(relevant_form)
    current_weights = weights[start_idx:]
    
    for i, char in enumerate(relevant_form):
        w = current_weights[i]
        s = 3 if char.upper() == 'W' else 1 if char.upper() == 'D' else 0
        score += s * w
        total_weight += w
    return score / total_weight if total_weight > 0 else 1.5

# ================= 獲取數據 =================
def get_all_standings_with_stats():
    print("📊 正在計算各聯賽 [真實平均數據]...")
    standings_map = {}
    league_stats = {} 
    headers = {'X-Auth-Token': API_KEY}
    
    for comp in COMPETITIONS:
        try:
            url = f"{BASE_URL}/competitions/{comp}/standings"
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                total_h=0; total_a=0; total_m=0
                
                for table in data.get('standings', []):
                    table_type = table['type']
                    for entry in table['table']:
                        team_id = entry['team']['id']
                        if team_id not in standings_map:
                            standings_map[team_id] = {
                                'rank': 0, 'form': 'N/A', 
                                'home_att': 1.0, 'home_def': 1.0,
                                'away_att': 1.0, 'away_def': 1.0,
                                'volatility': 2.5, 'season_ppg': 1.3
                            }
                        
                        played = entry['playedGames']
                        points = entry['points']
                        gf = entry['goalsFor']; ga = entry['goalsAgainst']
                        avg_gf = gf/played if played>0 else 0
                        avg_ga = ga/played if played>0 else 0

                        if table_type == 'TOTAL':
                            standings_map[team_id]['rank'] = entry['position']
                            standings_map[team_id]['form'] = entry.get('form', 'N/A')
                            standings_map[team_id]['season_ppg'] = points/played if played>0 else 1.3
                            if played>0: standings_map[team_id]['volatility'] = (gf+ga)/played
                        elif table_type == 'HOME':
                            standings_map[team_id]['home_att'] = avg_gf if avg_gf>0 else 1.0
                            standings_map[team_id]['home_def'] = avg_ga if avg_ga>0 else 1.0
                            total_h += gf; 
                            if played>0: total_m += played
                        elif table_type == 'AWAY':
                            standings_map[team_id]['away_att'] = avg_gf if avg_gf>0 else 1.0
                            standings_map[team_id]['away_def'] = avg_ga if avg_ga>0 else 1.0
                            total_a += gf

                if total_m > 10:
                    league_stats[data['competition']['code']] = {'avg_home': total_h/total_m, 'avg_away': total_a/total_m}
                else:
                    league_stats[data['competition']['code']] = {'avg_home': 1.5, 'avg_away': 1.2}
            time.sleep(1.2) 
        except Exception as e:
            print(f"⚠️ 無法獲取 {comp}: {e}")
            
    return standings_map, league_stats

# ================= 預測模型 =================
def predict_match_outcome(home_stats, away_stats, home_val_str, away_val_str, h2h_summary, league_avg):
    lg_h = max(league_avg.get('avg_home', 1.5), 0.5)
    lg_a = max(league_avg.get('avg_away', 1.2), 0.5)

    # 1. Poisson
    h_att = home_stats['home_att'] / lg_h
    a_def = away_stats['away_def'] / lg_h
    raw_h = h_att * a_def * lg_h
    
    a_att = away_stats['away_att'] / lg_a
    h_def = home_stats['home_def'] / lg_a
    raw_a = a_att * h_def * lg_a
    
    # 2. 身價
    h_v = parse_market_value(home_val_str); a_v = parse_market_value(away_val_str)
    if h_v > 0 and a_v > 0:
        ratio = h_v / a_v
        factor = max(min(math.log(ratio) * 0.08, 0.25), -0.25)
        raw_h *= (1 + factor)
        raw_a *= (1 - factor)

    # 3. 動量
    h_form = calculate_weighted_form_score(home_stats['form'])
    a_form = calculate_weighted_form_score(away_stats['form'])
    h_mom = h_form - home_stats['season_ppg']
    a_mom = a_form - away_stats['season_ppg']
    raw_h *= (1 + (h_mom * 0.05))
    raw_a *= (1 + (a_mom * 0.05))

    # 4. H2H
    try:
        if "主" in h2h_summary and "勝" in h2h_summary:
            parts = h2h_summary.split('|')
            h_wins = int(parts[0].split('主')[1].split('勝')[0])
            a_wins = int(parts[2].split('客')[1].split('勝')[0])
            total = h_wins + a_wins + int(parts[1].split('和')[1])
            if total > 0:
                h_rate = h_wins/total; a_rate = a_wins/total
                raw_h *= (1 + (h_rate - 0.33) * 0.2)
                raw_a *= (1 + (a_rate - 0.33) * 0.2)
    except: pass

    # 5. 波動
    vol = (home_stats.get('volatility', 2.5) + away_stats.get('volatility', 2.5)) / 2
    
    return round(raw_h, 2), round(raw_a, 2), round(vol, 1), round(h_mom, 2), round(a_mom, 2)

# ================= H2H =================
def get_h2h_and_ou_stats(match_id, h_id, a_id):
    headers = {'X-Auth-Token': API_KEY}
    url = f"{BASE_URL}/matches/{match_id}/head2head"
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            matches = data.get('matches', []) 
            if not matches: return "無對賽記錄", "N/A"
            matches.sort(key=lambda x: x['utcDate'], reverse=True)
            recent = matches[:10]
            total=0; h_w=0; a_w=0; d=0; o15=0; o25=0; o35=0
            for m in recent:
                if m['status'] != 'FINISHED': continue
                total+=1
                w = m['score']['winner']
                if w == 'DRAW': d+=1
                elif w == 'HOME_TEAM':
                    if m['homeTeam']['id'] == h_id: h_w+=1
                    else: a_w+=1
                elif w == 'AWAY_TEAM':
                    if m['awayTeam']['id'] == h_id: h_w+=1
                    else: a_w+=1
                try:
                    g = m['score']['fullTime']['home'] + m['score']['fullTime']['away']
                    if g>1.5: o15+=1
                    if g>2.5: o25+=1
                    if g>3.5: o35+=1
                except: pass
            if total==0: return "無有效對賽", "N/A"
            p15=round(o15/total*100); p25=round(o25/total*100); p35=round(o35/total*100)
            return f"近{total}場: 主{h_w}勝 | 和{d} | 客{a_w}勝", f"近{total}場大球率: 1.5球({p15}%) | 2.5球({p25}%) | 3.5球({p35}%)"
        return "N/A", "N/A"
    except: return "N/A", "N/A"

# ================= 主流程 =================
def get_real_data(market_value_map):
    standings, league_stats = get_all_standings_with_stats()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 數據引擎啟動 (強制更新版)...")
    
    headers = {'X-Auth-Token': API_KEY}
    today = datetime.now()
    start_date = (today - timedelta(days=6)).strftime('%Y-%m-%d')
    end_date = (today + timedelta(days=3)).strftime('%Y-%m-%d')
    params = { 'dateFrom': start_date, 'dateTo': end_date, 'competitions': ",".join(COMPETITIONS) }

    try:
        response = requests.get(f"{BASE_URL}/matches", headers=headers, params=params)
        matches = response.json().get('matches', [])
        if not matches: return []

        cleaned = []
        hk_tz = pytz.timezone('Asia/Hong_Kong')
        print(f"🔍 發現 {len(matches)} 場賽事，正在計算波膽...")

        for index, match in enumerate(matches):
            utc_dt = datetime.strptime(match['utcDate'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            time_str = utc_dt.astimezone(hk_tz).strftime('%Y-%m-%d %H:%M') 
            status = '進行中' if match['status'] in ['IN_PLAY', 'PAUSED'] else '完場' if match['status'] == 'FINISHED' else '未開賽'
            
            h_id = match['homeTeam']['id']; a_id = match['awayTeam']['id']
            h_name = match['homeTeam']['shortName'] or match['homeTeam']['name']
            a_name = match['awayTeam']['shortName'] or match['awayTeam']['name']
            lg_code = match['competition']['code']
            
            h_info = standings.get(h_id, {'rank':0,'form':'N/A','home_att':1.2,'home_def':1.2,'volatility':2.5,'season_ppg':1.3})
            a_info = standings.get(a_id, {'rank':0,'form':'N/A','away_att':1.0,'away_def':1.0,'volatility':2.5,'season_ppg':1.3})
            h_val = market_value_map.get(h_name, "N/A"); a_val = market_value_map.get(a_name, "N/A")
            
            print(f"   🤖 計算中 [{index+1}/{len(matches)}]: {h_name} vs {a_name}...")
            h2h, ou = get_h2h_and_ou_stats(match['id'], h_id, a_id)
            time.sleep(6.1)

            lg_avg = league_stats.get(lg_code, {'avg_home': 1.5, 'avg_away': 1.2})
            pred_h, pred_a, vol, h_mom, a_mom = predict_match_outcome(h_info, a_info, h_val, a_val, h2h, lg_avg)
            
            # 計算波膽
            correct_score_str = calculate_correct_score_probs(pred_h, pred_a)

            cleaned.append({
                '時間': time_str, '聯賽': match['competition']['name'],
                '主隊': h_name, '客隊': a_name,
                '主排名': h_info['rank'], '客排名': a_info['rank'],
                '主近況': h_info['form'], '客近況': a_info['form'],
                '主預測': pred_h, '客預測': pred_a,
                '總球數': round(pred_h + pred_a, 1),
                '主攻(H)': round(pred_h * 1.2, 1), '客攻(A)': round(pred_a * 1.2, 1),
                '狀態': status,
                '主分': match['score']['fullTime']['home'] if match['score']['fullTime']['home'] is not None else '',
                '客分': match['score']['fullTime']['away'] if match['score']['fullTime']['away'] is not None else '',
                'H2H': h2h, '大小球統計': ou,
                '主隊身價': h_val, '客隊身價': a_val,
                '賽事風格': vol, '主動量': h_mom, '客動量': a_mom,
                '波膽預測': correct_score_str 
            })
        return cleaned
    except Exception as e:
        print(f"⚠️ 錯誤: {e}"); return []

def main():
    spreadsheet = get_google_spreadsheet()
    market_value_map = load_manual_market_values(spreadsheet) if spreadsheet else {}
    real_data = get_real_data(market_value_map)
    if real_data:
        df = pd.DataFrame(real_data)
        # 強制定義欄位順序，包含 '波膽預測'
        cols = ['時間','聯賽','主隊','客隊','主排名','客排名','主近況','客近況','主預測','客預測','總球數','主攻(H)','客攻(A)','狀態','主分','客分','H2H','大小球統計','主隊身價','客隊身價','賽事風格','主動量','客動量','波膽預測']
        df = df.reindex(columns=cols, fill_value='')
        if spreadsheet:
            try:
                # 這裡使用 get_worksheet(0) 確保選到第一個分頁
                upload_sheet = spreadsheet.get_worksheet(0)
                print(f"🚀 正在強制重寫 Google Sheet 分頁: {upload_sheet.title}")
                print(f"   📋 準備寫入欄位: {', '.join(cols)}")
                
                # 關鍵：清空舊表
                upload_sheet.clear() 
                
                # 寫入新資料（含標題）
                upload_sheet.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print(f"✅ 成功寫入 {len(df)} 筆數據 (含波膽預測)！")
            except Exception as e: print(f"❌ 寫入失敗: {e}")

if __name__ == "__main__":
    main()
