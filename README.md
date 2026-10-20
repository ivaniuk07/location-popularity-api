# Location Popularity API

Django REST API для роботи з локаціями та їхньою популярністю. Проєкт використовує PostgreSQL для основних даних, Redis для кешу та Mailpit для локальної перевірки електронних листів.

## Потрібно для запуску

- Docker Desktop із Docker Compose.
- Git, щоб клонувати репозиторій.

PostgreSQL, Redis і Python окремо встановлювати на комп’ютер не потрібно: вони запускаються в Docker.

## Перший запуск

Відкрий термінал у папці проєкту та виконай кроки по черзі.

1. Створи локальний файл налаштувань із прикладу:

   ```bash
   cp .env.example .env
   ```

2. Відкрий `.env` і заміни `DJANGO_SECRET_KEY` та `POSTGRES_PASSWORD` на власні значення. Файл `.env` містить локальні секрети — не додавай його до Git.

3. Збери образ Django:

   ```bash
   docker compose build web
   ```

4. Запусти PostgreSQL, Redis і Mailpit:

   ```bash
   docker compose up -d db redis mailpit
   ```

5. Застосуй міграції Django до PostgreSQL:

   ```bash
   docker compose run --rm web python manage.py migrate
   ```

6. Запусти вебзастосунок:

   ```bash
   docker compose up -d web
   ```

7. Створи адміністратора:

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

Після цього відкрий:

- Django admin: <http://localhost:8000/admin/>
- Mailpit — тестова поштова скринька: <http://localhost:8025/>

## Корисні команди

Переглянути стан контейнерів:

```bash
docker compose ps
```

Переглянути журнал Django:

```bash
docker compose logs -f web
```

Застосувати нові міграції:

```bash
docker compose exec web python manage.py migrate
```

Зупинити контейнери, зберігши дані PostgreSQL:

```bash
docker compose down
```

PostgreSQL зберігає дані в Docker volume `postgres_data`. Щоб видалити також цей volume і всі дані бази, використовуй `docker compose down -v`.

## Перевірка скидання пароля без фронтенду

1. Переконайся, що контейнери запущені, а потім відкрий Mailpit: <http://localhost:8025/>.
2. Надішли POST-запит на `/api/auth/password-reset/` із JSON, наприклад:

   ```json
   {"email": "адреса_користувача@example.com"}
   ```

   Для локального запиту спершу отримай CSRF-токен через `GET /api/auth/csrf/`, збережи cookie та передай значення `csrfToken` у заголовку `X-CSRFToken`.
3. Відкрий лист «Скидання пароля» в Mailpit. У ньому є `uid` і `token` для наступного запиту.
4. Надішли POST-запит на `/api/auth/password-reset/confirm/` із JSON:

   ```json
   {
     "uid": "значення_з_листа",
     "token": "значення_з_листа",
     "new_password": "Новий-Складний-Пароль-482!"
   }
   ```

   До цього запиту також передай CSRF cookie та заголовок `X-CSRFToken`. Успішна відповідь означає, що пароль змінено. Після цього перевір вхід із новим паролем через `/api/auth/login/`.

Якщо вказати адресу, якої немає в системі, API поверне таку саму відповідь, як і для наявної адреси, але лист не надішле. Токен має обмежений строк дії; після успішної зміни пароля його повторне використання відхиляється.

## Налаштування для розробки

Сервіси проєкту описані в `docker-compose.yml`: Django (`web`), PostgreSQL (`db`), Redis (`redis`) і Mailpit (`mailpit`). У контейнері Django підключається до PostgreSQL та Redis за назвами сервісів. Листи, надіслані Django під час локальної розробки, потрапляють у Mailpit і не відправляються реальним одержувачам.

Зразок змінних середовища зберігається в `.env.example`. Локальні значення та секрети зберігай у `.env`; цей файл виключений із Git.
