import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import pytz
from datetime import datetime
import database as db

PARIS_TZ = pytz.timezone("Europe/Paris")
JOURS = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
HEURES = ["10:00","11:00","12:00","13:00","14:00","15:00","16:00",
          "17:00","18:00","19:00","20:00","21:00","22:00","23:00",
          "00:00","01:00","02:00","03:00"]

def is_open():
    h = datetime.now(PARIS_TZ).hour
    return (10 <= h < 24) or (0 <= h < 4)

def team_roles(guild):
    return [r for r in guild.roles if r.name.startswith("-")]

def member_team(member, guild):
    ids = {r.id for r in team_roles(guild)}
    for r in member.roles:
        if r.id in ids:
            return r
    return None


# ─── VUES PERSISTANTES ────────────────────────────────────

class LaunchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🚀 Lancer la recherche de scrims",
                       style=discord.ButtonStyle.primary,
                       custom_id="launch_scrim")
    async def launch(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_open():
            return await interaction.response.send_message(
                "😴 Bot en veille (actif 10h–4h).", ephemeral=True)
        roles = team_roles(interaction.guild)
        if not roles:
            return await interaction.response.send_message(
                "⚠️ Aucun rôle `-Team` trouvé.", ephemeral=True)
        await interaction.response.send_message(
            "go — **Quelle est ta team ?**",
            view=TeamView(interaction.user, roles), ephemeral=True)


class GoView(discord.ui.View):
    """Persistant — données récupérées via message_id en DB."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ GO — Accepter le scrim",
                       style=discord.ButtonStyle.success,
                       custom_id="accept_scrim")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = db.get_scrim(interaction.message.id)
        if not data:
            return await interaction.response.send_message(
                "❌ Données introuvables.", ephemeral=True)
        if interaction.user.id == int(data["requester_id"]):
            return await interaction.response.send_message(
                "❌ Tu ne peux pas accepter ton propre scrim.", ephemeral=True)
        guild = interaction.guild
        accepter = interaction.user
        accepter_role = member_team(accepter, guild)
        if not accepter_role:
            return await interaction.response.send_message(
                "❌ Tu n'as pas de rôle `-Team`.", ephemeral=True)
        requester = guild.get_member(int(data["requester_id"]))
        req_role = guild.get_role(int(data["requester_role_id"]))
        button.disabled = True
        button.label = "✅ Match trouvé !"
        await interaction.message.edit(view=self)
        await creer_salon(guild, requester, req_role, accepter, accepter_role,
                          data["jour"], data["heure"])
        await interaction.response.send_message(
            "🔒 Salon privé créé !", ephemeral=True)


class FermerSalonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🗑️ Fermer ce salon",
                       style=discord.ButtonStyle.danger,
                       custom_id="close_private")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Fermeture dans 5s...")
        await asyncio.sleep(5)
        await interaction.channel.delete(reason="Scrim terminé")


class LigaLabsView(discord.ui.View):
    """Bouton de soumission de résultat LigaLabs — max 2 par salon."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📊 Soumettre résultat LigaLabs",
                       style=discord.ButtonStyle.primary,
                       custom_id="ligalabs_result")
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        ch_data = db.get_scrim_ch(interaction.channel_id)
        if not ch_data:
            return await interaction.response.send_message("❌ Salon introuvable en DB.", ephemeral=True)
        if ch_data["result_count"] >= 2:
            return await interaction.response.send_message(
                "❌ Limite de 2 soumissions atteinte. Un admin doit reset.", ephemeral=True)
        await interaction.response.send_message(
            "Quel est le résultat ?", view=ResultSelectView(interaction.channel), ephemeral=True)

    @discord.ui.button(label="🎬 Envoyer une redif",
                       style=discord.ButtonStyle.secondary,
                       custom_id="send_redif")
    async def redif(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RedifModal())


class ResultSelectView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=60)
        self.channel = channel
        select = discord.ui.Select(
            placeholder="Résultat...",
            options=[
                discord.SelectOption(label="✅ Victoire", value="victoire"),
                discord.SelectOption(label="❌ Défaite", value="defaite"),
            ])
        select.callback = self.on_result
        self.add_item(select)

    async def on_result(self, interaction: discord.Interaction):
        result = interaction.data["values"][0]
        guild_id = str(interaction.guild_id)
        channel_id = str(self.channel.id)
        ch_data = db.get_scrim_ch(channel_id)
        db.inc_result(channel_id)

        # Envoyer dans le salon résultats configuré
        res_ch_id = db.cfg(guild_id, "resultats_channel")
        emoji = "✅" if result == "victoire" else "❌"
        embed = discord.Embed(title=f"{emoji} Résultat LigaLabs",
                              color=0x23A55A if result == "victoire" else 0xC0392B)
        embed.description = (f"Soumis par {interaction.user.mention}\n"
                             f"Salon : {self.channel.mention}\n"
                             f"Résultat : **{'Victoire' if result=='victoire' else 'Défaite'}**")

        if res_ch_id:
            ch = interaction.guild.get_channel(int(res_ch_id))
            if ch:
                await ch.send(embed=embed)

        await self.channel.send(embed=embed)
        await interaction.response.edit_message(
            content=f"✅ Résultat soumis ({db.get_scrim_ch(channel_id)['result_count']}/2).",
            view=None)


class RedifModal(discord.ui.Modal, title="Envoyer une redif"):
    lien = discord.ui.TextInput(label="Lien de la rediffusion", placeholder="https://...")

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        redif_ch_id = db.cfg(guild_id, "redif_channel")
        if redif_ch_id:
            ch = interaction.guild.get_channel(int(redif_ch_id))
            if ch:
                embed = discord.Embed(title="🎬 Rediffusion", color=0x9B59B6)
                embed.description = f"[Regarder la redif]({self.lien.value})"
                embed.add_field(name="Salon source", value=interaction.channel.mention)
                await ch.send(embed=embed)
        await interaction.response.send_message("✅ Redif envoyée !", ephemeral=True)


# ─── VUES ÉPHÉMÈRES ───────────────────────────────────────

class TeamView(discord.ui.View):
    def __init__(self, user, roles):
        super().__init__(timeout=120)
        self.user = user
        select = discord.ui.Select(
            placeholder="Choisis ta team...",
            options=[discord.SelectOption(label=r.name, value=str(r.id)) for r in roles[:25]])
        select.callback = self.on_team
        self.add_item(select)

    async def on_team(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(interaction.data["values"][0]))
        await interaction.response.edit_message(
            content=f"✅ Team **{role.name}** — Choisis le jour :",
            view=JourView(self.user, role))


class JourView(discord.ui.View):
    def __init__(self, user, team_role):
        super().__init__(timeout=120)
        self.user = user
        self.team_role = team_role
        select = discord.ui.Select(
            placeholder="Choisis un jour...",
            options=[discord.SelectOption(label=j, value=j) for j in JOURS])
        select.callback = self.on_jour
        self.add_item(select)

    async def on_jour(self, interaction: discord.Interaction):
        jour = interaction.data["values"][0]
        await interaction.response.edit_message(
            content=f"✅ **{self.team_role.name}** • **{jour}** — Heure :",
            view=HeureView(self.user, self.team_role, jour))


class HeureView(discord.ui.View):
    def __init__(self, user, team_role, jour):
        super().__init__(timeout=120)
        self.user = user
        self.team_role = team_role
        self.jour = jour
        s1 = discord.ui.Select(placeholder="Matin / Après-midi (10h–19h)",
                               options=[discord.SelectOption(label=h, value=h) for h in HEURES[:10]])
        s1.callback = self.on_heure
        s2 = discord.ui.Select(placeholder="Soir / Nuit (20h–3h)",
                               options=[discord.SelectOption(label=h, value=h) for h in HEURES[10:]])
        s2.callback = self.on_heure
        self.add_item(s1)
        self.add_item(s2)

    async def on_heure(self, interaction: discord.Interaction):
        heure = interaction.data["values"][0]
        await interaction.response.edit_message(
            content=f"📣 Annonce envoyée — **{self.team_role.name}** • **{self.jour}** à **{heure}**",
            view=None)
        await poster_annonce(interaction, self.user, self.team_role, self.jour, heure)


# ─── LOGIQUE ──────────────────────────────────────────────

async def poster_annonce(interaction, requester, team_role, jour, heure):
    guild_id = str(interaction.guild_id)
    ch_id = db.cfg(guild_id, "announce_channel")
    if not ch_id:
        return await interaction.followup.send(
            "⚠️ Pas de salon d'annonces. Utilise `/set-announce-channel`.", ephemeral=True)
    channel = interaction.guild.get_channel(int(ch_id))
    if not channel:
        return await interaction.followup.send("⚠️ Salon introuvable.", ephemeral=True)

    embed = discord.Embed(title="⚔️ Recherche de Scrim", color=0xF0B232)
    embed.description = (f"{requester.mention} **({team_role.mention})** souhaite scrim\n"
                         f"📅 **{jour}** à **{heure}**")
    embed.add_field(name="Team", value=team_role.mention, inline=True)
    embed.add_field(name="Date", value=f"{jour} à {heure}", inline=True)
    embed.set_footer(text="Clique GO pour accepter • Salon privé créé avec vos 2 rôles")

    view = GoView()
    msg = await channel.send(embed=embed, view=view)
    db.store_scrim(msg.id, guild_id, requester.id, team_role.id, jour, heure)


async def creer_salon(guild, requester, req_role, accepter, acc_role, jour, heure):
    cat = discord.utils.get(guild.categories, name="Scrims Privés")
    if not cat:
        cat = await guild.create_category("Scrims Privés")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        requester: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        accepter: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        req_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        acc_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    nom = (f"scrim-{req_role.name.lstrip('-')[:10].lower().replace(' ','-')}"
           f"-vs-{acc_role.name.lstrip('-')[:10].lower().replace(' ','-')}")
    salon = await cat.create_text_channel(nom, overwrites=overwrites)

    db.create_scrim_ch(salon.id, str(guild.id), str(req_role.id), str(acc_role.id))

    embed = discord.Embed(title="🔒 Salon Privé de Scrim", color=0x23A55A)
    embed.description = (f"{req_role.mention} **vs** {acc_role.mention}\n"
                         f"{requester.mention} **vs** {accepter.mention}")
    embed.add_field(name="Date", value=f"{jour} à {heure}", inline=True)
    embed.set_footer(text="Soumets le résultat LigaLabs (2 max) puis ferme ce salon")

    fermer_view = FermerSalonView()
    ligalabs_view = LigaLabsView()

    await salon.send(
        content=(f"📣 {req_role.mention} {acc_role.mention} — "
                 f"{requester.mention} {accepter.mention}\n"
                 f"Scrim confirmé : **{jour} à {heure}** 🎮"),
        embed=embed)
    await salon.send("**Actions disponibles :**", view=ligalabs_view)
    await salon.send("**Fermeture du salon :**", view=fermer_view)


# ─── COG ──────────────────────────────────────────────────

class ScrimCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(LaunchView())
        bot.add_view(GoView())
        bot.add_view(FermerSalonView())
        bot.add_view(LigaLabsView())

    @app_commands.command(name="setup-scrim",
                          description="Affiche le panel permanent de recherche de scrims")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def setup_scrim(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎯 Recherche de Scrims", color=0x5865F2,
            description=("Lance une recherche d'adversaire.\n"
                         "Tu choisiras ta **team**, le **jour** et l'**heure**."))
        embed.set_footer(text="Actif 10h–4h • LigaLabs Bot")
        await interaction.response.send_message(embed=embed, view=LaunchView())

    @app_commands.command(name="set-announce-channel",
                          description="Salon pour les annonces scrims")
    @app_commands.describe(channel="Salon d'annonces")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_announce(self, interaction: discord.Interaction,
                           channel: discord.TextChannel):
        db.set_cfg(interaction.guild_id, "announce_channel", channel.id)
        await interaction.response.send_message(
            f"✅ Annonces scrims → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set-redif-channel",
                          description="Salon privé pour les rediffusions")
    @app_commands.describe(channel="Salon redifs")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_redif(self, interaction: discord.Interaction,
                        channel: discord.TextChannel):
        db.set_cfg(interaction.guild_id, "redif_channel", channel.id)
        await interaction.response.send_message(
            f"✅ Redifs → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set-resultats-channel",
                          description="Salon pour les résultats LigaLabs")
    @app_commands.describe(channel="Salon résultats")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_resultats(self, interaction: discord.Interaction,
                            channel: discord.TextChannel):
        db.set_cfg(interaction.guild_id, "resultats_channel", channel.id)
        await interaction.response.send_message(
            f"✅ Résultats LigaLabs → {channel.mention}", ephemeral=True)

    @app_commands.command(name="reset-ligalabs",
                          description="[ADMIN] Remet à 0 les soumissions LigaLabs du salon")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_ligalabs(self, interaction: discord.Interaction):
        db.reset_result(interaction.channel_id)
        await interaction.response.send_message(
            "✅ Compteur de résultats remis à 0 pour ce salon.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ScrimCog(bot))
