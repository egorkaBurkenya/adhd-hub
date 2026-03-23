#!/usr/bin/env python3
"""ADHD Hub — Telegram-бот для захвата мыслей через AI-роутер."""

import asyncio
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from groq import Groq
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --- Конфигурация ---

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])
HUB_DIR = Path(os.environ.get("HUB_DIR", Path.home() / "hub"))
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "opus")

# Инструменты, разрешённые Claude CLI
ALLOWED_TOOLS = ",".join([
    "Read", "Write", "Edit",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(mkdir:*)",
    "Bash(mv:*)", "Bash(cp:*)", "Bash(find:*)",
    "Bash(grep:*)", "Bash(head:*)", "Bash(tail:*)",
    "Bash(wc:*)", "Bash(date:*)",
])

# Расширения аудиофайлов для транскрипции
AUDIO_EXTENSIONS = {
    ".ogg", ".oga", ".mp3", ".wav", ".m4a",
    ".flac", ".aac", ".opus", ".wma",
}

# Текстовые расширения — содержимое передаётся Claude
TEXT_EXTENSIONS = {
    ".md", ".txt", ".json", ".csv", ".py", ".js", ".ts",
    ".yaml", ".yml", ".toml", ".cfg", ".ini", ".sh",
    ".html", ".css", ".xml", ".sql", ".log", ".conf",
    ".jsx", ".tsx", ".rs", ".go", ".rb", ".java",
}

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("adhd-hub")

groq_client = Groq(api_key=GROQ_API_KEY)
queue: asyncio.Queue = asyncio.Queue()

# Паттерн для очистки ANSI escape-кодов
ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


# --- Утилиты ---


def is_allowed(update: Update) -> bool:
    """Только разрешённый пользователь."""
    return update.effective_user is not None and update.effective_user.id == ALLOWED_USER_ID


def hub_tree() -> str:
    """Дерево ~/hub/ (3 уровня глубины)."""
    try:
        result = subprocess.run(
            ["find", str(HUB_DIR), "-maxdepth", "3", "-not", "-path", "*/.*"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = []
        for line in sorted(result.stdout.strip().split("\n")):
            if not line.strip():
                continue
            rel = os.path.relpath(line, HUB_DIR)
            if rel == ".":
                continue
            depth = rel.count(os.sep)
            name = os.path.basename(rel)
            prefix = "  " * depth + "├── "
            if os.path.isdir(line):
                name += "/"
            lines.append(f"{prefix}{name}")
        return "\n".join(lines[:100]) if lines else "(пусто)"
    except Exception:
        return "(не удалось прочитать)"


def load_rules() -> str:
    """Загрузить правила роутинга из CLAUDE.md."""
    path = Path(__file__).parent / "CLAUDE.md"
    return path.read_text() if path.exists() else ""


def clean_output(text: str) -> str:
    """Убрать ANSI escape-коды из вывода Claude."""
    return ANSI_RE.sub("", text)


def unique_path(directory: Path, filename: str) -> Path:
    """Уникальный путь — добавить суффикс если файл существует."""
    path = directory / filename
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    i = 1
    while path.exists():
        path = directory / f"{stem}_{i}{suffix}"
        i += 1
    return path


# --- Транскрипция ---


async def transcribe(file_path: str) -> str:
    """Транскрибировать аудио через Groq Whisper."""

    def _call():
        with open(file_path, "rb") as f:
            return groq_client.audio.transcriptions.create(
                file=(Path(file_path).name, f),
                model="whisper-large-v3-turbo",
                language="ru",
            ).text

    return await asyncio.get_event_loop().run_in_executor(None, _call)


# --- Claude CLI ---


async def route_with_claude(content: str) -> str:
    """Отправить контент Claude для роутинга и получить отчёт."""
    rules = load_rules()
    tree = hub_tree()

    prompt = f"""# Правила роутинга
{rules}

# Текущая структура ~/hub/
{tree}

# Входящее сообщение
{content}

Обработай входящее сообщение по правилам роутинга. Верни краткий отчёт (3-5 строк):
- ✅ Что сделано
- 📁 Куда сохранено/мигрировано
- 🔔 Рекомендации (если есть)"""

    cmd = [
        "claude",
        "-p",
        "--model",
        CLAUDE_MODEL,
        "--allowedTools",
        ALLOWED_TOOLS,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(HUB_DIR),
    )
    stdout, stderr = await proc.communicate(input=prompt.encode())

    if proc.returncode != 0:
        err = stderr.decode()[:500]
        log.error("Claude CLI ошибка (rc=%d): %s", proc.returncode, err)
        return f"❌ Ошибка Claude: {err}"

    result = clean_output(stdout.decode().strip())
    return result or "⚠️ Claude вернул пустой ответ"


# --- Воркер очереди ---


async def queue_worker():
    """Последовательная обработка задач из очереди."""
    while True:
        chat_id, context, content = await queue.get()
        try:
            await context.bot.send_message(chat_id, "⏳ Обрабатываю...")
            report = await route_with_claude(content)
            # Telegram лимит — 4096 символов на сообщение
            for i in range(0, len(report), 4000):
                await context.bot.send_message(chat_id, report[i : i + 4000])
        except Exception as e:
            log.exception("Ошибка обработки задачи")
            try:
                await context.bot.send_message(chat_id, f"❌ Ошибка: {e}")
            except Exception:
                pass
        finally:
            queue.task_done()


async def enqueue(
    update: Update, context: ContextTypes.DEFAULT_TYPE, content: str
):
    """Добавить задачу в очередь и уведомить о позиции."""
    chat_id = update.effective_chat.id
    await queue.put((chat_id, context, content))
    qsize = queue.qsize()
    if qsize > 1:
        await update.message.reply_text(f"📥 Принято. В очереди: {qsize}")
    else:
        await update.message.reply_text("📥 Принято")


# --- Обработчики сообщений ---


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие."""
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "🧠 ADHD Hub\n\n"
        "Кидай мысли — голосом, текстом, файлами.\n"
        "Транскрибирую, классифицирую, разложу по папкам.\n\n"
        "/status — очередь и структура хаба"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статус очереди и дерево файлов."""
    if not is_allowed(update):
        return
    tree = hub_tree()
    qsize = queue.qsize()
    status = f"📊 В очереди: {qsize}" if qsize else "📊 Очередь пуста"
    await update.message.reply_text(f"{status}\n\n📂 ~/hub/\n{tree}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Текстовое сообщение → Claude роутит напрямую."""
    if not is_allowed(update):
        return
    await enqueue(update, context, update.message.text)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Голосовое → транскрипция → очередь."""
    if not is_allowed(update):
        return

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        tg_file = await context.bot.get_file(update.message.voice.file_id)
        await tg_file.download_to_drive(tmp_path)
        await update.message.reply_text("🎙 Транскрибирую...")
        text = await transcribe(tmp_path)
        await enqueue(update, context, f"[Голосовое сообщение]\n{text}")
    except Exception as e:
        log.exception("Ошибка транскрипции голосового")
        await update.message.reply_text(f"❌ Ошибка транскрипции: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Аудиофайл (отправлен как музыка) → транскрипция → очередь."""
    if not is_allowed(update):
        return

    audio = update.message.audio
    suffix = Path(audio.file_name or "audio.mp3").suffix or ".mp3"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        tg_file = await context.bot.get_file(audio.file_id)
        await tg_file.download_to_drive(tmp_path)
        await update.message.reply_text("🎙 Транскрибирую...")
        text = await transcribe(tmp_path)
        await enqueue(update, context, f"[Аудиофайл: {audio.file_name}]\n{text}")
    except Exception as e:
        log.exception("Ошибка транскрипции аудио")
        await update.message.reply_text(f"❌ Ошибка транскрипции: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Документ → определить тип, сохранить/транскрибировать, роутить."""
    if not is_allowed(update):
        return

    doc = update.message.document
    filename = doc.file_name or "unknown_file"
    ext = Path(filename).suffix.lower()

    # Аудиофайлы, отправленные как документ → транскрибировать
    is_audio = ext in AUDIO_EXTENSIONS or (
        doc.mime_type and doc.mime_type.startswith("audio/")
    )

    if is_audio:
        with tempfile.NamedTemporaryFile(
            suffix=ext or ".ogg", delete=False
        ) as tmp:
            tmp_path = tmp.name
        try:
            tg_file = await context.bot.get_file(doc.file_id)
            await tg_file.download_to_drive(tmp_path)
            await update.message.reply_text("🎙 Транскрибирую...")
            text = await transcribe(tmp_path)
            await enqueue(
                update, context, f"[Аудиофайл: {filename}]\n{text}"
            )
        except Exception as e:
            log.exception("Ошибка транскрипции документа-аудио")
            await update.message.reply_text(f"❌ Ошибка транскрипции: {e}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        return

    # Остальные документы → сохранить в inbox
    inbox = HUB_DIR / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    save_path = unique_path(inbox, filename)

    tg_file = await context.bot.get_file(doc.file_id)
    await tg_file.download_to_drive(str(save_path))

    # Текстовые форматы → прочитать содержимое для Claude
    content_preview = ""
    if ext in TEXT_EXTENSIONS:
        try:
            raw = save_path.read_text(errors="replace")[:3000]
            content_preview = f"\n\nСодержимое:\n```\n{raw}\n```"
        except Exception:
            pass

    caption = update.message.caption or ""
    prompt = (
        f"[Документ: {filename}]\n"
        f"Сохранён: {save_path}\n"
        f"Описание: {caption}"
        f"{content_preview}"
    )
    await enqueue(update, context, prompt)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Фото → сохранить в inbox, передать описание Claude."""
    if not is_allowed(update):
        return

    photo = update.message.photo[-1]  # наибольший размер
    inbox = HUB_DIR / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    save_path = inbox / f"photo_{photo.file_unique_id}.jpg"
    tg_file = await context.bot.get_file(photo.file_id)
    await tg_file.download_to_drive(str(save_path))

    caption = update.message.caption or "без описания"
    prompt = f"[Фото]\nСохранено: {save_path}\nОписание: {caption}"
    await enqueue(update, context, prompt)


# --- Инициализация ---


def init_hub():
    """Создать базовую структуру ~/hub/ если отсутствует."""
    for d in ["projects", "tasks", "notes", "inbox"]:
        (HUB_DIR / d).mkdir(parents=True, exist_ok=True)

    # Начальные файлы
    defaults = {
        "tasks/tasks.md": "# Задачи\n",
        "notes/ideas.md": "# Идеи\n",
        "notes/log.md": "# Лог\n",
    }
    for rel_path, content in defaults.items():
        full = HUB_DIR / rel_path
        if not full.exists():
            full.write_text(content)


async def post_init(app: Application):
    """Запуск при старте бота."""
    init_hub()
    task = asyncio.create_task(queue_worker(), name="queue_worker")
    task.add_done_callback(
        lambda t: log.error("Воркер упал: %s", t.exception())
        if t.exception()
        else None
    )
    log.info("ADHD Hub запущен. HUB_DIR=%s", HUB_DIR)


def main():
    app = (
        Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    )

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))

    # Контент — порядок важен
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    log.info("Запуск бота...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
