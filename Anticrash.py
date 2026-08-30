# ============================================================
# DISCORD GUARD / ANTICRASH
# Python 3.12
# disnake
#
# Установка:
# py -3.12 -m pip install -U disnake
#
# Команда:
# /guard
# ============================================================

import json
import io
import time
from pathlib import Path
from collections import defaultdict, deque
from datetime import datetime, timezone

import disnake
from disnake.ext import commands


# ============================================================
# TOKEN
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN", "")

# Пользователь, которому разрешён полный доступ к Guard
# вместе с владельцем сервера.
AUTHORIZED_USER_ID = 1121847543354101932

# Формат переносимого шаблона сервера
BACKUP_FORMAT = "guard-server-template-v1"


# ============================================================
# DATABASE
# ============================================================

DATA_FILE = Path("guard_data.json")


# ============================================================
# ACTIONS
# ============================================================

ACTIONS = {
    "ban": "Бан участников",
    "kick": "Кик участников",

    "channel_create": "Создание каналов",
    "channel_delete": "Удаление каналов",

    "role_create": "Создание ролей",
    "role_delete": "Удаление ролей",
    "role_update": "Изменение ролей",

    "member_role_update": "Выдача/снятие ролей",
    "dangerous_role_grant": "Выдача опасных ролей",

    "webhook_create": "Создание вебхуков",
    "webhook_update": "Изменение вебхуков",
    "webhook_delete": "Удаление вебхуков",

    "nickname": "Изменение ника",

    "voice_mute": "Мьют в голосовом",
    "voice_deaf": "Мьют наушников",
    "voice_move": "Перемещение участников",

    "guild_update": "Изменение сервера",
    "overwrite_update": "Изменение прав каналов",
}


# ============================================================
# AUDIT LOG ACTIONS
# ============================================================

AUDIT_ACTION_MAP = {
    "ban": "ban",
    "kick": "kick",

    "channel_create": "channel_create",
    "channel_delete": "channel_delete",

    "role_create": "role_create",
    "role_delete": "role_delete",
    "role_update": "role_update",

    "member_role_update": "member_role_update",

    "webhook_create": "webhook_create",
    "webhook_update": "webhook_update",
    "webhook_delete": "webhook_delete",

    "member_move": "voice_move",

    "guild_update": "guild_update",

    "overwrite_create": "overwrite_update",
    "overwrite_update": "overwrite_update",
    "overwrite_delete": "overwrite_update",
}


# ============================================================
# DEFAULT CONFIG
# ============================================================

def default_config():
    return {
        # Guard
        "enabled": True,

        # Сколько секунд считается одно окно лимита
        "window": 60,

        # Какая роль выдаётся при карантине
        "punishment_role": None,

        # Канал логов
        "logs_channel": None,

        # Роли и их лимиты
        "roles": {},

        # ----------------------------------------------------
        # Anti Bot
        # ----------------------------------------------------

        "anti_bot": {
            "enabled": False,
        },

        # ----------------------------------------------------
        # Anti Raid
        # ----------------------------------------------------

        "anti_raid": {
            "enabled": False,

            # Сколько входов за окно считать рейдом
            "threshold": 5,

            # Окно в секундах
            "window": 10,

            # quarantine / kick
            "action": "quarantine",
        },

        # ----------------------------------------------------
        # Quarantine
        # ----------------------------------------------------

        "quarantine": {},
    }


# ============================================================
# LOAD DATABASE
# ============================================================

def load_data():
    if not DATA_FILE.exists():
        return {}

    try:
        with open(
            DATA_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if isinstance(data, dict):
            return data

    except Exception as error:
        print(
            "[DATABASE] Ошибка:",
            repr(error),
        )

    return {}


def save_data():
    try:
        with open(
            DATA_FILE,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                DATA,
                file,
                ensure_ascii=False,
                indent=4,
            )

    except Exception as error:
        print(
            "[DATABASE] Ошибка сохранения:",
            repr(error),
        )


DATA = load_data()


# ============================================================
# GET CONFIG
# ============================================================

def get_config(
    guild_id: int,
):
    guild_id = str(guild_id)

    if guild_id not in DATA:
        DATA[guild_id] = default_config()
        save_data()

    config = DATA[guild_id]

    config.setdefault(
        "enabled",
        True,
    )

    config.setdefault(
        "window",
        60,
    )

    config.setdefault(
        "punishment_role",
        None,
    )

    config.setdefault(
        "logs_channel",
        None,
    )

    config.setdefault(
        "roles",
        {},
    )

    config.setdefault(
        "anti_bot",
        {
            "enabled": False,
        },
    )

    config["anti_bot"].setdefault(
        "enabled",
        False,
    )

    config.setdefault(
        "anti_raid",
        {
            "enabled": False,
            "threshold": 5,
            "window": 10,
            "action": "quarantine",
        },
    )

    config["anti_raid"].setdefault(
        "enabled",
        False,
    )

    config["anti_raid"].setdefault(
        "threshold",
        5,
    )

    config["anti_raid"].setdefault(
        "window",
        10,
    )

    config["anti_raid"].setdefault(
        "action",
        "quarantine",
    )

    config.setdefault(
        "quarantine",
        {},
    )

    return config


# ============================================================
# ROLE CONFIG
# ============================================================

def get_role_config(
    guild_id: int,
    role_id: int,
):
    config = get_config(
        guild_id
    )

    role_id = str(
        role_id
    )

    if role_id not in config["roles"]:

        config["roles"][role_id] = {
            "name": "",
            "limits": {},
        }

    role_config = config["roles"][role_id]

    role_config.setdefault(
        "name",
        "",
    )

    role_config.setdefault(
        "limits",
        {},
    )

    for action in ACTIONS:

        role_config["limits"].setdefault(
            action,
            0,
        )

    return role_config


# ============================================================
# BOT
# ============================================================

intents = disnake.Intents.all()

bot = commands.InteractionBot(
    intents=intents,
)


# ============================================================
# ACTION HISTORY
# ============================================================

ACTION_HISTORY = defaultdict(
    lambda: defaultdict(
        lambda: defaultdict(
            deque
        )
    )
)


# ============================================================
# PROCESSED AUDIT LOGS
# ============================================================

PROCESSED_AUDIT = set()


# ============================================================
# PUNISHING MEMBERS
# ============================================================

PUNISHING = set()


# ============================================================
# ANTI RAID HISTORY
# ============================================================

RAID_HISTORY = defaultdict(
    deque
)


# ============================================================
# HELPERS
# ============================================================

def is_owner(
    guild: disnake.Guild,
    member: disnake.Member,
):
    return member.id == guild.owner_id


def is_guard_admin(
    guild: disnake.Guild,
    member: disnake.Member,
):
    """Владелец сервера или доверенный пользователь."""
    return (
        member.id == guild.owner_id
        or member.id == AUTHORIZED_USER_ID
    )


def action_label(
    action: str,
):
    return ACTIONS.get(
        action,
        action,
    )


def get_member_limit(
    guild: disnake.Guild,
    member: disnake.Member,
    action: str,
):
    """
    Если у пользователя несколько Guard-ролей,
    используется самый большой разрешённый лимит.

    0  = запрещено
    5  = максимум 5
    -1 = безлимит
    """

    config = get_config(
        guild.id
    )

    limits = []

    for role in member.roles:

        role_config = config[
            "roles"
        ].get(
            str(role.id)
        )

        if not role_config:
            continue

        value = role_config[
            "limits"
        ].get(
            action,
            0,
        )

        try:
            value = int(value)
        except Exception:
            value = 0

        limits.append(
            value
        )

    if not limits:
        return None

    if -1 in limits:
        return -1

    return max(
        limits
    )


def clean_history(
    guild_id: int,
    action: str,
    member_id: int,
    window: int,
):
    history = ACTION_HISTORY[
        guild_id
    ][
        action
    ][
        member_id
    ]

    now = time.time()

    while history:

        if now - history[0] <= window:
            break

        history.popleft()


def get_access_roles(
    guild: disnake.Guild,
    action: str,
):
    config = get_config(
        guild.id
    )

    result = []

    for role_id in config[
        "roles"
    ]:

        role_config = config[
            "roles"
        ][role_id]

        limit = role_config[
            "limits"
        ].get(
            action,
            0,
        )

        if int(limit) == 0:
            continue

        role = guild.get_role(
            int(role_id)
        )

        if role:
            result.append(
                role
            )

    return result


def roles_mentions(
    roles,
):
    if not roles:
        return "Нет"

    return ", ".join(
        role.mention
        for role in roles
    )


# ============================================================
# LOGS
# ============================================================

async def send_log(
    guild: disnake.Guild,
    title: str,
    description: str,
    color=disnake.Color.blurple(),
):
    config = get_config(
        guild.id
    )

    channel_id = config.get(
        "logs_channel"
    )

    if not channel_id:
        return

    channel = guild.get_channel(
        int(channel_id)
    )

    if channel is None:
        return

    embed = disnake.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=disnake.utils.utcnow(),
    )

    embed.set_footer(
        text=f"Guard • {guild.name}",
    )

    try:

        await channel.send(
            embed=embed
        )

    except Exception as error:

        print(
            "[LOG ERROR]",
            repr(error),
        )


# ============================================================
# QUARANTINE MESSAGE
# ============================================================

def quarantine_embed(
    guild: disnake.Guild,
    member: disnake.Member | None,
    reason: str,
):
    mention = (
        member.mention
        if member
        else
        "Пользователь"
    )

    embed = disnake.Embed(
        title="Guard • Карантин",
        description=(
            f"{mention} был отправлен в карантин.\n\n"
            f"**Причина:**\n"
            f"{reason}\n\n"
            "Все старые роли пользователя сохранены.\n"
            "Владелец сервера может восстановить их "
            "кнопкой ниже."
        ),
        color=disnake.Color.red(),
        timestamp=disnake.utils.utcnow(),
    )

    if member:

        embed.add_field(
            name="Пользователь",
            value=(
                f"{member.mention}\n"
                f"`{member.id}`"
            ),
            inline=False,
        )

    return embed


# ============================================================
# QUARANTINE VIEW
# ============================================================

class QuarantineView(
    disnake.ui.View
):
    def __init__(
        self,
        guild_id: int,
        member_id: int,
    ):
        super().__init__(
            timeout=None
        )

        self.guild_id = guild_id
        self.member_id = member_id

    @disnake.ui.button(
        label="Снять карантин",
        style=disnake.ButtonStyle.success,
        custom_id="guard_quarantine_restore",
    )
    async def restore_button(
        self,
        button: disnake.ui.Button,
        interaction: disnake.MessageInteraction,
    ):
        guild = interaction.guild

        if guild is None:
            return

        if not is_guard_admin(
            guild,
            interaction.author,
        ):

            await interaction.response.send_message(
                "Только владелец сервера или доверенный пользователь может снять карантин.",
                ephemeral=True,
            )

            return

        config = get_config(
            guild.id
        )

        quarantine = config[
            "quarantine"
        ].get(
            str(self.member_id)
        )

        if quarantine is None:

            await interaction.response.send_message(
                "Этот карантин уже снят или запись отсутствует.",
                ephemeral=True,
            )

            return

        member = guild.get_member(
            self.member_id
        )

        if member is None:

            await interaction.response.send_message(
                "Пользователь не находится на сервере.",
                ephemeral=True,
            )

            return

        bot_member = guild.me

        if bot_member is None:
            return

        old_role_ids = quarantine.get(
            "roles",
            [],
        )

        restore_roles = []

        for role_id in old_role_ids:

            role = guild.get_role(
                int(role_id)
            )

            if role is None:
                continue

            if role.is_default():
                continue

            if role.managed:
                continue

            # Discord не позволит боту выдать роль
            # выше/на уровне высшей роли бота.
            if role >= bot_member.top_role:
                continue

            restore_roles.append(
                role
            )

        try:

            await member.edit(
                roles=restore_roles,
                reason="Guard: снятие карантина",
            )

        except disnake.Forbidden:

            await interaction.response.send_message(
                (
                    "Не удалось восстановить роли. "
                    "Проверь иерархию ролей бота."
                ),
                ephemeral=True,
            )

            return

        except Exception as error:

            await interaction.response.send_message(
                f"Ошибка: `{error}`",
                ephemeral=True,
            )

            return

        config[
            "quarantine"
        ].pop(
            str(self.member_id),
            None,
        )

        save_data()

        old_message = interaction.message

        disabled_view = QuarantineView(
            self.guild_id,
            self.member_id,
        )

        for item in disabled_view.children:

            item.disabled = True

            if isinstance(
                item,
                disnake.ui.Button
            ):
                item.label = "Карантин снят"

        embed = disnake.Embed(
            title="Guard • Карантин снят",
            description=(
                f"{member.mention} больше не находится "
                "в карантине.\n\n"
                "Сохранённые роли восстановлены."
            ),
            color=disnake.Color.green(),
            timestamp=disnake.utils.utcnow(),
        )

        try:

            await old_message.edit(
                embed=embed,
                view=disabled_view,
            )

        except Exception:
            pass

        await interaction.response.send_message(
            (
                f"Карантин с {member.mention} снят.\n"
                f"Восстановлено ролей: "
                f"`{len(restore_roles)}`"
            ),
            ephemeral=True,
        )

        await send_log(
            guild,
            "Guard • Карантин снят",
            (
                f"**Пользователь:** {member.mention}\n"
                f"**Снял:** {interaction.author.mention}\n"
                f"**Восстановлено ролей:** "
                f"`{len(restore_roles)}`"
            ),
            disnake.Color.green(),
        )


# ============================================================
# SEND QUARANTINE
# ============================================================

async def send_quarantine_message(
    guild: disnake.Guild,
    member: disnake.Member,
    reason: str,
):
    config = get_config(
        guild.id
    )

    channel_id = config.get(
        "logs_channel"
    )

    if not channel_id:
        return

    channel = guild.get_channel(
        int(channel_id)
    )

    if channel is None:
        return

    embed = quarantine_embed(
        guild,
        member,
        reason,
    )

    try:

        message = await channel.send(
            embed=embed,
            view=QuarantineView(
                guild.id,
                member.id,
            ),
        )

        config[
            "quarantine"
        ][
            str(member.id)
        ][
            "message_id"
        ] = message.id

        save_data()

    except Exception as error:

        print(
            "[QUARANTINE MESSAGE ERROR]",
            repr(error),
        )


# ============================================================
# QUARANTINE MEMBER
# ============================================================

async def quarantine_member(
    guild: disnake.Guild,
    member: disnake.Member,
    reason: str,
):
    if member.id in PUNISHING:
        return

    if member.id == guild.owner_id:
        return

    bot_member = guild.me

    if bot_member is None:
        return

    PUNISHING.add(
        member.id
    )

    try:

        config = get_config(
            guild.id
        )

        # Если уже в карантине
        if str(member.id) in config[
            "quarantine"
        ]:
            return

        # ----------------------------------------------------
        # Сохраняем старые роли
        # ----------------------------------------------------

        old_roles = []

        for role in member.roles:

            if role.is_default():
                continue

            old_roles.append(
                role.id
            )

        # ----------------------------------------------------
        # Роль карантина
        # ----------------------------------------------------

        punishment_role_id = config.get(
            "punishment_role"
        )

        punishment_role = None

        if punishment_role_id:

            punishment_role = guild.get_role(
                int(punishment_role_id)
            )

        # ----------------------------------------------------
        # Сохраняем карантин
        # ----------------------------------------------------

        config[
            "quarantine"
        ][
            str(member.id)
        ] = {
            "roles": old_roles,
            "reason": reason,
            "created_at": int(
                time.time()
            ),
            "message_id": None,
        }

        save_data()

        # ----------------------------------------------------
        # Снимаем роли
        # ----------------------------------------------------

        new_roles = []

        if punishment_role:

            if (
                not punishment_role.managed
                and punishment_role < bot_member.top_role
            ):
                new_roles.append(
                    punishment_role
                )

        try:

            await member.edit(
                roles=new_roles,
                reason=(
                    f"Guard карантин: {reason}"
                ),
            )

        except Exception as error:

            print(
                "[QUARANTINE ROLE ERROR]",
                repr(error),
            )

        # ----------------------------------------------------
        # Отправляем сообщение
        # ----------------------------------------------------

        await send_quarantine_message(
            guild,
            member,
            reason,
        )

        # ----------------------------------------------------
        # Лог
        # ----------------------------------------------------

        await send_log(
            guild,
            "Guard • Пользователь отправлен в карантин",
            (
                f"**Пользователь:** {member.mention}\n"
                f"**ID:** `{member.id}`\n"
                f"**Причина:** {reason}\n"
                f"**Сохранено ролей:** `{len(old_roles)}`\n"
                f"**Роль карантина:** "
                f"{punishment_role.mention if punishment_role else 'не настроена'}"
            ),
            disnake.Color.red(),
        )

    finally:

        PUNISHING.discard(
            member.id
        )


# ============================================================
# REGISTER ACTION
# ============================================================

async def register_action(
    guild: disnake.Guild,
    member: disnake.Member,
    action: str,
    amount: int = 1,
):
    config = get_config(
        guild.id
    )

    if not config.get(
        "enabled",
        True,
    ):
        return

    if member.id == guild.owner_id:
        return

    limit = get_member_limit(
        guild,
        member,
        action,
    )

    # Ничего не настроено для пользователя
    if limit is None:
        return

    # Без ограничений
    if limit == -1:
        return

    window = int(
        config.get(
            "window",
            60,
        )
    )

    window = max(
        10,
        min(
            window,
            3600,
        ),
    )

    clean_history(
        guild.id,
        action,
        member.id,
        window,
    )

    history = ACTION_HISTORY[
        guild.id
    ][
        action
    ][
        member.id
    ]

    for _ in range(
        max(
            1,
            amount,
        )
    ):

        history.append(
            time.time()
        )

    count = len(
        history
    )

    # --------------------------------------------------------
    # Лимит 0
    # --------------------------------------------------------

    if limit == 0:

        await quarantine_member(
            guild,
            member,
            (
                f"{action_label(action)} "
                "запрещено для его Guard-роли"
            ),
        )

        return

    # --------------------------------------------------------
    # Превышение лимита
    # --------------------------------------------------------

    if count > limit:

        await quarantine_member(
            guild,
            member,
            (
                f"{action_label(action)}\n"
                f"Количество действий: `{count}`\n"
                f"Лимит: `{limit}`\n"
                f"Окно: `{window}` секунд"
            ),
        )


# ============================================================
# GET MEMBER FROM OBJECT
# ============================================================

async def resolve_member(
    guild: disnake.Guild,
    obj,
):
    if obj is None:
        return None

    member_id = getattr(
        obj,
        "id",
        None,
    )

    if not member_id:
        return None

    member = guild.get_member(
        int(member_id)
    )

    if member:
        return member

    try:

        return await guild.fetch_member(
            int(member_id)
        )

    except Exception:

        return None


# ============================================================
# ROLE EXTRACTION
# ============================================================

def extract_roles(
    entry: disnake.AuditLogEntry,
):
    result = set()

    try:

        before = entry.changes.before
        after = entry.changes.after

    except Exception:

        return []

    for state in (
        before,
        after,
    ):

        if state is None:
            continue

        try:

            roles = getattr(
                state,
                "roles",
                None,
            )

            if not roles:
                continue

            for role in roles:

                role_id = getattr(
                    role,
                    "id",
                    None,
                )

                if role_id:
                    result.add(
                        int(role_id)
                    )

        except Exception:
            continue

    roles = []

    for role_id in result:

        role = entry.guild.get_role(
            role_id
        )

        if role:
            roles.append(
                role
            )

    return roles


# ============================================================
# AUDIT LOG
# ============================================================

@bot.event
async def on_audit_log_entry_create(
    entry: disnake.AuditLogEntry,
):
    try:

        guild = entry.guild

        if guild is None:
            return

        config = get_config(
            guild.id
        )

        if not config.get(
            "enabled",
            True,
        ):
            return

        if entry.id in PROCESSED_AUDIT:
            return

        PROCESSED_AUDIT.add(
            entry.id
        )

        if len(
            PROCESSED_AUDIT
        ) > 15000:

            PROCESSED_AUDIT.clear()

        # ====================================================
        # EXECUTOR
        # ====================================================

        executor = await resolve_member(
            guild,
            entry.user,
        )

        if executor is None:
            return

        # Игнорируем владельца
        if executor.id == guild.owner_id:
            return

        # Игнорируем самого бота
        if bot.user and executor.id == bot.user.id:
            return

        audit_action = getattr(
            entry.action,
            "name",
            None,
        )

        if not audit_action:
            return

        # ====================================================
        # ANTI BOT
        # ====================================================

        if audit_action == "bot_add":

            anti_bot = config[
                "anti_bot"
            ]

            if not anti_bot.get(
                "enabled",
                False,
            ):
                return

            bot_target = await resolve_member(
                guild,
                entry.target,
            )

            if bot_target is None:
                return

            if not bot_target.bot:
                return

            # Кикаем добавленного бота
            try:

                await bot_target.kick(
                    reason=(
                        "Guard AntiBot: "
                        "добавление бота запрещено"
                    )
                )

                await send_log(
                    guild,
                    "Guard • AntiBot",
                    (
                        f"Добавленный бот "
                        f"{bot_target.mention} "
                        f"был автоматически кикнут.\n\n"
                        f"**Добавил:** "
                        f"{executor.mention}"
                    ),
                    disnake.Color.red(),
                )

            except Exception as error:

                await send_log(
                    guild,
                    "Guard • AntiBot ошибка",
                    (
                        f"Не удалось кикнуть бота.\n\n"
                        f"Бот: {bot_target.mention}\n"
                        f"Добавил: {executor.mention}\n"
                        f"Ошибка: `{error}`"
                    ),
                    disnake.Color.dark_red(),
                )

            return

        # ====================================================
        # ACTION MAP
        # ====================================================

        mapped_action = AUDIT_ACTION_MAP.get(
            audit_action
        )

        # ====================================================
        # MEMBER UPDATE
        # ====================================================

        if audit_action == "member_update":

            try:

                before = entry.changes.before
                after = entry.changes.after

            except Exception:

                return

            # ------------------------------------------------
            # NICK
            # ------------------------------------------------

            before_nick = getattr(
                before,
                "nick",
                None,
            )

            after_nick = getattr(
                after,
                "nick",
                None,
            )

            if (
                before_nick
                != after_nick
            ):

                await register_action(
                    guild,
                    executor,
                    "nickname",
                )

            # ------------------------------------------------
            # SERVER MUTE
            # ------------------------------------------------

            before_mute = getattr(
                before,
                "mute",
                None,
            )

            after_mute = getattr(
                after,
                "mute",
                None,
            )

            if (
                before_mute
                != after_mute
            ):

                await register_action(
                    guild,
                    executor,
                    "voice_mute",
                )

            # ------------------------------------------------
            # SERVER DEAF
            # ------------------------------------------------

            before_deaf = getattr(
                before,
                "deaf",
                None,
            )

            after_deaf = getattr(
                after,
                "deaf",
                None,
            )

            if (
                before_deaf
                != after_deaf
            ):

                await register_action(
                    guild,
                    executor,
                    "voice_deaf",
                )

            return

        # ====================================================
        # MEMBER ROLE UPDATE
        # ====================================================

        if audit_action == "member_role_update":

            roles = extract_roles(
                entry
            )

            amount = max(
                1,
                len(roles),
            )

            await register_action(
                guild,
                executor,
                "member_role_update",
                amount,
            )

            dangerous_count = 0

            for role in roles:

                if role.permissions.administrator:
                    dangerous_count += 1

            if dangerous_count:

                await register_action(
                    guild,
                    executor,
                    "dangerous_role_grant",
                    dangerous_count,
                )

            return

        # ====================================================
        # ROLE UPDATE
        # ====================================================

        if audit_action == "role_update":

            await register_action(
                guild,
                executor,
                "role_update",
            )

            try:

                before_perms = getattr(
                    entry.changes.before,
                    "permissions",
                    None,
                )

                after_perms = getattr(
                    entry.changes.after,
                    "permissions",
                    None,
                )

                before_admin = (
                    bool(
                        before_perms.administrator
                    )
                    if before_perms
                    else False
                )

                after_admin = (
                    bool(
                        after_perms.administrator
                    )
                    if after_perms
                    else False
                )

                if (
                    not before_admin
                    and after_admin
                ):

                    await register_action(
                        guild,
                        executor,
                        "dangerous_role_grant",
                    )

            except Exception:
                pass

            return

        # ====================================================
        # MEMBER MOVE
        # ====================================================

        if audit_action == "member_move":

            extra = getattr(
                entry,
                "extra",
                None,
            )

            count = getattr(
                extra,
                "count",
                1,
            )

            try:
                count = int(count)
            except Exception:
                count = 1

            await register_action(
                guild,
                executor,
                "voice_move",
                max(
                    1,
                    count,
                ),
            )

            return

        # ====================================================
        # NORMAL ACTIONS
        # ====================================================

        if mapped_action:

            await register_action(
                guild,
                executor,
                mapped_action,
            )

    except Exception as error:

        print(
            "[AUDIT ERROR]",
            repr(error),
        )


# ============================================================
# ANTI RAID
# ============================================================

@bot.event
async def on_member_join(
    member: disnake.Member,
):
    try:

        guild = member.guild

        config = get_config(
            guild.id
        )

        anti_raid = config[
            "anti_raid"
        ]

        if not anti_raid.get(
            "enabled",
            False,
        ):
            return

        now = time.time()

        history = RAID_HISTORY[
            guild.id
        ]

        window = max(
            5,
            min(
                int(
                    anti_raid.get(
                        "window",
                        10,
                    )
                ),
                3600,
            ),
        )

        threshold = max(
            2,
            int(
                anti_raid.get(
                    "threshold",
                    5,
                )
            ),
        )

        # Очищаем старые входы
        while history:

            if now - history[0] <= window:
                break

            history.popleft()

        history.append(
            now
        )

        count = len(
            history
        )

        if count < threshold:
            return

        action = anti_raid.get(
            "action",
            "quarantine",
        )

        reason = (
            f"AntiRaid: "
            f"{count} участников вошли "
            f"за {window} секунд"
        )

        # ====================================================
        # KICK
        # ====================================================

        if action == "kick":

            try:

                await member.kick(
                    reason=reason
                )

                await send_log(
                    guild,
                    "Guard • AntiRaid",
                    (
                        f"{member.mention} был кикнут.\n\n"
                        f"**Входов:** `{count}`\n"
                        f"**Окно:** `{window}` секунд"
                    ),
                    disnake.Color.red(),
                )

            except Exception as error:

                print(
                    "[ANTI RAID KICK ERROR]",
                    repr(error),
                )

        # ====================================================
        # QUARANTINE
        # ====================================================

        else:

            await quarantine_member(
                guild,
                member,
                reason,
            )

    except Exception as error:

        print(
            "[ANTI RAID ERROR]",
            repr(error),
        )


# ============================================================
# GUARD MAIN EMBED
# ============================================================

def main_embed(
    guild: disnake.Guild,
):
    config = get_config(
        guild.id
    )

    enabled = config.get(
        "enabled",
        True,
    )

    anti_bot = config[
        "anti_bot"
    ].get(
        "enabled",
        False,
    )

    anti_raid = config[
        "anti_raid"
    ].get(
        "enabled",
        False,
    )

    punishment_role_id = config.get(
        "punishment_role"
    )

    if punishment_role_id:

        punishment_role = guild.get_role(
            int(punishment_role_id)
        )

        punishment_text = (
            punishment_role.mention
            if punishment_role
            else "роль удалена"
        )

    else:

        punishment_text = "не настроена"

    logs_channel_id = config.get(
        "logs_channel"
    )

    if logs_channel_id:

        logs_channel = guild.get_channel(
            int(logs_channel_id)
        )

        logs_text = (
            logs_channel.mention
            if logs_channel
            else "канал удалён"
        )

    else:

        logs_text = "не настроен"

    embed = disnake.Embed(
        title="Guard",
        description=(
            "Панель защиты сервера.\n\n"
            "Все настройки Guard находятся здесь.\n\n"
            "Backup позволяет сохранить структуру сервера в переносимый JSON "
            "и позже восстановить её на другом сервере."
        ),
        color=(
            disnake.Color.green()
            if enabled
            else disnake.Color.red()
        ),
    )

    embed.add_field(
        name="Guard",
        value=(
            "🟢 Включён"
            if enabled
            else
            "🔴 Выключен"
        ),
        inline=True,
    )

    embed.add_field(
        name="AntiBot",
        value=(
            "🟢 Включён"
            if anti_bot
            else
            "🔴 Выключен"
        ),
        inline=True,
    )

    embed.add_field(
        name="AntiRaid",
        value=(
            "🟢 Включён"
            if anti_raid
            else
            "🔴 Выключен"
        ),
        inline=True,
    )

    embed.add_field(
        name="Роль карантина",
        value=punishment_text,
        inline=True,
    )

    embed.add_field(
        name="Логи",
        value=logs_text,
        inline=True,
    )

    embed.add_field(
        name="Окно лимитов",
        value=(
            f"`{config.get('window', 60)} сек.`"
        ),
        inline=True,
    )

    roles_count = len(
        config.get(
            "roles",
            {},
        )
    )

    quarantine_count = len(
        config.get(
            "quarantine",
            {},
        )
    )

    backup_dir = Path("guard_backups")
    backup_count = 0

    if backup_dir.exists():
        backup_count = sum(
            1
            for item in backup_dir.iterdir()
            if item.is_file() and item.suffix.lower() == ".json"
        )

    embed.add_field(
        name="Guard-роли",
        value=f"`{roles_count}`",
        inline=True,
    )

    embed.add_field(
        name="Карантинов",
        value=f"`{quarantine_count}`",
        inline=True,
    )

    embed.add_field(
        name="Backup-файлов",
        value=f"`{backup_count}`",
        inline=True,
    )

    return embed


# ============================================================
# ROLES EMBED
# ============================================================

def roles_embed(
    guild: disnake.Guild,
):
    config = get_config(
        guild.id
    )

    embed = disnake.Embed(
        title="Guard • Роли",
        description=(
            "Добавь обычную Discord-роль в Guard, "
            "после чего можно настроить ей лимиты."
        ),
        color=disnake.Color.blurple(),
    )

    lines = []

    for role_id, role_config in config[
        "roles"
    ].items():

        role = guild.get_role(
            int(role_id)
        )

        if role is None:
            continue

        active = 0

        for action in ACTIONS:

            limit = role_config[
                "limits"
            ].get(
                action,
                0,
            )

            if int(limit) != 0:
                active += 1

        lines.append(
            f"{role.mention} — `{active}` настроек"
        )

    embed.add_field(
        name="Guard-роли",
        value=(
            "\n".join(
                lines[:25]
            )
            if lines
            else
            "Нет настроенных ролей"
        ),
        inline=False,
    )

    return embed


# ============================================================
# LIMITS EMBED
# ============================================================

def limits_embed(
    guild: disnake.Guild,
    role_id: int,
):
    role = guild.get_role(
        role_id
    )

    config = get_role_config(
        guild.id,
        role_id,
    )

    embed = disnake.Embed(
        title="Guard • Лимиты роли",
        description=(
            f"Роль: "
            f"{role.mention if role else 'не найдена'}\n\n"
            "`0` = запрещено\n"
            "`5` = максимум 5 действий\n"
            "`-1` = безлимит"
        ),
        color=disnake.Color.blurple(),
    )

    text = []

    for action, name in ACTIONS.items():

        value = config[
            "limits"
        ].get(
            action,
            0,
        )

        display = (
            "∞"
            if int(value) == -1
            else str(value)
        )

        text.append(
            f"**{name}** — `{display}`"
        )

    embed.add_field(
        name="Действия",
        value="\n".join(
            text
        ),
        inline=False,
    )

    embed.add_field(
        name="Окно",
        value=(
            f"`{get_config(guild.id).get('window', 60)} сек.`"
        ),
        inline=False,
    )

    return embed


# ============================================================
# ANTI BOT EMBED
# ============================================================

def anti_bot_embed(
    guild: disnake.Guild,
):
    config = get_config(
        guild.id
    )

    enabled = config[
        "anti_bot"
    ].get(
        "enabled",
        False,
    )

    embed = disnake.Embed(
        title="Guard • AntiBot",
        description=(
            "Когда пользователь добавляет бота "
            "на сервер, Guard автоматически "
            "кикает добавленного бота."
        ),
        color=(
            disnake.Color.green()
            if enabled
            else disnake.Color.red()
        ),
    )

    embed.add_field(
        name="Состояние",
        value=(
            "🟢 Включён"
            if enabled
            else "🔴 Выключен"
        ),
        inline=False,
    )

    return embed


# ============================================================
# ANTI RAID EMBED
# ============================================================

def anti_raid_embed(
    guild: disnake.Guild,
):
    config = get_config(
        guild.id
    )

    raid = config[
        "anti_raid"
    ]

    enabled = raid.get(
        "enabled",
        False,
    )

    action = raid.get(
        "action",
        "quarantine",
    )

    action_text = (
        "Карантин"
        if action == "quarantine"
        else "Кик"
    )

    embed = disnake.Embed(
        title="Guard • AntiRaid",
        description=(
            "Настрой защиту от массового "
            "захода участников."
        ),
        color=(
            disnake.Color.green()
            if enabled
            else disnake.Color.red()
        ),
    )

    embed.add_field(
        name="Состояние",
        value=(
            "🟢 Включён"
            if enabled
            else "🔴 Выключен"
        ),
        inline=True,
    )

    embed.add_field(
        name="Порог",
        value=(
            f"`{raid.get('threshold', 5)}` участников"
        ),
        inline=True,
    )

    embed.add_field(
        name="Окно",
        value=(
            f"`{raid.get('window', 10)}` секунд"
        ),
        inline=True,
    )

    embed.add_field(
        name="Действие",
        value=action_text,
        inline=True,
    )

    return embed


# ============================================================
# QUARANTINE ROLE MODAL
# ============================================================

class QuarantineRoleView(
    disnake.ui.View
):
    def __init__(
        self,
        guild_id: int,
    ):
        super().__init__(
            timeout=900,
        )

        self.guild_id = guild_id
        self.selected_role = None

    async def interaction_check(
        self,
        interaction,
    ):
        if not is_guard_admin(
            interaction.guild,
            interaction.author,
        ):

            await interaction.response.send_message(
                "Только владелец сервера или доверенный пользователь.",
                ephemeral=True,
            )

            return False

        return True

    @disnake.ui.role_select(
        placeholder="Выбери роль карантина",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def role_select(
        self,
        select,
        interaction,
    ):
        self.selected_role = select.values[0]

        await interaction.response.send_message(
            f"Выбрана роль: {self.selected_role.mention}",
            ephemeral=True,
        )

    @disnake.ui.button(
        label="Сохранить",
        style=disnake.ButtonStyle.success,
        row=1,
    )
    async def save(
        self,
        button,
        interaction,
    ):
        if not self.selected_role:

            await interaction.response.send_message(
                "Сначала выбери роль.",
                ephemeral=True,
            )

            return

        role = self.selected_role

        bot_member = interaction.guild.me

        if bot_member is None:
            return

        if role.is_default():

            await interaction.response.send_message(
                "Нельзя использовать @everyone.",
                ephemeral=True,
            )

            return

        if role.managed:

            await interaction.response.send_message(
                "Нельзя использовать managed-роль.",
                ephemeral=True,
            )

            return

        if role >= bot_member.top_role:

            await interaction.response.send_message(
                "Роль должна находиться ниже роли бота.",
                ephemeral=True,
            )

            return

        config = get_config(
            self.guild_id
        )

        config[
            "punishment_role"
        ] = role.id

        save_data()

        await interaction.response.send_message(
            f"Роль карантина сохранена: {role.mention}",
            ephemeral=True,
        )

    @disnake.ui.button(
        label="Сбросить",
        style=disnake.ButtonStyle.danger,
        row=1,
    )
    async def clear(
        self,
        button,
        interaction,
    ):
        config = get_config(
            self.guild_id
        )

        config[
            "punishment_role"
        ] = None

        save_data()

        await interaction.response.send_message(
            "Роль карантина отключена. При нарушении роли будут просто сняты.",
            ephemeral=True,
        )

    @disnake.ui.button(
        label="Назад",
        style=disnake.ButtonStyle.secondary,
        row=2,
    )
    async def back(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=main_embed(
                interaction.guild
            ),
            view=GuardMainView(
                self.guild_id
            ),
        )


# ============================================================
# LIMIT MODAL
# ============================================================

class LimitModal(
    disnake.ui.Modal
):
    def __init__(
        self,
        guild_id: int,
        role_id: int,
        action: str,
    ):
        self.guild_id = guild_id
        self.role_id = role_id
        self.action = action

        current = get_role_config(
            guild_id,
            role_id,
        )[
            "limits"
        ].get(
            action,
            0,
        )

        components = [
            disnake.ui.TextInput(
                label=action_label(action),
                custom_id="limit",
                value=str(current),
                placeholder="0 / 5 / 10 / -1",
                style=disnake.TextInputStyle.short,
                min_length=1,
                max_length=6,
                required=True,
            )
        ]

        super().__init__(
            title="Настройка лимита",
            custom_id=(
                f"guard_limit_"
                f"{guild_id}_"
                f"{role_id}_"
                f"{action}"
            ),
            components=components,
        )

    async def callback(
        self,
        interaction,
    ):
        try:

            value = int(
                interaction.text_values[
                    "limit"
                ]
            )

        except Exception:

            await interaction.response.send_message(
                "Нужно указать целое число.",
                ephemeral=True,
            )

            return

        if value < -1:

            await interaction.response.send_message(
                "Минимальное значение: -1.",
                ephemeral=True,
            )

            return

        role = interaction.guild.get_role(
            self.role_id
        )

        if role is None:

            await interaction.response.send_message(
                "Роль не найдена.",
                ephemeral=True,
            )

            return

        config = get_role_config(
            self.guild_id,
            self.role_id,
        )

        config[
            "name"
        ] = role.name

        config[
            "limits"
        ][
            self.action
        ] = value

        save_data()

        await interaction.response.send_message(
            (
                f"{role.mention}\n"
                f"**{action_label(self.action)}** → `{value}`"
            ),
            ephemeral=True,
        )


# ============================================================
# WINDOW MODAL
# ============================================================

class WindowModal(
    disnake.ui.Modal
):
    def __init__(
        self,
        guild_id: int,
    ):
        self.guild_id = guild_id

        config = get_config(
            guild_id
        )

        components = [
            disnake.ui.TextInput(
                label="Окно лимитов в секундах",
                custom_id="window",
                value=str(
                    config.get(
                        "window",
                        60,
                    )
                ),
                placeholder="10 - 3600",
                style=disnake.TextInputStyle.short,
                required=True,
                max_length=4,
            )
        ]

        super().__init__(
            title="Окно Guard",
            custom_id=(
                f"guard_window_{guild_id}"
            ),
            components=components,
        )

    async def callback(
        self,
        interaction,
    ):
        try:

            value = int(
                interaction.text_values[
                    "window"
                ]
            )

        except Exception:

            await interaction.response.send_message(
                "Укажи число.",
                ephemeral=True,
            )

            return

        if not 10 <= value <= 3600:

            await interaction.response.send_message(
                "Значение должно быть от 10 до 3600 секунд.",
                ephemeral=True,
            )

            return

        config = get_config(
            self.guild_id
        )

        config[
            "window"
        ] = value

        save_data()

        await interaction.response.send_message(
            f"Окно Guard установлено: `{value}` секунд.",
            ephemeral=True,
        )


# ============================================================
# ANTI RAID MODAL
# ============================================================

class AntiRaidModal(
    disnake.ui.Modal
):
    def __init__(
        self,
        guild_id: int,
    ):
        self.guild_id = guild_id

        raid = get_config(
            guild_id
        )[
            "anti_raid"
        ]

        components = [
            disnake.ui.TextInput(
                label="Количество входов",
                custom_id="threshold",
                value=str(
                    raid.get(
                        "threshold",
                        5,
                    )
                ),
                placeholder="Например: 5",
                style=disnake.TextInputStyle.short,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Окно в секундах",
                custom_id="window",
                value=str(
                    raid.get(
                        "window",
                        10,
                    )
                ),
                placeholder="Например: 10",
                style=disnake.TextInputStyle.short,
                required=True,
            ),
        ]

        super().__init__(
            title="Настройка AntiRaid",
            custom_id=(
                f"guard_antiraid_{guild_id}"
            ),
            components=components,
        )

    async def callback(
        self,
        interaction,
    ):
        try:

            threshold = int(
                interaction.text_values[
                    "threshold"
                ]
            )

            window = int(
                interaction.text_values[
                    "window"
                ]
            )

        except Exception:

            await interaction.response.send_message(
                "Оба значения должны быть числами.",
                ephemeral=True,
            )

            return

        if threshold < 2 or threshold > 1000:

            await interaction.response.send_message(
                "Порог должен быть от 2 до 1000.",
                ephemeral=True,
            )

            return

        if window < 5 or window > 3600:

            await interaction.response.send_message(
                "Окно должно быть от 5 до 3600 секунд.",
                ephemeral=True,
            )

            return

        config = get_config(
            self.guild_id
        )

        config[
            "anti_raid"
        ][
            "threshold"
        ] = threshold

        config[
            "anti_raid"
        ][
            "window"
        ] = window

        save_data()

        await interaction.response.send_message(
            (
                f"AntiRaid:\n"
                f"Порог: `{threshold}`\n"
                f"Окно: `{window}` секунд"
            ),
            ephemeral=True,
        )


# ============================================================
# ROLES VIEW
# ============================================================

class RolesView(
    disnake.ui.View
):
    def __init__(
        self,
        guild_id: int,
    ):
        super().__init__(
            timeout=900,
        )

        self.guild_id = guild_id
        self.selected_role_id = None

    async def interaction_check(
        self,
        interaction,
    ):
        if not is_guard_admin(
            interaction.guild,
            interaction.author,
        ):

            await interaction.response.send_message(
                "Только владелец сервера или доверенный пользователь.",
                ephemeral=True,
            )

            return False

        return True

    @disnake.ui.role_select(
        placeholder="Выбери Guard-роль",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def role_select(
        self,
        select,
        interaction,
    ):
        role = select.values[0]

        self.selected_role_id = role.id

        await interaction.response.send_message(
            f"Выбрана роль: {role.mention}",
            ephemeral=True,
        )

    @disnake.ui.button(
        label="Добавить",
        style=disnake.ButtonStyle.success,
        row=1,
    )
    async def add(
        self,
        button,
        interaction,
    ):
        if not self.selected_role_id:

            await interaction.response.send_message(
                "Сначала выбери роль.",
                ephemeral=True,
            )

            return

        role = interaction.guild.get_role(
            self.selected_role_id
        )

        if role is None:
            return

        if role.is_default():

            await interaction.response.send_message(
                "Нельзя добавить @everyone.",
                ephemeral=True,
            )

            return

        if role.managed:

            await interaction.response.send_message(
                "Нельзя добавить managed-роль.",
                ephemeral=True,
            )

            return

        config = get_config(
            self.guild_id
        )

        config[
            "roles"
        ].setdefault(
            str(role.id),
            {
                "name": role.name,
                "limits": {
                    action: 0
                    for action in ACTIONS
                },
            },
        )

        save_data()

        await interaction.response.edit_message(
            embed=roles_embed(
                interaction.guild
            ),
            view=RolesView(
                self.guild_id
            ),
        )

    @disnake.ui.button(
        label="Удалить",
        style=disnake.ButtonStyle.danger,
        row=1,
    )
    async def remove(
        self,
        button,
        interaction,
    ):
        if not self.selected_role_id:

            await interaction.response.send_message(
                "Сначала выбери роль.",
                ephemeral=True,
            )

            return

        config = get_config(
            self.guild_id
        )

        config[
            "roles"
        ].pop(
            str(
                self.selected_role_id
            ),
            None,
        )

        save_data()

        await interaction.response.edit_message(
            embed=roles_embed(
                interaction.guild
            ),
            view=RolesView(
                self.guild_id
            ),
        )

    @disnake.ui.button(
        label="Лимиты",
        style=disnake.ButtonStyle.primary,
        row=1,
    )
    async def limits(
        self,
        button,
        interaction,
    ):
        if not self.selected_role_id:

            await interaction.response.send_message(
                "Сначала выбери роль.",
                ephemeral=True,
            )

            return

        role = interaction.guild.get_role(
            self.selected_role_id
        )

        if role is None:
            return

        await interaction.response.edit_message(
            embed=limits_embed(
                interaction.guild,
                role.id,
            ),
            view=LimitsView(
                self.guild_id,
                role.id,
            ),
        )

    @disnake.ui.button(
        label="Назад",
        style=disnake.ButtonStyle.secondary,
        row=2,
    )
    async def back(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=main_embed(
                interaction.guild
            ),
            view=GuardMainView(
                self.guild_id
            ),
        )


# ============================================================
# LIMITS VIEW
# ============================================================

class LimitsView(
    disnake.ui.View
):
    def __init__(
        self,
        guild_id: int,
        role_id: int,
    ):
        super().__init__(
            timeout=900,
        )

        self.guild_id = guild_id
        self.role_id = role_id
        self.selected_action = None

        self.add_action_select()

    def add_action_select(self):

        options = []

        for action, name in ACTIONS.items():

            options.append(
                disnake.SelectOption(
                    label=name[:100],
                    value=action,
                )
            )

        select = disnake.ui.StringSelect(
            placeholder="Выбери действие",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

        async def callback(
            interaction,
        ):
            self.selected_action = (
                select.values[0]
            )

            await interaction.response.send_message(
                (
                    f"Выбрано: "
                    f"**{action_label(self.selected_action)}**"
                ),
                ephemeral=True,
            )

        select.callback = callback

        self.add_item(
            select
        )

    @disnake.ui.button(
        label="Изменить",
        style=disnake.ButtonStyle.primary,
        row=1,
    )
    async def edit(
        self,
        button,
        interaction,
    ):
        if not self.selected_action:

            await interaction.response.send_message(
                "Сначала выбери действие.",
                ephemeral=True,
            )

            return

        await interaction.response.send_modal(
            LimitModal(
                self.guild_id,
                self.role_id,
                self.selected_action,
            )
        )

    @disnake.ui.button(
        label="Обновить",
        style=disnake.ButtonStyle.secondary,
        row=1,
    )
    async def refresh(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=limits_embed(
                interaction.guild,
                self.role_id,
            ),
            view=LimitsView(
                self.guild_id,
                self.role_id,
            ),
        )

    @disnake.ui.button(
        label="Назад",
        style=disnake.ButtonStyle.secondary,
        row=2,
    )
    async def back(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=roles_embed(
                interaction.guild
            ),
            view=RolesView(
                self.guild_id
            ),
        )


# ============================================================
# ANTI BOT VIEW
# ============================================================

class AntiBotView(
    disnake.ui.View
):
    def __init__(
        self,
        guild_id: int,
    ):
        super().__init__(
            timeout=900,
        )

        self.guild_id = guild_id

    async def interaction_check(
        self,
        interaction,
    ):
        if not is_guard_admin(
            interaction.guild,
            interaction.author,
        ):

            await interaction.response.send_message(
                "Только владелец сервера или доверенный пользователь.",
                ephemeral=True,
            )

            return False

        return True

    @disnake.ui.button(
        label="Вкл / Выкл",
        style=disnake.ButtonStyle.success,
        row=0,
    )
    async def toggle(
        self,
        button,
        interaction,
    ):
        config = get_config(
            self.guild_id
        )

        config[
            "anti_bot"
        ][
            "enabled"
        ] = not config[
            "anti_bot"
        ].get(
            "enabled",
            False,
        )

        save_data()

        await interaction.response.edit_message(
            embed=anti_bot_embed(
                interaction.guild
            ),
            view=AntiBotView(
                self.guild_id
            ),
        )

    @disnake.ui.button(
        label="Назад",
        style=disnake.ButtonStyle.secondary,
        row=1,
    )
    async def back(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=main_embed(
                interaction.guild
            ),
            view=GuardMainView(
                self.guild_id
            ),
        )


# ============================================================
# ANTI RAID VIEW
# ============================================================

class AntiRaidView(
    disnake.ui.View
):
    def __init__(
        self,
        guild_id: int,
    ):
        super().__init__(
            timeout=900,
        )

        self.guild_id = guild_id

    async def interaction_check(
        self,
        interaction,
    ):
        if not is_guard_admin(
            interaction.guild,
            interaction.author,
        ):

            await interaction.response.send_message(
                "Только владелец сервера или доверенный пользователь.",
                ephemeral=True,
            )

            return False

        return True

    @disnake.ui.button(
        label="Вкл / Выкл",
        style=disnake.ButtonStyle.success,
        row=0,
    )
    async def toggle(
        self,
        button,
        interaction,
    ):
        config = get_config(
            self.guild_id
        )

        config[
            "anti_raid"
        ][
            "enabled"
        ] = not config[
            "anti_raid"
        ].get(
            "enabled",
            False,
        )

        save_data()

        await interaction.response.edit_message(
            embed=anti_raid_embed(
                interaction.guild
            ),
            view=AntiRaidView(
                self.guild_id
            ),
        )

    @disnake.ui.button(
        label="Настроить порог",
        style=disnake.ButtonStyle.primary,
        row=0,
    )
    async def configure(
        self,
        button,
        interaction,
    ):
        await interaction.response.send_modal(
            AntiRaidModal(
                self.guild_id
            )
        )

    @disnake.ui.button(
        label="Действие: карантин",
        style=disnake.ButtonStyle.secondary,
        row=1,
    )
    async def change_action(
        self,
        button,
        interaction,
    ):
        config = get_config(
            self.guild_id
        )

        current = config[
            "anti_raid"
        ].get(
            "action",
            "quarantine",
        )

        config[
            "anti_raid"
        ][
            "action"
        ] = (
            "kick"
            if current == "quarantine"
            else "quarantine"
        )

        save_data()

        await interaction.response.edit_message(
            embed=anti_raid_embed(
                interaction.guild
            ),
            view=AntiRaidView(
                self.guild_id
            ),
        )

    @disnake.ui.button(
        label="Назад",
        style=disnake.ButtonStyle.secondary,
        row=2,
    )
    async def back(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=main_embed(
                interaction.guild
            ),
            view=GuardMainView(
                self.guild_id
            ),
        )


# ============================================================
# MAIN GUARD VIEW
# ============================================================

def list_local_backups():
    backup_dir = Path("guard_backups")
    backup_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = [
        item
        for item in backup_dir.iterdir()
        if item.is_file() and item.suffix.lower() == ".json"
    ]

    files.sort(
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    return files


def read_backup_file(path: Path):
    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def backup_menu_embed(
    guild: disnake.Guild,
):
    files = list_local_backups()

    embed = disnake.Embed(
        title="Guard • Восстановление",
        description=(
            "Выбери сохранённый шаблон и нажми "
            "«Восстановить выбранный».\n\n"
            "Восстановление добавляет роли и каналы поверх текущего сервера "
            "и не удаляет существующие элементы."
        ),
        color=disnake.Color.blurple(),
    )

    if not files:
        embed.add_field(
            name="Backup-файлы",
            value="Нет сохранённых шаблонов.",
            inline=False,
        )
        return embed

    lines = []

    for path in files[:10]:
        try:
            data = read_backup_file(path)
            source = data.get("source_guild", {}).get(
                "name",
                "Неизвестный сервер",
            )
            roles_count = len(
                data.get("roles", [])
            )
            channels_count = len(
                data.get("channels", [])
            )

            lines.append(
                f"• `{path.name}`\n"
                f"  {source} — ролей: `{roles_count}`, каналов: `{channels_count}`"
            )
        except Exception:
            lines.append(
                f"• `{path.name}` — файл повреждён"
            )

    embed.add_field(
        name="Последние backup-файлы",
        value="\n".join(lines),
        inline=False,
    )

    return embed


class BackupMenuView(
    disnake.ui.View
):
    def __init__(
        self,
        guild_id: int,
    ):
        super().__init__(
            timeout=900,
        )

        self.guild_id = guild_id
        self.selected_file = None

        files = list_local_backups()

        if files:
            options = []

            for path in files[:25]:
                try:
                    data = read_backup_file(path)
                    source = data.get(
                        "source_guild",
                        {},
                    ).get(
                        "name",
                        "Неизвестный сервер",
                    )
                except Exception:
                    source = "Повреждённый файл"

                options.append(
                    disnake.SelectOption(
                        label=source[:100],
                        description=path.name[:100],
                        value=path.name,
                    )
                )

            select = disnake.ui.StringSelect(
                placeholder="Выбери backup-файл",
                min_values=1,
                max_values=1,
                options=options,
                row=0,
            )

            async def select_callback(interaction):
                self.selected_file = select.values[0]

                await interaction.response.send_message(
                    f"Выбран backup: `{self.selected_file}`",
                    ephemeral=True,
                )

            select.callback = select_callback
            self.add_item(select)

    async def interaction_check(
        self,
        interaction,
    ):
        if not is_guard_admin(
            interaction.guild,
            interaction.author,
        ):
            await interaction.response.send_message(
                "Только владелец сервера или доверенный пользователь.",
                ephemeral=True,
            )
            return False

        return True

    @disnake.ui.button(
        label="Восстановить выбранный",
        style=disnake.ButtonStyle.success,
        row=1,
    )
    async def restore_selected(
        self,
        button,
        interaction,
    ):
        if not self.selected_file:
            await interaction.response.send_message(
                "Сначала выбери backup-файл.",
                ephemeral=True,
            )
            return

        path = Path("guard_backups") / self.selected_file

        if not path.exists():
            await interaction.response.send_message(
                "Backup-файл больше не существует.",
                ephemeral=True,
            )
            return

        try:
            await interaction.response.defer(
                ephemeral=True,
            )

            backup = read_backup_file(path)

            result = await restore_server_from_backup(
                interaction.guild,
                backup,
            )

            skipped = result.get(
                "skipped",
                [],
            )

            await interaction.followup.send(
                (
                    "Восстановление завершено.\n\n"
                    f"Ролей создано: `{result['roles_created']}`\n"
                    f"Каналов создано: `{result['channels_created']}`\n"
                    f"Пропущено: `{len(skipped)}`"
                ),
                ephemeral=True,
            )

            await send_log(
                interaction.guild,
                "Guard • Восстановление из локального backup",
                (
                    f"**Запустил:** {interaction.author.mention}\n"
                    f"**Файл:** `{path.name}`\n"
                    f"**Ролей создано:** `{result['roles_created']}`\n"
                    f"**Каналов создано:** `{result['channels_created']}`\n"
                    f"**Пропущено:** `{len(skipped)}`"
                ),
                disnake.Color.green(),
            )

        except Exception as error:
            print(
                "[LOCAL RESTORE ERROR]",
                repr(error),
            )

            await interaction.followup.send(
                f"Ошибка восстановления: `{error}`",
                ephemeral=True,
            )

    @disnake.ui.button(
        label="Обновить список",
        style=disnake.ButtonStyle.secondary,
        row=1,
    )
    async def refresh(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=backup_menu_embed(
                interaction.guild,
            ),
            view=BackupMenuView(
                self.guild_id,
            ),
        )

    @disnake.ui.button(
        label="Назад",
        style=disnake.ButtonStyle.secondary,
        row=2,
    )
    async def back(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=main_embed(
                interaction.guild,
            ),
            view=GuardMainView(
                self.guild_id,
            ),
        )


class GuardMainView(
    disnake.ui.View
):
    def __init__(
        self,
        guild_id: int,
    ):
        super().__init__(
            timeout=900,
        )

        self.guild_id = guild_id

    async def interaction_check(
        self,
        interaction,
    ):
        if not is_guard_admin(
            interaction.guild,
            interaction.author,
        ):

            await interaction.response.send_message(
                "Только владелец сервера или доверенный пользователь.",
                ephemeral=True,
            )

            return False

        return True

    # --------------------------------------------------------
    # GUARD
    # --------------------------------------------------------

    @disnake.ui.button(
        label="Guard Вкл / Выкл",
        style=disnake.ButtonStyle.success,
        row=0,
    )
    async def toggle_guard(
        self,
        button,
        interaction,
    ):
        config = get_config(
            self.guild_id
        )

        config[
            "enabled"
        ] = not config.get(
            "enabled",
            True,
        )

        save_data()

        await interaction.response.edit_message(
            embed=main_embed(
                interaction.guild
            ),
            view=GuardMainView(
                self.guild_id
            ),
        )

    # --------------------------------------------------------
    # ROLES
    # --------------------------------------------------------

    @disnake.ui.button(
        label="Роли и лимиты",
        style=disnake.ButtonStyle.primary,
        row=0,
    )
    async def roles_button(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=roles_embed(
                interaction.guild
            ),
            view=RolesView(
                self.guild_id
            ),
        )

    # --------------------------------------------------------
    # ANTI BOT
    # --------------------------------------------------------

    @disnake.ui.button(
        label="Антибот",
        style=disnake.ButtonStyle.danger,
        row=0,
    )
    async def anti_bot_button(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=anti_bot_embed(
                interaction.guild
            ),
            view=AntiBotView(
                self.guild_id
            ),
        )

    # --------------------------------------------------------
    # ANTI RAID
    # --------------------------------------------------------

    @disnake.ui.button(
        label="Антирейд",
        style=disnake.ButtonStyle.danger,
        row=0,
    )
    async def anti_raid_button(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=anti_raid_embed(
                interaction.guild
            ),
            view=AntiRaidView(
                self.guild_id
            ),
        )

    # --------------------------------------------------------
    # PUNISHMENT ROLE
    # --------------------------------------------------------

    @disnake.ui.button(
        label="Роль карантина",
        style=disnake.ButtonStyle.secondary,
        row=1,
    )
    async def punishment_button(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=disnake.Embed(
                title="Guard • Роль карантина",
                description=(
                    "Эта роль будет выдаваться "
                    "при отправке пользователя в карантин.\n\n"
                    "Если роль не настроить, "
                    "Guard просто снимет все роли."
                ),
                color=disnake.Color.orange(),
            ),
            view=QuarantineRoleView(
                self.guild_id
            ),
        )

    # --------------------------------------------------------
    # WINDOW
    # --------------------------------------------------------

    @disnake.ui.button(
        label="Окно лимитов",
        style=disnake.ButtonStyle.secondary,
        row=1,
    )
    async def window_button(
        self,
        button,
        interaction,
    ):
        await interaction.response.send_modal(
            WindowModal(
                self.guild_id
            )
        )

    # --------------------------------------------------------
    # LOGS CHANNEL
    # --------------------------------------------------------

    @disnake.ui.channel_select(
        placeholder="Выбери канал логов",
        min_values=1,
        max_values=1,
        channel_types=[
            disnake.ChannelType.text
        ],
        row=2,
    )
    async def log_channel(
        self,
        select,
        interaction,
    ):
        channel = select.values[0]

        config = get_config(
            self.guild_id
        )

        config[
            "logs_channel"
        ] = channel.id

        save_data()

        await interaction.response.send_message(
            f"Канал логов: {channel.mention}",
            ephemeral=True,
        )

    # --------------------------------------------------------
    # SAVE SERVER
    # --------------------------------------------------------

    @disnake.ui.button(
        label="Сохранить сервер",
        style=disnake.ButtonStyle.success,
        row=3,
    )
    async def save_server_button(
        self,
        button,
        interaction,
    ):
        try:
            backup = create_server_backup(
                interaction.guild
            )

            raw = json.dumps(
                backup,
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8")

            timestamp = datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%d_%H-%M-%S")

            filename = (
                f"server_template_"
                f"{interaction.guild.id}_"
                f"{timestamp}.json"
            )

            # Сохраняем копию на сервере бота.
            backup_dir = Path("guard_backups")
            backup_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            backup_path = backup_dir / filename
            backup_path.write_bytes(
                raw
            )

            file = disnake.File(
                io.BytesIO(raw),
                filename=filename,
            )

            await interaction.response.send_message(
                (
                    "Сервер сохранён.\n\n"
                    "Этот JSON можно использовать как переносимый "
                    "шаблон для другого сервера."
                ),
                file=file,
                ephemeral=True,
            )

            await send_log(
                interaction.guild,
                "Guard • Сервер сохранён",
                (
                    f"**Создал:** {interaction.author.mention}\n"
                    f"**Файл:** `{filename}`\n"
                    f"**Ролей:** `{len(backup.get('roles', []))}`\n"
                    f"**Каналов:** `{len(backup.get('channels', []))}`"
                ),
                disnake.Color.green(),
            )

        except Exception as error:
            print(
                "[BACKUP ERROR]",
                repr(error),
            )

            await interaction.response.send_message(
                f"Ошибка сохранения сервера: `{error}`",
                ephemeral=True,
            )

    # --------------------------------------------------------
    # RESTORE SERVER
    # --------------------------------------------------------

    @disnake.ui.button(
        label="Восстановить сервер",
        style=disnake.ButtonStyle.primary,
        row=3,
    )
    async def restore_server_button(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=backup_menu_embed(
                interaction.guild,
            ),
            view=BackupMenuView(
                self.guild_id,
            ),
        )

    # --------------------------------------------------------
    # CLEAR LOGS
    # --------------------------------------------------------

    @disnake.ui.button(
        label="Очистить канал логов",
        style=disnake.ButtonStyle.danger,
        row=4,
    )
    async def clear_logs(
        self,
        button,
        interaction,
    ):
        config = get_config(
            self.guild_id
        )

        config[
            "logs_channel"
        ] = None

        save_data()

        await interaction.response.edit_message(
            embed=main_embed(
                interaction.guild
            ),
            view=GuardMainView(
                self.guild_id
            ),
        )

    # --------------------------------------------------------
    # REFRESH
    # --------------------------------------------------------

    @disnake.ui.button(
        label="Обновить",
        style=disnake.ButtonStyle.secondary,
        row=4,
    )
    async def refresh(
        self,
        button,
        interaction,
    ):
        await interaction.response.edit_message(
            embed=main_embed(
                interaction.guild
            ),
            view=GuardMainView(
                self.guild_id
            ),
        )


# ============================================================
# SERVER BACKUP / RESTORE
# ============================================================

def serialize_permissions(overwrite: disnake.PermissionOverwrite):
    allow, deny = overwrite.pair()

    return {
        "allow": int(allow.value),
        "deny": int(deny.value),
    }


def serialize_overwrites(channel: disnake.abc.GuildChannel):
    result = []

    for target, overwrite in channel.overwrites.items():
        target_type = None
        target_id = getattr(target, "id", None)
        target_name = getattr(target, "name", None)

        if isinstance(target, disnake.Role):
            target_type = "role"
        elif isinstance(target, disnake.Member):
            target_type = "member"
        else:
            # Неизвестные/объектные targets не переносим.
            continue

        if target_id is None:
            continue

        result.append({
            "type": target_type,
            "id": int(target_id),
            "name": target_name,
            "permissions": serialize_permissions(overwrite),
        })

    return result


def serialize_channel(channel: disnake.abc.GuildChannel):
    data = {
        "id": int(channel.id),
        "type": getattr(channel.type, "name", str(channel.type)),
        "name": channel.name,
        "position": int(getattr(channel, "position", 0)),
        "category_id": getattr(channel, "category_id", None),
        "overwrites": serialize_overwrites(channel),
    }

    if isinstance(channel, disnake.CategoryChannel):
        data.update({
            "nsfw": bool(getattr(channel, "nsfw", False)),
        })

    elif isinstance(channel, disnake.TextChannel):
        data.update({
            "topic": getattr(channel, "topic", None),
            "nsfw": bool(getattr(channel, "nsfw", False)),
            "slowmode_delay": int(getattr(channel, "slowmode_delay", 0)),
        })

    elif isinstance(channel, disnake.ForumChannel):
        data.update({
            "topic": getattr(channel, "topic", None),
            "nsfw": bool(getattr(channel, "nsfw", False)),
            "slowmode_delay": int(getattr(channel, "slowmode_delay", 0)),
            "default_thread_slowmode_delay": int(
                getattr(channel, "default_thread_slowmode_delay", 0)
            ),
            "default_auto_archive_duration": int(
                getattr(channel, "default_auto_archive_duration", 1440)
            ),
        })

    elif isinstance(channel, disnake.StageChannel):
        rtc_region = getattr(channel, "rtc_region", None)

        data.update({
            "topic": getattr(channel, "topic", None),
            "bitrate": int(getattr(channel, "bitrate", 64000)),
            "user_limit": int(getattr(channel, "user_limit", 0)),
            "rtc_region": rtc_region,
            "nsfw": bool(getattr(channel, "nsfw", False)),
        })

    elif isinstance(channel, disnake.VoiceChannel):
        rtc_region = getattr(channel, "rtc_region", None)

        data.update({
            "bitrate": int(getattr(channel, "bitrate", 64000)),
            "user_limit": int(getattr(channel, "user_limit", 0)),
            "rtc_region": rtc_region,
            "nsfw": bool(getattr(channel, "nsfw", False)),
        })

    return data


def create_server_backup(
    guild: disnake.Guild,
):
    """
    Создаёт переносимый JSON-шаблон.

    В него входят:
    - название/описание сервера;
    - кастомные роли;
    - категории;
    - текстовые, голосовые, stage и forum каналы;
    - настройки каналов;
    - role/member permission overwrites.

    Member overwrites при восстановлении на другом сервере
    переносятся только если такой пользователь уже есть на целевом сервере.
    """

    roles = []

    for role in guild.roles:
        if role.is_default():
            continue

        if role.managed:
            continue

        roles.append({
            "id": int(role.id),
            "name": role.name,
            "permissions": int(role.permissions.value),
            "color": int(role.color.value),
            "hoist": bool(role.hoist),
            "mentionable": bool(role.mentionable),
            "position": int(role.position),
        })

    channels = []

    for channel in guild.channels:
        if isinstance(channel, disnake.VoiceChannel):
            pass

        try:
            channel_data = serialize_channel(
                channel
            )
            channels.append(
                channel_data
            )
        except Exception as error:
            print(
                "[BACKUP CHANNEL ERROR]",
                channel.name,
                repr(error),
            )

    backup = {
        "format": BACKUP_FORMAT,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source_guild": {
            "id": int(guild.id),
            "name": guild.name,
            "description": guild.description,
        },
        "settings": {
            "afk_timeout": int(
                getattr(guild, "afk_timeout", 300)
            ),
            "default_notifications": str(
                getattr(
                    getattr(guild, "default_notifications", None),
                    "name",
                    getattr(guild, "default_notifications", ""),
                )
            ),
            "verification_level": str(
                getattr(
                    getattr(guild, "verification_level", None),
                    "name",
                    getattr(guild, "verification_level", ""),
                )
            ),
            "explicit_content_filter": str(
                getattr(
                    getattr(guild, "explicit_content_filter", None),
                    "name",
                    getattr(guild, "explicit_content_filter", ""),
                )
            ),
        },
        "roles": roles,
        "channels": channels,
    }

    return backup


def restore_overwrites(
    guild: disnake.Guild,
    backup_channel: dict,
    role_map: dict[int, disnake.Role],
):
    overwrites = {}

    for item in backup_channel.get(
        "overwrites",
        [],
    ):
        target_type = item.get(
            "type"
        )

        target_id = item.get(
            "id"
        )

        permissions = item.get(
            "permissions",
            {},
        )

        if target_id is None:
            continue

        target = None

        if target_type == "role":
            source_id = int(
                target_id
            )

            # @everyone на другом сервере имеет другой ID,
            # поэтому распознаём его по имени из backup.
            if item.get("name") == "@everyone":
                target = guild.default_role
            else:
                target = role_map.get(
                    source_id
                )

        elif target_type == "member":
            try:
                target = guild.get_member(
                    int(target_id)
                )
            except Exception:
                target = None

        if target is None:
            continue

        try:
            allow = disnake.Permissions(
                int(
                    permissions.get(
                        "allow",
                        0,
                    )
                )
            )

            deny = disnake.Permissions(
                int(
                    permissions.get(
                        "deny",
                        0,
                    )
                )
            )

            overwrite = disnake.PermissionOverwrite.from_pair(
                allow,
                deny,
            )

            overwrites[target] = overwrite

        except Exception as error:
            print(
                "[RESTORE OVERWRITE ERROR]",
                repr(error),
            )

    return overwrites


async def restore_server_from_backup(
    guild: disnake.Guild,
    backup: dict,
):
    if backup.get("format") != BACKUP_FORMAT:
        raise ValueError(
            "Неподдерживаемый формат backup-файла."
        )

    bot_member = guild.me

    if bot_member is None:
        raise RuntimeError(
            "Не удалось определить бота на сервере."
        )

    created_roles = {}
    created_channels = {}
    skipped = []

    # --------------------------------------------------------
    # ROLES
    # --------------------------------------------------------

    source_roles = sorted(
        backup.get("roles", []),
        key=lambda item: int(
            item.get("position", 0)
        ),
    )

    for role_data in source_roles:
        try:
            permissions = disnake.Permissions(
                int(
                    role_data.get(
                        "permissions",
                        0,
                    )
                )
            )

            color = disnake.Color(
                int(
                    role_data.get(
                        "color",
                        0,
                    )
                )
            )

            role = await guild.create_role(
                name=str(
                    role_data.get(
                        "name",
                        "Restored Role",
                    )
                )[:100],
                permissions=permissions,
                color=color,
                hoist=bool(
                    role_data.get(
                        "hoist",
                        False,
                    )
                ),
                mentionable=bool(
                    role_data.get(
                        "mentionable",
                        False,
                    )
                ),
                reason="Guard: восстановление шаблона сервера",
            )

            created_roles[
                int(role_data["id"])
            ] = role

        except Exception as error:
            skipped.append(
                f"Роль `{role_data.get('name', '?')}`: {error}"
            )

    # Восстанавливаем позиции ролей через bulk API.
    positions = {}

    max_bot_position = max(
        1,
        bot_member.top_role.position - 1,
    )

    for role_data in source_roles:
        role = created_roles.get(
            int(role_data["id"])
        )

        if role is None:
            continue

        wanted_position = int(
            role_data.get(
                "position",
                1,
            )
        )

        # Бот физически не может двигать роль выше своей роли.
        wanted_position = min(
            max(
                1,
                wanted_position,
            ),
            max_bot_position,
        )

        positions[role] = wanted_position

    if positions:
        try:
            await guild.edit_role_positions(
                positions=positions,
                reason="Guard: восстановление позиций ролей",
            )
        except Exception as error:
            skipped.append(
                f"Позиции ролей: {error}"
            )

    # --------------------------------------------------------
    # CHANNELS
    # --------------------------------------------------------

    source_channels = sorted(
        backup.get("channels", []),
        key=lambda item: (
            0 if item.get("type") == "category" else 1,
            int(item.get("position", 0)),
        ),
    )

    # ID категории -> новый объект категории
    category_map = {}

    # First pass: categories.
    for channel_data in source_channels:
        if channel_data.get("type") != "category":
            continue

        try:
            overwrites = restore_overwrites(
                guild,
                channel_data,
                created_roles,
            )

            category = await guild.create_category(
                name=str(
                    channel_data.get(
                        "name",
                        "Restored Category",
                    )
                )[:100],
                overwrites=overwrites or None,
                nsfw=bool(
                    channel_data.get(
                        "nsfw",
                        False,
                    )
                ),
                reason="Guard: восстановление категории",
            )

            category_map[
                int(channel_data["id"])
            ] = category
            created_channels[
                int(channel_data["id"])
            ] = category

        except Exception as error:
            skipped.append(
                f"Категория `{channel_data.get('name', '?')}`: {error}"
            )

    # Second pass: regular channels.
    for channel_data in source_channels:
        if channel_data.get("type") == "category":
            continue

        channel_type = channel_data.get(
            "type"
        )

        if channel_type == "media":
            # Если API/сервер не позволяет создать MediaChannel,
            # не ломаем весь импорт.
            create_kind = "media"
        else:
            create_kind = channel_type

        category = category_map.get(
            int(
                channel_data.get(
                    "category_id",
                    0,
                ) or 0
            )
        )

        overwrites = restore_overwrites(
            guild,
            channel_data,
            created_roles,
        )

        name = str(
            channel_data.get(
                "name",
                "restored-channel",
            )
        )[:100]

        try:
            created = None

            if create_kind in ("text", "news"):
                created = await guild.create_text_channel(
                    name=name,
                    category=category,
                    topic=channel_data.get(
                        "topic"
                    ),
                    nsfw=bool(
                        channel_data.get(
                            "nsfw",
                            False,
                        )
                    ),
                    slowmode_delay=int(
                        channel_data.get(
                            "slowmode_delay",
                            0,
                        )
                    ),
                    news=(
                        create_kind == "news"
                    ),
                    overwrites=overwrites or None,
                    reason="Guard: восстановление канала",
                )

            elif create_kind == "voice":
                created = await guild.create_voice_channel(
                    name=name,
                    category=category,
                    bitrate=int(
                        channel_data.get(
                            "bitrate",
                            64000,
                        )
                    ),
                    user_limit=int(
                        channel_data.get(
                            "user_limit",
                            0,
                        )
                    ),
                    rtc_region=channel_data.get(
                        "rtc_region"
                    ),
                    nsfw=bool(
                        channel_data.get(
                            "nsfw",
                            False,
                        )
                    ),
                    overwrites=overwrites or None,
                    reason="Guard: восстановление канала",
                )

            elif create_kind == "stage":
                created = await guild.create_stage_channel(
                    name=name,
                    category=category,
                    topic=channel_data.get(
                        "topic"
                    ),
                    bitrate=int(
                        channel_data.get(
                            "bitrate",
                            64000,
                        )
                    ),
                    user_limit=int(
                        channel_data.get(
                            "user_limit",
                            0,
                        )
                    ),
                    rtc_region=channel_data.get(
                        "rtc_region"
                    ),
                    nsfw=bool(
                        channel_data.get(
                            "nsfw",
                            False,
                        )
                    ),
                    overwrites=overwrites or None,
                    reason="Guard: восстановление канала",
                )

            elif create_kind == "forum":
                created = await guild.create_forum_channel(
                    name=name,
                    category=category,
                    topic=channel_data.get(
                        "topic"
                    ),
                    nsfw=bool(
                        channel_data.get(
                            "nsfw",
                            False,
                        )
                    ),
                    slowmode_delay=int(
                        channel_data.get(
                            "slowmode_delay",
                            0,
                        )
                    ),
                    default_thread_slowmode_delay=int(
                        channel_data.get(
                            "default_thread_slowmode_delay",
                            0,
                        )
                    ),
                    default_auto_archive_duration=int(
                        channel_data.get(
                            "default_auto_archive_duration",
                            1440,
                        )
                    ),
                    overwrites=overwrites or None,
                    reason="Guard: восстановление форума",
                )

            elif create_kind == "media" and hasattr(
                guild,
                "create_media_channel",
            ):
                created = await guild.create_media_channel(
                    name=name,
                    category=category,
                    topic=channel_data.get(
                        "topic"
                    ),
                    nsfw=bool(
                        channel_data.get(
                            "nsfw",
                            False,
                        )
                    ),
                    slowmode_delay=int(
                        channel_data.get(
                            "slowmode_delay",
                            0,
                        )
                    ),
                    overwrites=overwrites or None,
                    reason="Guard: восстановление media-канала",
                )

            else:
                skipped.append(
                    f"Канал `{name}`: неподдерживаемый тип `{channel_type}`"
                )
                continue

            created_channels[
                int(channel_data["id"])
            ] = created

        except Exception as error:
            skipped.append(
                f"Канал `{name}`: {error}"
            )

    # --------------------------------------------------------
    # POSITIONS
    # --------------------------------------------------------

    for channel_data in source_channels:
        created = created_channels.get(
            int(channel_data["id"])
        )

        if created is None:
            continue

        try:
            position = max(
                0,
                int(
                    channel_data.get(
                        "position",
                        0,
                    )
                ),
            )

            await created.edit(
                position=position,
                reason="Guard: восстановление позиции канала",
            )

        except Exception as error:
            skipped.append(
                f"Позиция канала `{getattr(created, 'name', '?')}`: {error}"
            )

    return {
        "roles_created": len(
            created_roles
        ),
        "channels_created": len(
            created_channels
        ),
        "skipped": skipped,
    }


@bot.slash_command(
    name="guard_restore",
    description="Восстановить сервер из Guard JSON-шаблона",
)
async def guard_restore(
    interaction: disnake.ApplicationCommandInteraction,
    file: disnake.Attachment,
):
    guild = interaction.guild

    if guild is None:
        await interaction.response.send_message(
            "Команда доступна только на сервере.",
            ephemeral=True,
        )
        return

    if not is_guard_admin(
        guild,
        interaction.author,
    ):
        await interaction.response.send_message(
            "Только владелец сервера или доверенный пользователь.",
            ephemeral=True,
        )
        return

    if not file.filename.lower().endswith(".json"):
        await interaction.response.send_message(
            "Нужен файл с расширением `.json`.",
            ephemeral=True,
        )
        return

    try:
        await interaction.response.defer(
            ephemeral=True
        )

        raw = await file.read()

        if len(raw) > 5 * 1024 * 1024:
            await interaction.followup.send(
                "Файл слишком большой для шаблона Guard.",
                ephemeral=True,
            )
            return

        backup = json.loads(
            raw.decode("utf-8-sig")
        )

        if backup.get("format") != BACKUP_FORMAT:
            await interaction.followup.send(
                "Это не Guard-шаблон подходящего формата.",
                ephemeral=True,
            )
            return

        await send_log(
            guild,
            "Guard • Начато восстановление",
            (
                f"**Запустил:** {interaction.author.mention}\n"
                f"**Источник:** {backup.get('source_guild', {}).get('name', 'неизвестно')}\n"
                f"**Ролей:** `{len(backup.get('roles', []))}`\n"
                f"**Каналов:** `{len(backup.get('channels', []))}`"
            ),
            disnake.Color.orange(),
        )

        result = await restore_server_from_backup(
            guild,
            backup,
        )

        skipped = result[
            "skipped"
        ]

        description = (
            f"**Ролей создано:** `{result['roles_created']}`\n"
            f"**Каналов создано:** `{result['channels_created']}`\n"
            f"**Пропущено:** `{len(skipped)}`"
        )

        if skipped:
            preview = "\n".join(
                f"• {item}"
                for item in skipped[:15]
            )

            description += (
                "\n\n**Некоторые элементы не восстановлены:**\n"
                + preview
            )

        await interaction.followup.send(
            (
                "Восстановление завершено.\n\n"
                + description
                + "\n\n"
                "Существующие каналы и роли бота не удалял — шаблон добавлен поверх сервера."
            ),
            ephemeral=True,
        )

        await send_log(
            guild,
            "Guard • Восстановление завершено",
            (
                f"**Запустил:** {interaction.author.mention}\n"
                f"**Ролей создано:** `{result['roles_created']}`\n"
                f"**Каналов создано:** `{result['channels_created']}`\n"
                f"**Пропущено:** `{len(skipped)}`"
            ),
            disnake.Color.green(),
        )

    except json.JSONDecodeError:
        await interaction.followup.send(
            "Файл повреждён или это не JSON.",
            ephemeral=True,
        )

    except Exception as error:
        print(
            "[RESTORE ERROR]",
            repr(error),
        )

        await interaction.followup.send(
            f"Ошибка восстановления: `{error}`",
            ephemeral=True,
        )


# ============================================================
# /GUARD
# ============================================================

@bot.slash_command(
    name="guard",
    description="Открыть панель защиты сервера",
)
async def guard(
    interaction: disnake.ApplicationCommandInteraction,
):
    guild = interaction.guild

    if guild is None:

        await interaction.response.send_message(
            "Команда только для сервера.",
            ephemeral=True,
        )

        return

    if not is_guard_admin(
        guild,
        interaction.author,
    ):

        await interaction.response.send_message(
            "Только владелец сервера или доверенный пользователь может открыть Guard.",
            ephemeral=True,
        )

        return

    await interaction.response.send_message(
        embed=main_embed(
            guild
        ),
        view=GuardMainView(
            guild.id
        ),
        ephemeral=True,
    )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    # --------------------------------------------------------
    # ВОССТАНОВЛЕНИЕ КНОПОК КАРАНТИНА
    # --------------------------------------------------------

    for guild_id, config in DATA.items():

        quarantine = config.get(
            "quarantine",
            {}
        )

        for member_id, data in quarantine.items():

            message_id = data.get(
                "message_id"
            )

            if not message_id:
                continue

            try:

                bot.add_view(
                    QuarantineView(
                        int(guild_id),
                        int(member_id),
                    ),
                    message_id=int(
                        message_id
                    ),
                )

            except Exception as error:

                print(
                    "[VIEW RESTORE ERROR]",
                    repr(error)
                )

    print(
        "=============================================="
    )

    print(
        f"Bot: {bot.user}"
    )

    print(
        f"ID: {bot.user.id}"
    )

    print(
        f"Servers: {len(bot.guilds)}"
    )

    print(
        "Guard: ONLINE"
    )

    print(
        "AntiBot: READY"
    )

    print(
        "AntiRaid: READY"
    )

    print(
        "Quarantine: READY"
    )

    print(
        "=============================================="
    )


# ============================================================
# ERROR
# ============================================================

@bot.event
async def on_slash_command_error(
    interaction,
    error,
):
    print(
        "[COMMAND ERROR]",
        repr(error),
    )

    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                "Произошла ошибка.",
                ephemeral=True,
            )

        else:

            await interaction.response.send_message(
                "Произошла ошибка.",
                ephemeral=True,
            )

    except Exception:
        pass


# ============================================================
# START
# ============================================================

if TOKEN == "ВСТАВЬ_СЮДА_ТОКЕН_БОТА":

    raise RuntimeError(
        "Вставь токен в переменную TOKEN."
    )


bot.run(
    TOKEN
)