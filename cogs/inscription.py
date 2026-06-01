import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import database as db

RANKS = [
    ("🟦 Diamant 💎", "diamant"),
    ("🟪 Mythique 👑", "mythique"),
    ("🟥 Légendaire 👿", "legendaire"),
    ("🟧 Master ⭐", "master"),
    ("🟩 Pro 🏆", "pro"),
]
ANNEES = [str(y) for y in range(2022, 2027)]

# Sessions en mémoire pour le flux multi-étapes
sessions: dict[int, dict] = {}


class InscriptionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Commande principale ────────────────────────────────
    @app_commands.command(name="inscription",
                          description="Inscrire une team à la LigaLabs")
    async def inscription(self, interaction: discord.Interaction):
        sessions[interaction.user.id] = {}
        await interaction.response.send_message(
            "📋 **Inscription d'une team** — Étape 1/7\nQuel est le **nom de la team** ?",
            view=NomTeamView(self.bot, interaction.user, interaction.channel),
            ephemeral=True)

    # ── Commande interne appelée par ticket.py ─────────────
    async def start_inscription(self, channel: discord.TextChannel,
                                user: discord.Member):
        sessions[user.id] = {}
        await channel.send(
            f"{user.mention} 📋 **Inscription — Étape 1/7**\nQuel est le **nom de la team** ?",
            view=NomTeamView(self.bot, user, channel, ticket_mode=True))


# ─── STEP 1 — Nom de la team (Modal) ──────────────────────

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
        select = discord.ui.Select(
            placeholder="Année de création...",
            options=[discord.SelectOption(label=a, value=a) for a in ANNEES])
        select.callback = self.on_annee
        self.add_item(select)

    async def on_annee(self, interaction: discord.Interaction):
        sessions[self.user.id]["annee"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content=f"✅ Année **{interaction.data['values'][0]}** — Étape 3/7\nNombre de rosters ?",
            view=RostersView(self.bot, self.user, self.channel, self.ticket_mode))


# ─── STEP 3 — Nombre de rosters ───────────────────────────

class RostersView(discord.ui.View):
    def __init__(self, bot, user, channel, ticket_mode=False):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.ticket_mode = ticket_mode
        select = discord.ui.Select(
            placeholder="Nombre de rosters (max 5)...",
            options=[discord.SelectOption(label=str(i), value=str(i)) for i in range(1, 6)])
        select.callback = self.on_rosters
        self.add_item(select)

    async def on_rosters(self, interaction: discord.Interaction):
        n = int(interaction.data["values"][0])
        sessions[self.user.id]["nb_rosters"] = n
        sessions[self.user.id]["rosters"] = []
        sessions[self.user.id]["current_roster"] = 1
        sessions[self.user.id]["current_player"] = 1
        sessions[self.user.id]["current_players"] = []
        await interaction.response.edit_message(
            content=("✅ **" + str(n) + " roster(s)** — Étape 4/7\n"
                     "**Roster 1** — Ping le joueur 1 en répondant dans ce salon\n"
                     "(ou tape `fin` pour terminer ce roster)"),
            view=None)
        await self._wait_players(interaction.channel if not self.ticket_mode else self.channel)

    async def _wait_players(self, channel):
        user = self.user
        sess = sessions[user.id]

        while sess["current_roster"] <= sess["nb_rosters"]:
            r_num = sess["current_roster"]
            p_num = sess["current_player"]

            def check(m):
                return m.author.id == user.id and m.channel.id == channel.id

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=180)
            except asyncio.TimeoutError:
                await channel.send("⏱️ Temps écoulé. Recommence avec `/inscription`.")
                return

            if msg.content.lower() == "fin" or not msg.mentions:
                # Fin de ce roster
                sess["rosters"].append(list(sess["current_players"]))
                sess["current_players"] = []
                sess["current_roster"] += 1
                sess["current_player"] = 1
                if sess["current_roster"] <= sess["nb_rosters"]:
                    await channel.send(f"✅ Roster {r_num} enregistré ! "
                                       f"**Roster {sess['current_roster']}** — Ping le joueur 1 :")
            else:
                player = msg.mentions[0]
                sess["current_players"].append(
                    {"id": str(player.id), "name": player.display_name})
                sess["current_player"] += 1
                await channel.send(f"✅ {player.display_name} ajouté — "
                                   f"Ping le joueur {sess['current_player']} "
                                   f"(ou tape `fin`) :")

        # Tous les rosters collectés → étape rank
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
        select = discord.ui.Select(
            placeholder="Niveau ranked...",
            options=[discord.SelectOption(label=label, value=val) for label, val in RANKS])
        select.callback = self.on_rank
        self.add_item(select)

    async def on_rank(self, interaction: discord.Interaction):
        sessions[self.user.id]["rank"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content="✅ Niveau enregistré ! — **Étape 6/7** Ping l'**owner** de la team :",
            view=None)
        await self._wait_owner(interaction.channel if not self.ticket_mode else self.channel)

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
            "id": str(msg.mentions[0].id),
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
        await self._wait_logo(interaction.channel if not self.ticket_mode else self.channel)

    @discord.ui.button(label="❌ Non", style=discord.ButtonStyle.secondary)
    async def non(self, interaction: discord.Interaction, button: discord.ui.Button):
        sessions[self.user.id]["logo_url"] = None
        await interaction.response.edit_message(content="✅ Pas de logo.", view=None)
        await envoyer_recap(self.bot, self.user,
                            interaction.channel if not self.ticket_mode else self.channel,
                            interaction.guild)

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
    sess = sessions.get(user.id, {})
    guild_id = str(guild.id)
    ch_id = db.cfg(guild_id, "inscription_channel")

    embed = discord.Embed(title="📋 Nouvelle Inscription Team", color=0x5865F2)
    embed.add_field(name="Team", value=sess.get("nom", "?"), inline=True)
    embed.add_field(name="Année", value=sess.get("annee", "?"), inline=True)
    embed.add_field(name="Owner", value=sess.get("owner", {}).get("name", "?"), inline=True)
    embed.add_field(name="Rank moyen", value=sess.get("rank", "?"), inline=True)
    embed.add_field(name="Nb rosters", value=str(sess.get("nb_rosters", 0)), inline=True)

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
