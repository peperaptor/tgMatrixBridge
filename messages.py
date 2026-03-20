#common
no_access = "нет доступа"
error_send = "ошибка отправки: {error}"
only_text = "только текстовые сообщения"

#/start
start_tg_only = (
    "доступные команды:\n"
    "/changeRecipient <matrixLogin> - выбрать получателя\n"
    "/whoRecipient - текущий получатель\n"
    "/listRecipient - список получателей\n"
    "/help - справка"
)
start_authorized = "аккаунт привязан к {matrix_id}, подтвердите токен в матриксе (вам его отправит тот, кто зарегестрировал)\n\n/help - список команд"
start_not_linked = (
    "введите логин вашего matrix аккаунта (без @ и домена)\n"
    "пример: username"
)
start_already_linked = "аккаунт уже привязан к {matrix_id}"

#linking
link_bad_login = "неверный формат, введите только логин без @ и домена"
link_taken = "этот matrix аккаунт уже привязан к другому пользователю"
link_instruction = "напишите боту в matrix (@bridge_bot:{domain}):"
link_token = "!confirm {token}"
link_confirmed = "matrix аккаунт привязан: {matrix_id}\nтеперь вы можете добавлять пользователей"
link_bad_token = "неверный или устаревший токен"

#/addUser
adduser_usage = "использование: /addUser <tgLogin> <matrixLogin>"
adduser_bad_tg = "неверный telegram username"
adduser_bad_matrix = "неверный matrix логин"
adduser_success = "пользователь @{tg} добавлен\nmatrix: {matrix_id}\nон автоматически добавлен в ваш список получателей"
adduser_need_confirm = (
    "пользователь @{tg} создан\n"
    "попросите его написать /start боту в телеграме и подтвердить матрикс аккаунт токеном в матриксе (@bridge_bot:{domain}:\n"
    "!confirm {token}"
)

#/addRecipient
addrecipient_usage = "использование: /addRecipient <matrixLogin>"
addrecipient_bad = "неверный matrix логин"
addrecipient_success = "получатель добавлен: {matrix_id}"
addrecipient_not_found = "пользователь с matrix id {matrix_id} не найден среди matrix_authorized"

#/listRecipient
list_header = "получатели:"
list_item_full = "  @{tg} - {matrix_id}"
list_item_tg_only = "  @{tg} - (без matrix)"
list_empty = "список получателей пуст"

#/changeRecipient
change_usage = "использование: /changeRecipient <matrixLogin>"
change_bad = "неверный matrix логин"
change_success = "активный получатель: {matrix_id}\nотправляйте сообщения - они будут пересылаться"
change_not_in_list = "этот получатель не в вашем списке. Сначала добавьте через /addRecipient"

#/whoRecipient
who_none = "активный получатель не выбран"
who_matrix = "активный получатель: {matrix_id}"
who_tg = "активный получатель: @{tg_login}"

#входящие из matrix
incoming_from_matrix = "{matrix_id}: {text}"

#входящие из telegram
incoming_from_tg = "@{tg_login}: {text}"

#/help - tg_only
help_tg_only = (
    "команды:\n"
    "/changeRecipient <matrixLogin> - выбрать получателя и начать переписку\n"
    "/whoRecipient - показать текущего получателя\n"
    "/listRecipient - список всех получателей\n"
    "/help - эта справка\n\n"
    "отправляйте текст когда выбран получатель - сообщение будет переслано"
)

#/help - matrix_authorized
help_matrix_authorized = (
    "команды telegram:\n"
    "/addUser <tgLogin> <matrixLogin> - добавить matrix_authorized пользователя\n"
    "/addRecipient <matrixLogin> - добавить получателя по matrix логину\n"
    "/removeRecipient <tgLogin> - удалить получателя из списка\n"
    "/changeRecipient <matrixLogin> - выбрать получателя и начать переписку\n"
    "/whoRecipient - показать текущего получателя\n"
    "/listRecipient - список всех получателей\n"
    "/help - эта справка\n\n"
    "команды matrix (начинаются с !):\n"
    "!addUser <tgLogin> <matrixLogin> - добавить matrix_authorized пользователя\n"
    "!addRecipient <tgLogin> - добавить tg_only получателя\n"
    "!removeRecipient <tgLogin> - удалить получателя из списка\n"
    "!changeRecipient <tgLogin> - выбрать получателя и начать переписку\n"
    "!whoRecipient - показать текущего получателя\n"
    "!listRecipient - список всех получателей\n"
    "!help - эта справка"
)

#matrix команды
matrix_start = (
    "бот-мост между matrix и telegram\n\n"
    "если вас добавили через addUser:\n"
    "1. напишите боту /start в telegram\n"
    "2. введите логин matrix аккаунта\n"
    "3. введите здесь: !confirm <токен>\n\n"
    "!help -список команд"
)
matrix_confirm_success = "аккаунт привязан"
matrix_bad_token = "неверный или устаревший токен"
matrix_no_access = "нет доступа"
matrix_adduser_usage = "использование: !addUser <tgLogin> <matrixLogin>"
matrix_adduser_bad_tg = "неверный telegram username"
matrix_adduser_bad_matrix = "неверный matrix логин"
matrix_adduser_success = "пользователь @{tg} добавлен, matrix: {matrix_id}"
matrix_addrecipient_usage = "использование: !addRecipient <tgLogin>"
matrix_addrecipient_bad = "неверный telegram username"
matrix_addrecipient_success = "получатель @{tg} добавлен"
matrix_change_usage = "использование: !changeRecipient <tgLogin>"
matrix_change_bad = "неверный telegram username"
matrix_change_not_found = "пользователь @{tg} не найден в получателях"
matrix_change_success = "активный получатель: @{tg}\nотправляйте сообщения"
matrix_who_none = "активный получатель не выбран"
matrix_who = "активный получатель: @{tg_login}"
matrix_list_header = "получатели:"
matrix_list_item = "  @{tg}"
matrix_list_empty = "список получателей пуст"
matrix_help = (
    "команды:\n"
    "!addUser <tgLogin> <matrixLogin> - добавить matrix_authorized пользователя\n"
    "!addRecipient <tgLogin> - добавить tg_only получателя\n"
    "!changeRecipient <tgLogin> - выбрать получателя\n"
    "!whoRecipient - текущий получатель\n"
    "!listRecipient - список получателей\n"
    "!help - эта справка"
)

#/removeRecipient
removerecipient_usage = "использование: /removeRecipient <tgLogin>"
removerecipient_bad = "неверный telegram username"
removerecipient_success = "получатель @{tg} удалён из вашего списка"
removerecipient_not_found = "получатель @{tg} не найден в вашем списке"
matrix_removerecipient_usage = "использование: !removeRecipient <tgLogin>"
matrix_removerecipient_success = "получатель @{tg} удалён из вашего списка"
matrix_removerecipient_not_found = "получатель @{tg} не найден в вашем списке"