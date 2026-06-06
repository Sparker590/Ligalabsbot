import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import database as db

RANKS = [
    ("🟦 Diamant 💎",    "diamant"),
    ("🟪 Mythique 👑",   "mythique"),
    ("🟥 Légendaire 👿", "legendaire"),
    ("🟧 Master ⭐",     "master"),
    ("🟩 Pro 🏆",        "pro"),
]
ANNEES = [str(y) for y in range(2022, 2027)]

sessions: dict[int, dict] = {}


# ─── PANEL PERMANENT ──────────────────────────────────────

class PanelInscriptionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📋 Inscrire ma team",
        style=discord.ButtonStyle.primary,
        custom_id="lancer_inscription_labs")
    async def lancer(self, interaction: discord.Interaction, btn: discord.ui.Button):
        sessions[interaction.user.id] = {}
        await interaction.response.send_message(
            "📋 **Inscription d'une team** — Étape 1/7\nQuel est le **nom de la team** ?",
            view=NomTeamView(interaction.client, interaction.user, interaction.channel),
            ephemeral=True)


# ─── COG ──────────────────────────────────────────────────

class InscriptionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(PanelInscriptionView())

    # ── Panel public ───────────────────────────────────────
    @app_commands.command(
        name="setup-inscription",
        description="Affiche le panel d'inscription de team dans ce salon")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def setup_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 Inscription LigaLabs",
            description=(
                "Clique sur le bouton pour inscrire ta team.\n\n"
                "Le bot te posera 7 questions :\n"
                "• Nom de la team\n"
                "• Année de création\n"
                "• Nombre de rosters & joueurs\n"
                "• Niveau ranked moyen\n"
                "• Owner de la team\n"
                "• Logo (optionnel)"),
            color=0x5865F2)
        embed.set_footer(text="LigaLabs • Inscriptions")
        await interaction.channel.send(embed=embed, view=PanelInscriptionView())
        await interaction.response.send_message("✅ Panel inscription créé.", ephemeral=True)

    # ── Salon d'annonces ───────────────────────────────────
    @app_commands.command(
        name="set-inscription-channel",
        description="Salon où arrivent les fiches d'inscription des teams")
    @app_commands.describe(channel="Salon de destination")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_insc_ch(self, interaction: discord.Interaction,
                          channel: discord.TextChannel):
        db.set_cfg(interaction.guild_id, "inscription_channel", channel.id)
        await interaction.response.send_message(
            f"✅ Annonces inscriptions → {channel.mention}", ephemeral=True)

    # ── Commande slash directe ─────────────────────────────
    @app_commands.command(name="inscription",
                          description="Inscrire une team à la LigaLabs")
    async def inscription(self, interaction: discord.Interaction):
        sessions[interaction.user.id] = {}
        await interaction.response.send_message(
            "📋 **Inscription d'une team** — Étape 1/7\nQuel est le **nom de la team** ?",
            view=NomTeamView(self.bot, interaction.user, interaction.channel),
            ephemeral=True)

    # ── Appelé par ticket.py ───────────────────────────────
    async def start_inscription(self, channel: discord.TextChannel,
                                user: discord.Member):
        sessions[user.id] = {}
        await channel.send(
            f"{user.mention} 📋 **Inscription — Étape 1/7**\nQuel est le **nom de la team** ?",
            view=NomTeamView(self.bot, user, channel, ticket_mode=True))


# ─── STEP 1 — Nom ─────────────────────────────────────────

class NomTeamModal(discord.ui.Modal, title="Nom de la team"):
    nom = discord.ui.TextInput(label="Nom de la team", placeholder="Ex: Wolves Esport",
                               max_length=50)

    def __init__(self, bot, user, channel, ticket_mode=False):
        super().__init__()
        self.bot = bot
        self.user = user
        self.channel = channel
        self.ticket_mode = ticket_mode

    async def on_submit(self, interaction: discord.Interaction):
        sessions[self.user.id]["nom"] = self.nom.value
        await interaction.response.edit_message(
            content=f"✅ Team **{self.nom.value}** — Étape 2/7\nAnnée de création ?",
            view=AnneeView(self.bot, self.user, self.channel, self.ticket_mode))


class NomTeamView(discord.ui.View):
    def __init__(self, bot, user, channel, ticket_mode=False):
        super().__init__(timeout=300)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.ticket_mode = ticket_mode

    @discord.ui.button(label="✏️ Saisir le nom", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            NomTeamModal(self.bot, self.user, self.channel, self.ticket_mode))


# ─── STEP 2 — Année ───────────────────────────────────────

class AnneeView(discord.ui.View):
    def __init__(self, bot, user, channel, ticket_mode=False):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.ticket_mode = ticket_mode
        sel = discord.ui.Select(
            placeholder="Année de création...",
            options=[discord.SelectOption(label=a, value=a) for a in ANNEES])
        sel.callback = self.on_annee
        self.add_item(sel)

    async def on_annee(self, interaction: discord.Interaction):
        sessions[self.user.id]["annee"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content=f"✅ Année **{interaction.data['values'][0]}** — Étape 3/7\nNombre de rosters ?",
            view=RostersView(self.bot, self.user, self.channel, self.ticket_mode))


# ─── STEP 3 — Rosters ─────────────────────────────────────

class RostersView(discord.ui.View):
    def __init__(self, bot, user, channel, ticket_mode=False):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.ticket_mode = ticket_mode
        sel = discord.ui.Select(
            placeholder="Nombre de rosters (max 5)...",
            options=[discord.SelectOption(label=str(i), value=str(i)) for i in range(1, 6)])
        sel.callback = self.on_rosters
        self.add_item(sel)

    async def on_rosters(self, interaction: discord.Interaction):
        n = int(interaction.data["values"][0])
        sessions[self.user.id]["nb_rosters"] = n
        sessions[self.user.id]["rosters"] = []
        sessions[self.user.id]["current_roster"] = 1
        sessions[self.user.id]["current_player"] = 1
        sessions[self.user.id]["current_players"] = []
        await interaction.response.edit_message(
            content=(f"✅ **{n} roster(s)** — Étape 4/7\n"
                     f"**Roster 1** — Ping le joueur 1 en répondant dans ce salon\n"
                     "(ou tape `fin` pour terminer ce roster)"),
            view=None)
        ch = interaction.channel if not self.ticket_mode else self.channel
        await self._wait_players(ch)

    async def _wait_players(self, channel):
        user = self.user
        sess = sessions[user.id]

        while sess["current_roster"] <= sess["nb_rosters"]:
            r_num = sess["current_roster"]

            def check(m):
                return m.author.id == user.id and m.channel.id == channel.id

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=180)
            except asyncio.TimeoutError:
                await channel.send("⏱️ Temps écoulé. Recommence avec `/inscription`.")
                return

            if msg.content.lower() == "fin" or not msg.mentions:
                sess["rosters"].append(list(sess["current_players"]))
                sess["current_players"] = []
                sess["current_roster"] += 1
                sess["current_player"] = 1
                if sess["current_roster"] <= sess["nb_rosters"]:
                    await channel.send(
                        f"✅ Roster {r_num} enregistré ! "
                        f"**Roster {sess['current_roster']}** — Ping le joueur 1 :")
            else:
                player = msg.mentions[0]
                sess["current_players"].append(
                    {"id": str(player.id), "name": player.display_name})
                sess["current_player"] += 1
                await channel.send(
                    f"✅ {player.display_name} ajouté — "
                    f"Ping le joueur {sess['current_player']} (ou tape `fin`) :")

        await channel.send(
            "✅ Rosters enregistrés ! — **Étape 5/7** Niveau ranked moyen ?",
            view=RankView(self.bot, user, channel, self.ticket_mode))


# ─── STEP 5 — Rank ────────────────────────────────────────

class RankView(discord.ui.View):
    def __init__(self, bot, user, channel, ticket_mode=False):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.ticket_mode = ticket_mode
        sel = discord.ui.Select(
            placeholder="Niveau ranked...",
            options=[discord.SelectOption(label=label, value=val) for label, val in RANKS])
        sel.callback = self.on_rank
        self.add_item(sel)

    async def on_rank(self, interaction: discord.Interaction):
        sessions[self.user.id]["rank"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content="✅ Niveau enregistré ! — **Étape 6/7** Ping l'**owner** de la team :",
            view=None)
        ch = interaction.channel if not self.ticket_mode else self.channel
        await self._wait_owner(ch)

    async def _wait_owner(self, channel):
        user = self.user

        def check(m):
            return m.author.id == user.id and m.channel.id == channel.id and m.mentions

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=180)
        except asyncio.TimeoutError:
            await channel.send("⏱️ Temps écoulé.")
            return

        sessions[user.id]["owner"] = {
            "id":   str(msg.mentions[0].id),
            "name": msg.mentions[0].display_name
        }
        await channel.send(
            "✅ Owner enregistré ! — **Étape 7/7** La team a-t-elle un logo ?",
            view=LogoView(self.bot, user, channel, self.ticket_mode))


# ─── STEP 7 — Logo ────────────────────────────────────────

class LogoView(discord.ui.View):
    def __init__(self, bot, user, channel, ticket_mode=False):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.ticket_mode = ticket_mode

    @discord.ui.button(label="✅ Oui", style=discord.ButtonStyle.success)
    async def oui(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="📎 Envoie le logo en pièce jointe dans ce salon :", view=None)
        ch = interaction.channel if not self.ticket_mode else self.channel
        await self._wait_logo(ch)

    @discord.ui.button(label="❌ Non", style=discord.ButtonStyle.secondary)
    async def non(self, interaction: discord.Interaction, button: discord.ui.Button):
        sessions[self.user.id]["logo_url"] = None
        await interaction.response.edit_message(content="✅ Pas de logo.", view=None)
        ch = interaction.channel if not self.ticket_mode else self.channel
        await envoyer_recap(self.bot, self.user, ch, interaction.guild)

    async def _wait_logo(self, channel):
        user = self.user

        def check(m):
            return m.author.id == user.id and m.channel.id == channel.id and m.attachments

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=180)
            sessions[user.id]["logo_url"] = msg.attachments[0].url
            await channel.send("✅ Logo reçu !")
        except asyncio.TimeoutError:
            sessions[user.id]["logo_url"] = None
            await channel.send("⏱️ Pas de logo reçu.")

        await envoyer_recap(self.bot, user, channel, channel.guild)


# ─── RÉCAPITULATIF FINAL ──────────────────────────────────

async def envoyer_recap(bot, user, channel, guild):
    sess     = sessions.get(user.id, {})
    guild_id = str(guild.id)
    ch_id    = db.cfg(guild_id, "inscription_channel")

    embed = discord.Embed(title="📋 Nouvelle Inscription Team", color=0x5865F2)
    embed.add_field(name="Team",      value=sess.get("nom",   "?"), inline=True)
    embed.add_field(name="Année",     value=sess.get("annee", "?"), inline=True)
    embed.add_field(name="Owner",     value=sess.get("owner", {}).get("name", "?"), inline=True)
    embed.add_field(name="Rank moyen",value=sess.get("rank",  "?"), inline=True)
    embed.add_field(name="Nb rosters",value=str(sess.get("nb_rosters", 0)), inline=True)

    for i, roster in enumerate(sess.get("rosters", []), 1):
        joueurs = ", ".join(p["name"] for p in roster) if roster else "Aucun"
        embed.add_field(name=f"Roster {i}", value=joueurs, inline=False)

    if sess.get("logo_url"):
        embed.set_thumbnail(url=sess["logo_url"])

    embed.set_footer(text=f"Soumis par {user.display_name}")

    if ch_id:
        target = guild.get_channel(int(ch_id))
        if target:
            await target.send(embed=embed)

    await channel.send("✅ **Inscription envoyée !**", embed=embed)
    sessions.pop(user.id, None)


async def setup(bot):
    await bot.add_cog(InscriptionCog(bot))
