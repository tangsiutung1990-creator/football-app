import requests
import pandas as pd
import time
import math
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
import random

# ================= 設定區 =================
API_KEY = '531bb40a089446bdae76a019f2af3beb' # 建議換上你自己的 Key 避免共用額度
BASE_URL = 'https://api.football-data.org/v4'
GOOGLE_SHEET_NAME = "數據上傳" 
MANUAL_TAB_NAME = "球隊身價表" 

# 聯賽列表
COMPETITIONS = ['PL','PD','CL','SA','BL1','FL1','DED','PPL','ELC','BSA','CLI','WC','EC']

# [核心修正] 聯賽風格係數 (大於 1.0 代表大球聯賽)
# 這裡數值調高，強制模型傾向預測更多入球
LEAGUE_GOAL_FACTOR = {
    'BL1': 1.25, # 德甲 (超大)
    'DED': 1.25, # 荷甲 (超大)
    'PL': 1.10,  # 英超 (偏大)
    'PD': 1.05,  # 西甲 (標準)
    'SA': 1.05,  # 意甲 (標準)
    'FL1': 1.02, # 法甲
    'PPL': 1.10, # 葡超
    'BSA': 0.98, # 巴甲
    'ELC': 1.05  # 英冠
}

# ================= 智能 API 請求函式 =================
def call_api_with_retry(url, params=None, headers=None, retries=3):
    for i in range(retries):
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200: return response.json()
            elif response.status_code == 429:
                print(f"🛑 API 頻率限制 (429)，休息 65 秒...")
                time.sleep(65)
                continue 
            elif response.status_code >= 400:
                 print(f"⚠️ API 錯誤: {response.status_code} | {url}")
                 return None
        except Exception as e:
            print(f"❌ 連線異常: {e}")
            time.sleep(5)
            continue
    return None

# ================= Google Sheet 連接 =================
def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except Exception as e:
        print(f"❌ Google Sheet 連線失敗: {e}")
        return None

# ================= 讀取身價表 =================
def load_manual_market_values(spreadsheet):
    print(f"📖 讀取 '{MANUAL_TAB_NAME}'...")
    market_value_map = {}
    try:
        worksheet = spreadsheet.worksheet(MANUAL_TAB_NAME)
        records = worksheet.get_all_records()
        for row in records:
            team = str(row.get('球隊名稱', '')).strip()
            val = str(row.get('身價', '')).strip()
            if team and val: market_value_map[team] = val
        print(f"✅ 讀取了 {len(market_value_map)} 支球隊身價")
        return market_value_map
    except: return {}

def parse_market_value(val_str):
    if not val_str or val_str == 'N/A': return 0
    try:
        clean = str(val_str).replace('€', '').replace('M', '').replace(',', '').strip()
        return float(clean)
    except: return 0

# ================= [數學核心] 進階機率計算 =================
def calculate_advanced_probs(home_exp, away_exp):
    def poisson(k, lam): return (lam**k * math.exp(-lam)) / math.factorial(k)
    
    h_win=0; draw=0; a_win=0
    for h in range(10):
        for a in range(10):
            p = poisson(h, home_exp) * poisson(a, away_exp)
            if h > a: h_win += p
            elif h == a: draw += p
            else: a_win += p
            
    p_h_score = 1 - poisson(0, home_exp)
    p_a_score = 1 - poisson(0, away_exp)
    btts = p_h_score * p_a_score
    
    odds_h = 1/h_win if h_win > 0.01 else 99.0
    odds_d = 1/draw if draw > 0.01 else 99.0
    odds_a = 1/a_win if a_win > 0.01 else 99.0
    
    return {'btts': round(btts*100, 1), 'cs_h': round(poisson(0, away_exp)*100, 1), 
            'cs_a': round(poisson(0, home_exp)*100, 1), 'odds_h': round(odds_h, 2), 
            'odds_d': round(odds_d, 2), 'odds_a': round(odds_a, 2)}

def calculate_correct_score_probs(home_exp, away_exp):
    def poisson(k, lam): return (lam**k * math.exp(-lam)) / math.factorial(k)
    scores = []
    # [優化] 擴大計算範圍，捕捉 3-0, 4-1 等高比分
    for h in range(8):
        for a in range(8):
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            scores.append({'score': f"{h}:{a}", 'prob': prob})
    scores.sort(key=lambda x: x['prob'], reverse=True)
    top_3 = [f"{s['score']} ({int(s['prob']*100)}%)" for s in scores[:3]]
    return " | ".join(top_3)

def calculate_weighted_form_score(form_str):
    if not form_str or form_str == 'N/A': return 1.5 
    score = 0; total_weight = 0
    relevant = form_str.replace(',', '').strip()[-5:]
    weights = [1.0, 1.2, 1.4, 1.6, 2.0] # [優化] 加大近期權重
    start_idx = 5 - len(relevant)
    curr_weights = weights[start_idx:]
    for i, char in enumerate(relevant):
        w = curr_weights[i]
        s = 3 if char.upper()=='W' else 1 if char.upper()=='D' else 0
        score += s * w
        total_weight += w
    return score / total_weight if total_weight > 0 else 1.5

# ================= 數據獲取 =================
def get_all_standings_with_stats():
    print("📊 計算聯賽基數...")
    standings_map = {}
    league_stats = {} 
    headers = {'X-Auth-Token': API_KEY}
    
    for i, comp in enumerate(COMPETITIONS):
        url = f"{BASE_URL}/competitions/{comp}/standings"
        data = call_api_with_retry(url, headers=headers)
        if data:
            total_h=0; total_a=0; total_m=0
            tables = data.get('standings', [])
            for table in tables:
                t_type = table['type']
                for entry in table['table']:
                    tid = entry['team']['id']
                    if tid not in standings_map:
                        standings_map[tid] = {'rank':0,'form':'N/A','home_att':1.3,'home_def':1.3,'away_att':1.0,'away_def':1.0,'volatility':2.5,'season_ppg':1.3}
                    
                    played = entry['playedGames']
                    points = entry['points']
                    gf = entry['goalsFor']; ga = entry['goalsAgainst']
                    
                    # [核心修正] 防止除以零，且給予較高的預設值 (避免數據不足時變成 0)
                    avg_gf = gf/played if played>0 else 1.35
                    avg_ga = ga/played if played>0 else 1.35

                    if t_type == 'TOTAL':
                        standings_map[tid]['rank'] = entry['position']
                        standings_map[tid]['form'] = entry.get('form', 'N/A')
                        standings_map[tid]['season_ppg'] = points/played if played>0 else 1.3
                        if played>0: standings_map[tid]['volatility'] = (gf+ga)/played
                    elif t_type == 'HOME':
                        standings_map[tid]['home_att'] = avg_gf
                        standings_map[tid]['home_def'] = avg_ga
                        total_h += gf; 
                        if played>0: total_m += played
                    elif t_type == 'AWAY':
                        standings_map[tid]['away_att'] = avg_gf
                        standings_map[tid]['away_def'] = avg_ga
                        total_a += gf
            
            # [核心修正] 聯賽平均值地板 (Floor) - 強制不低於 2.7 球
            if total_m > 10:
                avg_h = max(total_h/total_m, 1.45) 
                avg_a = max(total_a/total_m, 1.25)
            else:
                avg_h = 1.6; avg_a = 1.3 # 預設值調高
            
            league_stats[data['competition']['code']] = {'avg_home': avg_h, 'avg_away': avg_a}
        time.sleep(6.1)
    return standings_map, league_stats

# ================= 預測模型 (V4.0 Aggressive) =================
def predict_match_outcome(home_stats, away_stats, home_val_str, away_val_str, h2h_summary, league_avg, lg_code):
    # 1. 基數設定
    lg_h = league_avg.get('avg_home', 1.6)
    lg_a = league_avg.get('avg_away', 1.3)
    
    # 2. 聯賽風格加成
    factor = LEAGUE_GOAL_FACTOR.get(lg_code, 1.05)
    
    # 3. 攻防能力計算 (引入 Power Scaling ^1.3 拉開差距)
    # 如果攻擊力是 1.2 (比平均強 20%)，^1.3 後變成 1.26
    # 如果攻擊力是 0.8 (比平均弱 20%)，^1.3 後變成 0.74 (更弱)
    h_att_r = (home_stats['home_att'] / lg_h) 
    a_def_r = (away_stats['away_def'] / lg_h)
    h_strength = (h_att_r * a_def_r) ** 1.3  # 次方放大
    
    a_att_r = (away_stats['away_att'] / lg_a)
    h_def_r = (home_stats['home_def'] / lg_a)
    a_strength = (a_att_r * h_def_r) ** 1.3  # 次方放大

    # 4. 基礎預期入球
    raw_h = h_strength * lg_h * factor
    raw_a = a_strength * lg_a * factor
    
    # 5. 身價暴力修正 (權重提升至 0.25)
    h_v = parse_market_value(home_val_str); a_v = parse_market_value(away_val_str)
    if h_v > 0 and a_v > 0:
        ratio = h_v / a_v
        # Log 修正後直接乘 0.25，這會讓身價高 10 倍的球隊獲得顯著加成
        val_factor = max(min(math.log(ratio) * 0.25, 0.6), -0.6)
        raw_h *= (1 + val_factor)
        raw_a *= (1 - val_factor)

    # 6. 動量修正
    h_mom = calculate_weighted_form_score(home_stats['form']) - home_stats['season_ppg']
    a_mom = calculate_weighted_form_score(away_stats['form']) - away_stats['season_ppg']
    raw_h *= (1 + (h_mom * 0.12))
    raw_a *= (1 + (a_mom * 0.12))
    
    # 7. H2H 修正
    try:
        if "主" in h2h_summary and "勝" in h2h_summary:
            parts = h2h_summary.split('|')
            h_wins = int(parts[0].split('主')[1].split('勝')[0])
            total = int(parts[0].split('主')[1].split('勝')[0]) + int(parts[2].split('客')[1].split('勝')[0]) + int(parts[1].split('和')[1])
            if total > 0:
                h_rate = h_wins/total
                raw_h *= (1 + (h_rate - 0.4) * 0.2) # 主場勝率高於 40% 才加分
    except: pass

    # 8. 波動性 (防止死守小球)
    vol = (home_stats.get('volatility', 2.5) + away_stats.get('volatility', 2.5)) / 2
    if vol > 3.2: # 雙方都是大球隊
        raw_h *= 1.2; raw_a *= 1.2
    
    # 9. [最後防線] 確保強隊入球不會太低
    if raw_h < 0.5: raw_h = 0.55
    if raw_a < 0.4: raw_a = 0.45

    return round(raw_h, 2), round(raw_a, 2), round(vol, 1), round(h_mom, 2), round(a_mom, 2)

# ================= H2H 函式 (維持原樣) =================
def get_h2h_and_ou_stats(match_id, h_id, a_id):
    headers = {'X-Auth-Token': API_KEY}
    url = f"{BASE_URL}/matches/{match_id}/head2head"
    data = call_api_with_retry(url, headers=headers)
    try:
        if data:
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
                    if g>1.5: o15+=1; 
                    if g>2.5: o25+=1; 
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
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 V4.0 暴力拉伸版引擎啟動...")
    headers = {'X-Auth-Token': API_KEY}
    utc_now = datetime.now(pytz.utc)
    start_date = (utc_now - timedelta(days=3)).strftime('%Y-%m-%d') 
    end_date = (utc_now + timedelta(days=7)).strftime('%Y-%m-%d') 
    params = { 'dateFrom': start_date, 'dateTo': end_date, 'competitions': ",".join(COMPETITIONS) }

    try:
        response_json = call_api_with_retry(f"{BASE_URL}/matches", params=params, headers=headers)
        if not response_json: return []
        matches = response_json.get('matches', [])
        if not matches: return []

        cleaned = []
        hk_tz = pytz.timezone('Asia/Hong_Kong')

        for index, match in enumerate(matches):
            utc_dt = datetime.strptime(match['utcDate'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            time_str = utc_dt.astimezone(hk_tz).strftime('%Y-%m-%d %H:%M') 
            
            status = '進行中' if match['status'] in ['IN_PLAY','PAUSED'] else '完場' if match['status']=='FINISHED' else '延期/取消' if match['status'] in ['POSTPONED','CANCELLED'] else '未開賽'
            
            h_id = match['homeTeam']['id']; a_id = match['awayTeam']['id']
            h_name = match['homeTeam']['shortName'] or match['homeTeam']['name']
            a_name = match['awayTeam']['shortName'] or match['awayTeam']['name']
            lg_code = match['competition']['code']
            lg_name = match['competition']['name']
            
            h_info = standings.get(h_id, {'rank':0,'form':'N/A','home_att':1.3,'home_def':1.3,'volatility':2.5,'season_ppg':1.3})
            a_info = standings.get(a_id, {'rank':0,'form':'N/A','away_att':1.1,'away_def':1.1,'volatility':2.5,'season_ppg':1.3})
            h_val = market_value_map.get(h_name, "N/A"); a_val = market_value_map.get(a_name, "N/A")
            
            h2h, ou = get_h2h_and_ou_stats(match['id'], h_id, a_id)
            time.sleep(6.1)

            # 確保有聯賽平均值
            lg_avg = league_stats.get(lg_code, {'avg_home': 1.6, 'avg_away': 1.3})
            
            pred_h, pred_a, vol, h_mom, a_mom = predict_match_outcome(h_info, a_info, h_val, a_val, h2h, lg_avg, lg_code)
            
            # Debug: 如果預測結果太小，印出來檢查
            if pred_h + pred_a < 1.5:
                print(f"⚠️ [Debug] {h_name} vs {a_name} 預測偏低: {pred_h}:{pred_a}")

            correct_score_str = calculate_correct_score_probs(pred_h, pred_a)
            adv_stats = calculate_advanced_probs(pred_h, pred_a)

            score_h = match['score']['fullTime']['home']
            score_a = match['score']['fullTime']['away']
            if score_h is None: score_h = ''
            if score_a is None: score_a = ''

            cleaned.append({
                '時間': time_str, '聯賽': lg_name,
                '主隊': h_name, '客隊': a_name,
                '主排名': h_info['rank'], '客排名': a_info['rank'],
                '主近況': h_info['form'], '客近況': a_info['form'],
                '主預測': pred_h, '客預測': pred_a,
                '總球數': round(pred_h + pred_a, 1),
                '主攻(H)': round(pred_h * 1.2, 1), '客攻(A)': round(pred_a * 1.2, 1),
                '狀態': status,
                '主分': score_h, '客分': score_a,
                'H2H': h2h, '大小球統計': ou,
                '主隊身價': h_val, '客隊身價': a_val,
                '賽事風格': vol, '主動量': h_mom, '客動量': a_mom,
                '波膽預測': correct_score_str,
                'BTTS': adv_stats['btts'],
                '主零封': adv_stats['cs_h'], '客零封': adv_stats['cs_a'],
                '主賠': adv_stats['odds_h'], '和賠': adv_stats['odds_d'], '客賠': adv_stats['odds_a']
            })
        return cleaned
    except Exception as e:
        print(f"⚠️ 嚴重錯誤: {e}"); return []

def main():
    spreadsheet = get_google_spreadsheet()
    market_value_map = load_manual_market_values(spreadsheet) if spreadsheet else {}
    real_data = get_real_data(market_value_map)
    if real_data:
        df = pd.DataFrame(real_data)
        cols = ['時間','聯賽','主隊','客隊','主排名','客排名','主近況','客近況','主預測','客預測',
                '總球數','主攻(H)','客攻(A)','狀態','主分','客分','H2H','大小球統計',
                '主隊身價','客隊身價','賽事風格','主動量','客動量','波膽預測',
                'BTTS','主零封','客零封','主賠','和賠','客賠']
        df = df.reindex(columns=cols, fill_value='')
        if spreadsheet:
            try:
                upload_sheet = spreadsheet.sheet1 
                print(f"🚀 清空舊資料...")
                upload_sheet.clear() 
                print(f"📝 寫入新數據 (V4.0)... 共 {len(df)} 筆")
                upload_sheet.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print(f"✅ 完成！")
            except Exception as e: print(f"❌ 上傳失敗: {e}")
    else: print("⚠️ 無數據產生。")

if __name__ == "__main__":
    main()
