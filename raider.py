import os
import time
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
from threading import Thread
from colorama import init, Fore
import re
import asyncio

# Colorama init
init(autoreset=True)

# Flask setup
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    thread = Thread(target=run_flask)
    thread.daemon = True
    thread.start()

keep_alive()

# Discord bot setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.typing = False
intents.presences = False

bot = commands.Bot(command_prefix="!", intents=intents)

# Constants
OWNER_ID = 475160980280705024
GUILD_ID = 1005186618031869952
ACCESS_ROLE_ID = 1365076710265192590

# Universal embed notification
async def send_embed_notification(interaction, title, description, color=discord.Color(0x2f3136)):
    embed = discord.Embed(title=title, description=description, color=color)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.NotFound:
        print("⚠ Interaction უკვე ამოიცურა ან გაუქმდა.")
    except discord.HTTPException as e:
        print(f"⚠ HTTP შეცდომა Embed-ის გაგზავნისას: {e}")

# Helper: Check permissions
async def check_user_permissions(interaction, required_role_id: int, guild_id: int):
    home_guild = discord.utils.get(bot.guilds, id=guild_id)
    if not home_guild:
        await send_embed_notification(interaction, "⚠️ მთავარი სერვერი არ არის ნაპოვნი", "⌚️ სცადეთ მოგვიანებით.")
        return None

    try:
        member = await home_guild.fetch_member(interaction.user.id)
    except discord.NotFound:
        await send_embed_notification(
            interaction,
            "⛔️ ტქვენ არ ხართ მთავარ სერვერზე",
            "🌐 შემოგვიერთ ახლავე [Server](https://discord.gg/byScSM6T9Q)"
        )
        return None

    if not any(role.id == required_role_id for role in member.roles):
        await send_embed_notification(
            interaction,
            "🚫 თქვენ არ შეგუთსიათ ამ ფუნქციის გამოყენება",
            "💸 შესაცენად ეცვიეთ სერვერს [Server](https://discord.gg/byScSM6T9Q) 💸"
        )
        return None

    return member

# Cooldown dictionary
cooldowns = {}

def dm_cooldown(seconds: int):
    def predicate(interaction: discord.Interaction):
        now = time.time()
        user_id = interaction.user.id
        last_used = cooldowns.get(user_id, 0)

        if now - last_used < seconds:
            remaining = int(seconds - (now - last_used))
            raise app_commands.CheckFailure(f"გთხოვთ დეელოდოთ {remaining} წამს ბრძანების ხელახლა გამოქენებთ.")

        cooldowns[user_id] = now
        return True

    return app_commands.check(predicate)

# Button classes (SpamButton and SingleUseButton) stay unchanged

# /spamraid command
# (UNCHANGED)

# /onlyone command
# (UNCHANGED)

# /dmmsg command
# (UNCHANGED)

# Helper: Duration parsing (for /giveacces)
def parse_duration(duration_str):
    pattern = r"(\d+)([smhd])"
    matches = re.findall(pattern, duration_str.lower())
    if not matches:
        return None

    seconds = 0
    for amount, unit in matches:
        amount = int(amount)
        if unit == "s":
            seconds += amount
        elif unit == "m":
            seconds += amount * 60
        elif unit == "h":
            seconds += amount * 3600
        elif unit == "d":
            seconds += amount * 86400
    return seconds

# /giveacces command
@bot.tree.command(name="giveacces", description="მიეცით არჩეულ მომხმარებელს დროებითი წვდომა მთავარ სერვერზე")
@app_commands.describe(
    user="მომხმარებელი ვისაც გსურთ წვდომის მინიჭება",
    duration="დროის პერიოდით (მაგალითად: 30m, 5h, 14d)"
)
async def giveacces(interaction: discord.Interaction, user: discord.User, duration: str):
    await bot.wait_until_ready()

    if interaction.user.id != OWNER_ID:
        await send_embed_notification(interaction, "⛔ უფლება არ გეძლევა", "მხოლოდ სერვერის მფლობელს შეუძლია ამ ბრძანების გამოყენება.")
        return

    guild = discord.utils.get(bot.guilds, id=GUILD_ID)
    if not guild:
        await send_embed_notification(interaction, "⚠️ მთავარი სერვერი ვერ მოიძებნა", "სცადეთ მოგვიანებით.")
        return

    try:
        member = await guild.fetch_member(user.id)
    except discord.NotFound:
        await send_embed_notification(interaction, "🚫 მომხმარებელი ვერ მოიძებნა", "ეს მომხმარებელი არ არის სერვერზე.")
        return

    role = guild.get_role(ACCESS_ROLE_ID)
    if not role:
        await send_embed_notification(interaction, "⚠️ როლი ვერ მოიძებნა", "შეამოწმეთ როლის ID.")
        return

    seconds = parse_duration(duration)
    if not seconds or seconds <= 0:
        await send_embed_notification(interaction, "⚠️ არასწორი დროის ფორმატი", "გამოიყენეთ: 30m, 5h, 7d და ა.შ.")
        return

    try:
        await member.add_roles(role, reason=f"Role granted for {duration} by {interaction.user}")
    except discord.Forbidden:
        await send_embed_notification(interaction, "🚫 ბოტს არ აქვს როლის მინიჭების უფლება", "შეამოწმეთ ბოტის Permissions.")
        return
    except discord.HTTPException as e:
        await send_embed_notification(interaction, "❌ შეცდომა როლის მინიჭებისას", f"დეტალები: {e}")
        return

    await send_embed_notification(interaction, "✅ წარმატებით მიენიჭა წვდომა", f"{member.mention} როლი მიენიჭა {duration}-ით.")

    async def remove_role_later():
        await asyncio.sleep(seconds)
        try:
            updated_member = await guild.fetch_member(user.id)
            await updated_member.remove_roles(role, reason="Access time expired")
            print(f"✅ Role '{role.name}' მოხსნილია {updated_member} -ზე {duration}-ის შემდეგ.")
        except discord.NotFound:
            print(f"⚠ წევრი {user} აღარ მოიძებნა როლის მოხსნისას.")
        except discord.Forbidden:
            print(f"🚫 ბოტს არ აქვს უფლება role მოეხსნას {user}.")
        except discord.HTTPException as e:
            print(f"❌ შეცდომა role-ის მოხსნისას: {e}")

    bot.loop.create_task(remove_role_later())

# Bot ready
@bot.event
async def on_ready():
    print(f"✅ Bot connected as {bot.user}")
    await bot.change_presence(status=discord.Status.invisible)
    try:
        await bot.tree.sync()
        print(Fore.GREEN + "✅ Slash commands synced successfully.")
    except Exception as e:
        print(Fore.RED + f"❌ Failed to sync commands: {e}")

# Run bot
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print(Fore.RED + "❌ DISCORD_TOKEN environment variable is not set.")
