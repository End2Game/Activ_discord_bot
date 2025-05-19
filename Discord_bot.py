import discord
from discord.ext import commands
import sqlite3
from discord.ext import tasks
from discord import app_commands
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json,dotenv
import os

# Завантаження токена з .env
dotenv.load_dotenv()
token = os.getenv("DISCORD_TOKEN")
token = ("MTM3MjIxMzc5MjMyMjIyNDE2OQ.GVzx5l.QiDuvIloNs4RDk_RBoaJg99z1iBUHbRjTAyH88")  # Замінити на безпечний

# Конфігурація винагород
MESSAGES_PER_REWARD = 8       # Кожні 8 повідомлення
MESSAGE_REWARD_AMOUNT = 2     # — отримуєш 2 копійку
VOICE_REWARD_PER_MIN = 2    # Копійок за 1 хв в голосі

# Інтенти
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

# Клієнт
class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = MyClient()

# Файли
CHAT_TIME_FILE = "chat_times.json"
VOICE_TIME_FILE = "voice_times.json"
BALANCE_FILE = "balances.json"
MESSAGE_COUNT_FILE = "message_counts.json"

# Дані
user_chat_times = defaultdict(float)
voice_join_times = {}
voice_total_times = defaultdict(float)
voice_weekly_times = defaultdict(list)
message_counts = defaultdict(int)
user_balances = defaultdict(float)

# Вкажи тут ID каналу, де дозволені лише зображення
IMAGE_ONLY_CHANNEL_ID = 1332009384946962483  # <-- заміни на свій ID

# Перелік допустимих розширень для зображень
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp' , '.mp4' , '.avi')

# Завантаження
def load_data():
    if os.path.exists(CHAT_TIME_FILE):
        with open(CHAT_TIME_FILE, "r") as f:
            try:
                data = json.load(f)
                for k, v in data.items():
                    user_chat_times[k] = float(v)
            except:
                pass

    if os.path.exists(VOICE_TIME_FILE):
        with open(VOICE_TIME_FILE, "r") as f:
            try:
                data = json.load(f)
                for k, v in data.get("total", {}).items():
                    voice_total_times[k] = float(v)
                for k, v in data.get("weekly", {}).items():
                    voice_weekly_times[k] = [
                        (datetime.fromtimestamp(t, tz=timezone.utc), float(dur)) for t, dur in v
                    ]
            except:
                pass

    if os.path.exists(BALANCE_FILE):
        with open(BALANCE_FILE, "r") as f:
            try:
                data = json.load(f)
                for k, v in data.items():
                    user_balances[k] = float(v)
            except:
                pass

    if os.path.exists(MESSAGE_COUNT_FILE):
        with open(MESSAGE_COUNT_FILE, "r") as f:
            try:
                data = json.load(f)
                for k, v in data.items():
                    message_counts[k] = int(v)
            except:
                pass

# Збереження
def save_data():
    with open(CHAT_TIME_FILE, "w") as f:
        json.dump(dict(user_chat_times), f)

    with open(VOICE_TIME_FILE, "w") as f:
        json.dump({
            "total": dict(voice_total_times),
            "weekly": {
                k: [(t.timestamp(), dur) for t, dur in v]
               for k, v in voice_weekly_times.items()
            }
        }, f)

    with open(BALANCE_FILE, "w") as f:
        json.dump(dict(user_balances), f)

    with open(MESSAGE_COUNT_FILE, "w") as f:
        json.dump(dict(message_counts), f)

    print("[SAVE] Дані збережено успішно.")

#def cleanup_old_voice_data():
#   week_ago = datetime.now(timezone.utc) - timedelta(days=7)
#    removed = 0
#   for user_id in list(voice_weekly_times.keys()):
#   original = len(voice_weekly_times[user_id])
#        voice_weekly_times[user_id] = [
#            (t, dur) for t, dur in voice_weekly_times[user_id] if t > week_ago
#       ]
#        removed += original - len(voice_weekly_times[user_id])
#    if removed > 0:
#        print(f"[CLEANUP] Видалено {removed} старих voice-сесій.")

load_data()

@client.event
async def on_ready():
    print(f"✅ Бот {client.user} запущено")

    for guild in client.guilds:
        for vc in guild.voice_channels:
            for member in vc.members:
                if not member.bot and str(member.id) not in voice_join_times:
                    voice_join_times[str(member.id)] = datetime.now(timezone.utc)
                    print(f"[RESTORE] {member.name} перебуває в voice")

    save_loop.start()
    print("[DEBUG] Автозбереження запущено")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)

    # --- Обробка зображень у спец. каналі ---
    if message.channel.id == IMAGE_ONLY_CHANNEL_ID:
        has_image = any(
            attachment.filename.lower().endswith(IMAGE_EXTENSIONS)
            for attachment in message.attachments
        ) or any(
            word.lower().endswith(IMAGE_EXTENSIONS)
            for word in message.content.split()
        )

        if not has_image:
            try:
                await message.delete()
            except discord.Forbidden:
                print("Немає прав на видалення повідомлення.")
            except discord.HTTPException as e:
                print(f"Помилка при видаленні повідомлення: {e}")
            return  # Не нараховуємо копійки, якщо нема зображення

    # --- Нарахування за повідомлення ---
    user_chat_times[user_id] += 1
    message_counts[user_id] += 1

    if message_counts[user_id] % MESSAGES_PER_REWARD == 0:
        user_balances[user_id] += MESSAGE_REWARD_AMOUNT
        print(f"[PAY] {message.author.name} отримав {MESSAGE_REWARD_AMOUNT} коп.")

@client.event
async def on_voice_state_update(member, before, after):
    now = datetime.now(timezone.utc)
    user_id = str(member.id)

    if before.channel is None and after.channel is not None:
        voice_join_times[user_id] = now
        print(f"[JOIN] {member.name} зайшов у {after.channel.name}")

    elif before.channel is not None and after.channel is None:
        join_time = voice_join_times.pop(user_id, None)
        if join_time:
            duration = (now - join_time).total_seconds()
            voice_total_times[user_id] += duration
            voice_weekly_times[user_id].append((now, duration))
            coins_earned = int(duration // 60) * VOICE_REWARD_PER_MIN
            if coins_earned > 0:
                user_balances[user_id] += coins_earned
                print(f"[VOICE PAY] {member.name} отримав {coins_earned} Копійок за voice")
            print(f"[LEAVE] {member.name} — {duration:.2f} сек")
        save_data()

    elif before.channel != after.channel:
        join_time = voice_join_times.get(user_id)
        if join_time:
            duration = (now - join_time).total_seconds()
            voice_total_times[user_id] += duration
            voice_weekly_times[user_id].append((now, duration))
            coins_earned = int(duration // 60)
            if coins_earned > 0:
                user_balances[user_id] += coins_earned
                print(f"[VOICE PAY] {member.name} отримав {coins_earned} Копійок за voice")
            print(f"[SWITCH] {member.name} — {duration:.2f} сек між каналами")
        voice_join_times[user_id] = now
        save_data()

@client.tree.command(name="online", description="Показати активність у voice-чатах")
@app_commands.describe(user="Кого перевірити (за замовчуванням — ви)")
async def online(interaction: discord.Interaction, user: discord.User = None):
    user = user or interaction.user
    user_id = str(user.id)
    now = datetime.now(timezone.utc)

    total_seconds = voice_total_times.get(user_id, 0)
    week_ago = now - timedelta(days=7)
    week_seconds = sum(d for t, d in voice_weekly_times.get(user_id, []) if t > week_ago)

    if user_id in voice_join_times:
        session_start = voice_join_times[user_id]
        session_seconds = (now - session_start).total_seconds()
        total_seconds += session_seconds
        if session_start > week_ago:
            week_seconds += session_seconds

    def format_time(seconds):
        minutes, sec = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours} год {minutes} хв {sec} сек"

    embed = discord.Embed(
        title=f"🎙 Voice-активність — {user.name}",
        color=discord.Color.blurple()
    )
    embed.add_field(name="Всього (voice)", value=format_time(total_seconds), inline=False)
    embed.add_field(name="Тижневий (voice)", value=format_time(week_seconds), inline=False)

    if user.avatar:
        embed.set_thumbnail(url=user.avatar.url)

    await interaction.response.send_message(embed=embed,ephemeral=True)

@client.tree.command(name="top", description="Показує топ користувачів за копійок")
async def top(interaction: discord.Interaction):
    top_users = sorted(user_balances.items(), key=lambda x: x[1], reverse=True)[:10]

    if not top_users:
        await interaction.response.send_message("Немає даних для відображення топу.")
        return

    embed = discord.Embed(title="🏆 Топ 10 користувачів за копійок", color=discord.Color.gold())

    for i, (user_id, balance) in enumerate(top_users, start=1):
        try:
            user = await client.fetch_user(int(user_id))
            embed.add_field(
                name=f"{i}. {user.name}",
                value=f"💰 {balance:.2f} копійок",
                inline=False
            )
        except:
            embed.add_field(
                name=f"{i}. Unknown User",
                value=f"💰 {balance:.2f} копійок",
                inline=False
            )

    await interaction.response.send_message(embed=embed)

@client.tree.command(name="topvoice", description="ТОП-15 користувачів за голосовою активністю")
async def topvoice(interaction: discord.Interaction):
    await interaction.response.defer()  # повідомляємо Discord, що відповідь буде пізніше

    now = datetime.now(timezone.utc)
    durations = dict(voice_total_times)
    for user_id, join_time in voice_join_times.items():
        durations[user_id] = durations.get(user_id, 0) + (now - join_time).total_seconds()

    top = sorted(durations.items(), key=lambda x: x[1], reverse=True)[:15]
    medals = ["👑", "🥈", "🥉"] + [f"#{i}" for i in range(4, 16)]

    embed = discord.Embed(
        title="🎙️ ТОП-15 Активних за весь час",
        color=discord.Color.purple(),
        timestamp=now
    )
    embed.set_footer(text="Активність за весь час")

    description = ""
    for i, (user_id, seconds) in enumerate(top):
        hours = round(seconds / 3600, 2)
        emoji = medals[i]
        try:
            user = await client.fetch_user(int(user_id))
            name = f"<@{user.id}>"
        except:
            name = "`Unknown User`"
        description += f"**{emoji}** {name} — `{hours} годин`\n"

    embed.description = description

    # після defer потрібно використовувати followup.send
    await interaction.followup.send(embed=embed)

@client.tree.command(name="topchat", description="ТОП-15 користувачів за активністю в чаті")
async def topchat(interaction: discord.Interaction):
    await interaction.response.defer()  # дає більше часу на виконання

    top = sorted(message_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    medals = ["👑", "🥈", "🥉"] + [f"#{i}" for i in range(4, 16)]
    embed = discord.Embed(
        title="💬 ТОП-15 Чатерів",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="Повідомлення за весь час")

    description = ""
    for i, (user_id, count) in enumerate(top):
        emoji = medals[i]
        try:
            user = await client.fetch_user(int(user_id))
            name = f"<@{user.id}>"
        except:
            name = "`Unknown User`"
        description += f"**{emoji}** {name} — `{count} повідомлень`\n"

    embed.description = description
    await interaction.followup.send(embed=embed)  # використовуй followup

@client.tree.command(name="me", description="Показати вашу текстову активність")
async def me(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    msg_count = message_counts.get(user_id,message_counts[user_id])
    embed = discord.Embed(
        title=f"💬 Активність {interaction.user.name}",
        description=f"Ви надіслали `{msg_count}` повідомлень з моменту запуску бота.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.tree.command(name="balance", description="Показати ваш баланс копійок")
async def balance(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    amount = round(user_balances.get(user_id, 0.0), 2)
    embed = discord.Embed(
        title=f"💳 Баланс {interaction.user.name}",
        description=f"На вашому рахунку: `{amount} Копійок`",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.tree.command(name="pay", description="Передати копійки іншому користувачу")
@app_commands.describe(user="Кому передати", amount="Скільки передати")
async def pay(interaction: discord.Interaction, user: discord.User, amount: float):
    sender_id = str(interaction.user.id)
    receiver_id = str(user.id)
    if amount <= 0:
        await interaction.response.send_message("Сума має бути більшою за 0!", ephemeral=True)
        return
    if user_balances[sender_id] < amount:
        await interaction.response.send_message("Недостатньо коштів!", ephemeral=True)
        return
    user_balances[sender_id] -= amount
    user_balances[receiver_id] += amount
    save_data()
    await interaction.response.send_message(f"✅ Ви передали {amount:.2f} монет користувачу {user.mention}", ephemeral=True)

@client.tree.command(name="give", description="Видати копійки користувачу (тільки для адмінів)")
@app_commands.describe(user="Кому видати", amount="Скільки копійок")
async def give(interaction: discord.Interaction, user: discord.User, amount: float):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Лише для адміністраторів!", ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message("Сума має бути більшою за 0!", ephemeral=True)
        return
    user_balances[str(user.id)] += amount
    save_data()
    await interaction.response.send_message(f"✅ Видано {amount:.2f} копійок користувачу {user.mention}", ephemeral=True)

@client.tree.command(name="take", description="Зняти копійки з користувача (тільки для адмінів)")
@app_commands.describe(user="З кого зняти", amount="Скільки копійок")
async def take(interaction: discord.Interaction, user: discord.User, amount: float):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Лише для адміністраторів!", ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message("Сума має бути більшою за 0!", ephemeral=True)
        return
    user_balances[str(user.id)] = max(0.0, user_balances[str(user.id)] - amount)
    save_data()
    await interaction.response.send_message(f"✅ Знято {amount:.2f} копійок з користувача {user.mention}", ephemeral=True)

@tasks.loop(minutes=1)
async def save_loop():
    save_data()
#    cleanup_old_voice_data()
    print("[AUTOSAVE] Дані збережено.")

client.run(token)
