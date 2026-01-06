def main():
    # --- 計算日期 (昨+今+未來) ---
    today = datetime.now()
    start_date = today - timedelta(days=1)
    end_date = today + timedelta(days=DAYS_TO_FETCH)
    date_from, date_to = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

    print(f"1. 正在搜尋賽程 (由 {date_from} 到 {date_to})...")
    
    url = f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}"
    data = fetch_data(url)
    matches = data.get('matches', []) if data else []
    
    if not matches:
        print("⚠️ 這段時間暫無重點賽事。")
        return

    # --- 獲取積分榜 (含入球數據) ---
    leagues = list(set([m['competition']['code'] for m in matches]))
    print(f"2. 發現 {len(matches)} 場賽事，涉及聯賽: {leagues}")
    print("   正在下載數據 (包含攻防能力值)...")
    
    stats_db = {}
    for code in leagues:
        # 這裡只做一次請求，避免太頻繁被封鎖
        print(f"   -> 正在下載 {code} 積分榜...")
        d = fetch_data(f"https://api.football-data.org/v4/competitions/{code}/standings")
        if d:
            for t in d.get('standings', []):
                if t['type'] == 'TOTAL':
                    for r in t.get('table', []):
                        name = r['team']['name']
                        gf = r.get('goalsFor', 0)    
                        ga = r.get('goalsAgainst', 0) 
                        pg = r.get('playedGames', 1)  
                        if pg == 0: pg = 1
                        
                        stats_db[name] = {
                            'rank': str(r.get('position', '')),
                            'form': str(r.get('form', '')).replace(",", "") if r.get('form') else "",
                            'gf': gf, 'ga': ga, 'pg': pg
                        }
        time.sleep(1.5) # 稍微縮短等待時間，加快速度

    # --- 整理數據 ---
    print("3. 正在整理數據 (含即時比分)...")
    
    # 🔥 修改標題：加入「狀態」欄位，把「備註」移到最後
    all_rows = [["時間", "狀態", "聯賽", "主隊", "客隊", "主排", "客排", "主近", "客近", 
                 "主勝", "和", "客勝", "主攻", "主防", "客攻", "客防", "主分", "客分"]]

    for m in matches:
        try:
            h = m['homeTeam']['name']
            a = m['awayTeam']['name']
            league_code = m['competition']['code']
            status_raw = m['status'] # 獲取原始狀態

            # 時間處理 (修正時差 +8)
            dt = datetime.strptime(m['utcDate'], "%Y-%m-%dT%H:%M:%SZ")
            hk_time = dt + timedelta(hours=8)
            t_str = hk_time.strftime("%m/%d %H:%M") 
            
            # --- 🔥 狀態判斷與比分優化 🔥 ---
            # 默認狀態
            status_display = "未開賽"
            score_h_str = "-"
            score_a_str = "-"

            s_h = m['score']['fullTime']['home']
            s_a = m['score']['fullTime']['away']

            # 根據 API 狀態代碼轉換中文
            if status_raw == 'FINISHED':
                status_display = "完場"
                score_h_str = str(s_h)
                score_a_str = str(s_a)
            elif status_raw == 'IN_PLAY':
                status_display = "🔴進行中" # 加個紅點比較顯眼
                # 進行中如有比分則顯示，否則顯示 0
                score_h_str = str(s_h) if s_h is not None else "0"
                score_a_str = str(s_a) if s_a is not None else "0"
            elif status_raw == 'PAUSED':
                status_display = "中場"
                score_h_str = str(s_h)
                score_a_str = str(s_a)
            elif status_raw == 'POSTPONED':
                status_display = "延期"

            # 獲取統計
            h_stat = stats_db.get(h, {'rank': '', 'form': '', 'gf':0, 'ga':0, 'pg':1})
            a_stat = stats_db.get(a, {'rank': '', 'form': '', 'gf':0, 'ga':0, 'pg':1})
            
            # 平均入球
            def calc_avg(val, games): return round(val/games, 2) if games > 0 else 0
            h_avg_gf = calc_avg(h_stat['gf'], h_stat['pg']) 
            h_avg_ga = calc_avg(h_stat['ga'], h_stat['pg']) 
            a_avg_gf = calc_avg(a_stat['gf'], a_stat['pg']) 
            a_avg_ga = calc_avg(a_stat['ga'], a_stat['pg'])

            row = [
                t_str, 
                status_display, # 新增狀態
                LEAGUE_MAP.get(league_code, league_code), 
                NAME_MAP.get(h, h), NAME_MAP.get(a, a),
                h_stat['rank'], a_stat['rank'],
                h_stat['form'], a_stat['form'],
                "","","", # 賠率位
                h_avg_gf, h_avg_ga, 
                a_avg_gf, a_avg_ga, 
                score_h_str, score_a_str
            ]
            all_rows.append(row)
        except Exception as e:
            print(f"跳過一場賽事 ({h} vs {a}): {e}")
            pass

    # --- 上傳 ---
    print(f"4. 正在連線到 Google Sheet ({GOOGLE_SHEET_FILENAME})...")
    try:
        client = get_google_sheet_client()
        sh = client.open(GOOGLE_SHEET_FILENAME)
        sheet = sh.sheet1
        sheet.clear() 
        sheet.update(all_rows) 
        print(f"✅ 成功！已更新 {len(all_rows)-1} 場賽事 (含比分) 到雲端。")
        
    except FileNotFoundError:
        print(f"❌ 錯誤：找不到 key.json")
    except Exception as e:
        print(f"❌ 上傳失敗: {e}")
