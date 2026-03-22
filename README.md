# telegram to matrix and vice versa bridge bot

бот пересылает сообщения между telegram и matrix в обе стороны.

## требования

- python 3.10+
- matrix synapse сервер
- telegram bot token
- xray с socks5 inbound (на сервере, для доступа к telegram)

## установка

```bash
git clone https://github.com/youruser/tg-matrix-bridge
cd tg-matrix-bridge
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

## настройка .env

```env
TELEGRAM_BOT_TOKEN=токен от botfather
TELEGRAM_ADMIN_ID=числовой telegram id админа
TELEGRAM_ADMIN_LOGIN=telegram username админа (без @)
ADMIN_MATRIX_LOGIN=matrix логин админа (без @ и домена)
MATRIX_HOMESERVER=
MATRIX_USER=
MATRIX_PASSWORD=
MATRIX_DOMAIN=
PROXY_HOST=127.0.0.1
PROXY_PORT=10808
```

опциональные переменные:
```env
DB_PATH=bridge.db
LOG_FILE=bot.log
TOKEN_TTL_MINUTES=60
DEBUG=false
```

## деплой на сервер (systemd)

```bash
sudo nano /etc/systemd/system/tg-matrix-bridge.service
```

```ini
[Unit]
Description=Telegram Matrix Bridge Bot
After=network.target matrix-synapse.service xray.service

[Service]
Type=simple
User=oleg
WorkingDirectory=/opt/tg-matrix-bridge
ExecStart=/usr/bin/python3 /opt/tg-matrix-bridge/bot.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/tg-matrix-bridge/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable tg-matrix-bridge
sudo systemctl start tg-matrix-bridge
```

## настройка xray socks5 (на сервере)

добавь в `/usr/local/etc/xray/config.json`:

```json
{
  "tag": "socks-bridge",
  "port": 10808,
  "protocol": "socks",
  "settings": { "auth": "noauth", "udp": true },
  "listen": "127.0.0.1"
}
```

routing правило:
```json
{ "type": "field", "inboundTag": ["socks-bridge"], "outboundTag": "vless-out" }
```

---

## роли пользователей

**admin** — указывается в `.env`, привязан автоматически без подтверждения, имеет все права matrix_authorized

**matrix_authorized** — добавляется через `addUser`, должен подтвердить привязку через `!confirm` в matrix, может добавлять пользователей и управлять получателями

**tg_only** — добавляется через `!addRecipient`, только telegram, может выбирать получателей и писать сообщения

---

## команды telegram

### matrix_authorized и admin

| команда                            | описание |
|                                    | |
| `/addUser <tgLogin> <matrixLogin>` | добавить matrix_authorized пользователя |
| `/addRecipient <matrixLogin>`      | добавить получателя по matrix логину |
| `/removeRecipient <tgLogin>`       | удалить получателя из своего списка |
| `/changeRecipient <matrixLogin>`   | выбрать получателя и начать переписку |
| `/whoRecipient`                    | показать текущего получателя |
| `/listRecipient`                   | список своих получателей |
| `/help`                            | справка |

### tg_only

| команда                         | описание  |
|                                 | |
| `/changeRecipient <matrixLogin>`| выбрать получателя и начать переписку |
| `/whoRecipient`                 | показать текущего получателя |
| `/listRecipient`                | список тех кто тебя добавил |
| `/help`                         | справка |

## команды matrix (начинаются с !)

| команда                             | описание |
|                                     | |
| `!addUser <tgLogin> <matrixLogin>`  | добавить matrix_authorized пользователя |
| `!addRecipient <tgLogin>`           | добавить tg_only получателя |
| `!removeRecipient <tgLogin>`        | удалить получателя из своего списка |
| `!changeRecipient <tgLogin>`        | выбрать получателя и начать переписку |
| `!whoRecipient`                     | показать текущего получателя |
| `!listRecipient`                    | список своих получателей |
| `!confirm <токен>`                  | привязать telegram аккаунт |
| `!help`                             | справка |


## сценарии использования

### первый запуск

1. заполни `.env` — укажи telegram id, username и matrix логин админа
2. запусти бота — admin сразу считается привязанным
3. напиши `/start` в telegram

### добавить matrix_authorized пользователя

1. `/addUser valeria valeria` в telegram или `!addUser valeria valeria` в matrix
2. бот выдаст токен — передай его пользователю
3. пользователь пишет `/start` в telegram, вводит свой matrix логин, получает токен
4. пользователь пишет `!confirm <токен>` боту в matrix
5. аккаунт привязан, пользователь добавлен в твой список получателей

### добавить tg_only пользователя

1. `!addRecipient cartacartel` в matrix
2. пользователь пишет `/start` в telegram — получает доступ

### переписка

- telegram → matrix: `/changeRecipient <matrixLogin>`, затем пиши текст
- matrix → telegram: `!changeRecipient <tgLogin>`, затем пиши текст
- любая команда останавливает режим переписки

### формат сообщений

- из telegram в matrix: `@username: текст`
- из matrix в telegram: `login: текст` (только логин, без домена)