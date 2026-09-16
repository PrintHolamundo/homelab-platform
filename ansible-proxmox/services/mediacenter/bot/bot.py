#!/usr/bin/env python3
"""
Telegram MediaBot
Standalone automation service for Radarr and Sonarr via Telegram Long Polling.
"""

import html
import json
import logging
import os
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("telegram_mediabot")


def http_request(url, method="GET", data=None, headers=None, timeout=30):
    headers = headers or {}
    encoded_data = None
    if data is not None:
        encoded_data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"error": err_body}
    except Exception as e:
        return 0, {"error": str(e)}


class TelegramClient:
    def __init__(self, token: str):
        self.base_url = f"https://api.telegram.org/bot{token}"

    def delete_webhook(self, drop_pending_updates: bool = False):
        return http_request(
            f"{self.base_url}/deleteWebhook",
            method="POST",
            data={"drop_pending_updates": drop_pending_updates}
        )

    def get_me(self):
        return http_request(f"{self.base_url}/getMe", timeout=10)

    def get_updates(self, offset=None, timeout=25):
        params = {
            "timeout": timeout,
            "allowed_updates": json.dumps(["message", "callback_query"])
        }
        if offset is not None:
            params["offset"] = offset
        query_str = urllib.parse.urlencode(params)
        return http_request(f"{self.base_url}/getUpdates?{query_str}", timeout=35)

    def send_message(self, chat_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        status, res = http_request(f"{self.base_url}/sendMessage", method="POST", data=payload, timeout=15)
        return res

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        status, res = http_request(f"{self.base_url}/editMessageText", method="POST", data=payload, timeout=15)
        return res

    def answer_callback_query(self, callback_query_id, text=None):
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        http_request(f"{self.base_url}/answerCallbackQuery", method="POST", data=payload, timeout=5)


class RadarrClient:
    def __init__(self, base_url: str, api_key: str, root_folder: str, quality_profile_id: int):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.root_folder = root_folder
        self.quality_profile_id = quality_profile_id
        self.headers = {"X-Api-Key": self.api_key}

    def search_movies(self, query: str):
        query_encoded = urllib.parse.quote(query)
        status, res = http_request(
            f"{self.base_url}/api/v3/movie/lookup?term={query_encoded}",
            headers=self.headers,
            timeout=15
        )
        return res if status == 200 and isinstance(res, list) else []

    def get_movie_by_tmdb(self, tmdb_id: int):
        status, res = http_request(
            f"{self.base_url}/api/v3/movie/lookup?term=tmdb:{tmdb_id}",
            headers=self.headers,
            timeout=10
        )
        return res[0] if status == 200 and isinstance(res, list) and res else None

    def fetch_tmdb_template(self, tmdb_id: int):
        status, res = http_request(
            f"{self.base_url}/api/v3/movie/lookup/tmdb?tmdbId={tmdb_id}",
            headers=self.headers,
            timeout=10
        )
        return res if status == 200 and isinstance(res, dict) else None

    def add_movie(self, movie_data: dict):
        payload = dict(movie_data)
        payload["qualityProfileId"] = self.quality_profile_id
        payload["rootFolderPath"] = self.root_folder
        payload["monitored"] = True
        payload["addOptions"] = {"searchForMovie": True}
        return http_request(
            f"{self.base_url}/api/v3/movie",
            method="POST",
            data=payload,
            headers=self.headers,
            timeout=15
        )

    def trigger_search(self, movie_id: int):
        return http_request(
            f"{self.base_url}/api/v3/command",
            method="POST",
            data={"name": "MoviesSearch", "movieIds": [movie_id]},
            headers=self.headers,
            timeout=10
        )


class SonarrClient:
    def __init__(self, base_url: str, api_key: str, root_folder: str, quality_profile_id: int):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.root_folder = root_folder
        self.quality_profile_id = quality_profile_id
        self.headers = {"X-Api-Key": self.api_key}

    def search_series(self, query: str):
        query_encoded = urllib.parse.quote(query)
        status, res = http_request(
            f"{self.base_url}/api/v3/series/lookup?term={query_encoded}",
            headers=self.headers,
            timeout=15
        )
        return res if status == 200 and isinstance(res, list) else []

    def get_series_by_tvdb(self, tvdb_id: int):
        status, res = http_request(
            f"{self.base_url}/api/v3/series/lookup?term=tvdb:{tvdb_id}",
            headers=self.headers,
            timeout=10
        )
        return res[0] if status == 200 and isinstance(res, list) and res else None

    def add_series(self, series_data: dict):
        payload = dict(series_data)
        payload["qualityProfileId"] = self.quality_profile_id
        payload["rootFolderPath"] = self.root_folder
        payload["monitored"] = True
        payload["addOptions"] = {"searchForMissingEpisodes": True}
        return http_request(
            f"{self.base_url}/api/v3/series",
            method="POST",
            data=payload,
            headers=self.headers,
            timeout=15
        )

    def trigger_search(self, series_id: int):
        return http_request(
            f"{self.base_url}/api/v3/command",
            method="POST",
            data={"name": "SeriesSearch", "seriesId": series_id},
            headers=self.headers,
            timeout=10
        )


class MediaBot:
    def __init__(self, telegram: TelegramClient, radarr: RadarrClient, sonarr: SonarrClient):
        self.telegram = telegram
        self.radarr = radarr
        self.sonarr = sonarr
        self.running = True

    def stop(self):
        self.running = False

    def handle_movie_search(self, chat_id, query):
        if not query:
            self.telegram.send_message(
                chat_id,
                "ℹ️ Por favor escribe el nombre de la película.\n\nEjemplo: <code>/movie Oppenheimer</code>"
            )
            return

        logger.info(f"Searching Radarr: {query}")
        movies = self.radarr.search_movies(query)
        if not movies:
            self.telegram.send_message(
                chat_id,
                f"❌ No se encontraron películas para <b>{html.escape(query)}</b>."
            )
            return

        buttons = []
        for m in movies[:5]:
            title = m.get("title", "Desconocido")
            year = m.get("year")
            year_str = f" ({year})" if year else ""
            tmdb_id = m.get("tmdbId")
            if not tmdb_id:
                continue
            tag = " 📁" if m.get("id") else ""
            btn_text = f"🎬 {title}{year_str}{tag}"
            if len(btn_text.encode("utf-8")) > 60:
                btn_text = btn_text[:55] + "..."
            buttons.append([{"text": btn_text, "callback_data": f"m:{tmdb_id}"}])

        buttons.append([{"text": "❌ Cancelar", "callback_data": "cancel"}])
        self.telegram.send_message(
            chat_id,
            f"🔍 <b>Resultados en Radarr para:</b> <i>{html.escape(query)}</i>\n\nSelecciona una opción:",
            reply_markup={"inline_keyboard": buttons}
        )

    def handle_movie_selection(self, chat_id, message_id, tmdb_id):
        logger.info(f"Selecting movie tmdbId: {tmdb_id}")
        existing = self.radarr.get_movie_by_tmdb(tmdb_id)
        if existing and existing.get("id"):
            self.radarr.trigger_search(existing["id"])
            title = existing.get("title", "Película")
            year = existing.get("year", "")
            self.telegram.edit_message_text(
                chat_id,
                message_id,
                f"ℹ️ <b>{html.escape(title)} ({year})</b> ya está en tu biblioteca de Radarr.\n\n🚀 Se ha forzado una nueva búsqueda en qBittorrent."
            )
            return

        movie_data = self.radarr.fetch_tmdb_template(tmdb_id)
        if not movie_data:
            self.telegram.edit_message_text(chat_id, message_id, "⚠️ Error al obtener detalles de la película en Radarr.")
            return

        title = movie_data.get("title", "Película")
        year = movie_data.get("year", "")
        status, add_res = self.radarr.add_movie(movie_data)

        if status in [200, 201]:
            logger.info(f"Added movie '{title}' to Radarr")
            self.telegram.edit_message_text(
                chat_id,
                message_id,
                f"✅ <b>¡Película agregada con éxito!</b>\n\n"
                f"🎬 <b>{html.escape(title)}</b> ({year})\n"
                f"📁 Carpeta: <code>{self.radarr.root_folder}</code>\n"
                f"🎯 Calidad: <code>1080p - Custom</code>\n"
                f"🚀 <b>Descarga iniciada:</b> Radarr la buscará y enviará a qBittorrent automáticamente."
            )
        else:
            err_msg = str(add_res)
            if isinstance(add_res, list) and add_res:
                err_msg = add_res[0].get("errorMessage", str(add_res))
            logger.error(f"Failed adding movie: {status} {err_msg}")
            self.telegram.edit_message_text(chat_id, message_id, f"⚠️ Radarr no pudo agregar la película:\n<code>{html.escape(err_msg)}</code>")

    def handle_series_search(self, chat_id, query):
        if not query:
            self.telegram.send_message(
                chat_id,
                "ℹ️ Por favor escribe el nombre de la serie.\n\nEjemplo: <code>/series Breaking Bad</code>"
            )
            return

        logger.info(f"Searching Sonarr: {query}")
        series_list = self.sonarr.search_series(query)
        if not series_list:
            self.telegram.send_message(
                chat_id,
                f"❌ No se encontraron series para <b>{html.escape(query)}</b>."
            )
            return

        buttons = []
        for s in series_list[:5]:
            title = s.get("title", "Desconocido")
            year = s.get("year")
            year_str = f" ({year})" if year else ""
            tvdb_id = s.get("tvdbId")
            if not tvdb_id:
                continue
            tag = " 📁" if s.get("id") else ""
            btn_text = f"📺 {title}{year_str}{tag}"
            if len(btn_text.encode("utf-8")) > 60:
                btn_text = btn_text[:55] + "..."
            buttons.append([{"text": btn_text, "callback_data": f"s:{tvdb_id}"}])

        buttons.append([{"text": "❌ Cancelar", "callback_data": "cancel"}])
        self.telegram.send_message(
            chat_id,
            f"🔍 <b>Resultados en Sonarr para:</b> <i>{html.escape(query)}</i>\n\nSelecciona una opción:",
            reply_markup={"inline_keyboard": buttons}
        )

    def handle_series_selection(self, chat_id, message_id, tvdb_id):
        logger.info(f"Selecting series tvdbId: {tvdb_id}")
        s = self.sonarr.get_series_by_tvdb(tvdb_id)
        if not s:
            self.telegram.edit_message_text(chat_id, message_id, "⚠️ No se encontraron detalles de la serie en Sonarr.")
            return

        title = s.get("title", "Serie")
        year = s.get("year", "")

        if s.get("id"):
            self.sonarr.trigger_search(s["id"])
            self.telegram.edit_message_text(
                chat_id,
                message_id,
                f"ℹ️ <b>{html.escape(title)} ({year})</b> ya está en tu biblioteca de Sonarr.\n\n🚀 Se ha forzado una nueva búsqueda de episodios en qBittorrent."
            )
            return

        status, add_res = self.sonarr.add_series(s)
        if status in [200, 201]:
            logger.info(f"Added series '{title}' to Sonarr")
            self.telegram.edit_message_text(
                chat_id,
                message_id,
                f"✅ <b>¡Serie agregada con éxito!</b>\n\n"
                f"📺 <b>{html.escape(title)}</b> ({year})\n"
                f"📁 Carpeta: <code>{self.sonarr.root_folder}</code>\n"
                f"🎯 Calidad: <code>1080p - Custom</code>\n"
                f"🚀 <b>Descarga iniciada:</b> Sonarr buscará los episodios y los enviará a qBittorrent."
            )
        else:
            err_msg = str(add_res)
            if isinstance(add_res, list) and add_res:
                err_msg = add_res[0].get("errorMessage", str(add_res))
            logger.error(f"Failed adding series: {status} {err_msg}")
            self.telegram.edit_message_text(chat_id, message_id, f"⚠️ Sonarr no pudo agregar la serie:\n<code>{html.escape(err_msg)}</code>")

    def process_update(self, update):
        try:
            if "callback_query" in update:
                cb = update["callback_query"]
                cb_id = cb.get("id")
                cb_data = cb.get("data", "")
                msg = cb.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                message_id = msg.get("message_id")

                self.telegram.answer_callback_query(cb_id)

                if cb_data == "cancel":
                    self.telegram.edit_message_text(chat_id, message_id, "❌ Búsqueda cancelada.")
                elif cb_data.startswith("m:"):
                    tmdb_id = int(cb_data.split(":", 1)[1])
                    self.handle_movie_selection(chat_id, message_id, tmdb_id)
                elif cb_data.startswith("s:"):
                    tvdb_id = int(cb_data.split(":", 1)[1])
                    self.handle_series_selection(chat_id, message_id, tvdb_id)
                return

            if "message" in update and "text" in update["message"]:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                text = msg["text"].strip()

                parts = text.split(None, 1)
                raw_cmd = parts[0]
                cmd = raw_cmd.lower().split("@")[0]
                arg = parts[1].strip() if len(parts) > 1 else ""

                if cmd in ["/movie", "/pelicula", "/peli"]:
                    self.handle_movie_search(chat_id, arg)
                elif cmd in ["/series", "/serie", "/tv"]:
                    self.handle_series_search(chat_id, arg)
                elif cmd in ["/help", "/ayuda", "/start"]:
                    help_text = (
                        "🍿 <b>Media Center Bot</b>\n\n"
                        "<b>Comandos disponibles:</b>\n"
                        "• <code>/movie &lt;nombre&gt;</code> - Buscar y agregar película a Radarr\n"
                        "• <code>/series &lt;nombre&gt;</code> - Buscar y agregar serie a Sonarr\n\n"
                        "<i>Ejemplos:</i>\n"
                        "• <code>/movie Oppenheimer</code>\n"
                        "• <code>/series Severance</code>"
                    )
                    self.telegram.send_message(chat_id, help_text)

        except Exception as e:
            logger.error(f"Error processing update: {e}", exc_info=True)

    def run(self):
        self.telegram.delete_webhook()
        status, me = self.telegram.get_me()
        if status == 200 and me.get("ok"):
            logger.info(f"Bot authenticated as @{me['result'].get('username')}")
        else:
            logger.warning(f"Unable to verify bot details: status={status}")

        offset = None
        logger.info("Starting Telegram Long Polling loop...")

        while self.running:
            try:
                status, res = self.telegram.get_updates(offset=offset)
                if status == 200 and res.get("ok"):
                    for update in res.get("result", []):
                        offset = update["update_id"] + 1
                        self.process_update(update)
                elif status == 409:
                    logger.warning("Conflict 409: active webhook detected. Retrying deleteWebhook...")
                    self.telegram.delete_webhook()
                    time.sleep(2)
                else:
                    logger.warning(f"getUpdates error: HTTP {status} - {res}")
                    time.sleep(3)
            except Exception as e:
                logger.error(f"Polling error: {e}")
                time.sleep(3)

        logger.info("MediaBot loop stopped.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is required. Exiting.")
        sys.exit(1)

    radarr_url = os.getenv("RADARR_URL", "http://radarr:7878")
    radarr_api_key = os.getenv("RADARR_API_KEY", "").strip()
    sonarr_url = os.getenv("SONARR_URL", "http://sonarr:8989")
    sonarr_api_key = os.getenv("SONARR_API_KEY", "").strip()
    radarr_root = os.getenv("RADARR_ROOT", "/data/media/movies")
    sonarr_root = os.getenv("SONARR_ROOT", "/data/media/tv")
    quality_profile_id = int(os.getenv("QUALITY_PROFILE_ID", "7"))

    telegram = TelegramClient(token)
    radarr = RadarrClient(radarr_url, radarr_api_key, radarr_root, quality_profile_id)
    sonarr = SonarrClient(sonarr_url, sonarr_api_key, sonarr_root, quality_profile_id)

    bot = MediaBot(telegram, radarr, sonarr)

    def on_shutdown(sig, frame):
        logger.info(f"Signal {sig} received, stopping...")
        bot.stop()

    signal.signal(signal.SIGINT, on_shutdown)
    signal.signal(signal.SIGTERM, on_shutdown)

    bot.run()


if __name__ == "__main__":
    main()
