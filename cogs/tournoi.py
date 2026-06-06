import discord
from discord.ext import commands
from discord import app_commands
import database as db

JOURS = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
MOIS  = ["Janvier","Février","Mars","Avril","Mai","Juin",
         "Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
HEURES_MATIN = [f"{h:02d}:00" for h in range(10, 20)]
HEURES_SOIR  = [f"{h:02d}:00" for h in range(20, 24)] + ["00:00","01:00","02:00","03:00"]

# Sessions en mémoire
sessions: dict[int, dict] = {}


# ─── ÉTAPE 1 : Modal org + lien ───────────────────────────

class TournoiModal(discord.ui.Modal, title="🏆 Annoncer un tournoi"):
    orga = discord.ui.TextInput(
        label="Nom de l'organisation",
        placeholder="Ex: LigaLabs, Supercell, ESL...",
        max_length=80)
    lien = discord.ui.TextInput(
        label="Lien du tournoi / serveur",
        placeholder="https://...",
        max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        sessions[interaction.user.id] = {
            "orga": self.orga.value.strip(),
            "lien": self.lien.value.strip(),
        }
        await interaction.response.send_message(
            f"✅ **{self.orga.value.strip()}** — Étape 2/4 : **Choisis le jour**",
            view=JourView(interaction.user),
            ephemeral=True)


# ─── ÉTAPE 2 : Jour ───────────────────────────────────────

class JourView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=120)
        self.user = user
        sel = discord.ui.Select(
            placeholder="Jour du tournoi...",
            options=[discord.SelectOption(label=j, value=j) for j in JOURS])
        sel.callback = self.on_jour
        self.add_item(sel)

    async def on_jour(self, interaction: discord.Interaction):
        sessions[self.user.id]["jour"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content=f"✅ **{interaction.data['values'][0]}** — Étape 3/4 : **Mois ?**",
            view=MoisView(self.user))


# ─── ÉTAPE 3 : Mois ───────────────────────────────────────

class MoisView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=120)
        self.user = user
        sel = discord.ui.Select(
            placeholder="Mois du tournoi...",
            options=[discord.SelectOption(label=m, value=m) for m in MOIS])
        sel.callback = self.on_mois
        self.add_item(sel)

    async def on_mois(self, interaction: discord.Interaction):
        sessions[self.user.id]["mois"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content=f"✅ **{interaction.data['values'][0]}** — Étape 4/4 : **Heure ?**",
            view=HeureView(self.user))


# ─── ÉTAPE 4 : Heure ──────────────────────────────────────

class HeureView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=120)
        self.user = user
        s1 = discord.ui.Select(
            placeholder="Matin / Après-midi (10h–19h)",
            options=[discord.SelectOption(label=h, value=h) for h in HEURES_MATIN])
        s2 = discord.ui.Select(
            placeholder="Soir / Nuit (20h–3h)",
            options=[discord.SelectOption(label=h, value=h) for h in HEURES_SOIR])
        s1.callback = s2.callback = self.on_heure
        self.add_item(s1)
        self.add_item(s2)

    async def on_heure(self, interaction: discord.Interaction):
        sessions[self.user.id]["heure"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content="⏳ Publication du tournoi...", view=None)
        await _poster_tournoi(interaction, self.user)


# ─── PUBLICATION ──────────────────────────────────────────

async def _poster_tournoi(interaction: discord.Interaction, user: discord.Member):
    sess    = sessions.get(user.id, {})
    guild   = interaction.guild
    gid     = str(guild.id)
    ch_id   = db.cfg(gid, "tournoi_channel")

    embed = discord.Embed(title="🏆 Annonce de Tournoi", color=0xF0B232)
    embed.add_field(name="🏢 Organisateur", value=sess.get("orga", "?"), inline=False)
    embed.add_field(
        name="📅 Date",
        value=f"**{sess.get('jour','?')} {sess.get('mois','?')}** à **{sess.get('heure','?')}**",
        inline=True)
    embed.add_field(
        name="🔗 Lien",
        value=f"[Rejoindre le tournoi]({sess.get('lien','#')})",
        inline=True)
    embed.set_footer(text=f"Annoncé par {user.display_name}")

    # Envoi dans le salon d'annonces configuré
    if ch_id:
        target = guild.get_channel(int(ch_id))
        if target:
            await target.send(embed=embed)
            await interaction.edit_original_response(
                content=f"✅ **Tournoi annoncé dans {target.mention} !**")
            sessions.pop(user.id, None)
            return

    # Fallback si salon non configuré
    await interaction.edit_original_response(
        content="⚠️ Aucun salon d'annonces configuré (`/set-tournoi-channel`).\n"
                "Voici quand même le résultat :",
        embed=embed)
    sessions.pop(user.id, None)


# ─── PANEL PERMANENT ──────────────────────────────────────

class PanelTournoiView(discord.ui.View):
    """Bouton permanent posté par /setup-tournoi."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🏆 Annoncer un tournoi",
        style=discord.ButtonStyle.primary,
        custom_id="lancer_tournoi_labs")
    async def lancer(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(TournoiModal())


# ─── COG ──────────────────────────────────────────────────

class TournoiCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(PanelTournoiView())

    @app_commands.command(
        name="setup-tournoi",
        description="Affiche le panel d'annonce de tournois dans ce salon")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def setup_tournoi(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏆 Annoncer un Tournoi",
            description=(
                "Clique sur le bouton pour annoncer un tournoi.\n\n"
                "Tu renseigneras :\n"
                "• L'organisation qui organise\n"
                "• Le lien du tournoi\n"
                "• La date et l'heure"),
            color=0xF0B232)
        embed.set_footer(text="LigaLabs • Tournois")
        await interaction.channel.send(embed=embed, view=PanelTournoiView())
        await interaction.response.send_message("✅ Panel tournoi créé.", ephemeral=True)

    @app_commands.command(
        name="set-tournoi-channel",
        description="Salon où sont publiées les annonces de tournois")
    @app_commands.describe(channel="Salon d'annonces")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_tournoi_ch(self, interaction: discord.Interaction,
                             channel: discord.TextChannel):
        db.set_cfg(interaction.guild_id, "tournoi_channel", channel.id)
        await interaction.response.send_message(
            f"✅ Annonces tournois → {channel.mention}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(TournoiCog(bot))
