import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import database as db

JOURS = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
MOIS  = ["Janvier","Février","Mars","Avril","Mai","Juin",
          "Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
HEURES = [f"{h:02d}:00" for h in range(10, 24)] + ["00:00","01:00","02:00","03:00"]

tournoi_sessions: dict[int, dict] = {}


class TournoiCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tournoi",
                          description="Annoncer un tournoi")
    async def tournoi(self, interaction: discord.Interaction):
        tournoi_sessions[interaction.user.id] = {}
        await interaction.response.send_message(
            "🏆 **Annonce de Tournoi** — Étape 1/4\n"
            "**Écris le nom de l'organisation** qui organise le tournoi :",
            ephemeral=True)
        await self._wait_orga(interaction.user, interaction.channel)

    async def _wait_orga(self, user: discord.Member, channel: discord.TextChannel):
        def check(m):
            return m.author.id == user.id and m.channel.id == channel.id

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            await channel.send(f"{user.mention} ⏱️ Temps écoulé.")
            return

        tournoi_sessions[user.id]["orga"] = msg.content.strip()
        await channel.send(
            f"✅ **{msg.content.strip()}** — Étape 2/4\nChoisis le **jour** :",
            view=JourView(self.bot, user, channel))

    @app_commands.command(name="set-tournoi-channel",
                          description="Salon pour les annonces de tournois")
    @app_commands.describe(channel="Salon d'annonces tournois")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_tournoi_ch(self, interaction: discord.Interaction,
                             channel: discord.TextChannel):
        db.set_cfg(interaction.guild_id, "tournoi_channel", channel.id)
        await interaction.response.send_message(
            f"✅ Annonces tournois → {channel.mention}", ephemeral=True)


class JourView(discord.ui.View):
    def __init__(self, bot, user, channel):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        select = discord.ui.Select(
            placeholder="Jour du tournoi...",
            options=[discord.SelectOption(label=j, value=j) for j in JOURS])
        select.callback = self.on_jour
        self.add_item(select)

    async def on_jour(self, interaction: discord.Interaction):
        tournoi_sessions[self.user.id]["jour"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content=f"✅ **{interaction.data['values'][0]}** — Mois ?",
            view=MoisView(self.bot, self.user, self.channel))


class MoisView(discord.ui.View):
    def __init__(self, bot, user, channel):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        select = discord.ui.Select(
            placeholder="Mois...",
            options=[discord.SelectOption(label=m, value=m) for m in MOIS])
        select.callback = self.on_mois
        self.add_item(select)

    async def on_mois(self, interaction: discord.Interaction):
        tournoi_sessions[self.user.id]["mois"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content=f"✅ **{interaction.data['values'][0]}** — Heure ?",
            view=HeureView(self.bot, self.user, self.channel))


class HeureView(discord.ui.View):
    def __init__(self, bot, user, channel):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        s1 = discord.ui.Select(placeholder="Matin / Après-midi (10h–19h)",
                               options=[discord.SelectOption(label=h, value=h) for h in HEURES[:10]])
        s1.callback = self.on_heure
        s2 = discord.ui.Select(placeholder="Soir / Nuit (20h–3h)",
                               options=[discord.SelectOption(label=h, value=h) for h in HEURES[10:]])
        s2.callback = self.on_heure
        self.add_item(s1)
        self.add_item(s2)

    async def on_heure(self, interaction: discord.Interaction):
        tournoi_sessions[self.user.id]["heure"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content="✅ Heure notée ! — **Étape 4/4** Envoie le **lien du tournoi** en message :",
            view=None)
        await self._wait_lien(interaction.channel)

    async def _wait_lien(self, channel):
        user = self.user

        def check(m):
            return m.author.id == user.id and m.channel.id == channel.id

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            await channel.send(f"{user.mention} ⏱️ Temps écoulé.")
            return

        tournoi_sessions[user.id]["lien"] = msg.content.strip()
        await poster_tournoi(user, channel.guild, channel)


async def poster_tournoi(user, guild, source_channel):
    sess = tournoi_sessions.get(user.id, {})
    guild_id = str(guild.id)
    ch_id = db.cfg(guild_id, "tournoi_channel")

    embed = discord.Embed(title="🏆 Annonce de Tournoi", color=0xF0B232)
    embed.add_field(name="Organisateur", value=sess.get("orga", "?"), inline=False)
    embed.add_field(name="Date",
                    value=f"{sess.get('jour','?')} {sess.get('mois','?')} à {sess.get('heure','?')}",
                    inline=True)
    embed.add_field(name="Lien",
                    value=f"[Rejoindre le tournoi]({sess.get('lien','#')})", inline=True)
    embed.set_footer(text=f"Annoncé par {user.display_name}")

    if ch_id:
        target = guild.get_channel(int(ch_id))
        if target:
            await target.send(embed=embed)
    await source_channel.send("✅ Tournoi annoncé !", embed=embed)
    tournoi_sessions.pop(user.id, None)


async def setup(bot):
    await bot.add_cog(TournoiCog(bot))
