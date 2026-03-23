# ADHD Hub — Telegram-бот для захвата и поиска мыслей

## О проекте

- Telegram-бот с двумя режимами: capture (роутинг мыслей в файлы) и search (поиск по файлам)
- Голос/аудио → Groq Whisper → текст → Claude CLI обрабатывает
- Один пользователь (ALLOWED_USER_ID)

## Стек

- Python 3.11+, python-telegram-bot>=21.0
- Groq API (whisper-large-v3-turbo) — транскрипция
- Claude Code CLI (`claude -p`) — AI роутинг и поиск
- asyncio — очередь задач

## Команды

```bash
./run.sh                          # Запуск (загрузка .env + python bot.py)
source .env && python bot.py      # Запуск вручную
```

## Архитектура

```
bot.py                # Основной скрипт — бот, очередь, обработчики
prompts/
├── router.md         # Промпт для режима capture (роутинг мыслей)
└── search.md         # Промпт для режима search (поиск по hub)
hub/                  # Хранилище данных (создаётся автоматически)
├── projects/         # Папки проектов
├── tasks/tasks.md    # Задачи
├── notes/            # Идеи, лог, неотсортированное
└── inbox/            # Входящие файлы
```

- Промпты для Claude CLI живут в `prompts/`, не в CLAUDE.md
- `CLAUDE.md` — только для Claude Code при разработке
- Режимы пользователя: `/search` и `/capture` (дефолт)

## Стандарты кода

- Все строки на русском (логи, комментарии, сообщения бота)
- Новые промпты → в `prompts/`, загрузка через `load_prompt(name)`
- Новые режимы → добавить в `user_mode`, `queue_worker`, команду переключения
