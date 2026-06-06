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


# ─── PANEL SCRIM ──────────────────────────────────────────

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
            "**Quelle est ta team ?**",
            view=TeamView(interaction.user, roles), ephemeral=True)


class GoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ GO — Accepter le scrim",
                       style=discord.ButtonStyle.success,
                       custom_id="accept_scrim")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = db.get_scrim(interaction.message.id)
        if not data:
            return await interaction.response.send_message("❌ Données introuvables.", ephemeral=True)
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
        req_role  = guild.get_role(int(data["requester_role_id"]))
        button.disabled = True
        button.label = "✅ Match trouvé !"
        await interaction.message.edit(view=self)
        await creer_salon(guild, requester, req_role, accepter, accepter_role,
                          data["jour"], data["heure"])
        await interaction.response.send_message("🔒 Salon privé créé !", ephemeral=True)


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


# ─── RÉSULTATS LIGALABS ───────────────────────────────────

class LigaLabsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📊 Résultat LigaLabs (classement général)",
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
            "**Résultat pour le classement général LABS :**",
            view=ResultSelectView(interaction.channel), ephemeral=True)

    @discord.ui.button(label="⚽ Poule LigaLabs (saison)",
                       style=discord.ButtonStyle.success,
                       custom_id="poule_ligalabs")
    async def poule(self, interaction: discord.Interaction, button: discord.ui.Button):
        ch_data = db.get_scrim_ch(interaction.channel_id)
        if not ch_data:
            return await interaction.response.send_message("❌ Données introuvables.", ephemeral=True)
        user_roles = {str(r.id) for r in interaction.user.roles}
        t1 = ch_data["team1_id"]
        t2 = ch_data["team2_id"]
        if t1 in user_roles:
            user_tid, opp_tid = t1, t2
        elif t2 in user_roles:
            user_tid, opp_tid = t2, t1
        else:
            return await interaction.response.send_message(
                "❌ Tu n'appartiens à aucune des deux équipes de ce scrim.", ephemeral=True)
        await interaction.response.send_modal(
            PouleModal(interaction.channel, user_tid, opp_tid))

    @discord.ui.button(label="🎬 Envoyer une redif",
                       style=discord.ButtonStyle.secondary,
                       custom_id="send_redif")
    async def redif(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RedifModal())


# ─── MODAL POULE LIGALABS ─────────────────────────────────

class PouleModal(discord.ui.Modal, title="⚽ Poule LigaLabs"):
    roster_vous = discord.ui.TextInput(
        label="Votre roster",
        placeholder="Ex: Roster N°1, STM 2, Pro...",
        max_length=40)
    roster_adv = discord.ui.TextInput(
        label="Roster adverse",
        placeholder="Ex: Roster A, Roster EU...",
        max_length=40)
    resultat = discord.ui.TextInput(
        label="Résultat — V (Victoire) ou D (Défaite)",
        placeholder="V ou D",
        max_length=1)

    def __init__(self, channel, user_team_id, opp_team_id):
        super().__init__()
        self.channel      = channel
        self.user_team_id = user_team_id
        self.opp_team_id  = opp_team_id

    async def on_submit(self, interaction: discord.Interaction):
        res = self.resultat.value.upper().strip()
        if res not in ('V', 'D'):
            return await interaction.response.send_message(
                "❌ Résultat invalide — écris **V** (Victoire) ou **D** (Défaite).", ephemeral=True)

        guild_id = str(interaction.guild_id)
        roster1  = self.roster_vous.value.strip()
        roster2  = self.roster_adv.value.strip()

        count = db.count_poule(guild_id, self.user_team_id, roster1, self.opp_team_id, roster2)
        if count >= 2:
            return await interaction.response.send_message(
                f"❌ Ces deux rosters ont déjà joué **2 matchs** en poule cette saison.\n"
                f"Reset possible en fin de saison avec `/reset-saison-ligalabs`.", ephemeral=True)

        winner = self.user_team_id if res == 'V' else self.opp_team_id
        db.add_poule_match(guild_id, self.user_team_id, roster1, self.opp_team_id, roster2, winner)

        guild   = interaction.guild
        t1_role = guild.get_role(int(self.user_team_id))
        t2_role = guild.get_role(int(self.opp_team_id))
        t1_name = t1_role.mention if t1_role else "?"
        t2_name = t2_role.mention if t2_role else "?"

        color = 0x23A55A if res == 'V' else 0xC0392B
        embed = discord.Embed(title="⚽ Match de Poule LigaLabs enregistré", color=color)
        embed.add_field(name="Votre équipe / Roster", value=f"{t1_name} — **{roster1}**", inline=False)
        embed.add_field(name="Adversaire / Roster",   value=f"{t2_name} — **{roster2}**", inline=False)
        embed.add_field(name="Résultat", value="✅ Victoire" if res=='V' else "❌ Défaite", inline=True)
        embed.add_field(name="Match n°", value=f"{count+1}/2", inline=True)
        embed.set_footer(text="Utilise /export-ligalabs pour mettre à jour le site")

        await self.channel.send(embed=embed)
        await interaction.response.send_message(
            f"✅ Match de poule enregistré ! ({count+1}/2 entre ces rosters)", ephemeral=True)


# ─── RÉSULTAT CLASSEMENT GÉNÉRAL ─────────────────────────

class ResultSelectView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=60)
        self.channel = channel
        sel = discord.ui.Select(
            placeholder="Résultat...",
            options=[
                discord.SelectOption(label="✅ Victoire", value="victoire"),
                discord.SelectOption(label="❌ Défaite",  value="defaite"),
            ])
        sel.callback = self.on_result
        self.add_item(sel)

    async def on_result(self, interaction: discord.Interaction):
        result   = interaction.data["values"][0]
        guild_id = str(interaction.guild_id)
        ch_id    = str(self.channel.id)
        db.inc_result(ch_id)
        count = db.get_scrim_ch(ch_id)["result_count"]

        res_ch_id = db.cfg(guild_id, "resultats_channel")
        emoji = "✅" if result == "victoire" else "❌"
        embed = discord.Embed(
            title=f"{emoji} Résultat LigaLabs",
            color=0x23A55A if result == "victoire" else 0xC0392B)
        embed.description = (f"Soumis par {interaction.user.mention}\n"
                             f"Salon : {self.channel.mention}\n"
                             f"Résultat : **{'Victoire' if result=='victoire' else 'Défaite'}**\n"
                             f"Soumission **{count}/2**")
        if res_ch_id:
            ch = interaction.guild.get_channel(int(res_ch_id))
            if ch:
                await ch.send(embed=embed)
        await self.channel.send(embed=embed)
        await interaction.response.edit_message(
            content=f"✅ Résultat soumis ({count}/2).", view=None)


# ─── REDIF ────────────────────────────────────────────────

class RedifModal(discord.ui.Modal, title="Envoyer une redif"):
    lien = discord.ui.TextInput(label="Lien de la rediffusion", placeholder="https://...")

    async def on_submit(self, interaction: discord.Interaction):
        guild_id    = str(interaction.guild_id)
        redif_ch_id = db.cfg(guild_id, "redif_channel")
        if redif_ch_id:
            ch = interaction.guild.get_channel(int(redif_ch_id))
            if ch:
                embed = discord.Embed(title="🎬 Rediffusion", color=0x9B59B6)
                embed.description = f"[Regarder la redif]({self.lien.value})"
                embed.add_field(name="Salon source", value=interaction.channel.mention)
                await ch.send(embed=embed)
        await interaction.response.send_message("✅ Redif envoyée !", ephemeral=True)


# ─── SÉLECTION TEAM / JOUR / HEURE ────────────────────────

class TeamView(discord.ui.View):
    def __init__(self, user, roles):
        super().__init__(timeout=120)
        self.user = user
        sel = discord.ui.Select(
            placeholder="Choisis ta team...",
            options=[discord.SelectOption(label=r.name, value=str(r.id)) for r in roles[:25]])
        sel.callback = self.on_team
        self.add_item(sel)

    async def on_team(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(interaction.data["values"][0]))
        await interaction.response.edit_message(
            content=f"✅ **{role.name}** — Choisis le jour :",
            view=JourView(self.user, role))


class JourView(discord.ui.View):
    def __init__(self, user, team_role):
        super().__init__(timeout=120)
        self.user      = user
        self.team_role = team_role
        sel = discord.ui.Select(
            placeholder="Choisis un jour...",
            options=[discord.SelectOption(label=j, value=j) for j in JOURS])
        sel.callback = self.on_jour
        self.add_item(sel)

    async def on_jour(self, interaction: discord.Interaction):
        jour = interaction.data["values"][0]
        await interaction.response.edit_message(
            content=f"✅ **{self.team_role.name}** • **{jour}** — Heure :",
            view=HeureView(self.user, self.team_role, jour))


class HeureView(discord.ui.View):
    def __init__(self, user, team_role, jour):
        super().__init__(timeout=120)
        self.user      = user
        self.team_role = team_role
        self.jour      = jour
        s1 = discord.ui.Select(placeholder="Matin / Après-midi (10h–19h)",
             options=[discord.SelectOption(label=h, value=h) for h in HEURES[:10]])
        s2 = discord.ui.Select(placeholder="Soir / Nuit (20h–3h)",
             options=[discord.SelectOption(label=h, value=h) for h in HEURES[10:]])
        s1.callback = s2.callback = self.on_heure
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
    ch_id    = db.cfg(guild_id, "announce_channel")
    if not ch_id:
        return await interaction.followup.send(
            "⚠️ Pas de salon configuré. Utilise `/set-announce-channel`.", ephemeral=True)
    channel = interaction.guild.get_channel(int(ch_id))
    if not channel:
        return await interaction.followup.send("⚠️ Salon introuvable.", ephemeral=True)

    embed = discord.Embed(title="⚔️ Recherche de Scrim", color=0xF0B232)
    embed.description = (f"{requester.mention} **({team_role.mention})** souhaite scrim\n"
                         f"📅 **{jour}** à **{heure}**")
    embed.add_field(name="Team", value=team_role.mention, inline=True)
    embed.add_field(name="Date", value=f"{jour} à {heure}", inline=True)
    embed.set_footer(text="Clique GO pour accepter • Salon privé créé automatiquement")
    view = GoView()
    msg  = await channel.send(embed=embed, view=view)
    db.store_scrim(msg.id, guild_id, requester.id, team_role.id, jour, heure)


async def creer_salon(guild, requester, req_role, accepter, acc_role, jour, heure):
    cat = discord.utils.get(guild.categories, name="Scrims Privés")
    if not cat:
        cat = await guild.create_category("Scrims Privés")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        requester:  discord.PermissionOverwrite(read_messages=True, send_messages=True),
        accepter:   discord.PermissionOverwrite(read_messages=True, send_messages=True),
        req_role:   discord.PermissionOverwrite(read_messages=True, send_messages=True),
        acc_role:   discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me:   discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }
    nom = (f"scrim-{req_role.name.lstrip('-')[:10].lower().replace(' ','-')}"
           f"-vs-{acc_role.name.lstrip('-')[:10].lower().replace(' ','-')}")
    salon = await cat.create_text_channel(nom, overwrites=overwrites)
    db.create_scrim_ch(salon.id, str(guild.id), str(req_role.id), str(acc_role.id))

    embed = discord.Embed(title="🔒 Salon Privé de Scrim", color=0x23A55A)
    embed.description = (f"{req_role.mention} **vs** {acc_role.mention}\n"
                         f"{requester.mention} **vs** {accepter.mention}")
    embed.add_field(name="Date", value=f"{jour} à {heure}", inline=True)
    embed.add_field(
        name="📊 Résultat LigaLabs (classement général)",
        value="Enregistre ta victoire/défaite pour le classement général LABS. **Max 2 fois** par scrim.",
        inline=False)
    embed.add_field(
        name="⚽ Poule LigaLabs (saison)",
        value="Enregistre ce match dans la **poule de la saison**. **Max 2 fois** par paire de rosters.",
        inline=False)
    embed.set_footer(text="Les deux systèmes sont indépendants — LigaLabs Bot")

    await salon.send(
        content=(f"📣 {req_role.mention} {acc_role.mention} — "
                 f"{requester.mention} **vs** {accepter.mention} — Scrim **{jour} à {heure}** 🎮"),
        embed=embed)
    await salon.send("**Actions :**", view=LigaLabsView())
    await salon.send("** **", view=FermerSalonView())


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
            description="Lance une recherche d'adversaire.\nTu choisiras ta **team**, le **jour** et l'**heure**.")
        embed.set_footer(text="Actif 10h–4h • LigaLabs")
        await interaction.channel.send(embed=embed, view=LaunchView())
        await interaction.response.send_message("✅ Panel créé.", ephemeral=True)

    @app_commands.command(name="set-announce-channel", description="Salon pour les annonces scrims")
    @app_commands.describe(channel="Salon d'annonces")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_announce(self, interaction: discord.Interaction, channel: discord.TextChannel):
        db.set_cfg(interaction.guild_id, "announce_channel", channel.id)
        await interaction.response.send_message(f"✅ Annonces scrims → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set-redif-channel", description="Salon privé pour les rediffusions")
    @app_commands.describe(channel="Salon redifs")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_redif(self, interaction: discord.Interaction, channel: discord.TextChannel):
        db.set_cfg(interaction.guild_id, "redif_channel", channel.id)
        await interaction.response.send_message(f"✅ Redifs → {channel.mention}", ephemeral=True)

    @app_commands.command(name="set-resultats-channel", description="Salon pour les résultats LigaLabs")
    @app_commands.describe(channel="Salon résultats")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_resultats(self, interaction: discord.Interaction, channel: discord.TextChannel):
        db.set_cfg(interaction.guild_id, "resultats_channel", channel.id)
        await interaction.response.send_message(f"✅ Résultats → {channel.mention}", ephemeral=True)

    @app_commands.command(name="reset-ligalabs",
                          description="[ADMIN] Remet à 0 les soumissions LigaLabs du salon")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_ligalabs(self, interaction: discord.Interaction):
        db.reset_result(interaction.channel_id)
        await interaction.response.send_message("✅ Compteur remis à 0.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ScrimCog(bot))
