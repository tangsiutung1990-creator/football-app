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
API_KEY = '531bb40a089446bdae76a019f2af3beb'
BASE_URL = 'https://api.football-data.org/v4'
GOOGLE_SHEET_NAME = "數據上傳" 
MANUAL_TAB_NAME = "球隊身價表" 

# 完整支援的聯賽列表
COMPETITIONS = [
    'PL',   # 英超
    'PD',   # 西甲
    'CL',   # 歐聯
    'SA',   # 意甲
    'BL1',  # 德甲
    'FL1',  # 法甲
    'DED',  # 荷甲
    'PPL',  # 葡超
    'ELC',  # 英冠
    'BSA',  # 巴西甲
    'CLI',  # 自由盃
    'WC',   # 世界盃/國際賽
    'EC'    # 歐國盃
]

# [新增] 聯賽入球風格係數 (大於 1.0 代表大球聯賽，小於 1.0 代表防守聯賽)
LEAGUE_GOAL_FACTOR = {
    'BL1': 1.18, # 德甲 (大球)
    'DED': 1.20, # 荷甲 (大球)
    'PL': 1.05,  # 英超 (標準偏大)
    'PD': 0.95,  # 西甲 (技術型，入球稍少)
    'SA': 0.98,  # 意甲 (防守反擊)
    'FL1': 0.95, # 法甲
    'PPL': 1.05, # 葡超
    'BSA': 0.90, # 巴甲 (較為保守)
    'ELC': 1.02  # 英冠
}

# ================= 智能 API 請求函式 =================
def call_api_with_retry(url, params=None, headers=None, retries=3):
    """
    發送 API 請求，如果遇到 429 (頻率限制)，會自動休息後重試。
    """
    for i in range(retries):
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                wait_time = 65 
                print(f"🛑 觸發 API 頻率限制 (429)。程式將暫停 {wait_time} 秒後自動重試 ({i+1}/{retries})...")
                time.sleep(wait_time)
                continue 
            elif response.status_code == 400:
                 print(f"⚠️ 請求參數錯誤 (400): {url}")
                 print(f"   參數詳情: {params}")
                 print(f"   API 回傳: {response.text}")
                 return None
            else:
                print(f"⚠️ API 請求錯誤: {response.status_code} | {url}")
                return None
        except Exception as e:
            print(f"❌ 連線異常: {e}")
            time.sleep(5)
            continue
    print("❌ 重試次數已用盡，放棄此請求。")
    return None

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

# ================= [新增] 進階機率計算 (BTTS, 零封, 合理賠率) =================
def calculate_advanced_probs(home_exp, away_exp):
    def poisson(k, lam):
        return (lam**k * math.exp(-lam)) / math.factorial(k)
    
    h_win_prob = 0; draw_prob = 0; a_win_prob = 0
    for h in range(10):
        for a in range(10):
            p = poisson(h, home_exp) * poisson(a, away_exp)
            if h > a: h_win_prob += p
            elif h == a: draw_prob += p
            else: a_win_prob += p
            
    p_h_score = 1 - poisson(0, home_exp)
    p_a_score = 1 - poisson(0, away_exp)
    btts_prob = p_h_score * p_a_score
    
    cs_home = poisson(0, away_exp)
    cs_away = poisson(0, home_exp)
    
    odds_h = 1 / h_win_prob if h_win_prob > 0.01 else 99.0
    odds_d = 1 / draw_prob if draw_prob > 0.01 else 99.0
    odds_a = 1 / a_win_prob if a_win_prob > 0.01 else 99.0
    
    return {
        'btts': round(btts_prob * 100, 1),
        'cs_h': round(cs_home * 100, 1),
        'cs_a': round(cs_away * 100, 1),
        'odds_h': round(odds_h, 2),
        'odds_d': round(odds_d, 2),
        'odds_a': round(odds_a, 2)
    }

# ================= 輔助：計算波膽 (Correct Score) =================
def calculate_correct_score_probs(home_exp, away_exp):
    def poisson(k, lam):
        return (lam**k * math.exp(-lam)) / math.factorial(k)
    
    scores = []
    # [優化] 擴大波膽計算範圍到 7 球，避免漏掉大比分
    for h in range(8):
        for a in range(8):
            prob = poisson(h, home_exp) * poisson(a, away_exp)
            scores.append({'score': f"{h}:{a}", 'prob': prob})
    
    scores.sort(key=lambda x: x['prob'], reverse=True)
    # 顯示前 3 個最高機率波膽
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
    
    for i, comp in enumerate(COMPETITIONS):
        print(f"   ↳ 正在抓取積分榜: {comp} ({i+1}/{len(COMPETITIONS)})...")
        url = f"{BASE_URL}/competitions/{comp}/standings"
        
        data = call_api_with_retry(url, headers=headers)
        
        if data:
            total_h=0; total_a=0; total_m=0
            
            # [優化] 確保數據結構安全
            standings_list = data.get('standings', [])
            if not standings_list: continue

            for table in standings_list:
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
                    
                    # [優化] 防止 played 為 0 導致除以零錯誤，設定基礎值
                    avg_gf = gf/played if played>0 else 1.2
                    avg_ga = ga/played if played>0 else 1.2

                    if table_type == 'TOTAL':
                        standings_map[team_id]['rank'] = entry['position']
                        standings_map[team_id]['form'] = entry.get('form', 'N/A')
                        standings_map[team_id]['season_ppg'] = points/played if played>0 else 1.3
                        if played>0: standings_map[team_id]['volatility'] = (gf+ga)/played
                    elif table_type == 'HOME':
                        standings_map[team_id]['home_att'] = avg_gf 
                        standings_map[team_id]['home_def'] = avg_ga 
                        total_h += gf; 
                        if played>0: total_m += played
                    elif table_type == 'AWAY':
                        standings_map[team_id]['away_att'] = avg_gf 
                        standings_map[team_id]['away_def'] = avg_ga 
                        total_a += gf

            # [優化] 計算聯賽平均入球，如果樣本太少，給予較高的現代足球預設值 (2.8球)
            if total_m > 10:
                avg_h_score = total_h/total_m
                avg_a_score = total_a/total_m
            else:
                avg_h_score = 1.65
                avg_a_score = 1.35
            
            league_stats[data['competition']['code']] = {'avg_home': avg_h_score, 'avg_away': avg_a_score}
        
        time.sleep(6.5) 
            
    return standings_map, league_stats

# ================= 預測模型 (核心優化) =================
def predict_match_outcome(home_stats, away_stats, home_val_str, away_val_str, h2h_summary, league_avg, lg_code):
    # 1. 獲取聯賽平均值，並確保不為零
    lg_h = max(league_avg.get('avg_home', 1.6), 0.8)
    lg_a = max(league_avg.get('avg_away', 1.3), 0.8)

    # 2. 應用「聯賽風格係數」 (放大/縮小基礎入球率)
    style_factor = LEAGUE_GOAL_FACTOR.get(lg_code, 1.0)
    
    # [數學修正] 攻擊力 = 球隊平均入球 / 聯賽平均主場入球
    # 這裡引入 style_factor 來整體提升或降低該聯賽的入球期望
    h_att_strength = (home_stats['home_att'] / lg_h) * math.sqrt(style_factor)
    a_def_strength = (away_stats['away_def'] / lg_h) * math.sqrt(style_factor)
    
    a_att_strength = (away_stats['away_att'] / lg_a) * math.sqrt(style_factor)
    h_def_strength = (home_stats['home_def'] / lg_a) * math.sqrt(style_factor)
    
    # 3. 初始預期入球 (Lambda)
    # 增加 1.1 的係數，解決泊松分佈傾向保守的問題
    raw_h = h_att_strength * a_def_strength * lg_h * 1.1
    raw_a = a_att_strength * h_def_strength * lg_a * 1.1
    
    # 4. 身價修正 (實力懸殊修正)
    h_v = parse_market_value(home_val_str); a_v = parse_market_value(away_val_str)
    if h_v > 0 and a_v > 0:
        ratio = h_v / a_v
        # 放大身價的影響力：使用 log 後 x 0.15 (之前是 0.08)
        factor = max(min(math.log(ratio) * 0.15, 0.4), -0.4)
        raw_h *= (1 + factor)
        raw_a *= (1 - factor)

    # 5. 動量 (Form) 修正
    h_form = calculate_weighted_form_score(home_stats['form'])
    a_form = calculate_weighted_form_score(away_stats['form'])
    # 動量差值
    h_mom = h_form - home_stats['season_ppg']
    a_mom = a_form - away_stats['season_ppg']
    
    # [優化] 狀態好會直接增加入球期望值
    raw_h *= (1 + (h_mom * 0.1))
    raw_a *= (1 + (a_mom * 0.1))

    # 6. H2H 歷史修正
    try:
        if "主" in h2h_summary and "勝" in h2h_summary:
            parts = h2h_summary.split('|')
            h_wins = int(parts[0].split('主')[1].split('勝')[0])
            a_wins = int(parts[2].split('客')[1].split('勝')[0])
            total = h_wins + a_wins + int(parts[1].split('和')[1])
            if total > 0:
                h_rate = h_wins/total; a_rate = a_wins/total
                raw_h *= (1 + (h_rate - 0.33) * 0.15)
                raw_a *= (1 + (a_rate - 0.33) * 0.15)
    except: pass

    # 7. 波動性修正 (解決所有比賽都預測小球的問題)
    vol = (home_stats.get('volatility', 2.5) + away_stats.get('volatility', 2.5)) / 2
    if vol > 3.0: # 如果兩隊歷史上都是大開大合
        raw_h *= 1.15
        raw_a *= 1.15
    elif vol < 2.0: # 如果兩隊都是鐵桶陣
        raw_h *= 0.9
        raw_a *= 0.9

    return round(raw_h, 2), round(raw_a, 2), round(vol, 1), round(h_mom, 2), round(a_mom, 2)

# ================= H2H =================
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
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 數據引擎啟動 (V3.0 Aggressive Mode)...")
    
    headers = {'X-Auth-Token': API_KEY}
    
    utc_now = datetime.now(pytz.utc)
    start_date = (utc_now - timedelta(days=3)).strftime('%Y-%m-%d') 
    end_date = (utc_now + timedelta(days=7)).strftime('%Y-%m-%d') 
    
    print(f"📅 搜尋範圍 (UTC): {start_date} 至 {end_date}")
    params = { 'dateFrom': start_date, 'dateTo': end_date, 'competitions': ",".join(COMPETITIONS) }

    try:
        response_json = call_api_with_retry(f"{BASE_URL}/matches", params=params, headers=headers)
        
        if not response_json: return []

        matches = response_json.get('matches', [])
        if not matches: return []

        cleaned = []
        hk_tz = pytz.timezone('Asia/Hong_Kong')
        print(f"🔍 發現 {len(matches)} 場賽事，正在計算高階機率...")

        for index, match in enumerate(matches):
            utc_dt = datetime.strptime(match['utcDate'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            time_str = utc_dt.astimezone(hk_tz).strftime('%Y-%m-%d %H:%M') 
            
            raw_status = match['status']
            if raw_status == 'FINISHED': status = '完場'
            elif raw_status in ['IN_PLAY', 'PAUSED']: status = '進行中'
            elif raw_status in ['POSTPONED', 'SUSPENDED', 'CANCELLED']: status = '延期/取消'
            else: status = '未開賽'
            
            h_id = match['homeTeam']['id']; a_id = match['awayTeam']['id']
            h_name = match['homeTeam']['shortName'] or match['homeTeam']['name']
            a_name = match['awayTeam']['shortName'] or match['awayTeam']['name']
            lg_code = match['competition']['code']
            lg_name = match['competition']['name']
            
            h_info = standings.get(h_id, {'rank':0,'form':'N/A','home_att':1.2,'home_def':1.2,'volatility':2.5,'season_ppg':1.3})
            a_info = standings.get(a_id, {'rank':0,'form':'N/A','away_att':1.0,'away_def':1.0,'volatility':2.5,'season_ppg':1.3})
            h_val = market_value_map.get(h_name, "N/A"); a_val = market_value_map.get(a_name, "N/A")
            
            print(f"   🤖 分析中 [{index+1}/{len(matches)}]: {h_name} vs {a_name}...")
            
            h2h, ou = get_h2h_and_ou_stats(match['id'], h_id, a_id)
            time.sleep(6.1)

            lg_avg = league_stats.get(lg_code, {'avg_home': 1.6, 'avg_away': 1.3}) # 提高預設值
            
            # [修正] 傳入 lg_code 以獲取聯賽風格係數
            pred_h, pred_a, vol, h_mom, a_mom = predict_match_outcome(h_info, a_info, h_val, a_val, h2h, lg_avg, lg_code)
            
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
                print(f"🚀 正在強制清空舊資料表...")
                upload_sheet.clear() 
                print(f"📝 正在寫入新數據 (優化版V3)... 共 {len(df)} 筆")
                upload_sheet.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print(f"✅ Google Sheet 更新完成！")
            except Exception as e: print(f"❌ 上傳失敗: {e}")
    else:
        print("⚠️ 無數據產生。")

if __name__ == "__main__":
    main()
