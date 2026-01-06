# 檔案名稱: bot.py (前身是 football.py)
import os
import requests
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# ================= 配置區 =================
API_KEY = '531bb40a089446bdae76a019f2af3beb'

# 抓取範圍：(1=捉埋尋日, 2=捉埋尋日+今日+聽日)
DAYS_TO_FETCH = 2  

GOOGLE_SHEET_FILENAME = "數據上傳" 

# 自動修正路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_KEY_FILE = os.path.join(BASE_DIR, 'key.json')

# ================= 1. 聯賽翻譯 =================
LEAGUE_MAP = {
    "PL": "英超", "ELC": "英冠", "PD": "西甲", "SA": "意甲", "BL1": "德甲",
    "FL1": "法甲", "DED": "荷甲", "PPL": "葡超", "CL": "歐聯", "BSA": "巴甲",
    "CLI": "自由盃", "WC": "世界盃", "EC": "歐國盃", "FAC": "足總盃", "CDR": "國王盃",
    "UEL": "歐霸", "UECL": "歐協聯"
}

# ================= 2. 球隊翻譯 =================
NAME_MAP = {
    "Arsenal FC": "阿仙奴", "Aston Villa FC": "阿士東維拉", "AFC Bournemouth": "般尼茅夫",
    "Brentford FC": "賓福特", "Brighton & Hove Albion FC": "白禮頓",
    "Chelsea FC": "車路士", "Crystal Palace FC": "水晶宮", "Everton FC": "愛華頓",
    "Fulham FC": "富咸", "Ipswich Town FC": "葉士域治", "Leicester City FC": "李斯特城",
    "Liverpool FC": "利物浦", "Manchester City FC": "曼城", "Manchester United FC": "曼聯",
    "Newcastle United FC": "紐卡素", "Nottingham Forest FC": "諾定咸森林",
    "Southampton FC": "修咸頓", "Tottenham Hotspur FC": "熱刺",
    "West Ham United FC": "韋斯咸", "Wolverhampton Wanderers FC": "狼隊",
    "Leeds United FC": "列斯聯", "Sunderland AFC": "新特蘭", "Middlesbrough FC": "米杜士堡",
    "Blackburn Rovers FC": "布力般流浪", "Norwich City FC": "諾域治", "Stoke City FC": "史篤城",
    "Derby County FC": "打吡郡", "Hull City AFC": "侯城", "Watford FC": "屈福特",
    "Millwall FC": "米禾爾", "Swansea City AFC": "史雲斯", "Bristol City FC": "布里斯托城",
    "Preston North End FC": "普雷斯頓", "Portsmouth FC": "樸茨茅夫",
    "Birmingham City FC": "伯明翰", "Coventry City FC": "高雲地利", "Burnley FC": "般尼",
    "Sheffield United FC": "錫菲聯", "Oxford United FC": "牛津聯", "Luton Town FC": "盧頓",
    "Queens Park Rangers FC": "QPR", "Sheffield Wednesday FC": "錫周三", "West Bromwich Albion FC": "西博",
    "Real Madrid CF": "皇馬", "FC Barcelona": "巴塞隆拿", "Atlético de Madrid": "馬體會",
    "Girona FC": "基羅納", "Real Sociedad": "皇家蘇斯達", "Athletic Club": "畢爾包",
    "Real Betis Balompié": "貝迪斯", "Villarreal CF": "維拉利爾", "Sevilla FC": "西維爾",
    "Valencia CF": "華倫西亞", "RCD Mallorca": "馬略卡", "CA Osasuna": "奧沙辛拿",
    "Celta de Vigo": "切爾達", "Rayo Vallecano": "華歷簡奴", "Getafe CF": "加泰",
    "RCD Espanyol de Barcelona": "愛斯賓奴", "Real Valladolid CF": "華拉度列",
    "UD Las Palmas": "拉斯彭馬斯", "CD Leganés": "雷加利斯", "Deportivo Alavés": "艾拉維斯",
    "FC Internazionale Milano": "國米", "AC Milan": "AC米蘭", "Juventus FC": "祖雲達斯",
    "SSC Napoli": "拿玻里", "AS Roma": "羅馬", "Atalanta BC": "亞特蘭大", "SS Lazio": "拉素",
    "ACF Fiorentina": "費倫天拿", "Bologna FC 1909": "博洛尼亞", "Torino FC": "拖連奴",
    "Udinese Calcio": "烏甸尼斯", "Genoa CFC": "熱拿亞", "Parma Calcio 1913": "帕爾馬",
    "Hellas Verona FC": "維罗納", "Empoli FC": "安玻里", "US Lecce": "萊切",
    "AC Monza": "蒙沙", "Cagliari Calcio": "卡利亞里", "Venezia FC": "威尼斯", "Como 1907": "科木",
    "FC Bayern München": "拜仁", "Bayer 04 Leverkusen": "利華古遜", "Borussia Dortmund": "多蒙特",
    "RB Leipzig": "萊比錫", "VfB Stuttgart": "史特加", "Eintracht Frankfurt": "法兰克福",
    "TSG 1899 Hoffenheim": "賀芬咸", "SV Werder Bremen": "雲達不萊梅", "VfL Wolfsburg": "禾夫斯堡",
    "SC Freiburg": "弗賴堡", "1. FC Union Berlin": "柏林聯", "1. FSV Mainz 05": "緬恩斯",
    "Borussia Mönchengladbach": "慕遜加柏", "FC Augsburg": "奧格斯堡", "1. FC Heidenheim 1846": "海登咸",
    "FC St. Pauli": "聖保利", "Holstein Kiel": "基爾", "VfL Bochum 1848": "波琴",
    "Paris Saint-Germain FC": "PSG", "AS Monaco FC": "摩納哥", "Olympique de Marseille": "馬賽",
    "Olympique Lyonnais": "里昂", "LOSC Lille": "里爾", "OGC Nice": "尼斯", "RC Lens": "朗斯",
    "Stade Rennais FC 1901": "雷恩", "Stade de Reims": "兰斯", "Toulouse FC": "圖卢兹",
    "AFC Ajax": "阿積士", "PSV Eindhoven": "PSV燕豪芬", "Feyenoord Rotterdam": "飛燕諾",
    "AZ Alkmaar": "阿爾克馬爾", "FC Twente '65": "泰温特", "FC Utrecht": "烏德勒支",
    "SL
