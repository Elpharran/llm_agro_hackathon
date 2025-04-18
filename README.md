
# Agro Report Assistant 🤖🌾
Проект для хакатона LLM Coding Challenge по кейсу "Прогресс Агро"
_Автоматизация обработки полевых отчетов через Telegram-бота с использованием LLM_

## 🚀 Project Overview
**Проблема:** Агрономы присылают неструктурированные данные о выполненных работах в чат, что требует ручной систематизации и затрат времени.
**Решение:** Telegram-бот с интеграцией LLM (Mistral) для:
- Автоматического структурирования отчетов
- Валидации данных по заданным шаблонам
- Генерации готовых таблиц для главного агронома

## ✨ Key Features
- 📩 Автоматическая обработка текстовых сообщений и изображений
- 🧠 Валидация данных через Mistral API
- 📊 Генерация отчетов в структурированном виде (JSON/таблицы)
- 📁 Интеграция с базой данных для хранения истории
- 🔍 Параметрический контроль допустимых сущностей
- 📈 Дашборд для визуализации отчетов
- 🐳 Docker-контейнеризация сервисов

## ⚙️ Installation
```bash
git clone https://github.com/Elpharran/llm_agro_hackathon.git
cd agro-report-bot
```


## ⚡️ Configuration
Создать .env файл в корне проекта:

```ini
TELEGRAM_BOT_TOKEN='your telegram api token'
MISTRAL_API_KEY='your mistral api key'
ADMIN_USER_IDS='admin user ids'
ALLOWED_TELEGRAM_USER_IDS='allowed user ids'
GROUP_CHAT_ID='group chat id'
PROXY_IP='proxy ip'
PROXY_PORT='port'
PROXY_USERNAME='username
PROXY_PASSWORD='password'
DATABASE_HOST='db host'
DATABASE_PORT='db port
DATABASE_USER='db user'
DATABASE_PASSWORD='db password'
DATABASE_NAME='db name'
```
Настроить конфигурационные файлы:

```bot/src/configs/mistral_api.cfg.yml``` - параметры API (рекомендуется оставить значения по умолчанию)

```bot/src/configs/allowed_entities.json```- список разрешенных сущностей

Для полной настройки перед запуском:

    Обновите allowed_entities.json согласно требованиям агрономов


## 🛠 Usage
Запуск системы:

```bash
docker-compose up --build
```

Основные компоненты:

- Бот: Обработка сообщений в реальном времени

- Воркер: Фоновая обработка задач через RabbitMQ

- Дашборд: Веб-интерфейс по адресу http://localhost:8520

## 📂 Project Structure
```
├── app
│   └── dashboard.py
├── bot
│   ├── main.py
│   └── src
│       ├── configs
│       │   ├── allowed_entities.json
│       │   ├── logging.cfg.yml
│       │   ├── messages.json
│       │   └── mistral_api.cfg.yml
│       ├── image_utils.py
│       ├── logger_download.py
│       ├── prompts
│       │   ├── 0. system_prompt.md
│       │   ├── 1. initial.md
│       │   ├── 2. final.md
│       │   ├── 3. validation_fields.md
│       │   └── 4. validation_json.md
│       ├── report_builder.py
│       ├── telegram_bot.py
│       ├── utils.py
│       └── worker.py
├── db
│   ├── connection.py
│   ├── interaction.py
│   └── models.py
├── devops
│   ├── app.DockerFile
│   └── worker.DockerFile
├── docker-compose.yml
├── entrypoint.sh
├── requirements.bot.txt
└── requirements.worker.txt
```
## 🌱 Contributing
- Форкните репозиторий

- Создайте ветку для фичи/исправления

- Добавьте тесты (при необходимости)

- Отправьте Pull Request

