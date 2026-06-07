import discord
from discord.ext import commands
from discord import app_commands
import database as db
import io, json

RANKS = [
    ("🟦 Diamant 💎",    "diamant"),
    ("🟪 Mythique 👑",   "mythique"),
    ("🟥 Légendaire 👿", "legendaire"),
    ("🟧 Master ⭐",     "master"),
    ("🟩 Pro 🏆",        "pro"),
]
ANNEES = [str(y) for y in range(2022, 2027)]

# Sessions en mémoire { user_id: {nom, annee, nb_rosters, rosters, rank, owner, logo_url, recap_ch_id} }
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
            "📋 **Inscription — Étape 1/7** : Quel est le nom de ta team ?",
            view=NomTeamView(),
            ephemeral=True)


# ─── COG ──────────────────────────────────────────────────

class InscriptionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(PanelInscriptionView())

    @app_commands.command(name="setup-inscription",
                          description="Affiche le panel d'inscription dans ce salon")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def setup_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📋 Inscription LigaLabs",
            description=(
                "Clique sur le bouton pour inscrire ta team.\n\n"
                "Le formulaire posera 7 questions :\n"
                "• Nom de la team\n"
                "• Année de création\n"
                "• Rosters & joueurs (saisis librement)\n"
                "• Niveau ranked moyen\n"
                "• Owner de la team\n"
                "• Logo (URL, optionnel)"),
            color=0x5865F2)
        embed.set_footer(text="LigaLabs • Inscriptions")
        await interaction.channel.send(embed=embed, view=PanelInscriptionView())
        await interaction.response.send_message("✅ Panel inscription créé.", ephemeral=True)

    @app_commands.command(name="set-inscription-channel",
                          description="Salon où arrivent les fiches d'inscription des teams")
    @app_commands.describe(channel="Salon de destination")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_insc_ch(self, interaction: discord.Interaction,
                          channel: discord.TextChannel):
        db.set_cfg(interaction.guild_id, "inscription_channel", channel.id)
        await interaction.response.send_message(
            f"✅ Inscriptions → {channel.mention}", ephemeral=True)

    @app_commands.command(name="inscription",
                          description="Inscrire une team (commande directe)")
    async def inscription(self, interaction: discord.Interaction):
        sessions[interaction.user.id] = {}
        await interaction.response.send_message(
            "📋 **Inscription — Étape 1/7** : Quel est le nom de ta team ?",
            view=NomTeamView(),
            ephemeral=True)

    async def start_inscription(self, channel: discord.TextChannel,
                                user: discord.Member):
        """Appelé depuis ticket.py — poste un bouton dans le ticket."""
        sessions[user.id] = {"recap_ch_id": channel.id}
        await channel.send(
            f"{user.mention} 📋 **Inscription LigaLabs**\n"
            "Clique sur le bouton ci-dessous pour remplir le formulaire :",
            view=NomTeamView(expected_user_id=user.id))


# ═══════════════════════════════════════════════════════════
#  ÉTAPE 1 — NOM DE LA TEAM
# ═══════════════════════════════════════════════════════════

class NomTeamModal(discord.ui.Modal, title="Nom de la team"):
    nom = discord.ui.TextInput(
        label="Nom de la team",
        placeholder="Ex: Wolves Esport",
        max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        sessions.setdefault(interaction.user.id, {})
        sessions[interaction.user.id]["nom"] = self.nom.value
        # Après un modal, on NE PEUT PAS faire edit_message → send_message ephemeral
        await interaction.response.send_message(
            f"✅ **{self.nom.value}** — Étape 2/7 : Année de création ?",
            view=AnneeView(),
            ephemeral=True)


class NomTeamView(discord.ui.View):
    def __init__(self, expected_user_id: int = None):
        super().__init__(timeout=300)
        self.expected_user_id = expected_user_id

    @discord.ui.button(label="✏️ Saisir le nom", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if self.expected_user_id and interaction.user.id != self.expected_user_id:
            return await interaction.response.send_message(
                "❌ Ce bouton ne t'est pas destiné.", ephemeral=True)
        sessions.setdefault(interaction.user.id, {})
        await interaction.response.send_modal(NomTeamModal())


# ═══════════════════════════════════════════════════════════
#  ÉTAPE 2 — ANNÉE
# ═══════════════════════════════════════════════════════════

class AnneeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        sel = discord.ui.Select(
            placeholder="Année de création...",
            options=[discord.SelectOption(label=a, value=a) for a in ANNEES])
        sel.callback = self.on_annee
        self.add_item(sel)

    async def on_annee(self, interaction: discord.Interaction):
        sessions[interaction.user.id]["annee"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content=f"✅ **{interaction.data['values'][0]}** — Étape 3/7 : Nombre de rosters ?",
            view=RostersView())


# ═══════════════════════════════════════════════════════════
#  ÉTAPE 3 — NOMBRE DE ROSTERS
# ═══════════════════════════════════════════════════════════

class RostersView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        sel = discord.ui.Select(
            placeholder="Nombre de rosters (max 5)...",
            options=[discord.SelectOption(label=str(i), value=str(i)) for i in range(1, 6)])
        sel.callback = self.on_rosters
        self.add_item(sel)

    async def on_rosters(self, interaction: discord.Interaction):
        n = int(interaction.data["values"][0])
        sessions[interaction.user.id]["nb_rosters"] = n
        sessions[interaction.user.id]["rosters"] = []
        await interaction.response.edit_message(
            content=f"✅ **{n} roster(s)** — Étape 4/7 : Saisis les joueurs du Roster 1",
            view=RosterInputView(roster_num=1, total=n))


# ═══════════════════════════════════════════════════════════
#  ÉTAPE 4 — JOUEURS PAR ROSTER (modal, pas de wait_for)
# ═══════════════════════════════════════════════════════════

class RosterInputView(discord.ui.View):
    def __init__(self, roster_num: int, total: int):
        super().__init__(timeout=300)
        self.roster_num = roster_num
        self.total      = total

    @discord.ui.button(label="✏️ Saisir les joueurs", style=discord.ButtonStyle.primary)
    async def saisir(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(
            RosterModal(roster_num=self.roster_num, total=self.total))


class RosterModal(discord.ui.Modal):
    def __init__(self, roster_num: int, total: int):
        super().__init__(title=f"Joueurs du Roster {roster_num}")
        self.roster_num = roster_num
        self.total      = total
        self.joueurs    = discord.ui.TextInput(
            label=f"Joueurs (séparés par des virgules)",
            placeholder="Ex: Xeno, León, Nohan",
            style=discord.TextStyle.paragraph,
            max_length=500)
        self.add_item(self.joueurs)

    async def on_submit(self, interaction: discord.Interaction):
        joueurs = [j.strip() for j in self.joueurs.value.split(",") if j.strip()]
        sessions[interaction.user.id]["rosters"].append({
            "num":     self.roster_num,
            "joueurs": joueurs,
        })
        next_num = self.roster_num + 1
        if next_num <= self.total:
            # Prochain roster — nouvelle message ephemeral car après un modal
            await interaction.response.send_message(
                f"✅ Roster {self.roster_num} enregistré ! — **Roster {next_num}** :",
                view=RosterInputView(roster_num=next_num, total=self.total),
                ephemeral=True)
        else:
            # Tous les rosters saisis → rank
            await interaction.response.send_message(
                "✅ Rosters enregistrés ! — **Étape 5/7** : Niveau ranked moyen ?",
                view=RankView(),
                ephemeral=True)


# ═══════════════════════════════════════════════════════════
#  ÉTAPE 5 — RANK
# ═══════════════════════════════════════════════════════════

class RankView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        sel = discord.ui.Select(
            placeholder="Niveau ranked moyen...",
            options=[discord.SelectOption(label=label, value=val) for label, val in RANKS])
        sel.callback = self.on_rank
        self.add_item(sel)

    async def on_rank(self, interaction: discord.Interaction):
        sessions[interaction.user.id]["rank"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content="✅ Niveau enregistré ! — **Étape 6/7** : Qui est l'owner de la team ?",
            view=OwnerView())


# ═══════════════════════════════════════════════════════════
#  ÉTAPE 6 — OWNER
# ═══════════════════════════════════════════════════════════

class OwnerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="✏️ Saisir l'owner", style=discord.ButtonStyle.primary)
    async def saisir(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(OwnerModal())


class OwnerModal(discord.ui.Modal, title="Owner de la team"):
    owner = discord.ui.TextInput(
        label="Pseudo de l'owner",
        placeholder="Ex: TyLuffy",
        max_length=60)

    async def on_submit(self, interaction: discord.Interaction):
        sessions[interaction.user.id]["owner"] = self.owner.value
        await interaction.response.send_message(
            "✅ Owner enregistré ! — **Étape 7/7** : La team a-t-elle un logo ?",
            view=LogoView(),
            ephemeral=True)


# ═══════════════════════════════════════════════════════════
#  ÉTAPE 7 — LOGO
# ═══════════════════════════════════════════════════════════

class LogoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="✅ Oui — entrer l'URL", style=discord.ButtonStyle.success)
    async def oui(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(LogoModal())

    @discord.ui.button(label="❌ Non", style=discord.ButtonStyle.secondary)
    async def non(self, interaction: discord.Interaction, btn: discord.ui.Button):
        sessions[interaction.user.id]["logo_url"] = None
        await interaction.response.edit_message(content="✅ Pas de logo.", view=None)
        await envoyer_recap(interaction.client, interaction.user,
                            interaction.channel, interaction.guild)


class LogoModal(discord.ui.Modal, title="Logo de la team"):
    url = discord.ui.TextInput(
        label="URL du logo (Imgur, Discord CDN...)",
        placeholder="https://i.imgur.com/xxx.png",
        max_length=400)

    async def on_submit(self, interaction: discord.Interaction):
        sessions[interaction.user.id]["logo_url"] = self.url.value.strip()
        await interaction.response.send_message(
            "✅ Logo enregistré ! Envoi du récapitulatif...", ephemeral=True)
        await envoyer_recap(interaction.client, interaction.user,
                            interaction.channel, interaction.guild)


# ═══════════════════════════════════════════════════════════
#  RÉCAPITULATIF FINAL
# ═══════════════════════════════════════════════════════════

async def envoyer_recap(bot, user: discord.Member,
                        source_channel, guild: discord.Guild):
    sess     = sessions.get(user.id, {})
    guild_id = str(guild.id)
    insc_ch  = db.cfg(guild_id, "inscription_channel")

    embed = discord.Embed(title="📋 Nouvelle Inscription Team", color=0x5865F2)
    embed.add_field(name="Team",       value=sess.get("nom",   "?"), inline=True)
    embed.add_field(name="Année",      value=sess.get("annee", "?"), inline=True)
    embed.add_field(name="Owner",      value=sess.get("owner", "?"), inline=True)
    embed.add_field(name="Rank moyen", value=sess.get("rank",  "?"), inline=True)
    embed.add_field(name="Nb rosters", value=str(len(sess.get("rosters", []))), inline=True)

    for r in sess.get("rosters", []):
        joueurs = ", ".join(r["joueurs"]) if r["joueurs"] else "Aucun"
        embed.add_field(name=f"Roster {r['num']}", value=joueurs, inline=False)

    if sess.get("logo_url"):
        embed.set_thumbnail(url=sess["logo_url"])
    embed.set_footer(text=f"Soumis par {user.display_name}")

    # Envoi dans le salon d'inscriptions configuré
    if insc_ch:
        target = guild.get_channel(int(insc_ch))
        if target:
            try:
                await target.send(embed=embed)
            except Exception:
                pass

    # Envoi dans le salon source (ticket) si différent
    recap_ch_id = sess.get("recap_ch_id")
    if recap_ch_id and str(recap_ch_id) != str(insc_ch):
        recap_ch = guild.get_channel(int(recap_ch_id))
        if recap_ch:
            try:
                await recap_ch.send(f"✅ **Inscription soumise !**", embed=embed)
            except Exception:
                pass

    # Message de confirmation dans le canal courant si accessible
    if source_channel:
        try:
            await source_channel.send(
                f"✅ **Inscription de {sess.get('nom','?')} envoyée !**", embed=embed)
        except Exception:
            pass

    sessions.pop(user.id, None)


async def setup(bot):
    await bot.add_cog(InscriptionCog(bot))
