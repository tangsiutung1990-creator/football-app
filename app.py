import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import math
import os
from datetime import datetime
import textwrap

# ================= 設定區 =================
GOOGLE_SHEET_NAME = "數據上傳" 

st.set_page_config(page_title="足球AI Alpha Pro (V15.0)", page_icon="⚽", layout="wide")

# ================= CSS =================
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    div[data-testid="stMetric"] { background-color: #262730 !important; border: 1px solid #444; border-radius: 8px; padding: 10px; }
    div[data-testid="stMetricLabel"] p { color: #aaaaaa !important; font-size: 0.9rem; }
    div[data-testid="stMetricValue"] div { color: #ffffff !important; font-size: 1.5rem !important; }
    .css-card-container { background-color: #1a1c24; border: 1px solid #333; border-radius: 12px; padding: 15px; margin-bottom: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
    h1, h2, h3, h4, span, div, b, p { color: #ffffff !important; font-family: "Source Sans Pro", sans-serif; }
    .sub-text { color: #cccccc !important; font-size: 0.8rem; }
    .h2h-text { color: #ffd700 !important; font-size: 0.8rem; margin-bottom: 3px; font-weight: bold; }
    .ou-stats-text { color: #00ffff !important; font-size: 0.75rem; margin-bottom: 10px; opacity: 0.9; }
    .market-value-text { color: #28a745 !important; font-size: 0.85rem; font-weight: bold; margin-top: 2px; }
    .rank-badge { background-color: #444; color: #fff !important; padding: 1px 5px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; border: 1px solid #666; margin: 0 4px; }
    .form-circle { display: inline-block; width: 18px; height: 18px; line-height: 18px; text-align: center; border-radius: 50%; font-size: 0.65rem; margin: 0 1px; color: white !important; font-weight: bold; border: 1px solid rgba(255,255,255,0.2); }
    .form-w { background-color: #28a745 !important; }
    .form-d { background-color: #ffc107 !important; color: black !important; } 
    .form-l { background-color: #dc3545 !important; }
    .live-status { color: #ff4b4b !important; font-weight: bold; animation: blinker 1.5s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
    
    /* V15 Pro 樣式 */
    .adv-stats-box { background-color: #25262b; padding: 10px; border-radius: 6px; border: 1px solid #444; margin-top: 8px; font-size: 0.75rem; }
    .section-title { font-size: 0.8rem; font-weight: bold; color: #ff9800; border-bottom: 1px solid #444; padding-bottom: 2px; margin-bottom: 5px; margin-top: 5px; }
    .odds-row { display: flex; justify-content: space-between; margin-bottom: 3px; font-size: 0.75rem; }
    .odds-val { color: #fff; font-weight: bold; }
    .odds-val-high { color: #00ff00; font-weight: bold; }
    .value-bet { color: #ff00ff !important; font-weight: 900; animation: blinker 2s infinite; }
    
    .goal-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px; margin: 8px 0; text-align: center; }
    .goal-item { background: #333; padding: 4px; border-radius: 4px; border: 1px solid #444; }
    .goal-title { font-size: 0.7rem; color: #aaa; }
    .goal-val { font-size: 0.9rem; font-weight: bold; color: #fff; }
    .highlight-goal { border: 1px solid #28a745 !important; background: rgba
