#!/bin/bash

python bot/main.py &
TELEGRAM_BOT_PID=$!

if [ -z "$TELEGRAM_BOT_PID" ]; then
  echo "❌ Ошибка: Telegram-бот не запустился."
  exit 1
fi
echo "✅ Telegram-бот запущен с PID $TELEGRAM_BOT_PID."

python -c "from db.models import create_all; create_all()"
if [ $? -ne 0 ]; then
  echo "❌ Ошибка: не удалось инициализировать базу данных."
  kill -TERM $TELEGRAM_BOT_PID
  exit 1
fi

echo "🚀 Запускаем async worker_v1..."
python bot/src/worker.py worker_v1 &
WORKER1_PID=$!

echo "🚀 Запускаем async worker_v2..."
python bot/src/worker.py worker_v2 &
WORKER2_PID=$!

streamlit run app/dashboard.py --server.port=8520 &
STREAMLIT_PID=$!
if [ -z "$STREAMLIT_PID" ]; then
  echo "❌ Ошибка: Streamlit не запустился."
  exit 1
fi

echo "Streamlit запущен с PID $STREAMLIT_PID."

if [ -z "$WORKER1_PID" ] || [ -z "$WORKER2_PID" ]; then
  echo "❌ Ошибка: один из воркеров не запустился."
  kill -TERM $TELEGRAM_BOT_PID
  kill -TERM $STREAMLIT_PID
  [ ! -z "$WORKER1_PID" ] && kill -TERM $WORKER1_PID
  [ ! -z "$WORKER2_PID" ] && kill -TERM $WORKER2_PID
  exit 1
fi

echo "✅ Все сервисы запущены: Telegram Bot, Worker v1, Worker v2."


wait
