import os
import time
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
from flask import Flask
from threading import Thread
from colorama import init, Fore
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

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

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")  # render-ზე MONGO_URI უნდა იყოს დამატებული env-ში
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["discord_bot"]
access_roles_collection = db["access_roles"]

# Discord bot setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.typing = False
intents.presences = False
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

OWNER_ID = 475160980280705024
ROLE_ID = 1365076710265192590
GUILD_ID = 1005186618031869952
LOG_CHANNEL_ID = 1365381000619622460

# Universal embed notification
async def send_embed_notification(interaction, title, description, color=discord.Color(0x2f3136)):
    embed = discord.Embed(title=title, description=description, color=color)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.NotFound:
        print("⚠ Interaction უკვე ამოიწურა ან გაუქმდა.")
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
            "⛔️ თქვენ არ ხართ მთავარ სერვერზე",
            "🌐 შემოგვიერთდით ახლავე [Server](https://discord.gg/byScSM6T9Q)"
        )
        return None

    if not any(role.id == required_role_id for role in member.roles):
        await send_embed_notification(
            interaction,
            "🚫 თქვენ არ შეგიძლიათ ამ ფუნქციის გამოყენება",
            "💸 შესაძენად ეწვიეთ სერვერს [Server](https://discord.gg/byScSM6T9Q) 💸"
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
            raise app_commands.CheckFailure(f"გთხოვთ დაელოდოთ {remaining} წამს ბრძანების ხელახლა გამოსაყენებლად.")

        cooldowns[user_id] = now
        return True

    return app_commands.check(predicate)

# Spam button
class SpamButton(discord.ui.View):
    def __init__(self, message):
        super().__init__()
        self.message = message

    @discord.ui.button(label="გასპამვა", style=discord.ButtonStyle.red)
    async def spam_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        for _ in range(5):
            await interaction.followup.send(self.message)

# Single-use button
class SingleUseButton(discord.ui.View):
    def __init__(self, message):
        super().__init__()
        self.message = message
        self.sent = False

    @discord.ui.button(label="გაგზავნა", style=discord.ButtonStyle.green)
    async def send_once(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.sent:
            await interaction.response.send_message("⛔ უკვე გაგზავნილია!", ephemeral=True)
            return

        self.sent = True
        button.disabled = True

        await interaction.response.defer()
        await interaction.followup.send(self.message)

        try:
            original_message = await interaction.original_response()
            await original_message.edit(view=self)
        except discord.NotFound:
            print("⚠ ვერ მოხერხდა ღილაკის რედაქტირება — შეტყობინება აღარ არსებობს.")

# /spamraid command
@app_commands.describe(message="The message you want to spam")
@bot.tree.command(name="spamraid", description="გაგზავნეთ შეტყობინება და შექმენით ღილაკი სპამისთვის")
async def spamraid(interaction: discord.Interaction, message: str):
    await bot.wait_until_ready()

    member = await check_user_permissions(interaction, ROLE_ID, GUILD_ID)
    if not member:
        return

    embed = discord.Embed(title="💥 გასასპამი ტექსტი 💥", description=message, color=discord.Color(0x2f3136))
    embed.set_footer(text=f"შექმნილია {interaction.user.display_name}")

    view = SpamButton(message)
    try:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    except discord.NotFound:
        print("⚠ Interaction ვადა გასულია (spamraid).")

# /onlyone command
@app_commands.describe(message="შეტყობინება რაც გინდა რომ გაგზავნოს ერთხელ")
@bot.tree.command(name="onlyone", description="მხოლოდ ერთხელ გაგზავნის ღილაკით შეტყობინებას")
async def onlyone(interaction: discord.Interaction, message: str):
    await bot.wait_until_ready()

    member = await check_user_permissions(interaction, ROLE_ID, GUILD_ID)
    if not member:
        return

    embed = discord.Embed(title="🟢 ერთჯერადი გაგზავნის ღილაკი", description=message, color=discord.Color.green())
    embed.set_footer(text=f"შექმნილია {interaction.user.display_name}")

    view = SingleUseButton(message)
    try:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    except discord.NotFound:
        print("⚠ Interaction ვადა გასულია (onlyone).")

# /dmmsg command
@bot.tree.command(name="dmmsg", description="გაგზავნე DM არჩეულ მომხმარებელზე")
@app_commands.describe(
    user="მომხმარებელი, რომელსაც გსურს პირადში მიწერა",
    message="შეტყობინება რომელიც გსურს რომ გააგზავნო"
)
async def dmmsg(interaction: discord.Interaction, user: discord.User, message: str):
    await bot.wait_until_ready()

    seconds = 300  # 5 წუთი
    user_id = interaction.user.id
    now = time.time()
    last_used = cooldowns.get(user_id, 0)

    if now - last_used < seconds:
        remaining = int(seconds - (now - last_used))
        await send_embed_notification(interaction, "⏱ Cooldown აქტიურია", f"გთხოვთ დაელოდოთ {remaining} წამს ბრძანების ხელახლა გამოსაყენებლად.")
        return

    member = await check_user_permissions(interaction, ROLE_ID, GUILD_ID)
    if not member:
        return

    try:
        await user.send(message)
        cooldowns[user_id] = now
        await send_embed_notification(interaction, "✅ შეტყობინება გაგზავნილია", f"{user.mention}-ს მივწერეთ პირადში.")
    except discord.Forbidden:
        await send_embed_notification(interaction, "🚫 ვერ მოხერხდა გაგზავნა", f"{user.mention} არ იღებს პირად შეტყობინებებს.")
    except discord.HTTPException as e:
        await send_embed_notification(interaction, "❌ შეცდომა შეტყობინების გაგზავნისას", f"დეტალები: {e}")

# /giveacces Command
@bot.tree.command(name="giveaccess", description="მომხმარებელს აძლევს როლს დროებით")
@app_commands.describe(user="მომხმარებელი", duration="ვადა (მაგ.: 7d, 12h, 30m)")
async def giveaccess(interaction: discord.Interaction, user: discord.Member, duration: str):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("⛔ Owner Only!", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)

    # ვადის გამოთვლა
    try:
        if duration.endswith('d'):
            seconds = int(duration[:-1]) * 86400
        elif duration.endswith('h'):
            seconds = int(duration[:-1]) * 3600
        elif duration.endswith('m'):
            seconds = int(duration[:-1]) * 60
        else:
            return await interaction.followup.send("❌ Invalid format. Use: 7d, 12h, 30m")
    except ValueError:
        return await interaction.followup.send("❌ Numbers only (e.g., 7d).")

    expiration_time = datetime.utcnow() + timedelta(seconds=seconds)

    # როლის მინიჭება
    role = interaction.guild.get_role(ROLE_ID)
    if not role:
        return await interaction.followup.send("❌ Role not found.")

    try:
        await user.add_roles(role)
        await access_roles_collection.insert_one({
            "user_id": user.id,
            "guild_id": interaction.guild.id,
            "role_id": role.id,
            "expiration_time": expiration_time
        })
    except Exception as e:
        return await interaction.followup.send(f"❌ Error: {e}")

    # ლოგები
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(
            title="🎟️ Role Added",
            description=f"User: {user.mention}\nDuration: {duration}",
            color=discord.Color.green()
        )
        await log_channel.send(embed=embed)

    await interaction.followup.send(f"✅ {user.mention} received the role for {duration}!")

# /sync (გასწორებული)
@bot.tree.command(name="sync", description="Sync slash commands (Owner Only)")
async def sync(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Owner only!", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    try:
        # სინქრონიზაცია მხოლოდ მითითებულ სერვერზე (Rate Limit-ის თავიდან ასაცილებლად)
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        await interaction.followup.send(f"✅ Synced {len(synced)} commands!")
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Failed to sync: {e}")

# Task: Check expired roles
@tasks.loop(minutes=5)
async def check_expired_roles():
    now = datetime.utcnow()
    async for entry in access_roles_collection.find({"expiration_time": {"$lte": now}}):
        guild = bot.get_guild(entry["guild_id"])
        if not guild:
            continue

        user = guild.get_member(entry["user_id"])
        if not user:
            continue

        role = guild.get_role(entry["role_id"])
        if role:
            try:
                await user.remove_roles(role)
                await access_roles_collection.delete_one({"_id": entry["_id"]})
                print(f"Removed role from {user.name}")
            except Exception as e:
                print(f"Error removing role: {e}")

# Bot ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    
    # სინქრონიზაცია მხოლოდ ერთხელ, სპეციფიკურ სერვერზე
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Synced {len(synced)} commands to guild {GUILD_ID}")
    except Exception as e:
        print(f"Sync error: {e}")


    check_expired_roles.start()

# Run bot
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print(Fore.RED + "❌ DISCORD_TOKEN environment variable is not set.")
