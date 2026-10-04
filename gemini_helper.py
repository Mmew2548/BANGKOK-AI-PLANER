"""ตัวช่วยเรียก Gemini (REST) -- ไม่ต้องลงไลบรารีเพิ่ม ใช้ requests ที่มีอยู่แล้ว
ขอคีย์ฟรีที่ https://aistudio.google.com/apikey แล้วใส่ GEMINI_API_KEY ในไฟล์ .env
(เลือกรุ่นเองได้ด้วย GEMINI_MODEL ถ้าไม่ใส่ใช้ gemini-3.5-flash แล้วสำรองด้วย gemini-3.5-flash-lite ฯลฯ
 ชื่อรุ่นล่าสุดดูที่ https://ai.google.dev/gemini-api/docs/models)"""
import json
import re
import time
import requests

DEFAULT_MODEL = "gemini-3.5-flash"

ROUTER_SYSTEM = """คุณคือผู้ช่วยวางแผนเดินทางในกรุงเทพฯ (รถเมล์, รถไฟไทย รฟท., รถไฟฟ้า BTS/MRT/ARL/สายสีแดง/สายสีเหลือง/สายสีทอง, วิน, แท็กซี่)
ผู้ใช้จะพิมพ์ข้อความเข้ามา พร้อม "แผนปัจจุบัน" ที่ระบบคำนวณจาก Google Maps แล้ว
ตอบกลับเป็น JSON อย่างเดียว ตามรูปแบบนี้:
{"intent": "plan" หรือ "chat", "stops": [..], "reorder": true/false, "fixed_start": true/false, "answer": "..."}

กติกา
- intent="plan": ผู้ใช้ต้องการให้วางแผน/หาเส้นทางไปหลายจุด
  * stops = ชื่อสถานที่ตามลำดับที่ผู้ใช้บอก ใช้ชื่อที่คนทั่วไปเรียกและค้นหาใน Google Maps ได้ (เช่น "วัดอรุณ" "วัดโพธิ์" ไม่ต้องขยายเป็นชื่อทางการเต็มยาวๆ)
    (แก้คำพิมพ์/คำย่อ เช่น "โรงบาลราชวิถี" -> "โรงพยาบาลราชวิถี" ไม่ต้องใส่คำว่ากรุงเทพ) ตัดคำพูดอื่นออก เช่น "ฉันจะไป", "ควรไปไหนก่อนดี"
  * ถ้าผู้ใช้ให้เพียงปลายทางเดียวต่อจากแผนเดิม ให้ใส่ stops เป็น [จุดสุดท้ายของแผนเดิม, จุดใหม่]
  * reorder=true เมื่อผู้ใช้ขอให้ช่วยจัดลำดับ/ไม่สนลำดับ/ถามว่าควรไปที่ไหนก่อน-หลัง ไม่เช่นนั้น false
  * fixed_start=true เฉพาะเมื่อผู้ใช้ระบุชัดว่าเริ่มต้นจากที่ไหน (เช่น "จากสยามไป...", "ผมอยู่ที่...")
    ถ้าผู้ใช้แค่ลิสต์สถานที่ที่จะไปแล้วถามว่าไปไหนก่อน ให้ fixed_start=false (ทุกจุดสลับลำดับได้)
  * answer ปล่อยเป็น ""
- intent="chat": คำถามทั่วไป เช่น ควรลงสถานีไหน ใกล้ที่หมายที่สุด/ต่อรถอย่างไร/เปรียบเทียบวิธีเดินทาง
  * ตอบใน answer เป็น Markdown ภาษาไทย กระชับ ตรงคำถาม
  * อ้างอิงแผนปัจจุบันก่อน (สถานีที่ขึ้น/ลง ราคา เวลา) ราคาให้ใช้ตามแผนเท่านั้น ห้ามแต่งตัวเลขเอง
  * แผนแต่ละช่วงอาจมีทั้งเส้นทางหลักและ "ทางเลือกรถไฟ/รถไฟฟ้า (ไม่ใช้รถเมล์)" ถ้าถามเปรียบเทียบให้เทียบราคา เวลา และสถานีขึ้น-ลงของทั้งสองแบบ
  * ราคาที่มี ✨ คือราคาที่ Gemini ประมาณ ส่วนราคารถไฟไทย (รฟท.) ที่ระบุว่า "คำนวณตามระยะทาง" เป็นราคาประมาณชั้น 3 ธรรมดา ไม่รวมค่าธรรมเนียมรถเร็ว/รถด่วน ให้บอกผู้ใช้ว่าเป็นราคาประมาณเสมอ
  * ถ้าเป็นความรู้ทั่วไปที่ไม่แน่ใจ (ทางออก เวลาเปิด-ปิด) ให้บอกว่าไม่แน่ใจ และแนะนำให้เช็กใน Google Maps
  * stops=[] reorder=false
ห้ามมีข้อความอื่นนอกจาก JSON"""

ORDER_SYSTEM = """คุณคือผู้ช่วยวางแผนเที่ยวในกรุงเทพฯ ผู้ใช้จะส่งรายการสถานที่ที่มีหมายเลขกำกับ
ให้จัดลำดับการไปให้เดินทางสะดวกที่สุด โดยพิจารณา
- ที่ตั้งและระยะทางระหว่างจุด ไม่ให้ต้องเดินทางย้อนไปมา และแนวรถไฟฟ้า
- ช่วงเวลาที่เหมาะสม (วัด/สถานที่กลางแจ้งควรไปตอนเช้า ห้าง ตลาดกลางคืน ร้านอาหารค่ำไปทีหลัง) และเวลาเปิด-ปิดโดยทั่วไป
สมมติว่าเริ่มเดินทางประมาณ 09:00 ถ้าผู้ใช้ไม่ได้ระบุเวลา
{START_RULE}
ตอบ JSON อย่างเดียว ใช้ "หมายเลข" ตามที่ผู้ใช้ส่งมา ไม่ต้องพิมพ์ชื่อสถานที่:
{"order": [หมายเลขตามลำดับใหม่ ต้องครบทุกหมายเลข ไม่ซ้ำ],
 "reason": "เหตุผลสั้นๆ 1-3 ประโยค",
 "schedule": [{"n": หมายเลข, "time": "เวลาที่ควรไปถึงโดยประมาณ เช่น 09:00", "stay": "เวลาที่ควรใช้ เช่น 1.5 ชม.", "note": "เคล็ดลับสั้นๆ"}]}"""


def _clean_json(txt):
    txt = (txt or "").strip()
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt, flags=re.I)
    return json.loads(txt)


# รุ่นสำรอง: จะถูกต่อท้ายรุ่นที่ตั้งใน GEMINI_MODEL เสมอ ถ้ารุ่นไหนไม่พบ/เลิกให้บริการ/คนใช้เยอะ จะลองรุ่นถัดไปให้เอง
# (เพิ่มเองได้ที่ .env: GEMINI_FALLBACK_MODELS=รุ่น1,รุ่น2)
FALLBACK_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
RETRY_CODES = {429, 500, 502, 503, 504}
_DEAD = set()   # รุ่นที่ Google ตอบว่าไม่พบ/เลิกให้บริการ จำไว้ตลอดที่แอปรันอยู่ จะได้ไม่ลองซ้ำทุกครั้ง


def _fallbacks():
    import os
    extra = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()]
    return extra or FALLBACK_MODELS


def _is_model_gone(code, msg):
    """ข้อผิดพลาดที่แปลว่า 'รุ่นนี้ใช้ไม่ได้' (ไม่ใช่แค่ไม่ว่าง) -> ข้ามไปรุ่นถัดไป"""
    m = (msg or "").lower()
    return (code == 404 or "no longer available" in m or "is not found" in m
            or "not supported for generatecontent" in m or (code == 400 and "model" in m))


def call_json(key, model, system, prompt, timeout=None, max_total=None, parts=None, tools=None):
    """เรียก Gemini ให้ตอบเป็น JSON คืน dict
    - ลองรุ่นตามลำดับ: รุ่นใน GEMINI_MODEL (คั่นด้วยจุลภาคได้หลายรุ่น) แล้วต่อด้วยรุ่นสำรองเสมอ
    - ถ้ารุ่นไม่ว่าง (503/429/500) ลองซ้ำพร้อมหน่วงเวลา แล้วสลับไปรุ่นถัดไป
    - ถ้ารุ่นไม่พบ/เลิกให้บริการ ข้ามทันทีและจำไว้
    - ใช้เวลารวมไม่เกิน max_total วินาที ถ้ายังไม่ได้ raise Exception ข้อความอ่านง่าย"""
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts or [{"text": prompt}]}],   # parts = ข้อความ+รูป (inline_data)
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}}
    if tools:                                          # เช่น [{"google_search": {}}] -> ตอบเป็นข้อความ + แหล่งอ้างอิงจริงจากเว็บ
        body["tools"] = tools
        body["generationConfig"].pop("responseMimeType", None)
    given = [m for m in re.split(r"[,\s]+", model or "") if m]
    models = []
    for m in (given or [DEFAULT_MODEL]) + _fallbacks():
        m = re.sub(r"^models/", "", m.strip().strip("\"'"))
        if re.fullmatch(r"[A-Za-z0-9._-]+", m) and m not in models:   # ข้ามชื่อรุ่นที่ผิดรูปแบบ
            models.append(m)
    if not models:
        models = [DEFAULT_MODEL]
    models = [m for m in models if m not in _DEAD] or models           # ถ้าตายหมดให้ลองใหม่ทั้งหมด
    slow = "pro" in models[0].lower()                # รุ่น Pro คิดนานกว่า ให้เวลามากขึ้น
    timeout = timeout or (40 if slow else 20)
    max_total = max_total or (90 if slow else 30)
    t_end = time.time() + max_total
    last = "ไม่ทราบสาเหตุ"
    gone = []
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
        for attempt in range(2):                               # รุ่นละ 2 ครั้ง แล้วสลับรุ่น (แต่ละรุ่นโควตาแยกกัน)
            if time.time() > t_end:
                raise RuntimeError(f"Gemini ไม่ว่างชั่วคราว ลองใหม่อีกครั้งในอีกสักครู่ ({last})")
            try:
                read_to = max(3, min(timeout, t_end - time.time()))
                resp = requests.post(url, json=body, headers={"x-goog-api-key": key}, timeout=(5, read_to))
                r = resp.json()
                code = resp.status_code
            except requests.exceptions.Timeout:
                last = "timeout (รุ่นนี้ตอบช้าเกินไป)"
                break                                          # ช้าเกิน -> สลับไปรุ่นถัดไปเลย
            except Exception as e:
                last, code, r = str(e), 500, {}
            if isinstance(r, dict) and "error" in r:
                err = r["error"]
                last = err.get("message", "Gemini error")
                code = err.get("code", code)
                if _is_model_gone(code, last):                # ไม่พบ/เลิกให้บริการ -> ข้ามไปรุ่นถัดไป
                    _DEAD.add(m)
                    gone.append(m)
                    break
                busy = code in RETRY_CODES or "high demand" in last.lower() or err.get("status") in ("UNAVAILABLE", "RESOURCE_EXHAUSTED")
                if busy:
                    if attempt == 0:
                        time.sleep(1.5)                        # หน่วงนิดเดียวแล้วลองซ้ำ ถ้ายังไม่ว่างก็สลับรุ่น
                    continue
                raise RuntimeError(last)                       # เช่น คีย์ไม่ถูกต้อง ลองซ้ำก็ไม่หาย
            if code in RETRY_CODES and not r:
                if attempt == 0:
                    time.sleep(1.5)
                continue
            try:
                cand = r["candidates"][0]
                text = "".join(p.get("text", "") for p in cand["content"]["parts"])
                if tools:
                    chunks = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
                    return {"text": text, "sources": [c["web"] for c in chunks if (c.get("web") or {}).get("uri")]}
                return _clean_json(text)
            except (KeyError, IndexError, ValueError, TypeError):
                last = "Gemini ตอบกลับในรูปแบบที่อ่านไม่ได้"
                break                                          # ลองรุ่นถัดไป
    if gone and len(gone) == len(models):
        raise RuntimeError("ไม่พบรุ่น Gemini ที่ใช้ได้เลย (ลองแล้ว: " + ", ".join(gone) + ") "
                           "ตรวจชื่อรุ่นที่ GEMINI_MODEL ใน .env ดูรุ่นล่าสุดที่ https://ai.google.dev/gemini-api/docs/models "
                           f"· สาเหตุล่าสุด: {last}")
    raise RuntimeError(f"Gemini ไม่ว่างชั่วคราว ลองใหม่อีกครั้งในอีกสักครู่ ({last})")


def validate_order(original, proposed, fixed_start=True):
    """(ใช้กับชื่อ) ยอมรับลำดับใหม่ก็ต่อเมื่อมีสถานที่ครบเท่าเดิมและต้นทางยังอยู่แรกสุด"""
    original = [s.strip() for s in original]
    proposed = [str(s).strip() for s in (proposed or [])]
    if (len(proposed) == len(original) and sorted(proposed) == sorted(original)
            and proposed and (not fixed_start or proposed[0] == original[0])):
        return proposed
    return None


def _valid_idx(n, order, fixed_start=True):
    """order = หมายเลข (เริ่มที่ 1) -> คืนลิสต์ดัชนีเริ่ม 0 ถ้าครบ/ไม่ซ้ำ/ต้นทางยังอยู่แรก ไม่งั้นคืน None"""
    try:
        idx = [int(str(x).strip().rstrip(".")) - 1 for x in (order or [])]
    except (ValueError, TypeError):
        return None
    if sorted(idx) != list(range(n)) or (fixed_start and idx[0] != 0):
        return None
    return idx


def suggest_order(key, model, stops, fixed_start=True):
    """คืน (ลำดับใหม่, ข้อความอธิบายแบบ Markdown) ถ้า Gemini ตอบไม่ถูกต้องจะคืนลำดับเดิม
    fixed_start=True: จุดแรกคือต้นทางที่ผู้ใช้ระบุ ห้ามย้าย / False: ทุกจุดสลับได้
    ใช้ "หมายเลข" ในการสื่อสารกับ Gemini ไม่ใช่ชื่อ จะได้ไม่พังเพราะสะกดต่างกันนิดเดียว"""
    rule = ("จุดที่ 1 คือต้นทาง ต้องอยู่ลำดับแรกเสมอ" if fixed_start else
            "ผู้ใช้ยังไม่ได้ระบุต้นทาง ทุกจุดสลับลำดับได้ ให้เลือกจุดเริ่มต้นที่ทำให้ทั้งทริปสะดวกที่สุด")
    r = call_json(key, model, ORDER_SYSTEM.replace("{START_RULE}", rule),
                  "สถานที่:\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(stops)))
    idx = _valid_idx(len(stops), r.get("order"), fixed_start)
    if idx is None:                                       # เผื่อ Gemini ตอบเป็นชื่อกลับมา
        names = validate_order(stops, r.get("order"), fixed_start)
        idx = [stops.index(s) for s in names] if names and len(set(names)) == len(names) else None
    if idx is None:
        return list(stops), "Gemini จัดลำดับมาไม่ครบหรือไม่ถูกต้อง จึงใช้ลำดับเดิม"
    new = [stops[i] for i in idx]
    why = str(r.get("reason", "")).strip()
    sched = {}
    for row in r.get("schedule") or []:
        try:
            sched[int(row.get("n")) - 1] = row
        except (ValueError, TypeError, AttributeError):
            pass
    lines = []
    for pos, i in enumerate(idx, 1):
        row = sched.get(i)
        if row:
            bits = [f"ถึงประมาณ {row['time']}" if row.get("time") else "",
                    f"ใช้เวลา ~{row['stay']}" if row.get("stay") else ""]
            extra = " · ".join(b for b in bits if b)
            note = f" — {row['note']}" if row.get("note") else ""
            lines.append(f"- **{pos}. {stops[i]}**" + (f" · {extra}" if extra else "") + note)
    if lines:
        why = (why + "\n\n" if why else "") + "🕘 **ตารางเวลาแนะนำ** (ประมาณการ ปรับตามจริงได้)\n" + "\n".join(lines)
    return new, why


def route_message(key, model, context, message):
    """แยกว่าข้อความเป็นการวางแผน (plan) หรือคำถาม (chat) และตอบคำถามถ้าเป็น chat"""
    r = call_json(key, model, ROUTER_SYSTEM, f"แผนปัจจุบัน:\n{context}\n\nข้อความผู้ใช้: {message}")
    intent = "chat" if r.get("intent") == "chat" else "plan"
    stops = [str(s).strip() for s in (r.get("stops") or []) if str(s).strip()]
    return {"intent": intent, "stops": stops, "reorder": bool(r.get("reorder")),
            "fixed_start": bool(r.get("fixed_start", True)),
            "answer": str(r.get("answer") or "").strip()}