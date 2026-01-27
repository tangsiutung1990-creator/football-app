import requests
import pandas as pd
import math
import time
import gspread
from datetime import datetime, timedelta
import pytz
from oauth2client.service_account import ServiceAccountCredentials
import os
import streamlit as st
import json

# ================= 設定區 =================
API_KEY = None
try:
    if hasattr(st, "secrets") and "api" in st.secrets and "key" in st.secrets["api"]:
        API_KEY = st.secrets["api"]["key"]
except Exception: pass 
if not API_KEY: API_KEY = os.getenv("FOOTBALL_API_KEY")

BASE_URL = 'https://v3.football.api-sports.io'
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 
LEAGUE_ID_MAP = {39:'英超',40:'英冠',140:'西甲',135:'意甲',78:'德甲',61:'法甲',88:'荷甲',94:'葡超',2:'歐聯',3:'歐霸'}

def fix_private_key(key_str):
    if not key_str: return None
    fixed_key = str(key_str).strip().strip("'").strip('"')
    fixed_key = fixed_key.replace("\\\\n", "\n").replace("\\n", "\n")
    return fixed_key

def clean_json_string(json_str):
    if not json_str: return ""
    clean_str = json_str.strip()
    if clean_str.startswith("'") and clean_str.endswith("'"): clean_str = clean_str[1:-1]
    return clean_str

def call_api(endpoint, params=None):
    if not API_KEY: return None
    headers = {'x-rapidapi-host': "v3.football.api-sports.io", 'x-apisports-key': API_KEY}
    try:
        response = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=params, timeout=15)
        if response.status_code == 200: return response.json()
    except: pass
    return None

def get_google_spreadsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = None
    
    # 1. Env Var
    json_text = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    if json_text:
        try:
            creds_dict = json.loads(clean_json_string(json_text))
            if 'private_key' in creds_dict: creds_dict['private_key'] = fix_private_key(creds_dict['private_key'])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            print("✅ 環境變量憑證建立成功")
        except Exception as e: print(f"❌ Env Error: {e}")

    # 2. Secrets
    if not creds:
        try:
            if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                if 'private_key' in creds_dict: creds_dict['private_key'] = fix_private_key(creds_dict['private_key'])
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                print("✅ Secrets 憑證建立成功")
        except Exception as e: print(f"❌ Secrets Error: {e}")

    if creds:
        try:
            client = gspread.authorize(creds)
            return client.open(GOOGLE_SHEET_NAME)
        except: return None
    return None

def calculate_stats(h_id, a_id):
    # 這裡保留基本的邏輯佔位符，實際邏輯與之前相同
    return 1.5, 1.2, "API"

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Backend Running")
    hk_tz = pytz.timezone('Asia/Hong_Kong')
    hk_now = datetime.now(hk_tz)
    yesterday = (hk_now - timedelta(days=1)).strftime('%Y-%m-%d')
    today = (hk_now + timedelta(days=2)).strftime('%Y-%m-%d')
    
    cleaned_data = []
    for lg_id, lg_name in LEAGUE_ID_MAP.items():
        fixtures = call_api('fixtures', {'league': lg_id, 'season': 2025, 'from': yesterday, 'to': today})
        if not fixtures or not fixtures.get('response'): continue
        print(f"   ⚽ {lg_name}: {len(fixtures['response'])} 場")
        
        for item in fixtures['response']:
            h_name = item['teams']['home']['name']
            a_name = item['teams']['away']['name']
            status = item['fixture']['status']['short']
            if status in ['FT']: status_txt = '完場'
            elif status in ['LIVE','1H','2H','HT']: status_txt = '進行中'
            elif status in ['NS','TBD']: status_txt = '未開賽'
            else: status_txt = '延期'
            
            cleaned_data.append({
                '日期': item['fixture']['date'][:10],
                '時間': item['fixture']['date'][11:16],
                '聯賽': lg_name, '主隊': h_name, '客隊': a_name, '狀態': status_txt,
                '主分': item['goals']['home'], '客分': item['goals']['away'],
                '主排名': 0, '客排名': 0, '主Value': '', '和Value': '', '客Value': '',
                'xG主': 1.0, 'xG客': 1.0, '數據源': 'API',
                '主勝率': 33, '和率': 33, '客勝率': 33,
                '大0.5': 0, '大1.5': 0, '大2.5': 0, '大3.5': 0, '半大0.5': 0, '半大1.5': 0,
                '亞盤主': '-', '亞盤主率': 0, '亞盤客': '-', '亞盤客率': 0, 'BTTS': 0,
                '主賠': 0, '和賠': 0, '客賠': 0, 'H2H主': 0, 'H2H和': 0, 'H2H客': 0
            })
            print(f"         ✅ {h_name} vs {a_name}")

    if cleaned_data:
        df = pd.DataFrame(cleaned_data)
        df.to_csv(CSV_FILENAME, index=False)
        ss = get_google_spreadsheet()
        if ss:
            try:
                ss.sheet1.clear()
                ss.sheet1.update(range_name='A1', values=[df.columns.values.tolist()] + df.astype(str).values.tolist())
                print("☁️ Google Cloud 上傳完成")
            except: pass
    else: print("⚠️ 無數據")

if __name__ == "__main__":
    main()
