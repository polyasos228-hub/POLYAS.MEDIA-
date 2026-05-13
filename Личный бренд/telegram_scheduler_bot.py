# -*- coding: utf-8 -*-
"""Polyas Media — Premium Telegram Scheduler Bot v3.1"""

import json, os, sys, time, threading, logging
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

BOT_TOKEN     = "8735655400:AAEtJYVdFFI7dTrqt_YreIRrDEdvVhYOKms"
CONFIG_FILE   = "bot_config.json"
QUEUE_FILE    = "post_queue.json"
STATE_FILE    = "user_state.json"
STATS_FILE    = "stats.json"
FIRED_FILE    = "fired_slots.json"
DEFAULT_TIMES = ["10:00", "15:00", "20:00"]

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s",
                    level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("polyas")
API = "https://api.telegram.org/bot" + BOT_TOKEN
MSK = timezone(timedelta(hours=3))

MONTHS_RU = ["", "янв", "фев", "мар", "апр", "май", "июн",
             "июл", "авг", "сен", "окт", "ноя", "дек"]
DAYS_RU   = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


# ── API ────────────────────────────────────────────────

def api(method, **kw):
    url  = API + "/" + method
    data = json.dumps(kw).encode("utf-8")
    req  = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        body = e.read().decode()[:300]
        log.error("HTTP %s %s: %s", e.code, method, body)
        return {"ok": False, "description": body}
    except URLError as e:
        log.error("URL %s: %s", method, e.reason)
        return {"ok": False, "description": str(e)}
    except Exception as e:
        log.error("API %s: %s", method, e)
        return {"ok": False, "description": str(e)}

def download_tg_file(file_id):
    r = api("getFile", file_id=file_id)
    if not r.get("ok"):
        return None
    path = r["result"]["file_path"]
    url  = "https://api.telegram.org/file/bot" + BOT_TOKEN + "/" + path
    try:
        with urlopen(url, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        log.error("download_tg_file: %s", e)
        return None

def kb(rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in r] for r in rows]}

def send(cid, text, buttons=None, mode="HTML"):
    kw = dict(chat_id=cid, text=text, parse_mode=mode)
    if buttons: kw["reply_markup"] = kb(buttons)
    return api("sendMessage", **kw)

def edit(cid, mid, text, buttons=None, mode="HTML"):
    kw = dict(chat_id=cid, message_id=mid, text=text, parse_mode=mode)
    if buttons: kw["reply_markup"] = kb(buttons)
    result = api("editMessageText", **kw)
    if not result.get("ok"):
        if "not modified" in result.get("description", "").lower():
            return result
        return send(cid, text, buttons, mode)
    return result

def answer(cb_id, text=""):
    api("answerCallbackQuery", callback_query_id=cb_id, text=text)

def _fmt(post, is_caption=False):
    """Use stored entities (preserves premium emoji), else parse_mode HTML."""
    entities = post.get("entities")
    if entities:
        return {"caption_entities" if is_caption else "entities": entities}
    return {"parse_mode": "HTML"}

def publish_post(channel, post):
    text       = post.get("text", "")
    media_type = post.get("media_type")
    file_id    = post.get("file_id")
    if media_type == "photo":
        return api("sendPhoto",    chat_id=channel, photo=file_id,    caption=text, **_fmt(post, True))
    elif media_type == "video":
        return api("sendVideo",    chat_id=channel, video=file_id,    caption=text, **_fmt(post, True))
    elif media_type == "animation":
        return api("sendAnimation",chat_id=channel, animation=file_id,caption=text, **_fmt(post, True))
    elif media_type == "document":
        return api("sendDocument", chat_id=channel, document=file_id, caption=text, **_fmt(post, True))
    else:
        if not text:
            return {"ok": False, "description": "empty post"}
        return api("sendMessage", chat_id=channel, text=text, **_fmt(post))

def send_media_preview(cid, post):
    text       = post.get("text", "")
    media_type = post.get("media_type")
    file_id    = post.get("file_id")
    kw = {"chat_id": cid}
    if media_type == "photo":
        kw.update(photo=file_id,     caption=text, **_fmt(post, True)); return api("sendPhoto",     **kw)
    elif media_type == "video":
        kw.update(video=file_id,     caption=text, **_fmt(post, True)); return api("sendVideo",     **kw)
    elif media_type == "animation":
        kw.update(animation=file_id, caption=text, **_fmt(post, True)); return api("sendAnimation", **kw)
    elif media_type == "document":
        kw.update(document=file_id,  caption=text, **_fmt(post, True)); return api("sendDocument",  **kw)
    return {"ok": False}


# ── DATA ───────────────────────────────────────────────

def load_cfg():
    if os.path.exists(CONFIG_FILE):
        try: return json.load(open(CONFIG_FILE, encoding="utf-8"))
        except Exception as e: log.error("load_cfg: %s", e)
    return {"admin_id": None, "channel_id": None, "post_times": list(DEFAULT_TIMES)}

def save_cfg(c):
    try: json.dump(c, open(CONFIG_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception as e: log.error("save_cfg: %s", e)

def load_q():
    if os.path.exists(QUEUE_FILE):
        try: return json.load(open(QUEUE_FILE, encoding="utf-8"))
        except Exception as e: log.error("load_q: %s", e)
    return []

def save_q(q):
    try: json.dump(q, open(QUEUE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception as e: log.error("save_q: %s", e)

def load_states():
    if os.path.exists(STATE_FILE):
        try: return json.load(open(STATE_FILE, encoding="utf-8"))
        except Exception as e: log.error("load_states: %s", e)
    return {}

def save_states(s):
    try: json.dump(s, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception as e: log.error("save_states: %s", e)

def get_state(uid):
    return load_states().get(str(uid), {"state": "idle", "draft": None})

def set_state(uid, state, draft=None):
    s = load_states(); s[str(uid)] = {"state": state, "draft": draft}; save_states(s)

def load_stats():
    if os.path.exists(STATS_FILE):
        try: return json.load(open(STATS_FILE, encoding="utf-8"))
        except Exception as e: log.error("load_stats: %s", e)
    return {"total": 0, "posts": []}

def log_stat(post, slot):
    stats = load_stats()
    stats["total"] = stats.get("total", 0) + 1
    stats.setdefault("posts", []).append({
        "time": datetime.now(MSK).isoformat(), "slot": slot,
        "media_type": post.get("media_type"), "text_len": len(post.get("text", "")),
    })
    if len(stats["posts"]) > 500: stats["posts"] = stats["posts"][-500:]
    try: json.dump(stats, open(STATS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception as e: log.error("log_stat: %s", e)

def load_fired():
    if os.path.exists(FIRED_FILE):
        try: return json.load(open(FIRED_FILE, encoding="utf-8"))
        except Exception: pass
    return {}

def save_fired(d):
    try: json.dump(d, open(FIRED_FILE, "w", encoding="utf-8"), indent=2)
    except Exception as e: log.error("save_fired: %s", e)


# ── HELPERS ────────────────────────────────────────────

def _posts_word(n):
    if n % 10 == 1 and n % 100 != 11:          return "пост"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14): return "поста"
    return "постов"

def next_slot(cfg):
    times = sorted(cfg.get("post_times", DEFAULT_TIMES))
    now   = datetime.now(MSK)
    cur   = now.hour * 60 + now.minute
    for t in times:
        h, m = map(int, t.split(":"))
        if h * 60 + m > cur: return "сегодня в " + t + " МСК"
    return "завтра в " + times[0] + " МСК"

def clean_channel(raw):
    ch = raw.strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if prefix in ch:
            ch = ch.split(prefix)[-1].split("/")[0].split("?")[0]; break
    ch = ch.lstrip("@").strip()
    return ("@" + ch) if ch else None

def is_media_draft(draft):
    return isinstance(draft, dict) and draft.get("media_type")

def is_dated_state(draft):
    """Draft is a date-picking wrapper: {"_draft": ..., "_date": ...}"""
    return isinstance(draft, dict) and "_draft" in draft

def draft_preview(draft):
    if is_dated_state(draft):
        draft = draft.get("_draft")
    text = draft.get("text", "") if isinstance(draft, dict) else (draft or "")
    s = text[:60].replace("\n", " ")
    return s + ("..." if len(text) > 60 else "")

def make_post(draft, scheduled_at=None):
    now = datetime.now(MSK).isoformat()
    if is_dated_state(draft):
        draft = draft.get("_draft")
    if isinstance(draft, dict) and "media_type" in draft:
        return {"text": draft.get("text", ""), "media_type": draft.get("media_type"),
                "file_id": draft.get("file_id"), "entities": draft.get("entities"),
                "added_at": now, "scheduled_at": scheduled_at}
    text     = draft if isinstance(draft, str) else draft.get("text", "")
    entities = None  if isinstance(draft, str) else draft.get("entities")
    return {"text": text, "media_type": None, "file_id": None, "entities": entities,
            "added_at": now, "scheduled_at": scheduled_at}

def format_scheduled(sa):
    """Human-readable scheduled_at: '2026-05-20 15:00' → '20 мая в 15:00'."""
    if not sa: return ""
    if " " in sa:  # datetime
        try:
            dt = datetime.strptime(sa, "%Y-%m-%d %H:%M")
            return dt.strftime("%d ") + MONTHS_RU[dt.month] + dt.strftime(" в %H:%M")
        except Exception:
            return sa
    return sa + " МСК"  # plain time slot

def parse_import_txt(text):
    return [p.strip() for p in text.split("\n---\n") if p.strip()]


# ── KEYBOARDS ──────────────────────────────────────────

def main_menu_kb(q_count):
    return [
        [("📝  Новый пост", "pn"), ("📤  Импорт .txt", "pi")],
        [("📋  Очередь (" + str(q_count) + ")", "qv_0"), ("📊  Статус", "st")],
        [("🕐  Расписание", "sv"), ("⚙️  Настройки", "cfg")],
    ]

def draft_kb(is_media=False):
    label = "✏️  Ред. подпись" if is_media else "✏️  Редактировать"
    return [
        [("🚀  Опубликовать сейчас", "p_now")],
        [("📥  В очередь", "p_q"), ("📅  На конкретную дату", "p_date")],
        [(label, "p_edit"), ("❌  Отмена", "pc")],
    ]

def date_picker_kb():
    """28-day calendar grid."""
    now  = datetime.now(MSK)
    rows, row = [], []
    for delta in range(28):
        d     = now + timedelta(days=delta)
        dow   = DAYS_RU[d.weekday()]
        if delta == 0:
            label = "Сегодня " + d.strftime("%d.%m")
        elif delta == 1:
            label = "Завтра " + d.strftime("%d.%m")
        else:
            label = d.strftime("%d.%m") + " " + dow
        row.append((label, "pd_" + d.strftime("%Y-%m-%d")))
        if len(row) == 3: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([("◀️  Назад", "pc")])
    return rows

def dated_time_picker_kb():
    """Hourly time picker for specific-date scheduling."""
    slots = ["%02d:00" % h for h in range(7, 24)]
    rows, row = [], []
    for t in slots:
        row.append((t, "pdt_" + t))
        if len(row) == 4: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([("◀️  Назад", "pc")])
    return rows

def queue_kb(q, page=0):
    PER   = 3
    start = page * PER
    rows  = []
    for i, post in enumerate(q[start:start + PER]):
        real = start + i
        icon = "🖼 " if post.get("media_type") else ""
        prev = (icon + post.get("text", ""))[:35].replace("\n", " ")
        if len(icon + post.get("text", "")) > 35: prev += "..."
        sa  = post.get("scheduled_at")
        tag = "📅 " + format_scheduled(sa) if sa else "#" + str(real + 1)
        rows.append([(tag + "  " + prev, "noop")])
        row = []
        if real > 0: row.append(("⬆️ Выше", "qu_" + str(real)))
        row += [("🚀 Сейчас", "qp_" + str(real)), ("🗑️ Удалить", "qd_" + str(real))]
        rows.append(row)
    total_pages = max(1, (len(q) + PER - 1) // PER)
    nav = []
    if page > 0:              nav.append(("◀️", "qv_" + str(page - 1)))
    nav.append((str(page + 1) + "/" + str(total_pages), "noop"))
    if page < total_pages - 1: nav.append(("▶️", "qv_" + str(page + 1)))
    rows += [nav, [("🗑️ Очистить всё", "q_clear"), ("🏠 Меню", "m")]]
    return rows

def schedule_kb(times):
    rows = [[("🕐 " + t + " МСК", "noop"), ("🗑️ Удалить", "sd_" + t)] for t in sorted(times)]
    rows += [[("➕  Добавить время", "sa")], [("🏠  Меню", "m")]]
    return rows

def add_time_kb(existing):
    slots = ["07:00","08:00","09:00","10:00","11:00","12:00",
             "13:00","14:00","15:00","16:00","17:00","18:00",
             "19:00","20:00","21:00","22:00","23:00"]
    rows, row = [], []
    for t in slots:
        row.append(("✅ " + t if t in existing else t, "sa_" + t))
        if len(row) == 4: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([("◀️  Назад", "sv")]); return rows

def settings_kb(cfg):
    ch = cfg.get("channel_id") or "не задан"
    return [[("📢 Канал: " + ch, "noop")], [("✏️  Изменить канал", "cc")], [("🏠  Меню", "m")]]


# ── TEXTS ──────────────────────────────────────────────

def t_menu(cfg, q):
    ch    = cfg.get("channel_id") or "не привязан"
    times = ", ".join(sorted(cfg.get("post_times", DEFAULT_TIMES)))
    now   = datetime.now(MSK).strftime("%H:%M  %d.%m.%Y")
    return ("<b>Polyas Media Scheduler</b>\n——————————————————\n"
            "📢 Канал: <code>" + ch + "</code>\n"
            "📋 Очередь: <b>" + str(len(q)) + "</b> " + _posts_word(len(q)) + "\n"
            "🕐 Расписание: " + times + " МСК\n"
            "🗓 Сейчас: " + now + "\n")

def t_queue(q, page=0):
    if not q:
        return "<b>📋 Очередь пуста</b>\n\nОтправь текст/фото или нажми Новый пост."
    total_pages = max(1, (len(q) + 3 - 1) // 3)
    return ("<b>📋 Очередь постов</b>  (" + str(len(q)) + " шт, стр. "
            + str(page + 1) + "/" + str(total_pages) + ")\n"
            "——————————————————\n"
            "📅 = конкретная дата · 🕐 = слот · # = в общей очереди")

def t_status(cfg, q):
    ch    = cfg.get("channel_id") or "не привязан"
    times = sorted(cfg.get("post_times", DEFAULT_TIMES))
    now   = datetime.now(MSK)
    cur   = now.hour * 60 + now.minute
    next_t = next((t for t in times if int(t[:2]) * 60 + int(t[3:]) > cur), None)
    nxt   = ("сегодня в " + next_t + " МСК") if next_t else ("завтра в " + times[0] + " МСК")
    stats = load_stats()
    body  = ("<b>📊 Статус</b>\n——————————————————\n"
             "📢 Канал: <code>" + ch + "</code>\n"
             "🗓 Сейчас: " + now.strftime("%H:%M, %d.%m.%Y") + "\n"
             "📋 В очереди: <b>" + str(len(q)) + "</b> " + _posts_word(len(q)) + "\n"
             "⏭ Следующий слот: <b>" + nxt + "</b>\n"
             "🕐 Слотов в день: " + str(len(times)) + "\n"
             "📈 Опубликовано всего: <b>" + str(stats.get("total", 0)) + "</b>\n")
    if q:
        icon = "🖼 " if q[0].get("media_type") else ""
        prev = (icon + q[0].get("text", ""))[:70].replace("\n", " ")
        sa   = q[0].get("scheduled_at")
        body += "\n📄 Следующий пост" + (" (" + format_scheduled(sa) + ")" if sa else "") + ":\n<i>" + prev + "...</i>"
    return body

def t_schedule(cfg):
    times = sorted(cfg.get("post_times", DEFAULT_TIMES))
    lines = "\n".join("    🕐 " + t + " МСК" for t in times)
    return ("<b>🕐 Расписание публикаций</b>\n——————————————————\n"
            + lines + "\n\nСлотов в день: <b>" + str(len(times)) + "</b>\n"
            "В каждый слот бот публикует 1 пост из очереди.")

def t_settings(cfg):
    ch    = cfg.get("channel_id") or "не привязан"
    times = ", ".join(sorted(cfg.get("post_times", DEFAULT_TIMES)))
    return ("<b>⚙️ Настройки</b>\n——————————————————\n"
            "📢 Канал: <code>" + ch + "</code>\n"
            "🕐 Расписание: " + times + " МСК\n")


# ── SCREENS ────────────────────────────────────────────

def screen_menu(cid, mid=None):
    cfg = load_cfg(); q = load_q()
    txt = t_menu(cfg, q); btn = main_menu_kb(len(q))
    if mid: edit(cid, mid, txt, btn)
    else:   send(cid, txt, btn)

def screen_draft(cid, uid, draft, mid=None):
    if is_media_draft(draft):
        ICONS = {"photo": "🖼 Фото", "video": "🎥 Видео",
                 "animation": "🎞 GIF", "document": "📎 Документ"}
        label   = ICONS.get(draft.get("media_type"), "Медиа")
        caption = draft.get("text", "")
        preview = ("<i>Подпись: " + caption[:80] + "</i>") if caption else "<i>Без подписи</i>"
        txt = ("<b>📝 Превью: " + label + "</b>\n——————————————————\n"
               + preview + "\n——————————————————\nЧто делать с постом?")
        send_media_preview(cid, draft)
        if mid: edit(cid, mid, txt, draft_kb(is_media=True))
        else:   send(cid, txt, draft_kb(is_media=True))
    else:
        text = draft if isinstance(draft, str) else draft.get("text", "")
        txt  = ("<b>📝 Превью поста:</b>\n——————————————————\n"
                + text + "\n——————————————————\nЧто делать с постом?")
        if mid: edit(cid, mid, txt, draft_kb())
        else:   send(cid, txt, draft_kb())

def screen_date_picker(cid, uid, draft, mid=None):
    prev = draft_preview(draft)
    txt  = ("<b>📅 Выбери дату публикации</b>\n\n"
            "Пост: <i>" + prev + "</i>")
    btn  = date_picker_kb()
    set_state(uid, "pick_date", draft=draft)
    if mid:
        r = api("editMessageText", chat_id=cid, message_id=mid,
                text=txt, parse_mode="HTML", reply_markup=kb(btn))
        if not r.get("ok"): send(cid, txt, btn)
    else:
        send(cid, txt, btn)

def screen_dated_time_picker(cid, uid, date_str, orig_draft, mid=None):
    try:
        dt      = datetime.strptime(date_str, "%Y-%m-%d")
        display = str(dt.day) + " " + MONTHS_RU[dt.month] + " " + str(dt.year)
    except Exception:
        display = date_str
    txt = ("<b>🕐 Выбери время</b>\n\n"
           "📅 Дата: <b>" + display + "</b>\n"
           "Пост: <i>" + draft_preview(orig_draft) + "</i>")
    btn = dated_time_picker_kb()
    set_state(uid, "pick_dated_time", draft={"_draft": orig_draft, "_date": date_str})
    if mid:
        r = api("editMessageText", chat_id=cid, message_id=mid,
                text=txt, parse_mode="HTML", reply_markup=kb(btn))
        if not r.get("ok"): send(cid, txt, btn)
    else:
        send(cid, txt, btn)

def screen_queue(cid, page=0, mid=None):
    q   = load_q()
    txt = t_queue(q, page)
    btn = queue_kb(q, page) if q else [[("🏠 Меню", "m")]]
    if mid: edit(cid, mid, txt, btn)
    else:   send(cid, txt, btn)

def screen_schedule(cid, mid=None):
    cfg = load_cfg()
    txt = t_schedule(cfg); btn = schedule_kb(cfg.get("post_times", DEFAULT_TIMES))
    if mid: edit(cid, mid, txt, btn)
    else:   send(cid, txt, btn)

def screen_add_time(cid, mid=None):
    cfg = load_cfg()
    existing = cfg.get("post_times", DEFAULT_TIMES)
    txt = "<b>➕ Добавить слот</b>\n\nВыбери время (МСК).\n✅ = уже в расписании."
    if mid: edit(cid, mid, txt, add_time_kb(existing))
    else:   send(cid, txt, add_time_kb(existing))

def screen_status(cid, mid=None):
    cfg = load_cfg(); q = load_q()
    if mid: edit(cid, mid, t_status(cfg, q), [[("🏠 Меню", "m")]])
    else:   send(cid, t_status(cfg, q), [[("🏠 Меню", "m")]])

def screen_settings(cid, mid=None):
    cfg = load_cfg()
    if mid: edit(cid, mid, t_settings(cfg), settings_kb(cfg))
    else:   send(cid, t_settings(cfg), settings_kb(cfg))


# ── MESSAGE HANDLER ────────────────────────────────────

def handle_message(msg, cfg):
    uid  = msg["from"]["id"]
    text = msg.get("text", "")

    if cfg["admin_id"] is None:
        cfg["admin_id"] = uid; save_cfg(cfg)
        log.info("Admin registered: %s", uid)
        send(uid, "<b>Polyas Media Scheduler</b>\n\n✅ Ты администратор.\nID: <code>" + str(uid) + "</code>\n\nПривяжи канал:",
             [[("⚙️ Настройки", "cfg")]]); return

    if cfg["admin_id"] != uid: return

    sd    = get_state(uid)
    state = sd.get("state", "idle")
    log.info("MSG uid=%s state=%s", uid, state)

    if text.startswith("/"):
        cmd  = text.split()[0].split("@")[0].lstrip("/").lower()
        args = text.split()[1:]
        if cmd in ("start", "menu"): set_state(uid, "idle"); screen_menu(uid)
        elif cmd == "setchannel" and args:
            ch = clean_channel(args[0]) or ("@" + args[0])
            cfg["channel_id"] = ch; save_cfg(cfg)
            send(uid, "✅ Канал <code>" + ch + "</code> привязан!", [[("🏠 Меню", "m")]])
        return

    if state == "await_channel":
        if not text: send(uid, "⚠️ Отправь текстовый username."); return
        ch = clean_channel(text)
        if not ch: send(uid, "❌ Формат: <code>@mediapolyas</code>"); return
        cfg["channel_id"] = ch; save_cfg(cfg); set_state(uid, "idle")
        send(uid, "✅ Канал <code>" + ch + "</code> привязан!\n\nУбедись, что бот — администратор.",
             [[("🏠 Меню", "m")]]); return

    # Document
    document = msg.get("document")
    if document:
        fname = document.get("file_name", "")
        if fname.lower().endswith(".txt"):
            file_bytes = download_tg_file(document["file_id"])
            if not file_bytes: send(uid, "❌ Не удалось скачать файл."); return
            for enc in ("utf-8", "cp1251", "latin-1"):
                try: file_text = file_bytes.decode(enc); break
                except UnicodeDecodeError: continue
            else: send(uid, "❌ Не удалось прочитать. Сохрани в UTF-8."); return
            posts = parse_import_txt(file_text)
            if not posts:
                send(uid, "❌ Постов не найдено.\n\nРазделяй строкой:\n<code>---</code>"); return
            set_state(uid, "confirm_import", draft={"posts": posts})
            send(uid, "<b>📤 Импорт</b>\n\nНайдено <b>" + str(len(posts)) + "</b> " + _posts_word(len(posts)) + ".\n\n"
                 "Первый:\n<i>" + posts[0][:120] + ("..." if len(posts[0]) > 120 else "") + "</i>\n\nДобавить все?",
                 [[("✅ Добавить все", "import_confirm"), ("❌ Отмена", "m")]]); return
        else:
            cap_ent = msg.get("caption_entities")
            draft   = {"text": msg.get("caption", ""), "media_type": "document",
                       "file_id": document["file_id"], "entities": cap_ent}
            set_state(uid, "draft", draft=draft); screen_draft(uid, uid, draft); return

    # Photo / Video / Animation
    for media_key, media_type in (("photo", "photo"), ("video", "video"), ("animation", "animation")):
        m = msg.get(media_key)
        if m:
            cap_ent = msg.get("caption_entities")
            fid     = m[-1]["file_id"] if media_key == "photo" else m["file_id"]
            draft   = {"text": msg.get("caption", ""), "media_type": media_type,
                       "file_id": fid, "entities": cap_ent}
            set_state(uid, "draft", draft=draft); screen_draft(uid, uid, draft); return

    if not text:
        send(uid, "⚠️ Поддерживаются: текст, фото, видео, GIF, документы.\nИмпорт: отправь <b>.txt</b>"); return

    if state == "editing":
        cur = sd.get("draft")
        ent = msg.get("entities")
        if is_media_draft(cur):
            cur["text"] = text.strip(); cur["entities"] = ent
            set_state(uid, "draft", draft=cur); screen_draft(uid, uid, cur)
        else:
            new_draft = {"text": text, "media_type": None, "file_id": None, "entities": ent} if ent else text
            set_state(uid, "draft", draft=new_draft); screen_draft(uid, uid, new_draft)
        return

    ent   = msg.get("entities")
    draft = {"text": text, "media_type": None, "file_id": None, "entities": ent} if ent else text
    set_state(uid, "draft", draft=draft); screen_draft(uid, uid, draft)


# ── CALLBACK HANDLER ───────────────────────────────────

def handle_callback(cb, cfg):
    uid  = cb["from"]["id"]
    data = cb["data"]
    mid  = cb["message"]["message_id"]
    cid  = cb["message"]["chat"]["id"]
    log.info("CB uid=%s data=%s", uid, data)
    answer(cb["id"])
    if cfg["admin_id"] is None or int(cfg["admin_id"]) != int(uid): return
    try:
        _process_callback(uid, cid, mid, data, cfg)
    except Exception as e:
        log.error("CB ERROR uid=%s data=%s: %s", uid, data, e, exc_info=True)
        try: send(cid, "⚠️ Ошибка: " + str(e), [[("🏠 Меню", "m")]]); set_state(uid, "idle")
        except Exception: pass


def _process_callback(uid, cid, mid, data, cfg):
    sd    = get_state(uid)
    state = sd.get("state", "idle")
    draft = sd.get("draft")

    if data == "noop": return

    if data == "m":
        set_state(uid, "idle"); screen_menu(cid, mid); return

    # ── НОВЫЙ ПОСТ ───
    if data == "pn":
        set_state(uid, "await_text")
        edit(cid, mid,
             "<b>📝 Новый пост</b>\n\n"
             "Отправь <b>текст</b>, <b>фото</b>, <b>видео</b> или <b>GIF</b>.\n"
             "К медиафайлу можно добавить подпись.\n\n"
             "HTML: <code>&lt;b&gt;</code> <code>&lt;i&gt;</code> <code>&lt;code&gt;</code>",
             [[("❌ Отмена", "m")]]); return

    # ── ИМПОРТ ───
    if data == "pi":
        set_state(uid, "await_import")
        edit(cid, mid,
             "<b>📤 Импорт из .txt файла</b>\n\n"
             "Отправь <b>.txt файл</b>. Посты разделяй строкой:\n<code>---</code>\n\n"
             "<b>Пример:</b>\n<code>Первый пост\n---\nВторой пост\n---\nТретий</code>",
             [[("❌ Отмена", "m")]]); return

    if data == "import_confirm":
        if not isinstance(draft, dict) or "posts" not in draft:
            screen_menu(cid, mid); return
        posts = draft["posts"]; q = load_q(); now = datetime.now(MSK).isoformat()
        for p in posts:
            q.append({"text": p, "media_type": None, "file_id": None, "entities": None,
                      "added_at": now, "scheduled_at": None})
        save_q(q); set_state(uid, "idle")
        edit(cid, mid, "✅ <b>Импортировано " + str(len(posts)) + " " + _posts_word(len(posts)) + "!</b>\n\n"
             "Всего в очереди: <b>" + str(len(q)) + "</b>",
             [[("📋 Очередь", "qv_0"), ("🏠 Меню", "m")]]); return

    # ── ДЕЙСТВИЯ С ЧЕРНОВИКОМ ───
    if data == "p_now":
        if not draft: screen_menu(cid, mid); return
        ch = cfg.get("channel_id")
        if not ch:
            edit(cid, mid, "❌ Канал не привязан!", [[("⚙️ Настройки", "cfg"), ("🏠 Меню", "m")]]); return
        post = make_post(draft); result = publish_post(ch, post); set_state(uid, "idle")
        if result.get("ok"):
            log_stat(post, "manual"); q = load_q()
            edit(cid, mid, "✅ <b>Пост опубликован!</b>\n\nКанал: <code>" + ch + "</code>",
                 [[("📋 Очередь (" + str(len(q)) + ")", "qv_0"), ("🏠 Меню", "m")]])
        else:
            edit(cid, mid, "❌ Ошибка:\n<code>" + result.get("description", "") + "</code>",
                 [[("🏠 Меню", "m")]])
        return

    if data == "p_q":
        if not draft: screen_menu(cid, mid); return
        q = load_q(); q.append(make_post(draft)); save_q(q); set_state(uid, "idle")
        edit(cid, mid, "✅ <b>Добавлено в очередь #" + str(len(q)) + "</b>\n\n"
             "Следующая публикация: <b>" + next_slot(cfg) + "</b>",
             [[("📋 Очередь (" + str(len(q)) + ")", "qv_0"), ("🏠 Меню", "m")]]); return

    # ── ВЫБОР ДАТЫ ───
    if data == "p_date":
        if not draft: screen_menu(cid, mid); return
        screen_date_picker(cid, uid, draft, mid); return

    if data.startswith("pd_"):
        date_str = data[3:]  # "2026-05-20"
        orig     = draft if not is_dated_state(draft) else draft.get("_draft")
        screen_dated_time_picker(cid, uid, date_str, orig, mid); return

    if data.startswith("pdt_"):
        t = data[4:]  # "15:00"
        if not is_dated_state(draft): screen_menu(cid, mid); return
        date_str     = draft["_date"]
        orig_draft   = draft["_draft"]
        scheduled_at = date_str + " " + t  # "2026-05-20 15:00"
        q = load_q(); q.append(make_post(orig_draft, scheduled_at=scheduled_at)); save_q(q)
        set_state(uid, "idle")
        try:
            dt      = datetime.strptime(scheduled_at, "%Y-%m-%d %H:%M")
            display = str(dt.day) + " " + MONTHS_RU[dt.month] + " " + str(dt.year) + " в " + t + " МСК"
        except Exception:
            display = scheduled_at
        edit(cid, mid, "✅ <b>Запланировано!</b>\n\n📅 Дата: <b>" + display + "</b>\nВ очереди: <b>" + str(len(q)) + "</b>",
             [[("📋 Очередь", "qv_0"), ("🏠 Меню", "m")]]); return

    if data == "p_edit":
        if not draft: screen_menu(cid, mid); return
        set_state(uid, "editing", draft=draft)
        if is_media_draft(draft):
            cap = draft.get("text", "")
            edit(cid, mid, "<b>✏️ Редактировать подпись</b>\n\nТекущая: <i>" + (cap[:200] if cap else "(без подписи)") + "</i>\n\nОтправь новую:", [[("❌ Отмена", "pc")]])
        else:
            text = draft if isinstance(draft, str) else draft.get("text", "")
            edit(cid, mid, "<b>✏️ Редактировать пост</b>\n\nТекущий:\n<i>" + text[:200] + "</i>\n\nОтправь новый:", [[("❌ Отмена", "pc")]])
        return

    if data == "pc":
        # Unwrap dated state → go back to date picker
        if is_dated_state(draft):
            orig = draft.get("_draft")
            set_state(uid, "pick_date", draft=orig)
            screen_date_picker(cid, uid, orig, mid)
        elif draft:
            set_state(uid, "draft", draft=draft); screen_draft(cid, uid, draft, mid)
        else:
            set_state(uid, "idle"); screen_menu(cid, mid)
        return

    # ── ОЧЕРЕДЬ ───
    if data.startswith("qv_"):
        screen_queue(cid, int(data[3:]), mid); return

    if data.startswith("qd_"):
        idx = int(data[3:]); q = load_q()
        if 0 <= idx < len(q): q.pop(idx); save_q(q)
        screen_queue(cid, max(0, (idx // 3) - (1 if idx % 3 == 0 and idx > 0 else 0)), mid); return

    if data.startswith("qu_"):
        idx = int(data[3:]); q = load_q()
        if 1 <= idx < len(q): q[idx], q[idx-1] = q[idx-1], q[idx]; save_q(q)
        screen_queue(cid, max(0, (idx-1)//3), mid); return

    if data.startswith("qp_"):
        idx = int(data[3:]); q = load_q(); ch = cfg.get("channel_id")
        if not ch:
            edit(cid, mid, "❌ Канал не привязан!", [[("⚙️ Настройки", "cfg")]]); return
        if 0 <= idx < len(q):
            post = q.pop(idx); result = publish_post(ch, post)
            if result.get("ok"):
                log_stat(post, "manual_queue"); save_q(q); screen_queue(cid, 0, mid)
            else:
                q.insert(idx, post)
                edit(cid, mid, "❌ Ошибка: " + result.get("description", ""), [[("◀️ Назад", "qv_0")]])
        return

    if data == "q_clear":
        save_q([]); set_state(uid, "idle"); screen_queue(cid, 0, mid); return

    # ── РАСПИСАНИЕ ───
    if data == "sv":  screen_schedule(cid, mid); return
    if data == "sa":  screen_add_time(cid, mid); return

    if data.startswith("sa_"):
        t = data[3:]; times = list(cfg.get("post_times", DEFAULT_TIMES))
        if t not in times: times.append(t); cfg["post_times"] = sorted(times); save_cfg(cfg)
        screen_add_time(cid, mid); return

    if data.startswith("sd_"):
        t = data[3:]; times = list(cfg.get("post_times", DEFAULT_TIMES))
        if t in times and len(times) > 1: times.remove(t); cfg["post_times"] = sorted(times); save_cfg(cfg)
        screen_schedule(cid, mid); return

    # ── СТАТУС / НАСТРОЙКИ ───
    if data == "st":  screen_status(cid, mid);  return
    if data == "cfg": screen_settings(cid, mid); return

    if data == "cc":
        set_state(uid, "await_channel")
        edit(cid, mid, "<b>✏️ Изменить канал</b>\n\nОтправь username:\n<code>@mediapolyas</code>",
             [[("❌ Отмена", "cfg")]]); return

    log.warning("CB unhandled: %s", data)


# ── SCHEDULER ──────────────────────────────────────────

def scheduler_loop():
    log.info("Планировщик запущен")
    while True:
        try:
            now          = datetime.now(MSK)
            slot         = "%02d:%02d" % (now.hour, now.minute)
            today        = now.strftime("%Y-%m-%d")
            now_dt_str   = today + " " + slot          # "2026-05-20 15:00"
            date_slot    = today + "_" + slot

            cfg      = load_cfg()
            times    = cfg.get("post_times", DEFAULT_TIMES)
            admin_id = cfg.get("admin_id")
            channel  = cfg.get("channel_id")

            fired = load_fired()
            fired = {k: v for k, v in fired.items() if k[:10] >= today}  # prune old dates

            is_scheduled_slot = slot in times
            is_datetime_minute = True  # always check datetime posts every tick

            # Find post to publish this minute
            def find_post(q):
                # 1. Exact datetime match
                for i, p in enumerate(q):
                    sa = p.get("scheduled_at", "") or ""
                    if " " in sa and sa == now_dt_str:
                        return i
                # 2. Time-slot match (only on scheduled slots, not already fired)
                if is_scheduled_slot and date_slot not in fired:
                    for i, p in enumerate(q):
                        sa = p.get("scheduled_at", "") or ""
                        if sa and " " not in sa and sa == slot:
                            return i
                    # 3. Unscheduled (auto-queue)
                    for i, p in enumerate(q):
                        if not p.get("scheduled_at"):
                            return i
                return None

            q   = load_q()
            idx = find_post(q)

            # Mark slot as fired (even if queue empty, to prevent double-fire)
            if is_scheduled_slot and date_slot not in fired:
                fired[date_slot] = True
                save_fired(fired)

            if idx is not None and channel and admin_id:
                post   = q.pop(idx)
                result = publish_post(channel, post)
                if result.get("ok"):
                    save_q(q); log_stat(post, slot)
                    icon = " 🖼" if post.get("media_type") else ""
                    sa   = post.get("scheduled_at")
                    when = (" (" + format_scheduled(sa) + ")") if sa else (" (" + slot + " МСК)")
                    log.info("Автопост%s%s: %s...", icon, when, post.get("text", "")[:40])
                    send(admin_id,
                         "✅ <b>Пост опубликован</b>" + when + icon + "\n"
                         "Осталось: <b>" + str(len(q)) + "</b> " + _posts_word(len(q)),
                         [[("📋 Очередь", "qv_0"), ("🏠 Меню", "m")]])
                else:
                    q.insert(idx, post)
                    log.error("Ошибка автопоста %s: %s", slot, result)
                    send(admin_id, "❌ Ошибка публикации:\n" + result.get("description", str(result)),
                         [[("🏠 Меню", "m")]])

        except Exception as e:
            log.error("Scheduler error: %s", e)
        time.sleep(20)


# ── POLLING ────────────────────────────────────────────

def polling_loop():
    offset = 0
    log.info("Бот запущен...")
    try:
        result = api("getUpdates", offset=-1, timeout=1)
        if result.get("ok") and result.get("result"):
            offset = result["result"][-1]["update_id"] + 1
            log.info("Skipped %d pending update(s)", len(result["result"]))
    except Exception: pass

    while True:
        try:
            result = api("getUpdates", offset=offset, timeout=25,
                         allowed_updates=["message", "callback_query"])
            if not result.get("ok"):
                log.warning("getUpdates: %s", result.get("description")); time.sleep(3); continue
            for upd in result.get("result", []):
                offset = upd["update_id"] + 1
                cfg    = load_cfg()
                try:
                    if "message" in upd:       handle_message(upd["message"], cfg)
                    elif "callback_query" in upd: handle_callback(upd["callback_query"], cfg)
                except Exception as e:
                    log.error("Handler error upd=%s: %s", upd.get("update_id"), e, exc_info=True)
        except Exception as e:
            log.error("Polling error: %s", e); time.sleep(5)


# ── MAIN ───────────────────────────────────────────────

def main():
    cfg   = load_cfg()
    times = cfg.get("post_times", DEFAULT_TIMES)
    admin = cfg.get("admin_id")
    ch    = cfg.get("channel_id") or "не привязан"
    if ch and ch != "не привязан":
        fixed = clean_channel(ch)
        if fixed and fixed != ch: cfg["channel_id"] = fixed; save_cfg(cfg); ch = fixed

    print("=" * 50)
    print("  Polyas Media Scheduler Bot v3.1")
    print("=" * 50)
    print("  Расписание : " + ", ".join(times) + " МСК")
    print("  Канал      : " + ch)
    print("  Admin ID   : " + (str(admin) if admin else "не задан — отправь /start"))
    print("  Ctrl+C     : остановить")
    print("=" * 50)

    threading.Thread(target=scheduler_loop, daemon=True).start()
    polling_loop()

if __name__ == "__main__":
    main()
