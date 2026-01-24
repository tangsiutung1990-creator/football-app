import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime, timedelta
import pytz
import json

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 
CSV_FILENAME = "football_data_backup.csv" 

st.set_page_config(page_title="足球AI Pro", page_icon="⚽", layout="wide")

# ================= CSS 極致優化 =================
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    div[data-testid="stPills"] { gap: 4px; }
    
    .compact-card { 
        background-color: #1a1c24; 
        border: 1px solid #333; 
        border-radius: 6px; 
        padding: 2px 4px; 
        margin-bottom: 6px; 
        font-family: 'Arial', sans-serif; 
    }
    
    .match-header { 
        display: flex; 
        justify-content: space-between; 
        color: #999; 
        font-size: 0.8rem; 
        margin-bottom: 2px; 
        border-bottom: 1px solid #333; 
        padding-bottom: 2px;
    }
    
    .content-row { 
        display: grid; 
        grid-template-columns: 6.5fr 3.5fr; 
        align-items: center; 
        margin-bottom: 2px; 
    }
    
    .team-name { 
        font-weight: bold; 
        font-size: 1.1rem; 
        color: #fff; 
        line-height: 1.1;
    } 
    
    .team-sub { 
        font-size: 0.75rem; 
        color: #bbb; 
        margin-top: 1px;
    }
    
    .score-main { font-size: 1.8rem; font-weight: bold; color: #00ffea; line-height: 1; text-align: right; }
    .score-sub { font-size: 0.75rem; color: #888; text-align: right; }

    /* 矩陣優化: 使用百分比寬度以達到最窄效果 */
    .grid-matrix { 
        display: grid; 
        grid-template-columns: 27% 23% 23% 27%; 
        gap: 1px; 
        margin-top: 2px; 
        background: #333; /* 邊框顏色 */
        border-radius: 4px;
        overflow: hidden;
    }
    
    .matrix-col { 
        padding: 1px 2px; 
        background: #222; /* 單元格背景 */
    }
    
    .matrix-header { 
        color: #ff9800; 
        font-size: 0.75rem; 
        font-weight: bold;
        text-align: center;
        border-bottom: 1px solid #444; 
        margin-bottom: 1px;
    }
    
    .matrix-cell { 
        display: flex; 
        justify-content: space-between; 
        padding: 0 1px; 
        color: #ddd; 
        font-size: 0.8rem; 
        line-height: 1.3;
    }
    
    .matrix-label { color: #888; font-size:
