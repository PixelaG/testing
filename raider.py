import os
import time
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View
from flask import Flask
from threading import Thread
from colorama import init, Fore
from datetime import datetime, timedelta
from pymongo import MongoClient 
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

mongo_uri = os.getenv("MONGO_URI") 

# MongoDB კავშირი
client = MongoClient(mongo_uri)
db = client["discord_bot"]  # MongoDB მონაცემთა ბაზა
access_entries = db["access_entries"]  # MongoDB კოლექცია

# Discord bot setup
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
intents.typing = False
intents.presences = False

bot = commands.Bot(command_prefix="!", intents=intents)

async def check_expired_roles():
    """შეამოწმებს და ამოიღებს ვადაგასულ როლებს"""
    while True:
        try:
            now = datetime.utcnow()
            expired_entries = access_entries.find({"expiry_time": {"$lt": now}})
            
            for entry in expired_entries:
                guild = bot.get_guild(entry["guild_id"])
                if not guild:
                    continue
                
                try:
                    member = await guild.fetch_member(entry["user_id"])
                    role = guild.get_role(entry["role_id"])
                    
                    if role and member and role in member.roles:
                        await member.remove_roles(role)
                        
                        # ლოგირება
                        log_channel = guild.get_channel(entry["log_channel_id"])
                        if log_channel:
                            expired_embed = discord.Embed(
                                title="⏰ დაკარგა წვდომა ",
                                description=f"{member.mention}-ს აღარ აქვს {role.name} როლი",
                                color=discord.Color.red()
                            )
                            expired_embed.add_field(
                                name="🔚 ვადა გაუვიდა",
                                value=f"<t:{int(entry['expiry_time'].timestamp())}:F>",
                                inline=True
                            )
                            await log_channel.send(embed=expired_embed)
                    
                    # წაშალე ჩანაწერი ბაზიდან
                    access_entries.delete_one({"_id": entry["_id"]})
                
                except discord.NotFound:
                    access_entries.delete_one({"_id": entry["_id"]})
                except Exception as e:
                    print(f"შეცდომა როლის ამოღებისას: {e}")
        
        except Exception as e:
            print(f"შეცდომა check_expired_roles-ში: {e}")
        
        await asyncio.sleep(60)

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
    def __init__(self, message: str):
        super().__init__(timeout=180)
        self.message_content = message
        self.last_clicked = {}

    @discord.ui.button(label="გასპამვა", style=discord.ButtonStyle.danger)
    async def spam(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        now = time.time()

        last_time = self.last_clicked.get(user_id, 0)

        if now - last_time < 3:
            await interaction.response.send_message(
                "გთხოვთ დაელოდოთ 3 წამი სანამ ისევ დააჭერთ.", 
                ephemeral=True
            )
            return

        self.last_clicked[user_id] = now

        await interaction.response.defer(thinking=False)

        for _ in range(5):
            await interaction.followup.send(self.message_content)

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

    member = await check_user_permissions(interaction, 1365076710265192590, 1005186618031869952)
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

    member = await check_user_permissions(interaction, 1365076710265192590, 1005186618031869952)
    if not member:
        return

    embed = discord.Embed(title="🟢 ერთჯერადი გაგზავნის ღილაკი", description=message, color=discord.Color.green())
    embed.set_footer(text=f"შექმნილია {interaction.user.display_name}")

    view = SingleUseButton(message)
    try:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    except discord.NotFound:
        print("⚠ Interaction ვადა გასულია (onlyone).")

# /dmmsg command with cooldown
@bot.tree.command(name="dmmsg", description="გაგზავნე DM არჩეულ მომხმარებელზე")
@app_commands.describe(
    user="მომხმარებელი, რომელსაც გსურს პირადში მიწერა",
    message="შეტყობინება რომელიც გსურს რომ გააგზავნო"
)
async def dmmsg(interaction: discord.Interaction, user: discord.User, message: str):
    await bot.wait_until_ready()

    # Cooldown შემოწმება
    seconds = 300  # 5 წუთი
    user_id = interaction.user.id
    now = time.time()
    last_used = cooldowns.get(user_id, 0)

    if now - last_used < seconds:
        remaining = int(seconds - (now - last_used))
        await send_embed_notification(interaction, "⏱ Cooldown აქტიურია", f"გთხოვთ დაელოდოთ {remaining} წამს ბრძანების ხელახლა გამოსაყენებლად.")
        return

    # უფლებების შემოწმება
    member = await check_user_permissions(interaction, 1365076710265192590, 1005186618031869952)
    if not member:
        return

    try:
        await user.send(message)
        cooldowns[user_id] = now  # ✅ მხოლოდ წარმატების შემთხვევაში ვანახლებთ cooldown-ს
        await send_embed_notification(interaction, "✅ შეტყობინება გაგზავნილია", f"{user.mention}-ს მივწერეთ პირადში.")
    except discord.Forbidden:
        await send_embed_notification(interaction, "🚫 ვერ მოხერხდა გაგზავნა", f"{user.mention} არ იღებს პირად შეტყობინებებს.")
    except discord.HTTPException as e:
        await send_embed_notification(interaction, "❌ შეცდომა შეტყობინების გაგზავნისას", f"დეტალები: {e}")


@bot.tree.command(name="invisibletext", description="გააქრო ჩატი უხილავი ტექსტით")
async def invisibletext(interaction: discord.Interaction):
    await bot.wait_until_ready()

    try:
        # Interaction-ზე ვპასუხობთ ჩუმად, რომელსაც მხოლოდ user ნახავს
        await interaction.response.send_message("✅ წარმატებით გაიგზავნა უხილავი შეტყობინება.", ephemeral=True)

        # დაველოდოთ ცოტა დრო, რომ interaction-ის ვადა არ გასულიყო
        await asyncio.sleep(1)

        # ახლა ვReply-ებთ ჩვენს "✅" შეტყობინებას
        invisible_char = "\u200B"  # უხილავი სიმბოლო
        line_count = 1000
        message = (invisible_char + "\n") * line_count

        # Reply-ება "followup"-ით
        message_sent = await interaction.followup.send(content=message, ephemeral=False)

        # დაველოდოთ 5 წამი და შემდეგ წავშალოთ
        await asyncio.sleep(5)

        # მხოლოდ მაშინ წავშლით, თუ message_sent ისევ არსებობს
        try:
            await message_sent.delete()

# /giveaccess command - ONLY FOR BOT OWNER
@app_commands.describe(
    user="მომხმარებელი, რომელსაც უნდა მიეცეს წვდომა",
    duration="დრო (მაგ. 1d, 5h, 30m)"
)
@bot.tree.command(name="giveaccess", description="მიანიჭეთ დროებითი წვდომა მომხმარებელს (მხოლოდ მფლობელისთვის)")
async def giveaccess(interaction: discord.Interaction, user: discord.User, duration: str):
    await bot.wait_until_ready()
    
    BOT_OWNER_ID = 475160980280705024
    if interaction.user.id != BOT_OWNER_ID:
        await send_embed_notification(interaction, "⛔️ უარყოფილი წვდომა", "მხოლოდ ბოტის მფლობელს შეუძლია ამ ბრძანების გამოყენება!")
        return
    
    GUILD_ID = 1005186618031869952
    ROLE_ID = 1365076710265192590
    LOG_CHANNEL_ID = 1365381000619622460
    
    try:
        # დროის პარსინგი
        time_unit = duration[-1].lower()
        time_value = duration[:-1]
        
        if not time_value.isdigit():
            await send_embed_notification(interaction, "❌ არასწორი ფორმატი", "გამოიყენეთ მაგ. 1d, 5h, 30m")
            return
            
        time_value = int(time_value)
        
        if time_unit == 'd':
            delta = timedelta(days=time_value)
        elif time_unit == 'h':
            delta = timedelta(hours=time_value)
        elif time_unit == 'm':
            delta = timedelta(minutes=time_value)
        else:
            await send_embed_notification(interaction, "❌ არასწორი ერთეული", "გამოიყენეთ d (დღე), h (საათი) ან m (წუთი)")
            return
            
        expiry_time = datetime.utcnow() + delta

        # სერვერისა და მომხმარებლის პოვნა
        target_guild = bot.get_guild(GUILD_ID)
        if not target_guild:
            await send_embed_notification(interaction, "❌ სერვერი არ მოიძებნა", "დარწმუნდით, რომ ბოტი სერვერზეა")
            return
        
        try:
            target_member = await target_guild.fetch_member(user.id)
        except discord.NotFound:
            await send_embed_notification(interaction, "❌ მომხმარებელი არ მოიძებნა", f"{user.mention} არ არის სერვერზე")
            return
        
        access_role = target_guild.get_role(ROLE_ID)
        if not access_role:
            await send_embed_notification(interaction, "❌ როლი არ მოიძებნა", "დარწმუნდით, რომ როლი არსებობს")
            return
        
        # როლის მინიჭება
        await target_member.add_roles(access_role)
        
        # შენახვა MongoDB-ში
        access_entry = {
            "user_id": target_member.id,
            "guild_id": target_guild.id,
            "role_id": access_role.id,
            "log_channel_id": LOG_CHANNEL_ID,
            "assigned_by": interaction.user.id,
            "duration": duration,
            "assigned_at": datetime.utcnow(),
            "expiry_time": expiry_time,
            "is_active": True
        }
        access_entries.insert_one(access_entry)
        
        # Embed ლოგის შექმნა
        log_embed = discord.Embed(
            title="🎟 წვდომა მინიჭებულია",
            color=discord.Color.green()
        )
        log_embed.add_field(
            name="👤 მომხმარებელი",
            value=f"{target_member.mention} (`{target_member.display_name}`)",
            inline=False
        )
        log_embed.add_field(
            name="⏳ ვადა",
            value=f"`{duration}`",
            inline=True
        )
        log_embed.add_field(
            name="🕒 ვადის გასვლის დრო",
            value=f"<t:{int(expiry_time.timestamp())}:F>",
            inline=True
        )
        log_embed.add_field(
            name="🔑 მინიჭებულია",
            value=f"<@{interaction.user.id}> (Owner)",
            inline=False
        )
        log_embed.set_thumbnail(url=target_member.display_avatar.url)
        log_embed.set_footer(text=f"ID: {target_member.id}")

        # ლოგის არხში გაგზავნა
        log_channel = target_guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(embed=log_embed)

    # პასუხი მომხმარებელს (Owner-ს)
        await send_embed_notification(
            interaction,
            "✅ წვდომა მინიჭებულია",
            f"{target_member.mention}-ს მიენიჭა {access_role.name} როლი {duration}-ის განმავლობაში.\n"
            f"ვადა გაუვა: <t:{int(expiry_time.timestamp())}:R>"
        )
    
    except discord.Forbidden:
        await send_embed_notification(interaction, "❌ უფლებები არ არის", "ბოტს არ აქვს საკმარისი უფლებები")
    except Exception as e:
        await send_embed_notification(interaction, "❌ შეცდომა", f"ტექნიკური შეცდომა: `{e}`")

# Bot ready
@bot.event
async def on_ready():
    print(f"✅ Bot connected as {bot.user}")
    await bot.change_presence(status=discord.Status.invisible)
    
    # დაწყება ვადაგასული როლების შემოწმების
    bot.loop.create_task(check_expired_roles())
    
    try:
        # აღადგინე აქტიური როლები ბოტის რესტარტის შემთხვევაში
        now = datetime.utcnow()
        active_entries = access_entries.find({"expiry_time": {"$gt": now}, "is_active": True})
        
        for entry in active_entries:
            guild = bot.get_guild(entry["guild_id"])
            if not guild:
                continue
                
            try:
                member = await guild.fetch_member(entry["user_id"])
                role = guild.get_role(entry["role_id"])
                
                if role and member and role not in member.roles:
                    await member.add_roles(role)
                    print(f"აღდგენილი როლი: {member.display_name} -> {role.name}")
            except:
                continue
    
    except Exception as e:
        print(f"შეცდომა როლების აღდგენისას: {e}")
    
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
