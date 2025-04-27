import os
import time
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
from threading import Thread
from colorama import init, Fore
from datetime import datetime, timedelta
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

# /giveaccess command - ONLY FOR BOT OWNER
@app_commands.describe(
    user="მომხმარებელი, რომელსაც უნდა მიეცეს წვდომა",
    duration="დრო (მაგ. 1d, 5h, 30m)"
)
@bot.tree.command(name="giveaccess", description="მიანიჭეთ დროებითი წვდომა მომხმარებელს (მხოლოდ მფლობელისთვის)")
async def giveaccess(interaction: discord.Interaction, user: discord.Member, duration: str):
    await bot.wait_until_ready()
    
    # მფლობელის ID
    BOT_OWNER_ID = 475160980280705024
    
    # შემოწმება: არის თუ არა მფლობელი
    if interaction.user.id != BOT_OWNER_ID:
        await send_embed_notification(
            interaction,
            "⛔️ უარყოფილი წვდომა",
            "მხოლოდ ბოტის მფლობელს შეუძლია ამ ბრძანების გამოყენება!"
        )
        return
    
    # სერვერის, როლის და ლოგის არხის ID-ები
    GUILD_ID = 1005186618031869952
    ROLE_ID = 1365076710265192590
    LOG_CHANNEL_ID = 1365381000619622460
    
    try:
        # დროის პარსინგი (1d, 5h, 30m)
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

        # სერვერისა და როლის მოძებნა
        target_guild = bot.get_guild(GUILD_ID)
        if not target_guild:
            await send_embed_notification(interaction, "❌ სერვერი არ მოიძებნა", "დარწმუნდით, რომ ბოტი სერვერზეა")
            return
        
        target_member = target_guild.get_member(user.id)
        if not target_member:
            await send_embed_notification(interaction, "❌ მომხმარებელი არ მოიძებნა", f"{user.mention} არ არის მთავარ სერვერზე")
            return
        
        access_role = target_guild.get_role(ROLE_ID)
        if not access_role:
            await send_embed_notification(interaction, "❌ როლი არ მოიძებნა", "დარწმუნდით, რომ როლი არსებობს")
            return
        
        # როლის მინიჭება
        await target_member.add_roles(access_role)
        
        # ლოგირება
        log_channel = target_guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(
                f"🎟 {target_member.mention} ({target_member.display_name}) - მიენიჭა {access_role.name} როლი\n"
                f"⏳ ვადა: {duration}\n"
                f"🕒 ვადის გასვლის დრო: <t:{int(expiry_time.timestamp())}:F>\n"
                f"👤 მინიჭებულია: {interaction.user.mention} (Owner)"
            )
        
        # პასუხი მომხმარებელს (მფლობელს)
        await send_embed_notification(
            interaction,
            "✅ წვდომა მინიჭებულია",
            f"{target_member.mention}-ს მიენიჭა {access_role.name} როლი {duration}-ის განმავლობაში.\n"
            f"ვადა გაუვა: <t:{int(expiry_time.timestamp())}:R>"
        )
        
        # დროის გასვლის შემდეგ როლის ამოღება
        await asyncio.sleep(delta.total_seconds())
        
        if access_role in target_member.roles:
            await target_member.remove_roles(access_role, reason="ვადის გასვლა")
            if log_channel:
                await log_channel.send(f"⏰ {target_member.mention}-ს ამოეღო {access_role.name} როლი (ვადა გაუვიდა)")
    
    except discord.Forbidden:
        await send_embed_notification(interaction, "❌ უფლებები არ არის", "ბოტს არ აქვს საკმარისი უფლებები")
    except (ValueError, IndexError):
        await send_embed_notification(interaction, "❌ არასწორი დრო", "გამოიყენეთ მაგ. 1d, 5h, 30m")

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
