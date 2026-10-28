
import os
import json
import asyncio
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# ==================== CONFIGURARE ====================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CONFIG_FILE = "bot_config.json"

# Rolurile autorizate pentru gestionarea ticketelor
TICKET_STAFF_ROLES = {
    1564237862080352320,
    1564025268002361384,
}

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ==================== CONFIGURAȚIE ====================

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


config = load_config()


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def settings(guild_id):
    key = str(guild_id)
    if key not in config or not isinstance(config[key], dict):
        config[key] = {}
    return config[key]


def black_embed(title, description=""):
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.from_rgb(0, 0, 0)
    )


async def send_log(guild, text):
    if guild is None:
        return

    channel_id = settings(guild.id).get("log_channel")
    channel = guild.get_channel(channel_id) if channel_id else None

    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(
                embed=black_embed("📋 Jurnal moderare", text)
            )
        except discord.HTTPException:
            pass


def is_ticket_staff(member):
    return (
        member.guild_permissions.administrator
        or any(role.id in TICKET_STAFF_ROLES for role in member.roles)
    )


# ==================== TICKETE ====================

class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Revendică",
        emoji="🙋",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:claim"
    )
    async def claim(self, interaction, button):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Comandă disponibilă doar pe server.",
                ephemeral=True
            )
            return

        if not is_ticket_staff(interaction.user):
            await interaction.response.send_message(
                "Nu ai permisiunea să revendici acest ticket.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=black_embed(
                "🙋 Ticket revendicat",
                f"Ticketul a fost preluat de {interaction.user.mention}."
            )
        )

    @discord.ui.button(
        label="Închide ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:close"
    )
    async def close(self, interaction, button):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Comandă disponibilă doar pe server.",
                ephemeral=True
            )
            return

        if not is_ticket_staff(interaction.user):
            await interaction.response.send_message(
                "Nu ai permisiunea să închizi acest ticket.",
                ephemeral=True
            )
            return

        channel = interaction.channel
        await interaction.response.send_message(
            "Ticketul se închide..."
        )

        if isinstance(channel, discord.TextChannel):
            await asyncio.sleep(2)
            try:
                await channel.delete(
                    reason=f"Închis de {interaction.user}"
                )
            except discord.HTTPException:
                pass


class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Deschide ticket",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:create"
    )
    async def create(self, interaction, button):
        guild = interaction.guild
        user = interaction.user

        if guild is None or not isinstance(user, discord.Member):
            await interaction.response.send_message(
                "Folosește acest buton pe un server.",
                ephemeral=True
            )
            return

        for channel in guild.text_channels:
            if channel.topic == f"ticket-owner:{user.id}":
                await interaction.response.send_message(
                    f"Ai deja un ticket: {channel.mention}",
                    ephemeral=True
                )
                return

        overwrites = {
            guild.default_role:
                discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            )
        }

        for role in guild.roles:
            if role.id in TICKET_STAFF_ROLES:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True
            )

        category_id = settings(guild.id).get("ticket_category")
        category = guild.get_channel(category_id) if category_id else None

        if not isinstance(category, discord.CategoryChannel):
            category = None

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{user.id}",
                topic=f"ticket-owner:{user.id}",
                overwrites=overwrites,
                category=category,
                reason=f"Ticket deschis de {user}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Botul nu are permisiunea Manage Channels.",
                ephemeral=True
            )
            return

        await channel.send(
            f"{user.mention}",
            embed=black_embed(
                "🎫 Ticket deschis",
                "Personalul va răspunde aici. Folosește butoanele pentru gestionare."
            ),
            view=TicketControls()
        )

        await interaction.response.send_message(
            f"Ticket creat: {channel.mention}",
            ephemeral=True
        )


# ==================== EVENIMENTE ====================

@bot.event
async def on_ready():
    # Înregistrăm butoanele persistente o singură dată.
    if not getattr(bot, "_views_registered", False):
        bot.add_view(TicketPanel())
        bot.add_view(TicketControls())
        bot._views_registered = True

    try:
        synced = await bot.tree.sync()
        print(f"Comenzi sincronizate: {len(synced)}")
    except discord.HTTPException as error:
        print(f"Eroare la sincronizarea comenzilor: {error}")

    print(f"Bot conectat: {bot.user}")


@bot.event
async def on_member_join(member):
    cfg = settings(member.guild.id)

    # Autorol
    role_id = cfg.get("autorole")
    role = member.guild.get_role(role_id) if role_id else None

    if role:
        try:
            await member.add_roles(role, reason="Autorol")
        except discord.HTTPException:
            pass

    # Welcome
    channel_id = cfg.get("welcome_channel")
    channel = member.guild.get_channel(channel_id) if channel_id else None

    if isinstance(channel, discord.TextChannel):
        embed = black_embed(
            "👋 Bine ai venit!",
            f"Bine ai venit pe **{member.guild.name}**, {member.mention}!\n"
            "Citește regulile și distracție plăcută! 🎉"
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass


@bot.event
async def on_member_remove(member):
    cfg = settings(member.guild.id)
    channel_id = cfg.get("goodbye_channel")
    channel = member.guild.get_channel(channel_id) if channel_id else None

    if isinstance(channel, discord.TextChannel):
        embed = black_embed(
            "👋 La revedere!",
            f"**{discord.utils.escape_markdown(member.display_name)}** "
            "a părăsit serverul."
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass


# ==================== CONFIGURARE SERVER ====================

@bot.tree.command(name="welcome", description="Setează canalul de welcome")
@app_commands.checks.has_permissions(manage_guild=True)
async def welcome(
    interaction: discord.Interaction,
    canal: discord.TextChannel
):
    settings(interaction.guild_id)["welcome_channel"] = canal.id
    save_config()

    await interaction.response.send_message(
        embed=black_embed(
            "✅ Welcome configurat",
            f"Mesajele de bun venit vor apărea în {canal.mention}."
        ),
        ephemeral=True
    )


@bot.tree.command(name="goodbye", description="Setează canalul de goodbye")
@app_commands.checks.has_permissions(manage_guild=True)
async def goodbye(
    interaction: discord.Interaction,
    canal: discord.TextChannel
):
    settings(interaction.guild_id)["goodbye_channel"] = canal.id
    save_config()

    await interaction.response.send_message(
        embed=black_embed(
            "✅ Goodbye configurat",
            f"Mesajele de plecare vor apărea în {canal.mention}."
        ),
        ephemeral=True
    )


@bot.tree.command(name="autorole", description="Setează rolul automat")
@app_commands.checks.has_permissions(manage_roles=True)
async def autorole(
    interaction: discord.Interaction,
    rol: discord.Role
):
    guild = interaction.guild

    if guild and guild.me and rol >= guild.me.top_role:
        await interaction.response.send_message(
            "Mută rolul botului deasupra rolului pe care vrei să-l acorde.",
            ephemeral=True
        )
        return

    settings(interaction.guild_id)["autorole"] = rol.id
    save_config()

    await interaction.response.send_message(
        embed=black_embed(
            "✅ Autorol configurat",
            f"Membrii noi vor primi rolul {rol.mention}."
        ),
        ephemeral=True
    )


@bot.tree.command(name="setlogchannel", description="Setează canalul de loguri")
@app_commands.checks.has_permissions(manage_guild=True)
async def setlogchannel(
    interaction: discord.Interaction,
    canal: discord.TextChannel
):
    settings(interaction.guild_id)["log_channel"] = canal.id
    save_config()

    await interaction.response.send_message(
        embed=black_embed(
            "✅ Loguri configurate",
            f"Jurnalul va fi trimis în {canal.mention}."
        ),
        ephemeral=True
    )


@bot.tree.command(name="ticketpanel", description="Trimite panoul de tickete")
@app_commands.checks.has_permissions(manage_channels=True)
async def ticketpanel(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "Folosește comanda într-un canal text.",
            ephemeral=True
        )
        return

    await interaction.channel.send(
        embed=black_embed(
            "🎫 Sistem de tickete",
            "Apasă butonul pentru a deschide un ticket privat."
        ),
        view=TicketPanel()
    )

    await interaction.response.send_message(
        "Panoul a fost trimis.",
        ephemeral=True
    )


# ==================== MODERARE ====================

@bot.tree.command(name="warn", description="Avertizează un membru")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(
    interaction: discord.Interaction,
    membru: discord.Member,
    motiv: str = "Fără motiv specificat"
):
    await interaction.response.send_message(
        embed=black_embed(
            "⚠️ Avertisment",
            f"{membru.mention} a primit un avertisment.\n**Motiv:** {motiv}"
        )
    )
    await send_log(
        interaction.guild,
        f"{interaction.user.mention} l-a avertizat pe {membru.mention}.\n"
        f"**Motiv:** {motiv}"
    )


@bot.tree.command(name="timeout", description="Pune un membru în timeout")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(
    interaction: discord.Interaction,
    membru: discord.Member,
    minute: app_commands.Range[int, 1, 40320],
    motiv: str = "Fără motiv specificat"
):
    try:
        await membru.timeout(
            timedelta(minutes=minute),
            reason=f"{motiv} | De: {interaction.user}"
        )
        await interaction.response.send_message(
            embed=black_embed(
                "⏳ Timeout aplicat",
                f"{membru.mention} a primit timeout pentru {minute} minute.\n"
                f"**Motiv:** {motiv}"
            )
        )
        await send_log(
            interaction.guild,
            f"{interaction.user.mention} a aplicat timeout lui "
            f"{membru.mention} pentru {minute} minute.\n**Motiv:** {motiv}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "Nu pot aplica timeout acestui membru.",
            ephemeral=True
        )


@bot.tree.command(name="untimeout", description="Elimină timeoutul")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(
    interaction: discord.Interaction,
    membru: discord.Member
):
    try:
        await membru.timeout(
            None,
            reason=f"Timeout eliminat de {interaction.user}"
        )
        await interaction.response.send_message(
            embed=black_embed(
                "✅ Timeout eliminat",
                f"Timeoutul lui {membru.mention} a fost eliminat."
            )
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "Nu pot elimina timeoutul acestui membru.",
            ephemeral=True
        )


@bot.tree.command(name="kick", description="Elimină un membru")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(
    interaction: discord.Interaction,
    membru: discord.Member,
    motiv: str = "Fără motiv specificat"
):
    try:
        await membru.kick(reason=f"{motiv} | De: {interaction.user}")
        await interaction.response.send_message(
            embed=black_embed(
                "👢 Membru eliminat",
                f"{membru} a fost eliminat.\n**Motiv:** {motiv}"
            )
        )
        await send_log(
            interaction.guild,
            f"{interaction.user.mention} l-a eliminat pe {membru}.\n"
            f"**Motiv:** {motiv}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "Nu pot elimina acest membru. Verifică rolurile botului.",
            ephemeral=True
        )


@bot.tree.command(name="ban", description="Banează un membru")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(
    interaction: discord.Interaction,
    membru: discord.Member,
    motiv: str = "Fără motiv specificat"
):
    try:
        await membru.ban(reason=f"{motiv} | De: {interaction.user}")
        await interaction.response.send_message(
            embed=black_embed(
                "🔨 Membru banat",
                f"{membru} a fost banat.\n**Motiv:** {motiv}"
            )
        )
        await send_log(
            interaction.guild,
            f"{interaction.user.mention} l-a banat pe {membru}.\n"
            f"**Motiv:** {motiv}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "Nu pot bana acest membru. Verifică rolurile botului.",
            ephemeral=True
        )


@bot.tree.command(name="unban", description="Debanează după ID")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(
    interaction: discord.Interaction,
    user_id: str
):
    if not user_id.isdigit():
        await interaction.response.send_message(
            "ID-ul trebuie să conțină doar cifre.",
            ephemeral=True
        )
        return

    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(
            user,
            reason=f"Debanat de {interaction.user}"
        )
        await interaction.response.send_message(
            embed=black_embed(
                "✅ Ban eliminat",
                f"Utilizatorul **{user}** a fost debanat."
            )
        )
    except discord.NotFound:
        await interaction.response.send_message(
            "Utilizatorul nu este banat sau ID-ul nu există.",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "Nu am permisiunea să elimin banul.",
            ephemeral=True
        )


@bot.tree.command(name="addrole", description="Adaugă un rol")
@app_commands.checks.has_permissions(manage_roles=True)
async def addrole(
    interaction: discord.Interaction,
    membru: discord.Member,
    rol: discord.Role
):
    guild = interaction.guild

    if guild and guild.me and rol >= guild.me.top_role:
        await interaction.response.send_message(
            "Rolul este prea sus în ierarhie.",
            ephemeral=True
        )
        return

    try:
        await membru.add_roles(rol, reason=f"Adăugat de {interaction.user}")
        await interaction.response.send_message(
            embed=black_embed(
                "✅ Rol adăugat",
                f"{rol.mention} a fost adăugat lui {membru.mention}."
            )
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "Nu am permisiunea să adaug acest rol.",
            ephemeral=True
        )


@bot.tree.command(name="removerole", description="Elimină un rol")
@app_commands.checks.has_permissions(manage_roles=True)
async def removerole(
    interaction: discord.Interaction,
    membru: discord.Member,
    rol: discord.Role
):
    guild = interaction.guild

    if guild and guild.me and rol >= guild.me.top_role:
        await interaction.response.send_message(
            "Rolul este prea sus în ierarhie.",
            ephemeral=True
        )
        return

    try:
        await membru.remove_roles(
            rol,
            reason=f"Eliminat de {interaction.user}"
        )
        await interaction.response.send_message(
            embed=black_embed(
                "✅ Rol eliminat",
                f"{rol.mention} a fost eliminat de la {membru.mention}."
            )
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "Nu am permisiunea să elimin acest rol.",
            ephemeral=True
        )


@bot.tree.command(name="clear", description="Șterge mesaje din canal")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(
    interaction: discord.Interaction,
    numar: app_commands.Range[int, 1, 100]
):
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "Folosește comanda într-un canal text.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        deleted = await interaction.channel.purge(limit=numar)
        await interaction.followup.send(
            embed=black_embed(
                "🧹 Mesaje șterse",
                f"Am șters **{len(deleted)}** mesaje."
            ),
            ephemeral=True
        )
        await send_log(
            interaction.guild,
            f"{interaction.user.mention} a șters {len(deleted)} mesaje "
            f"în {interaction.channel.mention}."
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "Nu am permisiunea Manage Messages.",
            ephemeral=True
        )


@bot.tree.command(name="lock", description="Blochează canalul")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction):
    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "Folosește comanda într-un canal text.",
            ephemeral=True
        )
        return

    overwrite = channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite,
        reason=f"Blocat de {interaction.user}"
    )

    await interaction.response.send_message(
        embed=black_embed(
            "🔒 Canal blocat",
            f"{channel.mention} a fost blocat pentru @everyone."
        )
    )


@bot.tree.command(name="unlock", description="Deblochează canalul")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction):
    channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "Folosește comanda într-un canal text.",
            ephemeral=True
        )
        return

    overwrite = channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = None
    await channel.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite,
        reason=f"Deblocat de {interaction.user}"
    )

    await interaction.response.send_message(
        embed=black_embed(
            "🔓 Canal deblocat",
            "Permisiunea de trimitere a mesajelor a revenit la valoarea implicită."
        )
    )


# ==================== LISTA COMENZILOR ====================

@bot.tree.command(name="comenzi", description="Afișează comenzile botului")
async def comenzi(interaction: discord.Interaction):
    embed = black_embed(
        "📜 Comenzi Bot",
        "**⚙️ Configurare**\n"
        "`/welcome` — setează canalul de bun venit\n"
        "`/goodbye` — setează canalul de plecare\n"
        "`/autorole` — setează rolul automat\n"
        "`/setlogchannel` — setează canalul de loguri\n"
        "`/ticketpanel` — trimite panoul de tickete\n\n"
        "**🛡️ Moderare**\n"
        "`/warn` — avertizează un membru\n"
        "`/timeout` și `/untimeout` — gestionează timeoutul\n"
        "`/kick` — elimină un membru\n"
        "`/ban` și `/unban` — gestionează banurile\n"
        "`/addrole` și `/removerole` — gestionează rolurile\n"
        "`/clear` — șterge mesaje\n"
        "`/lock` și `/unlock` — blochează/deblochează canalul\n\n"
        "**🎫 Tickete**\n"
        "Deschide ticketul folosind butonul din panou."
    )
    embed.set_footer(text="Comenzile de moderare necesită permisiunile corespunzătoare.")
    await interaction.response.send_message(embed=embed)


# ==================== ERORI ====================

@bot.tree.error
async def command_error(interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        message = "Nu ai permisiunile necesare pentru această comandă."
    elif isinstance(error, app_commands.BotMissingPermissions):
        message = "Botului îi lipsesc permisiunile necesare."
    else:
        print(f"Eroare la comandă: {error}")
        message = "A apărut o eroare la executarea comenzii."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


# ==================== PORNIRE ====================

if not TOKEN:
    raise RuntimeError(
        "Nu găsesc DISCORD_TOKEN. Verifică fișierul .env."
    )

bot.run(TOKEN)
