#!/bin/bash
# Запуск ADHD Hub с загрузкой переменных окружения
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Загрузить .env если существует
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Добавить типичные пути к claude CLI
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/bot.py"
