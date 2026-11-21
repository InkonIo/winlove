"""Vercel Python function: принимает событие со страницы и отправляет его в Telegram.
Токен и chat id берутся из переменных окружения Vercel (TG_TOKEN, TG_CHAT_ID). В репозиторий их класть нельзя."""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

TITLES = {
    "lock": "👀 Зашла на страницу (ещё закрыто)",
    "open": "🎄 Открыла ёлку",
    "finale": "💌 Дошла до послания",
    "leave": "👋 Вышла со страницы",
}


def esc(value):
    return str(value if value is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def device(ua):
    if "iPhone" in ua or "iPad" in ua:
        os_name = "iPhone/iPad"
    elif "Android" in ua:
        os_name = "Android"
    elif "Windows" in ua:
        os_name = "Windows"
    elif "Mac OS X" in ua:
        os_name = "Mac"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = "неизвестно"
    if any(k in ua for k in ("Instagram", "FBAN", "FBAV", "Telegram")):
        browser = "встроенный браузер"
    elif "CriOS" in ua or "Chrome/" in ua:
        browser = "Chrome"
    elif "FxiOS" in ua or "Firefox/" in ua:
        browser = "Firefox"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = "браузер"
    return f"{os_name} · {browser}"


def mmss(seconds):
    return f"{seconds // 60} мин {seconds % 60} сек"


class handler(BaseHTTPRequestHandler):
    def _reply(self, code=200, text="ok"):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def do_GET(self):
        self._reply()

    def do_POST(self):
        token = os.environ.get("TG_TOKEN")
        chat = os.environ.get("TG_CHAT_ID")
        if not token or not chat:
            return self._reply(500, "not configured")
        try:
            size = min(int(self.headers.get("content-length") or 0), 2000)
            data = json.loads(self.rfile.read(size).decode("utf-8"))
        except Exception:
            return self._reply(400, "bad")
        kind = data.get("type")
        if kind not in TITLES:
            return self._reply(400, "bad")

        h = self.headers
        ip = (h.get("x-forwarded-for") or h.get("x-real-ip") or "?").split(",")[0].strip()
        city = urllib.parse.unquote(h.get("x-vercel-ip-city", ""))
        place = ", ".join(x for x in (city, h.get("x-vercel-ip-country-region", ""), h.get("x-vercel-ip-country", "")) if x) or "не определено"
        now = datetime.now(timezone(timedelta(hours=5))).strftime("%d.%m.%Y %H:%M:%S")

        lines = [
            f"<b>{TITLES[kind]}</b>",
            f"Время (Алматы): {now}",
            f"IP: <code>{esc(ip)}</code>",
            f"Место: {esc(place)}",
            f"Устройство: {esc(device(h.get('user-agent', '')))} · экран {esc(data.get('scr'))}",
            f"Язык: {esc(data.get('lang'))} · пояс: {esc(data.get('tz'))}",
        ]
        if kind == "leave":
            try:
                secs = int(data.get("secs") or 0)
            except (TypeError, ValueError):
                secs = 0
            viewed = [str(int(x)) for x in (data.get("viewed") or [])[:20] if isinstance(x, (int, float))]
            lines.append(f"На странице: {mmss(secs)}")
            lines.append(
                f"Тур до конца: {'да' if data.get('tour') else 'нет'} · послание: {'да' if data.get('finale') else 'нет'} · музыка: {'играла' if data.get('music') else 'выключена'}"
            )
            lines.append(f"Шары, которые открывала сама: {', '.join(viewed) if viewed else 'нет'}")
        lines.append(f"<i>сессия {esc(data.get('sid'))}</i>")

        payload = json.dumps({"chat_id": chat, "text": "\n".join(lines), "parse_mode": "HTML", "disable_web_page_preview": True}).encode("utf-8")
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=5).read()
        except Exception:
            return self._reply(502, "telegram error")
        return self._reply()
