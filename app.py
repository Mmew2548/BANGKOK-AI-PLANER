import os, re, json, time
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from html import escape as esc
import requests, streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from urllib.parse import quote
import fares
import gemini_helper as gh

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH, override=True)

def _env(name):
    return os.getenv(name, "").strip().strip('"').strip("'")

if _env("FORCE_IPV4").lower() in ("1", "true", "yes"):   # ตั้ง FORCE_IPV4=1 ใน .env ถ้าเชื่อมต่อ Google ช้า/ค้างเป็นประจำ
    import socket, urllib3.util.connection as _uc
    _uc.allowed_gai_family = lambda: socket.AF_INET

GKEY = _env("GOOGLE_MAPS_API_KEY")   # เส้นทาง + สถานี + ระยะทาง (Google Routes API)
KEY = _env("LONGDO_API_KEY")         # ใช้แสดงรูปแผนที่บนเว็บเท่านั้น (Longdo Map)
# Gemini ช่วยจัดลำดับจุด + ตอบคำถาม (ขอคีย์ที่ aistudio.google.com/apikey) รับได้หลายชื่อตัวแปรใน .env
GEMINI_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY", "GOOGLE_GENAI_API_KEY")
GEMINI_KEY = next((_env(n) for n in GEMINI_VARS if _env(n)), "")
GEMINI_VAR_USED = next((n for n in GEMINI_VARS if _env(n)), "")
# GEMINI_MODEL ใน .env ใส่ได้หลายรุ่นคั่นด้วยคอมมา เช่น gemini-2.5-flash,gemini-2.5-flash-lite
# ระบบจะลองทีละรุ่นตามลำดับ ถ้ารุ่นแรกโควต้าหมดหรือ error จะข้ามไปรุ่นถัดไป
GEMINI_MODELS = [m.strip() for m in (_env("GEMINI_MODEL") or gh.DEFAULT_MODEL).split(",") if m.strip()]
GEMINI_MODEL = GEMINI_MODELS[0]
MAX_STOPS = 8
WALK_MAX_KM = 0.5      # ระยะที่ถือว่า "เดินได้" (กม.) = 500 เมตร
AUTO_ORDER = True      # True = พิมพ์ในแชทตั้งแต่ 3 จุดขึ้นไป ให้ Gemini ช่วยจัดลำดับว่าไปที่ไหนก่อน-หลังให้อัตโนมัติ
AUTO_PLAN_DISCOVER = False  # False = แนะนำอย่างเดียว ใช้แค่คีย์ Gemini (ใส่รายชื่อในช่อง "จุดแวะ" ให้กดแสดงเส้นทางเอง)
                            # True = แนะนำเสร็จแล้วคำนวณเส้นทางให้เลย (ต้องใช้ GOOGLE_MAPS_API_KEY และกินโควต้า Google)
CHAT_ON_RIGHT = True   # True = แชทอยู่ขวา แผนที่อยู่ซ้าย / False = แชทอยู่ซ้ายเหมือนเดิม
CHAT_H = 640           # ความสูงกล่องแชท (px)
MAP_H = 430            # ความสูงแผนที่ (px)
IMAGES_PER_PLACE = 4   # จำนวนรูปสถานที่จาก Wikipedia ต่อ 1 ที่ (แสดงในแชท)
AI_ALL_TRANSIT = True  # True = ให้ Gemini คำนวณราคาทุกช่วง (รถเมล์ + รถไฟ/รถไฟฟ้า) ถ้า Gemini ตอบไม่ได้ค่อยใช้ราคาจากตาราง fares.py
                       # False = ใช้ Gemini เฉพาะช่วงที่ไม่มีราคาในระบบ (รถไฟฟ้าที่มีในตารางจะใช้ราคาตารางตามเดิม)
APP_TITLE = "BANGKOK AI PLANNER"   # ชื่อหัวเว็บ (อังกฤษล้วน ใช้ทั้งสองหน้า)
COLORS = ["rgba(47,111,228,.9)", "rgba(228,87,46,.9)", "rgba(40,170,80,.9)", "rgba(150,70,200,.9)",
          "rgba(230,170,20,.9)", "rgba(20,160,170,.9)", "rgba(200,60,120,.9)"]
import io, base64
from PIL import Image
LOGO_B64 = "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"   # โลโก้วัดอรุณ (สติกเกอร์พื้นโปร่งใส) ฝังไว้ในไฟล์
_LOGO_FILE = Path(__file__).resolve().parent / "logo.png"   # ถ้าวางไฟล์ logo.png ไว้ข้าง app.py จะใช้ไฟล์นี้แทน
if _LOGO_FILE.exists():
    LOGO_B64 = base64.b64encode(_LOGO_FILE.read_bytes()).decode()
st.set_page_config(page_title=APP_TITLE, page_icon=Image.open(io.BytesIO(base64.b64decode(LOGO_B64))), layout="wide")

_BG_FILE = Path(__file__).resolve().parent / "bg.jpg"   # วางรูปพื้นหลังไว้ข้าง app.py ตั้งชื่อ bg.jpg
if _BG_FILE.exists():
    BG = "data:image/jpeg;base64," + base64.b64encode(_BG_FILE.read_bytes()).decode()
else:
    BG = "https://images.unsplash.com/photo-1563492065599-3520f775eeed?w=1800"  # สำรอง ถ้าไม่มี bg.jpg
FONT_STACK = "'Hack', 'Sarabun', 'Tahoma', monospace"   # ฟอนต์ทั้งเว็บ: อังกฤษ/ตัวเลข = Hack, ภาษาไทย = Sarabun (Hack ไม่มีอักษรไทย)
st.markdown(f"""
<style>
@import url('https://cdn.jsdelivr.net/npm/hack-font@3.3.0/build/web/hack.css');
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@400;600;700;800&display=swap');
html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]):not(.material-icons):not(.material-symbols-rounded) {{font-family:{FONT_STACK} !important}}
:root {{--bgimg:url("{BG}")}}
header, footer {{visibility:hidden}}
.nav {{background:rgba(40,50,80,.85);color:#fff;border-radius:30px;padding:6px 22px;
 display:flex;align-items:center;gap:12px;margin-bottom:12px;font-size:16px}}
.nav .logo-img {{height:38px;width:auto;display:block;border-radius:10px}}
.nav .t1 {{font-size:20px;font-weight:700;letter-spacing:1px;line-height:1.2;font-family:'Hack',monospace !important}}
.stButton>button {{border-radius:40px;border:2px solid #000;font-weight:700}}
.stTextInput input, .stTextArea textarea {{border-radius:20px;border:2px solid #000}}
.box {{border:2px solid #000;border-radius:24px;padding:6px 18px;background:#fff}}

/* ---------- หน้าแรก (hero) ---------- */
.st-key-hero {{background:linear-gradient(rgba(10,10,40,.10),rgba(5,5,25,.35)),var(--bgimg) center 40%/cover no-repeat;
 padding:38px 5vw 60px;min-height:100vh;position:relative;overflow:hidden;
 border-radius:0}}
.hero-title {{font-size:clamp(48px,7vw,96px);font-weight:800;color:#fff;text-align:center;
 margin:9vh 0 11vh;line-height:1.1;text-shadow:0 3px 18px rgba(0,0,0,.65)}}
.hero-text {{color:#fff;text-align:center;font-size:18px;max-width:640px;margin:15vh auto 0;line-height:1.5;
 text-shadow:0 1px 8px rgba(0,0,0,.9)}}
.st-key-hero .stButton>button {{background:rgba(60,90,210,.80);backdrop-filter:blur(8px);
 border:none;border-radius:60px;height:64px;font-size:30px;font-weight:700;letter-spacing:3px;
 color:#fff;text-shadow:2px 2px 4px rgba(0,0,0,.35)}}
.st-key-hero .stButton>button *, .st-key-hero .stButton>button p {{color:#fff !important}}
.st-key-hero .stButton>button:hover {{background:rgba(90,120,235,.95);color:#fff}}
.st-key-hero .nav {{background:rgba(60,70,100,.7);backdrop-filter:blur(6px);margin-bottom:0}}
</style>""", unsafe_allow_html=True)

ss = st.session_state
ss.setdefault("page", "home"); ss.setdefault("stops_text", ""); ss.setdefault("legs", [])
ss.setdefault("markers", []); ss.setdefault("stations", []); ss.setdefault("debug", None)
ss.setdefault("fresh_places", [])
ss.setdefault("msgs", [{"role": "assistant", "content":
    "สวัสดีครับ 👋 ผมคือผู้ช่วยวางแผนเดินทางในกรุงเทพ\n\n"
    "พิมพ์ได้หลายที่ในประโยคเดียว เช่น\n"
    "- **จากสยามไปวัดโพธิ์ แล้วไปวัดอรุณ แล้วไปเยาวราช**\n"
    "- **สยาม, จตุจักร, อารีย์**\n\n"
    "หรือพิมพ์ทีละที่ในช่อง \"จุดแวะ\" ด้านขวา (บรรทัดละ 1 ที่ เริ่มจากต้นทาง)\n\n"
    "✨ ถ้ามีตั้งแต่ 3 จุดขึ้นไป Gemini จะช่วยจัดลำดับว่าควรไปที่ไหนก่อน-หลัง พร้อมเวลาแนะนำให้\n\n"
    "🎯 ไม่รู้จะไปไหน? ให้ Gemini แนะนำได้ เช่น **อยากไปเที่ยวโซนวัดพระแก้ว 5 ที่ แนะนำคาเฟ่ด้วย**\n\n"
    "💬 ถามต่อได้หลังวางแผนแล้ว เช่น **ควรลงสถานีไหนไปวัดโพธิ์** หรือ **ไปที่ไหนก่อนดี**"}])

def _brand(cls):
    """แถบหัวเว็บ: โลโก้ + ชื่อภาษาอังกฤษ (ไม่มีเมนู HOME / ABOUT / MORE)"""
    return (f'<div class="{cls}"><img class="logo-img" src="data:image/png;base64,{LOGO_B64}">'
            f'<div class="t1">{APP_TITLE}</div></div>')


NAV_HTML = _brand("nav")          # หน้าแรก
HEADER_HTML = _brand("topbar")    # หน้าวางแผน
if ss.page != "home":                                # หน้าแรกจะวางเมนูไว้ในรูปพื้นหลัง
    st.markdown(HEADER_HTML, unsafe_allow_html=True)


# ---------- Gemini: ลองทีละรุ่น ----------
def gemini_try(fn):
    """fn(model) -> ผลลัพธ์ ลองทุกรุ่นใน GEMINI_MODELS ตามลำดับ ถ้าพังหมดจึงโยน error สุดท้าย"""
    last = None
    for m in GEMINI_MODELS:
        try:
            return fn(m)
        except Exception as e:
            last = e
            print(f"[gemini] รุ่น {m} ใช้ไม่ได้: {e}", flush=True)
    raise last


def thai_fix(t):
    """รวมสระอำที่ถูกแยกเป็น นิคหิต(ํ)+า ให้เป็น ำ (เช่น น้ำ) ไม่งั้นฟอนต์แสดงเป็นตัวเพี้ยน"""
    if not isinstance(t, str):
        return t
    t = re.sub("\u0e4d([\u0e48-\u0e4b]?)\u0e32", lambda m: m.group(1) + "\u0e33", t)
    return re.sub("([\u0e48-\u0e4b])\u0e4d\u0e32", lambda m: m.group(1) + "\u0e33", t)


def is_quota_error(e):
    s = str(e).lower()
    return "quota" in s or "exceeded" in s or "429" in s


# ---------- ราคารถเมล์ (กรอกเองได้ที่นี่) ----------
# key = เลขสายตัวพิมพ์ใหญ่ เช่น "552" หรือ "3-25E"  value = ราคา (บาท)
# ไม่ต้องกรอกก็ได้ -- ถ้าไม่ใส่ Gemini จะประมาณราคาให้ (ถ้าใส่ไว้ จะใช้ราคาที่ใส่ก่อนเสมอ)
BUS_ROUTE_FARE = {
    # "552": 0,
    # "3-25E": 0,
}
BUS_DEFAULT_FARE = None   # ราคาเริ่มต้นสำหรับสายที่ไม่อยู่ในรายการ (None = ให้ Gemini ประมาณ)
BUS_TYPES = {"BUS", "INTERCITY_BUS", "TROLLEYBUS", "SHARE_TAXI"}


def bus_fare(*names):
    """ลองทุกเลขสายที่พบในชื่อ เช่น "3-25E EV (552 EV)" -> ["3-25E", "552"]"""
    for t in names:
        for tok in re.findall(r"\d+(?:-\d+)?[A-Za-z]*", str(t or "")):
            if tok.upper() in BUS_ROUTE_FARE:
                return BUS_ROUTE_FARE[tok.upper()]
    return BUS_DEFAULT_FARE


# ---------- แอร์พอร์ตลิงก์ (ARL): คิดราคาจากชื่อสถานี ----------
ARL_STATIONS = [("Phaya Thai", "พญาไท"), ("Ratchaprarop", "ราชปรารภ"), ("Makkasan", "มักกะสัน"),
                ("Ramkhamhaeng", "รามคำแหง"), ("Hua Mak", "หัวหมาก"), ("Ban Thap Chang", "บ้านทับช้าง"),
                ("Lat Krabang", "ลาดกระบัง"), ("Suvarnabhumi", "สุวรรณภูมิ")]
_ARL_KEYS = [[fares._key(en), fares._key(th)] for en, th in ARL_STATIONS]


def arl_index(name):
    k = fares._key(name)
    if not k:
        return None
    for i, keys in enumerate(_ARL_KEYS):
        if any(x and (k == x or x in k) for x in keys):
            return i
    return None


def arl_fare(dep_name, arr_name, n):
    a, b = arl_index(dep_name), arl_index(arr_name)
    stops = abs(a - b) if a is not None and b is not None else n   # ถ้าหาชื่อไม่เจอใช้จำนวนสถานีจาก Google
    return fares.table_fare(fares.ARL, stops)


SRT_AGENCY = re.compile(r"การรถไฟแห่งประเทศไทย|state railway of thailand|\bsrt\b|รฟท", re.I)


TRAIN_VTYPES = {"HEAVY_RAIL", "COMMUTER_TRAIN", "LONG_DISTANCE_TRAIN", "HIGH_SPEED_TRAIN", "RAIL", "TRAIN"}


def is_thai_train(txt, vtype=""):
    """รถไฟไทย (รฟท.) ขบวนปกติ: ไม่ใช่ ARL และไม่ใช่สายสีแดง ซึ่งมีตารางราคาของตัวเอง"""
    if re.search(r"\barl\b|airport rail|แอร์พอร์ต|สายสีแดง|red line|แดงเข้ม|แดงอ่อน|dark red|light red", txt, re.I):
        return False
    return bool(SRT_AGENCY.search(txt)) or vtype in ("COMMUTER_TRAIN", "LONG_DISTANCE_TRAIN")


def detect_system(txt, vtype=""):
    """จับ ARL ก่อน เพราะชื่อหน่วยงานของ ARL มีคำว่า SRT ทำให้เคยถูกจัดเป็นสายสีแดง แล้วจับรถไฟไทย (รฟท.)"""
    if re.search(r"\barl\b|airport rail|แอร์พอร์ต", txt, re.I):
        return "ARL"
    if is_thai_train(txt, vtype):
        return "รถไฟไทย"
    sysn = fares.resolve_system(txt)
    if not sysn and vtype in TRAIN_VTYPES:           # รถไฟที่ Google ไม่บอกผู้ให้บริการ (เช่น "Chuk Samet - Bangkok") ถือเป็นรถไฟไทย
        return "รถไฟไทย"
    return sysn


# ---------- Google Routes API: เส้นทาง + ราคาขนส่งสาธารณะ ----------
def decode_polyline(enc):
    pts, i, lat, lng = [], 0, 0, 0
    while i < len(enc):
        for k in (0, 1):
            shift = result = 0
            while True:
                b = ord(enc[i]) - 63; i += 1
                result |= (b & 0x1f) << shift; shift += 5
                if b < 0x20: break
            d = ~(result >> 1) if result & 1 else result >> 1
            if k == 0: lat += d
            else: lng += d
        pts.append([lng / 1e5, lat / 1e5])
    return pts


def with_bkk(t):
    return t if re.search(r"กรุงเทพ|bangkok|สนามบิน|airport", t, re.I) else t + " กรุงเทพ"


@st.cache_resource
def _geo_store():
    return {"cache": {}, "off_until": 0}


def _geo_longdo(name):
    """ค้นพิกัดด้วย Longdo Map Search (ใช้คีย์ Longdo ที่มีอยู่ ไม่ต้องผูกบัตร) เน้นโซนกรุงเทพ"""
    r = requests.get("https://search.longdo.com/mapsearch/json/search", timeout=(4, 8),
                     params={"keyword": name, "lon": 100.5018, "lat": 13.7563, "span": "60km",
                             "limit": 3, "key": KEY}).json()
    for it in (r.get("data") or []) if isinstance(r, dict) else []:
        try:
            return {"lat": float(it["lat"]), "lng": float(it["lon"])}
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _geo_google(name, store):
    """สำรอง: Places API (New) Text Search (ต้องเปิด API นี้ในโปรเจกต์ Google Cloud) ใช้ไม่ได้คืน None"""
    try:
        r = requests.post("https://places.googleapis.com/v1/places:searchText", timeout=(4, 8),
                          headers={"X-Goog-Api-Key": GKEY, "X-Goog-FieldMask": "places.displayName,places.location"},
                          json={"textQuery": with_bkk(name), "languageCode": "th", "regionCode": "TH", "pageSize": 1,
                                "locationBias": {"circle": {"center": {"latitude": 13.7563, "longitude": 100.5018},
                                                            "radius": 50000.0}}}).json()
    except Exception as e:
        print(f"[geocode-google] {name}: {e}", flush=True)
        store["off_until"] = time.time() + 300
        return None
    if "error" in r:
        print(f"[geocode-google] ใช้ไม่ได้: {r['error'].get('message')}", flush=True)
        store["off_until"] = time.time() + 600
        return None
    loc = ((r.get("places") or [{}])[0]).get("location")
    return {"lat": loc["latitude"], "lng": loc["longitude"]} if loc else None


def geocode(name, store):
    """หาพิกัดสถานที่: Longdo ก่อน แล้วสำรองด้วย Google Places -> {"lat","lng"} หรือ None (ไม่แคชผลที่หาไม่เจอ)"""
    k = name.strip().lower()
    if k in store["cache"]:
        return store["cache"][k]
    out = None
    if KEY and time.time() >= store.get("ld_off", 0):
        try:
            out = _geo_longdo(name)
        except Exception as e:
            print(f"[geocode-longdo] {name}: {e}", flush=True)
            store["ld_off"] = time.time() + 300
    if not out and GKEY and time.time() >= store["off_until"]:
        out = _geo_google(name, store)
    if out:
        store["cache"][k] = out
    return out


_CACHE = {}

def g_route(origin, dest, mode, gkey, geo=None):
    k = (origin, dest, mode)
    hit = _CACHE.get(k)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    t0 = time.time()
    print(f"[g_route] เริ่ม {mode}: {origin} -> {dest}", flush=True)
    res = _g_route(origin, dest, mode, gkey, geo)
    note = res["error"] if isinstance(res, dict) and "error" in res else ("ไม่พบเส้นทาง" if res is None else "OK")
    print(f"[g_route] จบ {mode}: {origin} -> {dest} ใช้ {time.time() - t0:.1f}s ผล: {note}", flush=True)
    if not (isinstance(res, dict) and "error" in res):   # ไม่แคชผลที่ error
        _CACHE[k] = (time.time(), res)
    return res


def _g_route(origin, dest, mode, gkey, geo=None):
    wp = lambda t: ({"location": {"latLng": {"latitude": geo[t]["lat"], "longitude": geo[t]["lng"]}}}
                    if geo and geo.get(t) else {"address": with_bkk(t)})   # มีพิกัดใช้พิกัด ไม่มีใช้ชื่อเหมือนเดิม
    body = {"origin": wp(origin), "destination": wp(dest),
            "travelMode": "TRANSIT" if mode in ("RAIL", "SRT") else mode, "languageCode": "th", "regionCode": "TH"}
    if mode == "TRANSIT":
        # เพิ่ม BUS เพื่อให้ได้ช่วงรถเมล์ด้วย (ไม่งั้น Gemini ไม่มีอะไรให้ประมาณราคา)
        body["transitPreferences"] = {"allowedTravelModes": ["BUS", "SUBWAY", "TRAIN", "LIGHT_RAIL", "RAIL"]}
    elif mode == "RAIL":                             # เส้นทางรถไฟ/รถไฟฟ้าล้วน (ไม่ใช้รถเมล์) แสดงควบคู่กับเส้นทางหลัก
        body["transitPreferences"] = {"allowedTravelModes": ["TRAIN", "SUBWAY", "LIGHT_RAIL", "RAIL"]}
    elif mode == "SRT":                              # เฉพาะรถไฟไทย (รฟท.) ไม่รวมรถไฟฟ้า/รถเมล์ จะได้ชื่อสถานีรถไฟแยกต่างหาก
        body["transitPreferences"] = {"allowedTravelModes": ["TRAIN"]}
    r, last_err = None, None
    for _ in range(2):                               # ลองซ้ำอีก 1 ครั้งถ้าช้า/หลุด
        try:
            r = requests.post("https://routes.googleapis.com/directions/v2:computeRoutes", json=body, timeout=(5, 15), headers={
                "X-Goog-Api-Key": gkey,
                "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline,"
                                    "routes.legs.startLocation,routes.legs.endLocation,"
                                    "routes.legs.steps.travelMode,routes.legs.steps.distanceMeters,"
                                    "routes.legs.steps.transitDetails"}).json()
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_err = e
        except Exception as e:
            return {"error": str(e)}
    if r is None:
        return {"error": "เชื่อมต่อ Google Routes ไม่ได้หรือช้าเกินไป (timeout) ตรวจอินเทอร์เน็ต/ไฟร์วอลล์/VPN "
                         f"แล้วลองใหม่ ({type(last_err).__name__})"}
    if "error" in r:
        return {"error": r["error"].get("message", "unknown error")}
    rt = (r.get("routes") or [None])[0]
    if not rt:
        return None
    leg = (rt.get("legs") or [{}])[0]
    ll = lambda k: (leg.get(k) or {}).get("latLng")
    return {"km": rt.get("distanceMeters", 0) / 1000, "mins": int(str(rt.get("duration", "0s"))[:-1] or 0) / 60,
            "poly": (rt.get("polyline") or {}).get("encodedPolyline"), "steps": leg.get("steps", []),
            "start": ll("startLocation"), "end": ll("endLocation"), "raw": r}


# ราคาที่ Gemini ประมาณ เก็บลงไฟล์ด้วย จะได้ไม่ต้องถามซ้ำหลังรีสตาร์ท (ลบไฟล์ ai_fares.json เพื่อล้าง)
FARE_FILE = Path(__file__).resolve().parent / "ai_fares.json"


@st.cache_resource
def _ai_fare_store():
    try:
        raw = json.loads(FARE_FILE.read_text(encoding="utf-8"))
        return {tuple(k.split("|")): v for k, v in raw.items()}
    except Exception:
        return {}   # (ชื่อสาย, ขึ้น, ลง) -> ราคาที่ Gemini ประมาณ


@st.cache_resource
def _ai_state():
    return {"block_until": 0}   # เวลาที่หยุดเรียก Gemini ชั่วคราวเมื่อโควต้าหมด


def step_info(s_):
    """อ่านข้อมูลหนึ่งช่วงขนส่งสาธารณะ และหาราคาจากข้อมูลที่ตั้งไว้ (fares.py / BUS_ROUTE_FARE) ถ้าไม่มี f=None"""
    td = s_.get("transitDetails")
    if not td:
        return None
    ln, sd = td.get("transitLine", {}), td.get("stopDetails", {})
    name, short = ln.get("name", ""), ln.get("nameShort", "")
    agencies = ", ".join(a.get("name", "") for a in ln.get("agencies", []))
    txt = " ".join([name, short, agencies])
    n = td.get("stopCount", 1)
    dep, arr = sd.get("departureStop", {}), sd.get("arrivalStop", {})
    dep_n, arr_n = dep.get("name", ""), arr.get("name", "")
    vtype = (ln.get("vehicle") or {}).get("type", "")
    fixed = False                                    # True = ราคาที่กรอกเองใน BUS_ROUTE_FARE (ใช้ก่อน Gemini เสมอ)
    if vtype in BUS_TYPES:                           # รถเมล์
        f = bus_fare(short, name)
        fixed = f is not None
        label, icon, unit = "รถเมล์", "🚌", "ป้าย"
    else:
        sysn = detect_system(txt, vtype)
        if sysn == "ARL":                            # แอร์พอร์ตลิงก์ คิดจากชื่อสถานี
            f = arl_fare(dep_n, arr_n, n)
        elif sysn == "รถไฟไทย":                      # รถไฟ รฟท. ไม่มีตารางในระบบ ให้ Gemini ประมาณตามระยะทาง
            f = None
        elif sysn:
            f = fares.fare_by_names(sysn, dep_n, arr_n, n)
        else:
            f = None
        label, icon, unit = (sysn or "ขนส่ง"), ("🚂" if sysn == "รถไฟไทย" else "🚆"), "สถานี"
    return {"name": name, "short": short, "agencies": agencies, "vtype": vtype, "n": n, "dep": dep, "arr": arr,
            "dep_n": dep_n, "arr_n": arr_n, "f": f, "label": label, "icon": icon, "unit": unit,
            "key": (name, dep_n, arr_n), "m": s_.get("distanceMeters", 0), "fixed": fixed, "srt": label == "รถไฟไทย"}


AI_FARE_SYSTEM = (
    "คุณคือผู้เชี่ยวชาญค่าโดยสารขนส่งสาธารณะในกรุงเทพมหานครและปริมณฑลของประเทศไทย "
    "ผู้ใช้จะส่งรายการช่วงเดินทางที่มีทั้งรถเมล์ (ขสมก./รถร่วม/รถเมล์ EV) และรถไฟ/รถไฟฟ้า "
    "(BTS, MRT, แอร์พอร์ตลิงก์, รถไฟสายสีแดง รฟท., สายสีทอง, รถไฟ รฟท., เรือ ฯลฯ) "
    "ให้คำนวณค่าโดยสารเป็นบาท สำหรับผู้โดยสารผู้ใหญ่ทั่วไป ต่อ 1 คน ตามอัตราจริงล่าสุดที่คุณรู้จักของระบบนั้นๆ "
    "รถไฟฟ้า/รถไฟ: คิดตามสถานีต้นทาง-ปลายทางและจำนวนสถานี "
    "รถเมล์: แยกประเภท (ธรรมดา/ปรับอากาศ ขสมก./รถร่วม/EV) แล้วใช้อัตราของประเภทนั้น "
    "รถไฟไทย (ระบบ=รถไฟไทย ผู้ให้บริการ รฟท.): ประมาณตามระยะทางจากสถานีต้นทางถึงปลายทาง "
    "ใช้อัตราชั้น 3 ขบวนรถธรรมดา/ชานเมืองเป็นหลัก ถ้าชื่อขบวนเป็นรถเร็ว/รถด่วน ให้บวกค่าธรรมเนียมตามประเภทขบวนที่คุณรู้จัก "
    "ต้องตอบให้ครบทุก id ที่ส่งมา ห้ามข้าม และต้องเป็นตัวเลขเสมอ "
    "(ถ้าไม่แน่ใจให้ประมาณจากระยะทาง/จำนวนป้ายหรือสถานี) "
    'ตอบเป็น JSON อย่างเดียว รูปแบบ {"fares":[{"id":0,"fare":15},{"id":1,"fare":32}]} โดย id ตรงกับรายการที่ส่งมา')


def wants_ai(inf):
    """ช่วงนี้ต้องใช้ราคาจาก Gemini ไหม: ไม่มีราคาในระบบ หรือเปิด AI_ALL_TRANSIT (ยกเว้นรถเมล์ที่กรอกราคาเองใน BUS_ROUTE_FARE)"""
    return inf["f"] is None or (AI_ALL_TRANSIT and not inf["fixed"])


def _ask_fares(batch):
    """batch = [(key, inf), ...] -> {key: ราคา} เฉพาะที่ Gemini ตอบเป็นตัวเลขที่สมเหตุสมผล"""
    items = [{"id": i, "ระบบ": inf["label"], "ประเภทพาหนะ": inf["vtype"] or "ไม่ระบุ", "ชื่อสาย": inf["name"],
              "เลขสาย": inf["short"], "ผู้ให้บริการ": inf["agencies"],
              "ขึ้นที่": inf["dep_n"], "ลงที่": inf["arr_n"],
              "จำนวนป้าย/สถานี": inf["n"], "ระยะทางเมตร": inf["m"]}
             for i, (_, inf) in enumerate(batch)]
    payload = json.dumps(items, ensure_ascii=False)
    r = gemini_try(lambda m: gh.call_json(GEMINI_KEY, m, AI_FARE_SYSTEM, payload, max_total=20))
    if isinstance(r, str):
        r = json.loads(r)
    rows = r.get("fares") if isinstance(r, dict) else r
    got = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        i, fare = row.get("id"), row.get("fare")
        if isinstance(i, str) and i.strip().isdigit():
            i = int(i)
        if isinstance(fare, str):                        # เผื่อตอบเป็น "32 บาท"
            try:
                fare = float(re.sub(r"[^\d.]", "", fare))
            except ValueError:
                fare = None
        if isinstance(i, int) and 0 <= i < len(batch) and isinstance(fare, (int, float)) and 0 < fare <= 500:
            got[batch[i][0]] = round(fare)
    return got


def ai_fares(trs):
    """ขอราคาจาก Gemini (ทั้งรถเมล์และรถไฟ รวมครั้งเดียวทั้งทริป) คืน {key: ราคา}"""
    store, state = _ai_fare_store(), _ai_state()
    ss.ai_err = None
    todo = {}
    for tr in trs:
        for s_ in tr["steps"]:
            inf = step_info(s_)
            if inf and wants_ai(inf) and inf["key"] not in store:
                todo[inf["key"]] = inf
    if not todo:
        return store
    if not GEMINI_KEY:
        ss.ai_err = "ยังไม่ได้ตั้งค่า GEMINI_API_KEY ในไฟล์ .env"
        return store
    if time.time() < state["block_until"]:          # โควต้าหมดเมื่อไม่นานมานี้ ไม่ต้องรอเรียกซ้ำ
        ss.ai_err = "โควต้า Gemini หมด (พักการเรียกชั่วคราว)"
        return store
    try:
        batch = list(todo.items())
        store.update(_ask_fares(batch))
        missing = [kv for kv in batch if kv[0] not in store]
        if missing:                                  # Gemini ข้ามบางช่วง (มักเป็นรถไฟ) ถามซ้ำเฉพาะช่วงที่ขาด 1 รอบ
            try:
                store.update(_ask_fares(missing))
            except Exception as e:
                print(f"[gemini-fare] ถามซ้ำช่วงที่ขาดไม่สำเร็จ: {e}", flush=True)
        left = [k for k, _ in batch if k not in store]
        if left:
            ss.ai_err = f"Gemini ตอบราคาไม่ครบ ({len(batch) - len(left)}/{len(batch)} ช่วง)"
        try:
            FARE_FILE.write_text(json.dumps({"|".join(k): v for k, v in store.items()}, ensure_ascii=False),
                                 encoding="utf-8")
        except Exception:
            pass
    except Exception as e:
        if is_quota_error(e):
            state["block_until"] = time.time() + 1800   # พัก 30 นาที
            ss.ai_err = "โควต้า Gemini หมด"
        else:
            ss.ai_err = str(e)
        print(f"[gemini-fare] ขอราคาจาก Gemini ไม่สำเร็จ: {e}", flush=True)
    return store


def fare_of(inf, ai):
    """ราคาของช่วงนี้ -> (ราคา หรือ None, เป็นราคาที่ Gemini ประมาณไหม, ข้อความราคา)"""
    f, est = inf["f"], False
    if inf["key"] in ai and wants_ai(inf):           # ใช้ราคาที่ Gemini คำนวณ (ไม่มีในระบบ หรือเปิด AI_ALL_TRANSIT)
        f, est = ai[inf["key"]], True
    if f is not None:
        txt = f"≈ **{f} บาท**" + (" ✨(Gemini ประมาณ)" if est else "")
    else:
        txt = "_(ไม่ทราบราคา)_"
    return f, est, txt


def stop_names(inf):
    """ชื่อจุดขึ้น/ลง รถไฟไทยแสดงเป็น "สถานีรถไฟ ..." ให้แยกจากรถไฟฟ้า"""
    dn, an = inf["dep_n"] or "?", inf["arr_n"] or "?"
    if inf["srt"]:
        dn, an = [x if x == "?" or x.startswith("สถานี") else "สถานีรถไฟ" + x for x in (dn, an)]
    return dn, an


def parse_transit(tr, ai=None, dest=None):
    ai = ai or {}
    lines, stations, total, unknown, ai_used = [], [], 0, False, False
    walk_m, seen = 0, False
    for s_ in tr["steps"]:
        inf = step_info(s_)
        if not inf:
            if s_.get("travelMode") == "WALK":
                walk_m += s_.get("distanceMeters", 0)
            continue
        f, est, price = fare_of(inf, ai)
        total += f or 0; unknown |= f is None; ai_used |= est
        dn, an = stop_names(inf)
        if walk_m >= 100:                            # เดินไปจุดขึ้น
            lines.append(f"- 🚶 เดิน ~{walk_m:.0f} ม. ไปที่ **{dn}**")
        walk_m, seen = 0, True
        lbl = "รถไฟไทย (รฟท.)" if inf["srt"] else inf["label"]
        lines.append(f"- {inf['icon']} **{lbl}** {inf['name']}: "
                     f"ขึ้น **{dn}** → ลง **{an}** ({inf['n']} {inf['unit']}) " + price)
        for st_, kind in ((inf["dep"], "ขึ้น"), (inf["arr"], "ลง")):
            loc = (st_.get("location") or {}).get("latLng")
            if loc:
                stations.append({"name": f"{kind}: {st_.get('name', '')}", "lon": loc["longitude"], "lat": loc["latitude"]})
    if seen and walk_m >= 100 and dest:              # เดินต่อจากจุดลงไปปลายทาง
        lines.append(f"- 🚶 เดินต่อ ~{walk_m:.0f} ม. ไปที่ **{dest}**")
    return lines, stations, total, unknown, ai_used


# ---------- สรุป "ขึ้นอะไรได้บ้าง" ทุกช่วง: รถเมล์ / BTS / MRT / แอร์พอร์ตลิงก์ / รถไฟไทย ----------
MODE_ORDER = [("bus", "🚌", "รถเมล์"), ("bts", "🚈", "BTS"), ("mrt", "🚇", "MRT"),
              ("arl", "✈️", "แอร์พอร์ตลิงก์"), ("srt", "🚂", "รถไฟไทย / สายสีแดง")]


def mode_cat(inf):
    if inf["vtype"] in BUS_TYPES:
        return "bus"
    lb = inf["label"]
    if lb == "BTS":
        return "bts"
    if lb in ("BLUE", "PINK", "YELLOW", "PURPLE"):
        return "mrt"
    if lb == "ARL":
        return "arl"
    if lb in ("รถไฟไทย", "RED"):
        return "srt"
    return None


def collect_modes(routes, ai):
    """รวมทุกเส้นทางที่ Google ให้มาในช่วงนี้ แล้วเก็บตัวอย่างการขึ้นของแต่ละประเภทพาหนะ -> {ประเภท: ข้อความ}"""
    found = {}
    for rt in routes:
        if not (isinstance(rt, dict) and "error" not in rt and rt.get("steps")):
            continue
        for s_ in rt["steps"]:
            inf = step_info(s_)
            cat = mode_cat(inf) if inf else None
            if cat and cat not in found:
                dn, an = stop_names(inf)
                _, _, price = fare_of(inf, ai)
                nm = inf["short"] or inf["name"]
                found[cat] = (f"{nm}: " if nm else ": ") + f"ขึ้น **{dn}** → ลง **{an}** ({inf['n']} {inf['unit']}) {price}"
    return found


@st.cache_resource
def _near_store():
    return {"cache": {}, "off_until": 0}


def near_srt_stations(pt, store, radius=3000):
    """สถานีรถไฟ (รฟท.) ที่ใกล้จุดนี้ ใช้เมื่อ Google ไม่มีเส้นทางรถไฟไทยให้ (ใช้ Places API (New) ถ้าใช้ไม่ได้คืน [])"""
    if not pt or not GKEY or time.time() < store["off_until"]:
        return []
    k = (round(pt["latitude"], 3), round(pt["longitude"], 3))
    if k in store["cache"]:
        return store["cache"][k]
    try:
        r = requests.post("https://places.googleapis.com/v1/places:searchNearby", timeout=(4, 8),
                          headers={"X-Goog-Api-Key": GKEY, "X-Goog-FieldMask": "places.displayName"},
                          json={"includedTypes": ["train_station"], "maxResultCount": 10, "languageCode": "th",
                                "rankPreference": "DISTANCE",
                                "locationRestriction": {"circle": {"center": {"latitude": pt["latitude"],
                                                                              "longitude": pt["longitude"]},
                                                                   "radius": float(radius)}}}).json()
    except Exception as e:
        print(f"[srt-near] {e}", flush=True)
        store["off_until"] = time.time() + 300
        return []
    if "error" in r:
        print(f"[srt-near] Places ใช้ไม่ได้: {r['error'].get('message')}", flush=True)
        store["off_until"] = time.time() + 600
        return []
    names = []
    for p in r.get("places", []):
        n = (p.get("displayName") or {}).get("text", "")
        if (n and re.search(r"รถไฟ|railway|train station", n, re.I)
                and not re.search(r"รถไฟฟ้า|bts|mrt|metro|airport rail|แอร์พอร์ต", n, re.I) and n not in names):
            names.append(n)
    store["cache"][k] = names[:3]
    return names[:3]


def plan_leg(o, d, res, ai=None):
    drv, tr = res[(o, d, "DRIVE")], res[(o, d, "TRANSIT")]
    drv_err = drv["error"] if isinstance(drv, dict) and "error" in drv else None
    tr_err = tr["error"] if isinstance(tr, dict) and "error" in tr else None
    if drv_err: drv = None                           # ถ้าอย่างใดอย่างหนึ่ง error ใช้อีกอย่างที่ยังใช้ได้
    if tr_err: tr = None
    if not drv and not tr:
        err = drv_err or tr_err
        return {"error": f"Google Routes API: {err}" if err else
                f"หาเส้นทาง {o} → {d} ไม่เจอ ลองระบุชื่อสถานที่ให้ชัดขึ้น"}
    base = drv or tr
    km, mins = base["km"], base["mins"]
    jam = max(0, mins - km / 30 * 60) * 0.5
    airport = any(w in o.lower() for w in ["สุวรรณภูมิ", "suvarnabhumi", "don mueang airport", "สนามบินดอนเมือง", "airport"])  # ค่าสนามบิน: ขึ้นจากสนามบิน
    leg = {"o": o, "d": d, "start": base["start"], "end": base["end"], "km": km, "mins": mins,
           "paths": [decode_polyline(base["poly"])] if base.get("poly") else [], "lines": [], "stations": [],
           "has_transit": False, "transit_total": 0, "unknown": False, "ai": False, "transit_mins": 0, "airport": airport,
           "moto": fares.motorcycle_fare(km), "taxi": fares.taxi_fare(km, jam, airport)}
    if tr:
        ss.debug = tr["raw"]
        lines, stations, total, unknown, ai_used = parse_transit(tr, ai, d)
        if lines:
            leg.update(has_transit=True, lines=lines, stations=stations, transit_total=total,
                       unknown=unknown, transit_mins=tr["mins"], ai=ai_used)
            if tr.get("poly"):
                leg["paths"] = [decode_polyline(tr["poly"])]
    wk = res.get((o, d, "WALK"))                     # เดินได้ถ้าไม่เกิน WALK_MAX_KM
    leg["walk"] = None
    if isinstance(wk, dict) and "error" not in wk and wk["km"] <= WALK_MAX_KM:
        leg["walk"] = {"km": wk["km"], "mins": wk["mins"]}
    leg["rail"] = None                               # ทางเลือกรถไฟ/รถไฟฟ้าล้วน (ไม่ใช้รถเมล์) แสดงควบคู่กับเส้นทางหลัก
    rl = res.get((o, d, "RAIL"))
    ks = lambda t: [(step_info(x) or {}).get("key") for x in ((t or {}).get("steps") or []) if x.get("transitDetails")]
    if isinstance(rl, dict) and "error" not in rl and rl.get("steps") and ks(rl) and ks(rl) != ks(tr):
        rlines, rstations, rtotal, runknown, rai = parse_transit(rl, ai, d)
        if rlines:
            leg["rail"] = {"lines": rlines, "stations": rstations, "total": rtotal, "unknown": runknown,
                           "ai": rai, "mins": rl["mins"]}
    # รถไฟไทยล้วน (ขอ Google แยกโหมด TRAIN) เอาชื่อสถานีไปแสดงบนแผนที่ และรวมเข้าสรุป "ขึ้นอะไรได้บ้าง"
    srt = res.get((o, d, "SRT"))
    leg["srt_stations"] = []
    if isinstance(srt, dict) and "error" not in srt and srt.get("steps"):
        leg["srt_stations"] = parse_transit(srt, ai, d)[1]
    leg["modes"] = collect_modes([tr, rl, srt], ai)
    return leg


def mode_lines(leg):
    """แสดงเฉพาะพาหนะที่ Google พบเส้นทางจริง"""
    modes = leg.get("modes") or {}
    return [f"  - {icon} **{nm}** {modes[cat]}" for cat, icon, nm in MODE_ORDER if cat in modes]


def plan_trip(stops):
    ss.legs, ss.markers, ss.stations = [], [], []
    ss.fresh_places = []
    if not GKEY:
        return "⚠️ ยังไม่ได้ตั้งค่า GOOGLE_MAPS_API_KEY ในไฟล์ .env"
    if len(stops) < 2:
        return "ต้องมีอย่างน้อย 2 จุด (ต้นทางและปลายทาง)"
    stops = stops[:MAX_STOPS]
    print(f"[plan_trip] เริ่มวางแผน {stops}", flush=True)
    gstore = _geo_store()
    with ThreadPoolExecutor(max_workers=4) as gx:
        geo = dict(zip(stops, gx.map(lambda x: geocode(x, gstore), stops)))
    no_geo = [x for x in stops if not geo.get(x)]
    pt = lambda nm, fb: ({"lon": geo[nm]["lng"], "lat": geo[nm]["lat"]} if geo.get(nm) else
                         ({"lon": fb["longitude"], "lat": fb["latitude"]} if fb else None))
    pairs = [(stops[i], stops[i + 1], m) for i in range(len(stops) - 1) for m in ("DRIVE", "TRANSIT", "RAIL", "SRT", "WALK")]
    ex = ThreadPoolExecutor(max_workers=8)
    futs = {k: ex.submit(g_route, k[0], k[1], k[2], GKEY, geo) for k in pairs}
    wait(list(futs.values()), timeout=45)            # รอรวมไม่เกิน 45 วินาที
    ex.shutdown(wait=False)                          # ไม่รอ thread ที่ค้าง
    res = {}
    for k, f in futs.items():
        try:
            res[k] = f.result() if f.done() else {"error": "หมดเวลารอ Google (เกิน 45 วินาที) ตรวจอินเทอร์เน็ต/VPN แล้วลองใหม่"}
        except Exception as e:
            res[k] = {"error": str(e)}
    print("[plan_trip] ดึงข้อมูลจาก Google เสร็จแล้ว", flush=True)
    trs = [x for x in (res.get((stops[i], stops[i + 1], md)) for i in range(len(stops) - 1) for md in ("TRANSIT", "RAIL", "SRT"))
           if isinstance(x, dict) and "error" not in x and x.get("steps") is not None]
    ai = ai_fares(trs)                               # ให้ Gemini ประมาณราคาช่วงที่ไม่มีใน fares (รถเมล์ รถไฟ รฟท. ฯลฯ)
    out = [f"## 🗺️ แผนเดินทาง {len(stops)} จุด", " → ".join(f"**{i+1}. {s}**" for i, s in enumerate(stops)), ""]
    if ss.get("ai_err"):
        out.append(f"⚠️ ขอราคาประมาณจาก Gemini ไม่สำเร็จ ({ss.ai_err}) จึงยังไม่แสดงราคาบางช่วง "
                   "ตรวจ GEMINI_MODEL / คีย์ ในไฟล์ .env แล้วกด \"ทดสอบเรียก Gemini\"\n")
    if no_geo:
        out.append(f"⚠️ หาพิกัดของ {', '.join(no_geo)} ไม่ได้ จึงใช้ชื่อค้นหาแทน ตำแหน่งหมุดอาจคลาดเคลื่อน "
                   "(ลองระบุชื่อสถานที่ให้ชัดขึ้น หรือตรวจคีย์ LONGDO_API_KEY)\n")
    tot_km = tot_min = tot_tr = tot_moto = tot_taxi = 0
    any_ai = False
    marked = set()
    for i in range(len(stops) - 1):
        leg = plan_leg(stops[i], stops[i + 1], res, ai)
        if "error" in leg:
            out.append(f"### ช่วงที่ {i+1}: {stops[i]} → {stops[i+1]}\n❌ {leg['error']}\n")
            continue
        s0, s1 = leg["start"], leg["end"]
        for idx, nm, fb in ((i, leg["o"], s0), (i + 1, leg["d"], s1)):   # เลขหมุด = ลำดับจุดแวะจริง
            p = pt(nm, fb)
            if idx not in marked and p:
                ss.markers.append({"n": idx + 1, "name": nm, **p}); marked.add(idx)
        ss.legs.append(leg); ss.stations += leg["stations"]
        for st_ in leg["srt_stations"]:              # สถานีรถไฟไทยแสดงบนแผนที่ด้วย
            if st_ not in ss.stations:
                ss.stations.append(st_)
        out.append(f"### ช่วงที่ {i+1}: {leg['o']} → {leg['d']}")
        out.append(f"ระยะทางประมาณ {leg['km']:.1f} กม.")
        gm = ("https://www.google.com/maps/dir/?api=1&origin=" + quote(with_bkk(leg["o"])) +
              "&destination=" + quote(with_bkk(leg["d"])) + "&travelmode=transit")
        out.append(f"[🔗 เปิดช่วงนี้ใน Google Maps]({gm})")
        if leg.get("walk"):                          # ระยะใกล้ เดินได้
            w = leg["walk"]
            dist = f"{w['km'] * 1000:.0f} ม." if w["km"] < 1 else f"{w['km']:.1f} กม."
            out.append(f"- 🚶 **เดินได้**: {leg['o']} → {leg['d']} ≈ {dist} · {w['mins']:.0f} นาที")
        if leg["has_transit"]:
            out += leg["lines"]
            if leg["transit_total"]:
                notes = (["รวมราคาที่ Gemini ประมาณ"] if leg["ai"] else []) + (["เฉพาะช่วงที่ทราบราคา"] if leg["unknown"] else [])
                out.append(f"- 💳 ขนส่งสาธารณะรวม ≈ **{leg['transit_total']} บาท**"
                           f"{' (' + ', '.join(notes) + ')' if notes else ''} · {leg['transit_mins']:.0f} นาที")
            else:
                out.append(f"- ⏱️ ขนส่งสาธารณะ {leg['transit_mins']:.0f} นาที")
            tot_tr += leg["transit_total"]; any_ai |= leg["ai"]
        if leg.get("rail"):
            rl = leg["rail"]
            out.append("- 🚆 **ทางเลือกรถไฟ/รถไฟฟ้า (ไม่ใช้รถเมล์)**")
            out += ["  " + x for x in rl["lines"]]
            rnotes = (["รวมราคาที่ Gemini ประมาณ"] if rl["ai"] else []) + (["เฉพาะช่วงที่ทราบราคา"] if rl["unknown"] else [])
            if rl["total"]:
                out.append(f"  - 💳 รวม ≈ **{rl['total']} บาท**"
                           f"{' (' + ', '.join(rnotes) + ')' if rnotes else ''} · {rl['mins']:.0f} นาที")
            else:
                out.append(f"  - ⏱️ {rl['mins']:.0f} นาที")
            for st_ in rl["stations"]:
                if st_ not in ss.stations:
                    ss.stations.append(st_)
        leg["mode_lines"] = mode_lines(leg)
        if leg["mode_lines"]:                        # สรุปเฉพาะพาหนะที่พบจริง
            out.append("- 🚏 **ขึ้นได้ด้วย**")
            out += leg["mode_lines"]
        out.append(f"- 🛵 วิน ≈ **{leg['moto']} บาท**")
        out.append(f"- 🚕 แท็กซี่ ≈ **{leg['taxi']} บาท**{' (รวมค่าบริการสนามบิน)' if leg['airport'] else ''}\n")
        tot_km += leg["km"]; tot_min += leg["mins"]; tot_moto += leg["moto"]; tot_taxi += leg["taxi"]
    if ss.legs:
        out += ["---", "### 💰 สรุปทั้งทริป",
                f"- ระยะทางรวม (ขับรถ) **{tot_km:.1f} กม.** ≈ {tot_min:.0f} นาที",
                *([f"- 🚆 ขนส่งสาธารณะ ≈ **{tot_tr} บาท**" + (" (บางช่วงเป็นราคาที่ Gemini ประมาณ อาจคลาดเคลื่อน)" if any_ai else "")] if tot_tr else []),
                f"- 🛵 วินมอเตอร์ไซค์ ≈ **{tot_moto} บาท**",
                f"- 🚕 แท็กซี่ ≈ **{tot_taxi} บาท** (ยังไม่รวมค่าทางด่วน)"]
    ss.fresh_places = [m["name"] for m in ss.markers]   # ให้แชทไปดึงรูปของจุดเหล่านี้จาก Wikipedia
    return "\n".join(out)


# ---------- Gemini: จัดลำดับจุด + ตอบคำถามจากแผนปัจจุบัน ----------
def trip_context():
    """สรุปแผนปัจจุบันให้ Gemini อ่าน (ใช้ข้อมูลจริงจาก Google ไม่ให้เดาเอง)"""
    if not ss.legs:
        cur = [x.strip() for x in ss.stops_text.splitlines() if x.strip()]
        return "(ยังไม่มีแผน)" + (f" จุดแวะที่กรอกไว้: {' -> '.join(cur)}" if cur else "")
    rows = []
    for i, l in enumerate(ss.legs, 1):
        rows.append(f"ช่วง {i}: {l['o']} -> {l['d']} | ขับรถ {l['km']:.1f} กม. {l['mins']:.0f} นาที | "
                    f"วิน ~{l['moto']} บาท | แท็กซี่ ~{l['taxi']} บาท")
        for ln in l["lines"]:
            rows.append("   " + re.sub(r"[*]", "", ln))
        if l["has_transit"]:
            rows.append(f"   ขนส่งสาธารณะรวม ~{l['transit_total']} บาท{' (บางส่วนไม่ทราบราคา)' if l['unknown'] else ''}"
                        f" เวลา {l['transit_mins']:.0f} นาที")
        if l.get("rail"):
            rows.append("   ทางเลือกรถไฟ/รถไฟฟ้า (ไม่ใช้รถเมล์):")
            for ln in l["rail"]["lines"]:
                rows.append("      " + re.sub(r"[*]", "", ln))
        if l.get("mode_lines"):
            rows.append("   ขึ้นอะไรได้บ้างในช่วงนี้:")
            for ln in l["mode_lines"]:
                rows.append("      " + re.sub(r"[*_]", "", ln).strip())
    return "\n".join(rows)


def run_plan(stops, reorder=False, fixed_start=True):
    """วางแผนเส้นทาง (ถ้า reorder=True ให้ Gemini จัดลำดับก่อนว่าไปที่ไหนก่อน-หลัง) คืนข้อความ markdown"""
    note = ""
    if reorder and GEMINI_KEY and len(stops) > (2 if fixed_start else 1):
        try:
            new, why = gemini_try(lambda m: gh.suggest_order(GEMINI_KEY, m, stops, fixed_start))
            if why.startswith("Gemini จัดลำดับมาไม่ครบ"):
                note = f"⚠️ {why}\n\n"
            else:
                stops = new
                note = f"✨ **Gemini จัดลำดับให้:** {' → '.join(stops)}\n\n{why}\n\n---\n\n"
        except Exception as e:
            note = f"⚠️ Gemini จัดลำดับไม่ได้ ({e}) ใช้ลำดับเดิม\n\n"
    ss.stops_text = "\n".join(stops[:MAX_STOPS])
    return note + plan_trip(stops)


# ---------- Gemini: แนะนำที่เที่ยว/คาเฟ่ตามโซน แล้วต่อเข้าระบบวางเส้นทาง ----------
# ตัด "แนะนำสถานี..." ออก เพราะเป็นคำถามเรื่องการเดินทาง ไม่ใช่ขอที่เที่ยว
DISCOVER_RE = re.compile(r"แนะนำ(?!สถานี|ป้าย|สาย|รถ)|คาเฟ่|cafe|ที่เที่ยว|อยากไปเที่ยว|เที่ยว.*(โซน|ย่าน|แถว)", re.I)

DISCOVER_SYSTEM = (
    "คุณคือไกด์ท่องเที่ยวกรุงเทพมหานคร ผู้ใช้จะบอกโซน/จำนวนที่/ความสนใจ เช่น 'โซนวัดพระแก้ว 5 ที่ แนะนำคาเฟ่ด้วย' "
    "ให้เลือกสถานที่ที่มีอยู่จริงและอยู่ในโซนนั้นหรือใกล้เคียง เดินทางต่อกันสะดวก "
    "ถ้าผู้ใช้ระบุจำนวนที่ ให้ยึดตามนั้น (รวมคาเฟ่/ร้านอาหารที่ขอ) ถ้าไม่ระบุให้เสนอ 5 ที่ สูงสุด 8 ที่ "
    "ผสมที่เที่ยวหลักกับที่เที่ยวรองที่คนมักมองข้าม และใส่คาเฟ่/ร้านอาหารเมื่อผู้ใช้ขอ "
    "name ต้องเป็นชื่อที่ค้นใน Google Maps แล้วเจอ (ชื่อทางการ ไม่ย่อ ห้ามแต่งชื่อขึ้น) "
    "ถ้าผู้ใช้เคยมีแผนอยู่แล้ว (แผนปัจจุบัน) ให้เสริมจากแผนนั้นและไม่ซ้ำกับที่มีอยู่ "
    'ตอบเป็น JSON อย่างเดียว รูปแบบ {"intro":"ข้อความสั้นๆ แนะนำโซนนี้","places":'
    '[{"name":"วัดพระแก้ว","kind":"attraction","why":"เหตุผลสั้นๆ","stay_min":90}]} '
    "โดย kind เป็น attraction, cafe หรือ food อย่างใดอย่างหนึ่ง และเรียง places ตามลำดับที่ควรไปที่สุด")

KIND_ICON = {"attraction": "🏛️", "cafe": "☕", "food": "🍜"}


def handle_discover(q):
    """ให้ Gemini แนะนำสถานที่ตามคำขอ แล้ววางแผนต่อ คืน markdown (คืน None ถ้าใช้ไม่ได้)"""
    payload = json.dumps({"คำขอ": q, "แผนปัจจุบัน": trip_context()}, ensure_ascii=False)
    r = gemini_try(lambda m: gh.call_json(GEMINI_KEY, m, DISCOVER_SYSTEM, payload, max_total=20))
    if isinstance(r, str):
        r = json.loads(r)
    if not isinstance(r, dict):
        return None
    places = [p for p in (r.get("places") or []) if isinstance(p, dict) and p.get("name")][:MAX_STOPS]
    if len(places) < 2:
        return None
    out = [f"✨ {r.get('intro') or 'ที่แนะนำสำหรับคุณ'}", ""]
    for i, p in enumerate(places, 1):
        icon = KIND_ICON.get(p.get("kind"), "📍")
        stay = f" · ใช้เวลา ~{p['stay_min']} นาที" if isinstance(p.get("stay_min"), (int, float)) else ""
        out.append(f"{i}. {icon} **{p['name']}** — {p.get('why', '')}{stay}")
    names = [thai_fix(str(p["name"]).strip()) for p in places]
    if AUTO_PLAN_DISCOVER:
        # fixed_start=False = ให้ Gemini เลือกจุดเริ่มต้นเองด้วย (ลำดับเที่ยวด้านล่างอาจต่างจากรายชื่อด้านบน)
        return "\n".join(out) + "\n\n---\n\n" + run_plan(names, reorder=True, fixed_start=False)
    ss.stops_text = "\n".join(names)
    ss.fresh_places = names                          # แนบรูปจาก Wikipedia (ไม่ต้องใช้คีย์)
    return "\n".join(out) + "\n\n👉 ใส่รายชื่อในช่อง \"จุดแวะ\" ให้แล้ว กด **แสดงเส้นทาง** ได้เลย หรือแก้ไขรายชื่อก่อนก็ได้"


def handle_message(q):
    """ข้อความจากแชท: ใช้ Gemini แยกว่าวางแผนหรือถามคำถาม ถ้าใช้ไม่ได้ถอยกลับไปตัวแยกคำเดิม"""
    prefix = ""
    if GEMINI_KEY:
        try:
            if DISCOVER_RE.search(q):                # ขอให้แนะนำที่เที่ยว/คาเฟ่
                ans = handle_discover(q)
                if ans:
                    return ans
            ctx = trip_context()
            r = gemini_try(lambda m: gh.route_message(GEMINI_KEY, m, ctx, q))
            if r["intent"] == "chat" and r["answer"]:
                return r["answer"]
            stops = r["stops"]
            cur = [x.strip() for x in ss.stops_text.splitlines() if x.strip()]
            if len(stops) == 1 and cur:
                stops = [cur[-1], stops[0]]
            if len(stops) >= 2:
                reorder = r["reorder"] or (AUTO_ORDER and len(stops) >= 3)   # 3 จุดขึ้นไป ให้ Gemini จัดลำดับให้เอง
                return run_plan(stops, reorder, r["fixed_start"])
        except Exception as e:
            print(f"[gemini] {e}", flush=True)
            prefix = f"⚠️ ใช้ Gemini ไม่ได้ ({e}) จึงใช้ตัวแยกคำแบบปกติแทน\n\n"
    stops = parse_stops(q)
    if stops:
        if wants_reorder(q):
            prefix += "ℹ️ จัดลำดับให้ไม่ได้ตอนนี้ (ต้องใช้ Gemini) จึงใช้ตามลำดับที่พิมพ์\n\n"
        return prefix + run_plan(stops)
    return prefix + "บอกอย่างน้อย 2 ที่หน่อยครับ เช่น **จากสยามไปวัดโพธิ์ แล้วไปเยาวราช**"


# ---------- รูปสถานที่จาก Wikipedia (Gemini เลือกบทความ โค้ดดึงรูปจริงจาก Wikipedia API) ----------
# ไม่ให้ Gemini ส่ง URL รูปมาเอง เพราะมักแต่งลิงก์ผิด ให้เลือกแค่ "ชื่อบทความ" แล้วโค้ดไปดึง URL จริงจาก Wikipedia
WIKI_HEADERS = {"User-Agent": "BangkokAITravelPlanner/1.0 (personal project; you@example.com)"}  # แก้อีเมลเป็นของคุณ
WIKI_BAD = re.compile(r"icon|logo|flag|symbol|locator|map|commons-|wikimedia|edit-|question|disambig|stub|"
                      r"ambox|portal|pictogram|signature|coat_of_arms|diagram|chart|template|"
                      r"\.svg$|\.gif$|\.tiff?$|\.ogg$|\.webm$|\.pdf$", re.I)   # ตัดไอคอน/โลโก้/ธง/แผนที่ ออก
WIKI_PICK_SYSTEM = (
    "คุณช่วยเลือกบทความ Wikipedia ที่ตรงกับสถานที่ท่องเที่ยวในกรุงเทพมหานคร "
    "ผู้ใช้จะส่งรายชื่อสถานที่ที่พิมพ์มา (อาจเป็นชื่อเรียกสั้นๆ หรือกำกวม เช่น สยาม = สยามสแควร์) "
    "ให้ตอบชื่อบทความ Wikipedia ที่ตรงที่สุดของแต่ละที่ เลือกภาษา th ก่อน ถ้าบทความไทยน่าจะไม่มีให้ใช้ en "
    "title ต้องเป็นชื่อบทความจริงที่คุณรู้จัก ห้ามแต่งขึ้น ถ้าไม่แน่ใจให้ใช้ชื่อที่ผู้ใช้พิมพ์ "
    'ตอบเป็น JSON อย่างเดียว รูปแบบ {"places":[{"id":0,"lang":"th","title":"วัดโพธิ์"}]} โดย id ตรงกับรายการที่ส่งมา')


@st.cache_resource
def _wiki_cache():
    return {}   # ชื่อสถานที่ -> (เวลา, ผลลัพธ์)


def _wiki_api(lang, **params):
    params.update(action="query", format="json", formatversion=2)
    r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", params=params, headers=WIKI_HEADERS, timeout=(4, 8))
    r.raise_for_status()
    return r.json()


def _wiki_page_images(lang, title, n):
    """คืน (ชื่อบทความจริง, [รูป]) ถ้าไม่มีบทความคืน (None, [])"""
    d = _wiki_api(lang, titles=title, redirects=1, prop="images|pageimages", imlimit=100, piprop="name")
    pages = d.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None, []
    page = pages[0]
    names = [i["title"] for i in page.get("images", []) if not WIKI_BAD.search(i["title"].split(":", 1)[-1])]
    lead = page.get("pageimage")                     # รูปหลักของบทความ เอาไว้ก่อน
    if lead:
        lead_n = lead.replace("_", " ")
        names = [x for x in names if x.split(":", 1)[-1] != lead_n]
        names.insert(0, "File:" + lead_n)
    names = names[: n * 3]                           # เผื่อบางรูปเล็กเกินจนถูกตัด
    if not names:
        return page["title"], []
    info = _wiki_api(lang, titles="|".join(names), prop="imageinfo", iiprop="url|size|mime", iiurlwidth=360)
    got = {}
    for p in info.get("query", {}).get("pages", []):
        ii = (p.get("imageinfo") or [None])[0]
        if ii and ii.get("mime") in ("image/jpeg", "image/png", "image/webp") \
                and ii.get("width", 0) >= 400 and ii.get("height", 0) >= 250:
            got[p["title"].split(":", 1)[-1]] = {"thumb": ii.get("thumburl") or ii["url"]}
    out = [got[t.split(":", 1)[-1]] for t in names if t.split(":", 1)[-1] in got]   # เรียงตามลำดับในบทความ
    return page["title"], out[:n]


def _wiki_gallery(name, pick, n):
    """ลองบทความที่ Gemini เลือก -> ค้นชื่อไทย -> ค้นชื่ออังกฤษ"""
    for lang, q in (pick, ("th", name), ("en", name + " Bangkok")):
        try:
            title, imgs = _wiki_page_images(lang, q, n)
            if not imgs:                             # ชื่อตรงๆ ไม่เจอ ลองค้นหา
                hits = _wiki_api(lang, list="search", srsearch=q, srlimit=1, srprop="").get("query", {}).get("search", [])
                if hits:
                    title, imgs = _wiki_page_images(lang, hits[0]["title"], n)
            if imgs:
                return {"name": name, "title": title, "images": imgs, "lang": lang,
                        "url": f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"}
        except Exception as e:
            print(f"[wiki] {lang} {q}: {e}", flush=True)
    return None


def pick_wiki_pages(names):
    """ให้ Gemini เลือกบทความ Wikipedia ของแต่ละสถานที่ (ถ้าใช้ไม่ได้ ใช้ชื่อที่พิมพ์แทน)"""
    picks = {n: ("th", n) for n in names}
    if not GEMINI_KEY:
        return picks
    try:
        items = [{"id": i, "ชื่อที่ผู้ใช้พิมพ์": n} for i, n in enumerate(names)]
        payload = json.dumps(items, ensure_ascii=False)
        r = gemini_try(lambda m: gh.call_json(GEMINI_KEY, m, WIKI_PICK_SYSTEM, payload, max_total=20))
        if isinstance(r, str):
            r = json.loads(r)
        for row in (r.get("places") if isinstance(r, dict) else r) or []:
            i, lang, title = row.get("id"), row.get("lang"), str(row.get("title") or "").strip()
            if isinstance(i, int) and 0 <= i < len(names) and lang in ("th", "en") and title:
                picks[names[i]] = (lang, title)
    except Exception as e:
        print(f"[gemini-wiki] {e}", flush=True)
    return picks


def fetch_place_images(names, n=IMAGES_PER_PLACE):
    cache = _wiki_cache()
    names = list(dict.fromkeys(x for x in names if x))
    todo = [x for x in names if not (x in cache and time.time() - cache[x][0] < 3600)]
    if todo:
        picks = pick_wiki_pages(todo)
        with ThreadPoolExecutor(max_workers=4) as ex:
            res = list(ex.map(lambda x: _wiki_gallery(x, picks[x], n), todo))
        for x, g in zip(todo, res):
            cache[x] = (time.time(), g)
    return [g for g in (cache[x][1] for x in names) if g]


def new_reply(content):
    """สร้างข้อความตอบกลับ ถ้าเพิ่งวางแผนเสร็จ ให้แนบรูปสถานที่ไปด้วย"""
    places = ss.get("fresh_places") or []
    ss.fresh_places = []
    msg = {"role": "assistant", "content": thai_fix(content)}
    if places:
        try:
            msg["images"] = fetch_place_images(places)
        except Exception as e:
            print(f"[wiki] {e}", flush=True)
    return msg


def render_images(places):
    for p in places:
        st.markdown(f"**📷 {p['name']}** · [{p['title']} · Wikipedia]({p['url']})")
        st.image([i["thumb"] for i in p["images"]], width=150)


def reorder_cb():
    """ปุ่ม 'ให้ Gemini จัดลำดับ' (ใช้ callback เพื่อแก้ค่าในช่องข้อความได้)"""
    stops = [x.strip() for x in ss.stops_text.splitlines() if x.strip()]
    if not GEMINI_KEY:
        ss.msgs.append({"role": "assistant", "content": "ยังไม่ได้ตั้งค่า GEMINI_API_KEY ในไฟล์ .env"})
    elif len(stops) < 3:
        ss.msgs.append({"role": "assistant", "content": "ต้องมีอย่างน้อย 3 จุดจึงจะจัดลำดับได้ (จุดแรกคือต้นทางเสมอ)"})
    else:
        ss.msgs.append(new_reply(run_plan(stops, reorder=True)))


# ---------- แยกหลายที่จากประโยค ----------
SEP = r"\s*(?:แล้วไป|จากนั้นไป|จากนั้น|ต่อไป|แล้ว|ไป(?!รษณีย์)|ถึง|→|->|,|،|\bthen\b|\bto\b)\s*"

def wants_reorder(t):
    return bool(re.search(r"ก่อน|ลำดับ|ควรไป|ไปไหนดี|จัดให้", t))


def parse_stops(t):
    t = t.strip()
    t = re.sub(r"\s*(ควร[^\s]*.*|ก่อนดี.*|ดีไหม.*|ดีมั้ย.*|ช่วยจัด.*)$", "", t)          # ตัดท้ายประโยคคำถาม
    t = re.sub(r"^(ฉัน|ผม|เรา|หนู|ดิฉัน)?\s*(อยากจะ|อยาก|จะ)?\s*", "", t)              # ตัด "ฉันจะ" "อยาก"
    t = re.sub(r"^(วางแผน(เที่ยว|เดินทาง)?|พาไป|ขอเส้นทาง)\s*", "", t)
    t = re.sub(r"^(จาก|from|ไป)\s*", "", t, flags=re.I)
    parts = [p.strip() for p in re.split(SEP, t, flags=re.I) if p.strip()]
    cur = [x.strip() for x in ss.stops_text.splitlines() if x.strip()]
    if len(parts) == 1 and cur:
        parts = [cur[-1], parts[0]]
    return parts if len(parts) >= 2 else None


# ---------- แผนที่ Longdo (แสดงผลอย่างเดียว) ----------
def show_map():
    if not KEY:
        st.warning("ยังไม่มี LONGDO_API_KEY จึงแสดงรูปแผนที่ไม่ได้ (ข้อมูลเส้นทางด้านซ้ายใช้ได้ปกติ)")
        return
    paths = [{"coords": c, "color": COLORS[i % len(COLORS)]} for i, leg in enumerate(ss.legs) for c in leg["paths"]]
    payload = json.dumps({"paths": paths, "markers": ss.markers, "stations": ss.stations},
                         ensure_ascii=False).replace("</", "<\\/")
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>html,body,#map{{height:100%;margin:0}}</style>
<script src="https://api.longdo.com/map/?key={KEY}"></script></head>
<body><div id="map"></div><script>
const D = {payload};
window.onload = function () {{
  if (typeof longdo === 'undefined') {{ document.body.innerText = 'โหลด Longdo Map ไม่ได้ ตรวจ API key / โดเมนที่อนุญาต'; return; }}
  const map = new longdo.Map({{ placeholder: document.getElementById('map'), language: 'th' }});
  const b = {{ minLon: 999, minLat: 999, maxLon: -999, maxLat: -999 }};
  const ext = p => {{ b.minLon = Math.min(b.minLon, p.lon); b.maxLon = Math.max(b.maxLon, p.lon);
                      b.minLat = Math.min(b.minLat, p.lat); b.maxLat = Math.max(b.maxLat, p.lat); }};
  D.paths.forEach(p => {{
    const pts = p.coords.map(c => ({{ lon: c[0], lat: c[1] }}));
    pts.forEach(ext);
    map.Overlays.add(new longdo.Polyline(pts, {{ lineWidth: 5, lineColor: p.color }}));
  }});
  D.markers.forEach(m => {{
    ext(m);
    map.Overlays.add(new longdo.Marker({{ lon: m.lon, lat: m.lat }}, {{
      title: m.name,
      icon: {{ html: '<div style="background:#222;color:#fff;border-radius:50%;width:28px;height:28px;line-height:28px;text-align:center;font:700 15px sans-serif;border:2px solid #fff">' + m.n + '</div>',
               offset: {{ x: 14, y: 14 }} }} }}));
  }});
  (D.stations || []).forEach(m => {{
    map.Overlays.add(new longdo.Marker({{ lon: m.lon, lat: m.lat }}, {{
      title: m.name,
      icon: {{ html: '<div style="background:#fff;border:3px solid #2f6fe4;border-radius:50%;width:12px;height:12px"></div>', offset: {{ x: 6, y: 6 }} }} }}));
  }});
  map.bound(b);
}};
</script></body></html>"""
    components.html(html, height=MAP_H)
    st.caption("แผนที่: Longdo Map · ข้อมูลเส้นทาง/ราคา: Google Maps · หมายเลข = ลำดับจุดแวะ · จุดวงกลมขาว = สถานีที่ขึ้น/ลง (ชี้เมาส์ดูชื่อ)")


# ---------- หน้าแรก ----------
if ss.page == "home":
    st.markdown("""<style>                           /* เต็มหน้าจอ: ตัดขอบว่างของ Streamlit เฉพาะหน้าแรก */
    .block-container, [data-testid="stMainBlockContainer"] {padding:0 !important;max-width:100% !important}
    [data-testid="stAppViewContainer"], .stApp {background:#000}
    [data-testid="stVerticalBlock"] {gap:0}
    .st-key-hero [data-testid="stVerticalBlock"] {gap:0}
    </style>""", unsafe_allow_html=True)
    with st.container(key="hero"):                   # ต้องใช้ Streamlit 1.39 ขึ้นไป
        st.markdown(NAV_HTML, unsafe_allow_html=True)
        st.markdown('<div class="hero-title">Where will you go</div>', unsafe_allow_html=True)
        _, c, _ = st.columns([2, 1.3, 2])
        if c.button("Start Plan", use_container_width=True):
            ss.page = "planner"; st.rerun()
        st.markdown('<div class="hero-text">Plan your Bangkok trip with ease. Discover places to visit, '
                    'get AI-powered travel recommendations, find the best routes, and explore everything '
                    'you need for your journey — all in one place.</div>', unsafe_allow_html=True)
    st.stop()

# ---------- หน้าวางแผน: ธีมกระจกฝ้าสีเข้มบนรูปพื้นหลัง · ซ้าย = จุดแวะ/ปุ่ม/แผนที่ · ขวา = แชท + รายละเอียดสถานที่ ----------
st.markdown("""<style>
.stApp {background:linear-gradient(rgba(8,12,38,.30),rgba(8,12,38,.58)),var(--bgimg) center 35%/cover no-repeat fixed !important}
[data-testid="stAppViewContainer"], [data-testid="stMain"] {background:transparent !important}
.block-container, [data-testid="stMainBlockContainer"] {padding:14px 3% 1.2rem !important;max-width:100% !important}
[data-testid="stMain"] {scrollbar-gutter:stable both-edges}   /* จองที่แถบเลื่อนให้เท่ากันทั้งซ้ายขวา ขอบจะได้สมมาตร */

/* ตัวอักษรสีสว่างทั้งหน้า */
.stApp [data-testid="stMarkdownContainer"] *:not(a), .stApp label, .stApp label *, .stApp summary, .stApp summary *,
.stApp [data-testid="stCaptionContainer"] *, .stApp [data-testid="stWidgetLabel"] * {color:#f3f6ff !important}
.stApp a {color:#9cc2ff}

/* แถบหัวเว็บ (ไม่มีเมนู) */
.topbar {background:rgba(30,40,85,.6);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
 border:1px solid rgba(255,255,255,.16);border-radius:30px;padding:6px 24px;margin:0 0 10px;
 display:flex;align-items:center;gap:12px;box-shadow:0 8px 30px rgba(0,0,0,.3)}
.topbar .logo-img {height:38px;width:auto;display:block;border-radius:10px}
.topbar .t1 {font-size:20px;font-weight:700;letter-spacing:1px;line-height:1.2;font-family:'Hack',monospace !important}

/* การ์ดซ้าย / แผงขวา */
.st-key-leftcard, .st-key-rightpanel {background:rgba(30,40,85,.55);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
 border:1px solid rgba(255,255,255,.18);border-radius:40px;box-shadow:0 10px 40px rgba(0,0,0,.35)}
.st-key-leftcard {padding:22px 26px}
.st-key-rightpanel {padding:0 0 18px;overflow:hidden}
.st-key-rightbody {padding:8px 24px 0}
.panel-head {display:flex;justify-content:space-between;align-items:center;padding:10px 24px;font-size:18px;font-weight:700;
 border-bottom:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.04)}
.panel-head .ph-title {display:flex;align-items:center;gap:12px;font-family:'Hack',monospace !important;letter-spacing:1px}
.panel-head .ph-logo {height:34px;width:auto;border-radius:8px}
.panel-head .plane {font-size:24px;opacity:.9}

/* ปุ่ม */
.stButton>button {background:rgba(255,255,255,.10);color:#fff;border:1px solid rgba(255,255,255,.32);border-radius:40px;
 height:50px;font-weight:700;backdrop-filter:blur(6px)}
.stButton>button:hover {background:rgba(255,255,255,.22);border-color:#fff;color:#fff}
.stButton>button[kind="primary"], [data-testid="stBaseButton-primary"] {background:linear-gradient(90deg,#5a7be6,#7a95f2) !important;
 border:none !important;color:#fff !important}

/* ปุ่มรอง (เช่น "ให้ Gemini จัดลำดับจุด", "ทดสอบเรียก ...") ให้เป็นสีน้ำเงินม่วง ตัวอักษรขาวอ่านชัด */
.stApp [data-testid="stBaseButton-secondary"] {background:rgba(70,95,200,.60) !important;
 border:1px solid rgba(255,255,255,.45) !important;color:#fff !important}
.stApp [data-testid="stBaseButton-secondary"] * {color:#fff !important}
.stApp [data-testid="stBaseButton-secondary"]:hover {background:rgba(95,125,235,.85) !important;border-color:#fff !important}

/* ช่องกรอก / เลือก */
.stTextArea [data-baseweb="textarea"], .stTextArea [data-baseweb="base-input"] {background:transparent !important;border-radius:20px !important}
.stTextArea textarea {background:rgba(255,255,255,.07) !important;color:#fff !important;border:1.5px solid rgba(255,255,255,.45) !important;border-radius:20px !important}
.stTextArea textarea::placeholder, [data-testid="stChatInput"] textarea::placeholder {color:rgba(255,255,255,.55) !important}
[data-baseweb="select"] > div {background:rgba(255,255,255,.09) !important;border:1px solid rgba(255,255,255,.35) !important;border-radius:16px !important}
[data-baseweb="select"] * {color:#fff !important}
[data-baseweb="select"] svg {fill:#fff !important}
[data-testid="stChatInput"], [data-testid="stChatInput"] > div, [data-testid="stChatInput"] textarea {background:transparent !important;color:#fff !important}
[data-testid="stChatInput"] {border:1px solid rgba(255,255,255,.35) !important;border-radius:28px !important;background:rgba(255,255,255,.08) !important}
[data-testid="stChatInput"] button svg {fill:#fff}

/* expander / กล่องข้อความ / กล่องแชท */
[data-testid="stExpander"] {background:rgba(255,255,255,.07) !important;border:1px solid rgba(255,255,255,.25) !important;border-radius:26px !important}
[data-testid="stExpander"] details {background:transparent !important;border:none !important}
.stApp [data-testid="stExpander"] summary {background:rgba(40,55,120,.60) !important;border-radius:26px}
.stApp [data-testid="stExpander"] summary:hover {background:rgba(55,75,160,.75) !important}
.stApp .stTextArea [data-baseweb="textarea"], .stApp .stTextArea [data-baseweb="base-input"],
.stApp .stTextArea textarea {background:rgba(20,30,80,.55) !important}
[data-testid="stAlert"] {background:rgba(255,255,255,.08) !important;border:1px solid rgba(255,255,255,.25) !important;border-radius:22px !important}
.st-key-rightbody [data-testid="stVerticalBlockBorderWrapper"] {border:1px solid rgba(255,255,255,.25) !important;border-radius:22px !important;background:rgba(255,255,255,.04)}
[data-testid="stChatMessage"] {background:transparent !important}

/* แถบข้อมูลเส้นทาง + แบนเนอร์จุดหมาย */
.info-bar {display:flex;flex-wrap:wrap;gap:6px 14px;font-size:15px;margin:0 0 12px;align-items:center}
.info-bar b {color:#9cc2ff !important}
.info-bar .sep {opacity:.5}
.banner {display:flex;gap:14px;align-items:center;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.22);
 border-radius:24px;padding:14px 20px;margin-bottom:14px}
.banner .bn-logo {height:62px;width:auto;border-radius:10px}
.banner .bn-t {font-size:19px;font-weight:800;line-height:1.3}
.banner .bn-s {font-size:14px;opacity:.88;margin:2px 0}
.banner a {font-size:14px;font-weight:700;color:#9cc2ff;text-decoration:none}

/* รายละเอียดสถานที่ (ขวา) */
.pd-hero {display:grid;grid-template-columns:42% 1fr;gap:18px;margin:8px 0 14px}
.pd-hero img {width:100%;height:215px;object-fit:cover;border-radius:18px}
.pd-name {font-size:22px;font-weight:800;line-height:1.3;margin-bottom:6px}
.pd-tags {margin-bottom:8px}
.pd-tags span {display:inline-block;background:rgba(255,255,255,.15);border-radius:20px;padding:2px 12px;font-size:13px;margin:0 6px 4px 0}
.pd-desc {font-size:14px;opacity:.9;line-height:1.55;margin-bottom:10px}
.pd-btns {display:flex;gap:8px;flex-wrap:wrap}
.pd-btn {border:1px solid rgba(255,255,255,.5);color:#fff !important;border-radius:30px;padding:6px 15px;font-weight:700;
 text-decoration:none !important;font-size:14px;background:rgba(255,255,255,.10)}
.pd-btn.pri {background:linear-gradient(90deg,#5a7be6,#7a95f2);border-color:transparent}
.pd-sec {font-weight:800;margin:14px 0 8px;font-size:16px;border-top:1px solid rgba(255,255,255,.18);padding-top:12px}
.pd-grid {display:grid;gap:10px}
.pd-grid.g3 {grid-template-columns:repeat(3,1fr)}
.pd-grid.g4 {grid-template-columns:repeat(4,1fr)}
.pd-grid figure {margin:0}
.pd-grid img {width:100%;height:105px;object-fit:cover;border-radius:14px;display:block}
.pd-grid figcaption {font-size:12px;opacity:.9;margin-top:4px;text-align:center;line-height:1.3}
.pd-foot {background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.2);border-radius:18px;padding:11px 16px;margin-top:14px;font-size:14px;line-height:1.5}
</style>""", unsafe_allow_html=True)


# ---------- ข้อมูลสถานที่จาก Wikipedia (ไม่ต้องใช้คีย์เพิ่ม) ----------
@st.cache_resource
def _wiki_sum_cache():
    return {}


def wiki_summary(lang, title):
    """คำอธิบายสั้นของบทความ Wikipedia -> {"desc":..., "extract":...} (แคช 1 ชั่วโมง ถ้าดึงไม่ได้คืน {})"""
    cache, k = _wiki_sum_cache(), (lang, title)
    hit = cache.get(k)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    out = {}
    try:
        r = requests.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}",
                         headers=WIKI_HEADERS, timeout=(4, 8))
        if r.ok:
            j = r.json()
            out = {"desc": j.get("description") or "", "extract": j.get("extract") or ""}
    except Exception as e:
        print(f"[wiki-summary] {e}", flush=True)
    cache[k] = (time.time(), out)
    return out


def trim(t, n=150):
    t = thai_fix((t or "").strip())
    return t if len(t) <= n else t[:n] + "…"


def gal_lang(g):
    try:
        return g["url"].split("//")[1].split(".")[0]
    except Exception:
        return "th"


def render_info_bar():
    """แถบ จุดเริ่มต้น | จุดหมาย | ระยะทางโดยประมาณ (ระยะทางขับรถรวมทุกช่วง)"""
    if not ss.legs:
        return
    km = sum(l["km"] for l in ss.legs)
    st.markdown(f'<div class="info-bar">📍 จุดเริ่มต้น: <b>{esc(ss.legs[0]["o"])}</b><span class="sep">|</span>'
                f'จุดหมาย: <b>{esc(ss.legs[-1]["d"])}</b><span class="sep">|</span>'
                f'ระยะทางโดยประมาณ: <b>{km:.1f} กม.</b></div>', unsafe_allow_html=True)


def render_dest_banner():
    """แบนเนอร์จุดหมายปลายทาง ใช้ข้อมูลที่แชทดึงไว้แล้ว ไม่เรียกเครือข่ายเพิ่มนอกจากคำอธิบายสั้น"""
    if not ss.legs:
        return
    dest = ss.legs[-1]["d"]
    hit = _wiki_cache().get(dest)
    g = hit[1] if hit else None
    title, sub, link = dest, "จุดหมายปลายทางของคุณ", ""
    if g:
        sm = wiki_summary(gal_lang(g), g["title"])
        title = g["title"]
        sub = trim(sm.get("desc") or sm.get("extract"), 110) or sub
        link = f'<a href="{esc(g["url"])}" target="_blank">ดูบน Wikipedia →</a>'
    st.markdown(f'<div class="banner"><img class="bn-logo" src="data:image/png;base64,{LOGO_B64}"><div><div class="bn-t">{esc(title)}</div>'
                f'<div class="bn-s">{esc(sub)}</div>{link}</div></div>', unsafe_allow_html=True)


def render_place_detail():
    """มุมมอง "รายละเอียดสถานที่" ของจุดที่เลือก: รูปหลัก คำอธิบาย ปุ่ม แกลเลอรี และสถานที่ในทริปใกล้เคียง"""
    names = list(dict.fromkeys([m["name"] for m in ss.markers] or
                               [x.strip() for x in ss.stops_text.splitlines() if x.strip()][:MAX_STOPS]))
    if not names:
        st.info("วางแผนเส้นทางก่อน แล้วรายละเอียดของสถานที่แต่ละจุดจะแสดงตรงนี้")
        return
    if ss.get("sel_place") not in names:
        ss.pop("sel_place", None)
    sel = st.selectbox("📍 เลือกสถานที่", names, index=len(names) - 1, key="sel_place")
    gm = "https://www.google.com/maps/search/?api=1&query=" + quote(with_bkk(sel))
    with st.spinner("กำลังดึงข้อมูลสถานที่..."):
        gal = {g["name"]: g for g in fetch_place_images(names)}
    g = gal.get(sel)
    if not g:
        st.markdown(f'<div class="pd-foot">ไม่พบข้อมูลหรือรูปของ <b>{esc(sel)}</b> ใน Wikipedia<br><br>'
                    f'<a class="pd-btn pri" href="{esc(gm)}" target="_blank">📍 ดูบน Google Maps</a></div>',
                    unsafe_allow_html=True)
        return
    sm = wiki_summary(gal_lang(g), g["title"])
    imgs = g["images"]
    tags = "".join(f"<span>{esc(t)}</span>" for t in (sm.get("desc"),) if t)
    h = (f'<div class="pd-hero"><img src="{esc(imgs[0]["thumb"])}"><div>'
         f'<div class="pd-name">{esc(g["title"])}</div><div class="pd-tags">{tags}</div>'
         f'<div class="pd-desc">{esc(trim(sm.get("extract"), 220))}</div>'
         f'<div class="pd-btns"><a class="pd-btn pri" href="{esc(gm)}" target="_blank">📍 ดูบน Google Maps</a>'
         f'<a class="pd-btn" href="{esc(g["url"])}" target="_blank">ℹ️ ดูรายละเอียด</a></div></div></div>')
    if len(imgs) > 1:
        h += '<div class="pd-sec">📷 ภาพบรรยากาศ</div><div class="pd-grid g3">' + "".join(
            f'<figure><img src="{esc(i["thumb"])}"></figure>' for i in imgs[1:4]) + "</div>"
    others = [gal[n] for n in names if n != sel and n in gal][:4]
    if others:
        h += '<div class="pd-sec">🧭 สถานที่ในเส้นทางเดียวกัน</div><div class="pd-grid g4">' + "".join(
            f'<figure><img src="{esc(o["images"][0]["thumb"])}"><figcaption>{esc(o["name"])}</figcaption></figure>'
            for o in others) + "</div>"
    rest = [n for n in names if n != sel]
    if rest:
        h += f'<div class="pd-foot">🔗 เชื่อมต่อสถานที่ท่องเที่ยวในแผนเดียวกัน เช่น {esc(" · ".join(rest[:4]))}</div>'
    st.markdown(h, unsafe_allow_html=True)


VIEW_CHAT, VIEW_PLACE = "💬 แชท", "📍 รายละเอียดสถานที่"
ss.setdefault("view", VIEW_CHAT)

if CHAT_ON_RIGHT:
    map_col, chat_col = st.columns([1.05, 1], gap="medium")
else:
    chat_col, map_col = st.columns([1, 1.05], gap="medium")

# หมายเหตุ: ต้องวาดฝั่งแชทก่อนฝั่งซ้าย เพราะการตอบแชทอาจแก้ ss.stops_text / ss.legs ก่อนที่ช่อง "จุดแวะ" และแผนที่จะถูกสร้าง
with chat_col:
    with st.container(key="rightpanel"):
        st.markdown(f'<div class="panel-head"><span class="ph-title"><img class="ph-logo" src="data:image/png;base64,{LOGO_B64}">{APP_TITLE}</span><span class="plane">✈️</span></div>',
                    unsafe_allow_html=True)
        with st.container(key="rightbody"):
            view = st.radio("มุมมอง", [VIEW_CHAT, VIEW_PLACE], horizontal=True, key="view", label_visibility="collapsed")
            if view == VIEW_CHAT:
                box = st.container(height=CHAT_H)
                for m in ss.msgs:
                    with box.chat_message(m["role"]):
                        st.markdown(thai_fix(m["content"]))
                        if m.get("images"):          # รูปสถานที่จาก Wikipedia
                            render_images(m["images"])

                if q := st.chat_input("เช่น จากสยามไปวัดโพธิ์ แล้วไปวัดอรุณ · โซนวัดพระแก้ว 5 ที่ แนะนำคาเฟ่ · ควรลงสถานีไหน"):
                    ss.msgs.append({"role": "user", "content": q})
                    with st.spinner("กำลังคิดและค้นหาเส้นทาง..."):
                        ss.fresh_places = []
                        ans = handle_message(q)
                        ss.msgs.append(new_reply(ans))
                    st.rerun()
            else:
                render_place_detail()

with map_col:
    with st.container(key="leftcard"):
        if not (KEY and GKEY):   # แสดงเฉพาะตอนอ่านคีย์จาก .env ไม่เจอ
            st.warning(f"อ่านคีย์จากไฟล์ .env ไม่ครบ ({ENV_PATH} → {'พบไฟล์' if ENV_PATH.exists() else 'ไม่พบไฟล์'}) "
                       "ตรวจชื่อตัวแปร GOOGLE_MAPS_API_KEY และ LONGDO_API_KEY แล้วรันใหม่")
        render_info_bar()
        render_dest_banner()
        with st.expander("✏️ จุดแวะ (บรรทัดละ 1 ที่ · บรรทัดแรก = จุดเริ่มต้น · สูงสุด 8 จุด)", expanded=not ss.legs):
            st.text_area("📍 จุดแวะ", key="stops_text", height=100, label_visibility="collapsed",
                         placeholder="สยาม\nวัดโพธิ์\nวัดอรุณ\nเยาวราช")
        b1, b2 = st.columns(2)
        if b1.button("🧭 แสดงเส้นทาง", type="primary", use_container_width=True):
            stops = [x.strip() for x in ss.stops_text.splitlines() if x.strip()]
            with st.spinner("กำลังค้นหาเส้นทางและราคา..."):
                ss.msgs.append(new_reply(plan_trip(stops)))
            st.rerun()
        b2.button("✨ ให้ Gemini จัดลำดับจุด", use_container_width=True, on_click=reorder_cb,
                  help="ให้ Gemini ช่วยวางแผนว่าควรไปที่ไหนก่อน-หลัง (จุดแรกคือต้นทางเสมอ) พร้อมเวลาแนะนำ แล้วคำนวณเส้นทางให้เลย")

        s1, s2 = st.columns(2)                       # แผงสถานะ 2 อันวางข้างกัน ประหยัดที่แนวตั้ง
        with s1:
            with st.expander("🔧 สถานะ Gemini", expanded=not GEMINI_KEY):
                if GEMINI_KEY:
                    st.write(f"✅ พบคีย์จากตัวแปร `{GEMINI_VAR_USED}` (ลงท้ายด้วย ...{GEMINI_KEY[-4:]}) · "
                             f"รุ่น (ลองตามลำดับ): {', '.join(f'`{m}`' for m in GEMINI_MODELS)}")
                    if st.button("ทดสอบเรียก Gemini"):
                        try:
                            r = gemini_try(lambda m: gh.call_json(GEMINI_KEY, m, 'ตอบ JSON อย่างเดียว', 'ตอบ {"ok": true}'))
                            st.success(f"เรียก Gemini สำเร็จ: {r}")
                        except Exception as e:
                            st.error(f"เรียก Gemini ไม่สำเร็จ: {e}")
                else:
                    st.write(f"❌ ไม่พบคีย์ Gemini ในไฟล์ `{ENV_PATH}` ({'พบไฟล์' if ENV_PATH.exists() else 'ไม่พบไฟล์'})")
                    st.write("ตั้งชื่อตัวแปรเป็นอย่างใดอย่างหนึ่ง: " + ", ".join(f"`{n}`" for n in GEMINI_VARS)
                             + " เขียนเป็น `GEMINI_API_KEY=คีย์` (ไม่มีช่องว่างรอบ =) แล้ว **หยุดและรัน Streamlit ใหม่**")
        with s2:
            with st.expander("🔧 สถานะ Google Routes", expanded=not GKEY):
                if GKEY:
                    st.write(f"✅ พบ GOOGLE_MAPS_API_KEY (ลงท้ายด้วย ...{GKEY[-4:]})")
                    if st.button("ทดสอบเรียก Google Routes"):
                        t0 = time.time()
                        r = _g_route("สยาม", "วัดโพธิ์", "DRIVE", GKEY)
                        dt = time.time() - t0
                        if isinstance(r, dict) and "error" in r:
                            st.error(f"ไม่สำเร็จ (ใช้ {dt:.1f} วินาที): {r['error']}")
                        elif r is None:
                            st.warning(f"เรียกได้แต่ไม่พบเส้นทาง (ใช้ {dt:.1f} วินาที)")
                        else:
                            st.success(f"สำเร็จใน {dt:.1f} วินาที · {r['km']:.1f} กม.")
                else:
                    st.write("❌ ไม่พบ GOOGLE_MAPS_API_KEY ใน .env")

        if ss.legs:
            show_map()
            if ss.debug:
                with st.expander("🔧 ข้อมูลดิบเส้นทางรถไฟฟ้าจาก Google (ไว้ตรวจสอบ)"):
                    st.json(ss.debug, expanded=False)
        else:
            st.info("พิมพ์หลายสถานที่ แล้วแผนที่เส้นทางจะแสดงตรงนี้")