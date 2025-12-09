# RAG Lab Deployment Guide

Полностью автоматизированное развертывание на Google Cloud Platform.

## 🚀 Быстрый старт

### Шаг 1: Настройка инфраструктуры (один раз)

```bash
cd deployment
chmod +x *.sh
./setup-infrastructure.sh
```

**Что вводить:**
- GCP Project ID
- GCP Region (по умолчанию: us-central1)

**Что создается автоматически:**
- ✅ Включение всех необходимых APIs
- ✅ Cloud Storage bucket
- ✅ Cloud SQL PostgreSQL instance
- ✅ Service Account с правами
- ✅ Генерация пароля БД
- ✅ Файл `.env` с конфигурацией
- ✅ Файл `credentials.txt` с паролями

**Время:** ~10-15 минут

### Шаг 2: Развертывание приложения

```bash
./deploy-cloudrun.sh
```

**Что делается:**
- ✅ Build Docker image через Cloud Build
- ✅ Deploy на Cloud Run
- ✅ Настройка env variables
- ✅ Проверка работоспособности
- ✅ Вывод URL сервиса

**Время:** ~3-5 минут

### Шаг 3: Тестирование

```bash
SERVICE_URL="https://raglab-xxx-uc.a.run.app"  # Из вывода deploy

# Health check
curl $SERVICE_URL/health

# Загрузка PDF
curl -X POST $SERVICE_URL/v1/documents/upload -F "file=@document.pdf"

# Запрос
curl -X POST $SERVICE_URL/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is RAG?", "top_k": 3}'
```

## 📋 Требования

- `gcloud` CLI установлен и авторизован (`gcloud auth login`)
- GCP проект создан
- Billing включен

## 📝 Скрипты

### `setup-infrastructure.sh`

Создает всю необходимую инфраструктуру GCP.

**Создает:**
- Cloud Storage bucket (тот же регион что Cloud Run)
- Cloud SQL PostgreSQL 15 (db-f1-micro)
- Database + user
- Service Account с правами:
  - `aiplatform.user` (Vertex AI)
  - `storage.objectAdmin` (Cloud Storage)
  - `cloudsql.client` (Cloud SQL)

**Выходные файлы:**
- `.env` - конфигурация
- `deployment/credentials.txt` - пароли (НЕ коммитить!)
- `.env.template` - шаблон

**Использование:**
```bash
./setup-infrastructure.sh

# Или с переменными:
GCP_PROJECT_ID="my-project" GCP_REGION="us-central1" ./setup-infrastructure.sh
```

### `deploy-cloudrun.sh`

Развертывает приложение на Cloud Run.

**Требует:**
- Запущенный `setup-infrastructure.sh`
- Файл `.env`

**Конфигурация:**
- Memory: 1Gi
- CPU: 1 vCPU
- Min instances: 0 (scale to zero)
- Max instances: 10
- Timeout: 300s
- Concurrency: 80

**Выходные файлы:**
- `deployment/deployment-info.txt` - информация о deployment

### `teardown.sh`

⚠️ **ОПАСНО**: Удаляет ВСЕ ресурсы!

```bash
./teardown.sh
# Введите 'DELETE-ALL' для подтверждения
```

**Удаляет:**
- Cloud Run service
- Cloud Storage bucket (все файлы!)
- Cloud SQL instance (все данные!)
- Service Account
- Локальные `.env` и `credentials.txt`

## 📂 Создаваемые файлы

### `.env`
```bash
GCP_PROJECT_ID="your-project"
GCP_REGION="us-central1"
GCS_BUCKET="raglab-documents-your-project"
DATABASE_URL="postgresql://raglab:password@10.1.2.3:5432/raglab"
SERVICE_ACCOUNT_EMAIL="raglab-sa@your-project.iam.gserviceaccount.com"
```

### `deployment/credentials.txt`
Секретные данные (добавлен в `.gitignore`):
- Пароль БД
- Connection strings
- Private IPs

### `deployment/deployment-info.txt`
Информация о deployment:
- Service URL
- Container image
- Configuration
- Timestamp

## 💰 Стоимость

### Development (monthly)
- Cloud Run: $0-5 (scale to zero)
- Cloud SQL (db-f1-micro): ~$7
- Cloud Storage: ~$0.20 for 10GB
- Vertex AI: Pay per use

**Итого:** ~$7-12/месяц

### Production (monthly)
- Cloud Run: $20-50
- Cloud SQL (db-n1-standard-1): ~$50
- Cloud Storage: ~$0.20/GB

## 🔧 Troubleshooting

### Setup fails: "APIs not enabled"
Подождите 1-2 минуты после enable, затем повторите.

### Cloud SQL creation slow
Нормально. Занимает 5-10 минут.

### Permission denied
Проверьте права Service Account:
```bash
gcloud projects get-iam-policy $GCP_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:raglab-sa@*"
```

### Health check fails
Проверьте логи:
```bash
gcloud run services logs read raglab --region us-central1 --limit 50
```

Частые причины:
- Неправильный `DATABASE_URL`
- Отсутствует `GCS_BUCKET`
- Vertex AI API не включен

### Database connection error
Проверьте private IP:
```bash
gcloud sql instances describe raglab-db \
  --format="value(ipAddresses[0].ipAddress)"
```

## 🔒 Безопасность

- ❌ **Никогда не коммитьте** `credentials.txt` или `.env`
- ✅ `.gitignore` автоматически исключает эти файлы
- ✅ Пароль БД генерируется автоматически (32 символа)
- ✅ Service Account с минимальными правами
- ✅ Cloud Storage с uniform bucket-level access
- ✅ Database с private IP (нет публичного доступа)

## 📊 Мониторинг

### Просмотр логов
```bash
# Real-time logs
gcloud run services logs tail raglab --region us-central1

# Last 100 lines
gcloud run services logs read raglab --region us-central1 --limit 100

# Filter errors
gcloud run services logs read raglab --region us-central1 | grep ERROR
```

### Метрики
```bash
# В GCP Console:
# Cloud Run > raglab > Metrics
```

## 🔄 Обновление приложения

После изменения кода:

```bash
cd deployment
./deploy-cloudrun.sh
```

Cloud Run автоматически:
- Билдит новый image
- Деплоит без downtime
- Переключает трафик на новую версию

## 🎯 Следующие шаги

После deployment:
1. Загрузите тестовые документы
2. Проверьте все endpoints
3. Настройте monitoring (опционально)
4. Настройте CI/CD (опционально)
5. Добавьте authentication (опционально)

## 📚 Дополнительно

Для детальной информации об архитектуре см. [главный README](../README.md).
