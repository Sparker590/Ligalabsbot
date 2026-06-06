import discord
from discord.ext import commands
from discord import app_commands
import database as db
import json, os

# ─── SYSTÈME DE POINTS ────────────────────────────────────
# Tier de VOTRE équipe → type d'événement → action → points

POINTS_TABLE = {
    "S": {
        "scrim":    {"win": 1,  "loose": -5},
        "tournoi":  {"win": 2,  "loose": -6,  "champion": 2,  "vice": 1,  "semi": 0},
        "officiel": {"win": 5,  "loose": -10, "champion": 4,  "vice": 3,  "semi": 2,  "quart": 1},
    },
    "A": {
        "scrim":    {"win": 3,  "loose": -5},
        "tournoi":  {"win": 4,  "loose": -6,  "champion": 3,  "vice": 2,  "semi": 1},
        "officiel": {"win": 8,  "loose": -6,  "champion": 5,  "vice": 4,  "semi": 3,  "quart": 2},
    },
    "B": {
        "scrim":    {"win": 3,  "loose": -4},
        "tournoi":  {"win": 4,  "loose": -5,  "champion": 4,  "vice": 3,  "semi": 2},
        "officiel": {"win": 10, "loose": -10, "champion": 10, "vice": 5,  "semi": 3,  "quart": 1},
    },
    "C": {
        "scrim":    {"win": 4,  "loose": -3},
        "tournoi":  {"win": 4,  "loose": -4,  "champion": 5,  "vice": 3,  "semi": 1},
        "officiel": {"win": 10, "loose": -8,  "champion": 15, "vice": 10, "semi": 5,  "quart": 3},
    },
    "D": {
        "scrim":    {"win": 5,  "loose": -3},
        "tournoi":  {"win": 6,  "loose": -4,  "champion": 10, "vice": 5,  "semi": 3},
        "officiel": {"win": 10, "loose": -6,  "champion": 20, "vice": 15, "semi": 10, "quart": 5},
    },
    "E": {
        "scrim":    {"win": 5,  "loose": -1},
        "tournoi":  {"win": 8,  "loose": -3,  "champion": 15, "vice": 10, "semi": 6},
        "officiel": {"win": 10, "loose": -5,  "champion": 25, "vice": 20, "semi": 15, "quart": 10},
    },
}

TIERS       = ["E", "D", "C", "B", "A", "S"]
TIER_EMOJI  = {"S": "🔴", "A": "🟠", "B": "🟡", "C": "🟢", "D": "🔵", "E": "⚪"}
ACTION_LABEL = {
    "win":      "✅ Victoire",
    "loose":    "❌ Défaite",
    "champion": "🥇 Champion",
    "vice":     "🥈 Vice-Champion",
    "semi":     "🏅 Demi-Finale",
    "quart":    "🎖️ Quarts de Finale",
}

# Sessions d'attribution en cours
attr_sessions: dict[int, dict] = {}


# ─── HELPERS ──────────────────────────────────────────────

def team_roles(guild):
    return [r for r in guild.roles if r.name.startswith("-")]

def calc_pts(tier: str, evt: str, action: str) -> int:
    return POINTS_TABLE.get(tier, {}).get(evt, {}).get(action, 0)

def build_classement_embed(guild_id, guild) -> discord.Embed:
    rows = db.get_leaderboard(str(guild_id))
    embed = discord.Embed(title="🏆 Classement LigaLabs", color=0xF0B232)
    if not rows:
        embed.description = "Aucune équipe enregistrée."
        embed.set_footer(text="Utilise /setup-attribution pour ajouter des points")
        return embed

    lines = []
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, row in enumerate(rows[:25], 1):
        role  = guild.get_role(int(row["role_id"]))
        name  = role.name if role else f"ID:{row['role_id']}"
        medal = medals.get(i, f"**{i}.**")
        tier  = row.get("tier", "E")
        pts   = row["points"]
        lines.append(f"{medal} {TIER_EMOJI.get(tier,'⚪')} **{name}** — `{pts:+} pts` · Tier {tier}")

    embed.description = "\n".join(lines)
    embed.set_footer(text="Classement en temps réel • LigaLabs")
    return embed

async def refresh_classement_msg(guild):
    """Met à jour le message de classement Discord s'il est configuré."""
    gid  = str(guild.id)
    mid  = db.cfg(gid, "classement_msg_id")
    chid = db.cfg(gid, "classement_channel")
    if not (mid and chid):
        return
    ch = guild.get_channel(int(chid))
    if not ch:
        return
    try:
        msg = await ch.fetch_message(int(mid))
        await msg.edit(embed=build_classement_embed(guild.id, guild))
    except Exception:
        pass


# ─── FLUX D'ATTRIBUTION (vues éphémères) ──────────────────

class AttrTeamView(discord.ui.View):
    def __init__(self, user, guild):
        super().__init__(timeout=120)
        self.user = user
        roles = team_roles(guild)
        if roles:
            sel = discord.ui.Select(
                placeholder="Sélectionne la team...",
                options=[discord.SelectOption(label=r.name, value=str(r.id))
                         for r in roles[:25]])
            sel.callback = self.on_team
            self.add_item(sel)

    async def on_team(self, interaction: discord.Interaction):
        rid  = interaction.data["values"][0]
        role = interaction.guild.get_role(int(rid))
        attr_sessions[self.user.id] = {"role_id": rid, "name": role.name}
        await interaction.response.edit_message(
            content=f"✅ Team **{role.name}**\n\n**Type d'événement :**",
            view=AttrTypeView(self.user))


class AttrTypeView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=120)
        self.user = user
        sel = discord.ui.Select(
            placeholder="Type d'événement...",
            options=[
                discord.SelectOption(label="⚔️ Scrim",                  value="scrim"),
                discord.SelectOption(label="🏆 Tournoi non-officiel",   value="tournoi"),
                discord.SelectOption(label="🌟 Tournoi Officiel",       value="officiel"),
            ])
        sel.callback = self.on_type
        self.add_item(sel)

    async def on_type(self, interaction: discord.Interaction):
        evt = interaction.data["values"][0]
        attr_sessions[self.user.id]["type"] = evt
        labels = {"scrim": "Scrim", "tournoi": "Tournoi non-officiel", "officiel": "Tournoi Officiel"}
        await interaction.response.edit_message(
            content=f"✅ **{labels[evt]}**\n\n**Tier de VOTRE équipe :**",
            view=AttrTierView(self.user))


class AttrTierView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=120)
        self.user = user
        sel = discord.ui.Select(
            placeholder="Tier de votre équipe...",
            options=[discord.SelectOption(label=f"Tier {t}", value=t) for t in TIERS])
        sel.callback = self.on_tier
        self.add_item(sel)

    async def on_tier(self, interaction: discord.Interaction):
        tier = interaction.data["values"][0]
        attr_sessions[self.user.id]["tier"] = tier
        evt  = attr_sessions[self.user.id]["type"]

        if evt == "scrim":
            opts = [
                discord.SelectOption(label="✅ Victoire (Win)",  value="win"),
                discord.SelectOption(label="❌ Défaite (Loose)", value="loose"),
            ]
        elif evt == "tournoi":
            opts = [
                discord.SelectOption(label="✅ Win (match individuel)", value="win"),
                discord.SelectOption(label="❌ Loose (match individuel)", value="loose"),
                discord.SelectOption(label="🥇 Prime Champion",        value="champion"),
                discord.SelectOption(label="🥈 Prime Vice-Champion",   value="vice"),
                discord.SelectOption(label="🏅 Prime Demi-Finale",     value="semi"),
            ]
        else:  # officiel
            opts = [
                discord.SelectOption(label="✅ Win (match individuel)",    value="win"),
                discord.SelectOption(label="❌ Loose (match individuel)",  value="loose"),
                discord.SelectOption(label="🥇 Prime Champion",           value="champion"),
                discord.SelectOption(label="🥈 Prime Vice-Champion",      value="vice"),
                discord.SelectOption(label="🏅 Prime Demi-Finale",        value="semi"),
                discord.SelectOption(label="🎖️ Prime Quarts de Finale",  value="quart"),
            ]

        await interaction.response.edit_message(
            content=f"✅ **Tier {tier}**\n\n**Résultat / Placement :**",
            view=AttrResultView(self.user, opts))


class AttrResultView(discord.ui.View):
    def __init__(self, user, opts):
        super().__init__(timeout=120)
        self.user = user
        sel = discord.ui.Select(placeholder="Résultat / placement...", options=opts)
        sel.callback = self.on_result
        self.add_item(sel)

    async def on_result(self, interaction: discord.Interaction):
        action = interaction.data["values"][0]
        sess   = attr_sessions.get(self.user.id, {})
        tier   = sess.get("tier", "E")
        evt    = sess.get("type", "scrim")
        rid    = sess.get("role_id")
        name   = sess.get("name", "?")
        gid    = str(interaction.guild_id)

        pts    = calc_pts(tier, evt, action)
        reason = f"Tier {tier} • {evt} • {ACTION_LABEL.get(action, action)}"
        db.add_points(gid, rid, pts, reason)

        sign  = "+" if pts >= 0 else ""
        color = 0x23A55A if pts > 0 else (0xC0392B if pts < 0 else 0x808080)

        embed = discord.Embed(title="📊 Points attribués", color=color)
        embed.add_field(name="Team",      value=f"**{name}**",    inline=True)
        embed.add_field(name="Événement", value=reason,           inline=True)
        embed.add_field(name="Points",    value=f"**{sign}{pts}**", inline=True)
        team = db.get_team(gid, rid)
        if team:
            embed.add_field(name="Total actuel", value=f"{team['points']} pts", inline=True)

        await interaction.response.edit_message(content=None, embed=embed, view=None)
        await refresh_classement_msg(interaction.guild)
        attr_sessions.pop(self.user.id, None)


# ─── PANELS PERSISTANTS ───────────────────────────────────

class AttribuerView(discord.ui.View):
    """Panel permanent d'attribution de points."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📊 Attribuer des points",
                       style=discord.ButtonStyle.primary,
                       custom_id="attribuer_pts_ligalabs")
    async def attribuer(self, interaction: discord.Interaction, btn: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "❌ Réservé aux administrateurs.", ephemeral=True)
        await interaction.response.send_message(
            "**Attribution de points — Sélectionne la team :**",
            view=AttrTeamView(interaction.user, interaction.guild),
            ephemeral=True)


class ClassementRefreshView(discord.ui.View):
    """Panel persistant du classement avec bouton refresh."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔄 Actualiser",
                       style=discord.ButtonStyle.secondary,
                       custom_id="refresh_classement_ligalabs")
    async def refresh(self, interaction: discord.Interaction, btn: discord.ui.Button):
        embed = build_classement_embed(interaction.guild_id, interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)


# ─── COG ──────────────────────────────────────────────────

class ClassementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(AttribuerView())
        bot.add_view(ClassementRefreshView())

    # ── Setup des panels ──────────────────────────────────

    @app_commands.command(name="setup-attribution",
                          description="[ADMIN] Panel permanent d'attribution de points")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_attr(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📊 Attribution de Points — LigaLabs",
            description=("Utilise ce panel pour attribuer des points aux équipes.\n"
                         "Réservé aux **administrateurs**."),
            color=0xF0B232)
        await interaction.channel.send(embed=embed, view=AttribuerView())
        await interaction.response.send_message("✅ Panel d'attribution créé.", ephemeral=True)

    @app_commands.command(name="setup-classement",
                          description="Affiche le classement en direct dans ce salon")
    async def setup_classement(self, interaction: discord.Interaction):
        embed = build_classement_embed(interaction.guild_id, interaction.guild)
        msg   = await interaction.channel.send(embed=embed, view=ClassementRefreshView())
        db.set_cfg(interaction.guild_id, "classement_channel", interaction.channel_id)
        db.set_cfg(interaction.guild_id, "classement_msg_id",  msg.id)
        await interaction.response.send_message("✅ Panel de classement créé.", ephemeral=True)

    # ── Gestion des tiers ─────────────────────────────────

    @app_commands.command(name="set-tier",
                          description="Définir le tier d'une équipe")
    @app_commands.describe(role="Rôle de l'équipe", tier="Tier : E / D / C / B / A / S")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_tier_cmd(self, interaction: discord.Interaction,
                           role: discord.Role, tier: str):
        tier = tier.upper()
        if tier not in TIERS:
            return await interaction.response.send_message(
                "❌ Tier invalide. Choix : E, D, C, B, A, S", ephemeral=True)
        db.set_tier(interaction.guild_id, role.id, tier)
        await interaction.response.send_message(
            f"✅ **{role.name}** → Tier **{tier}** {TIER_EMOJI.get(tier,'')}", ephemeral=True)

    # ── Reset de points ───────────────────────────────────

    @app_commands.command(name="reset-points",
                          description="[ADMIN] Remettre à 0 les points d'une équipe")
    @app_commands.describe(role="Rôle de l'équipe")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_pts(self, interaction: discord.Interaction, role: discord.Role):
        team = db.get_team(interaction.guild_id, role.id)
        if not team:
            return await interaction.response.send_message("❌ Équipe non trouvée.", ephemeral=True)
        current = team["points"]
        db.add_points(str(interaction.guild_id), str(role.id), -current, "Reset admin")
        await interaction.response.send_message(
            f"✅ Points de **{role.name}** remis à 0 (était {current}).", ephemeral=True)
        await refresh_classement_msg(interaction.guild)

    # ── Export JSON pour le site web ──────────────────────

    @app_commands.command(name="export-site",
                          description="[ADMIN] Exporte les données vers website/teams.json")
    @app_commands.checks.has_permissions(administrator=True)
    async def export_site(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows  = db.get_leaderboard(str(interaction.guild_id))
        guild = interaction.guild
        teams = []
        for row in rows:
            role = guild.get_role(int(row["role_id"]))
            teams.append({
                "role_id":    row["role_id"],
                "name":       role.name.lstrip("-").strip() if role else f"ID:{row['role_id']}",
                "points":     row["points"],
                "tier":       row.get("tier", "E"),
                "logo":       "",          # à remplir manuellement
                "annee":      "",          # à remplir manuellement
                "nationalite": "",         # à remplir manuellement
                "players":    [],          # à remplir manuellement
            })
        os.makedirs("website", exist_ok=True)
        with open("website/teams.json", "w", encoding="utf-8") as f:
            json.dump({"teams": teams}, f, indent=2, ensure_ascii=False)
        await interaction.followup.send(
            f"✅ `website/teams.json` exporté ({len(teams)} équipes).\n"
            "Tu peux maintenant compléter `logo`, `annee`, `nationalite`, `players` manuellement.",
            ephemeral=True)



    @app_commands.command(name="reset-saison-ligalabs",
                          description="[ADMIN] Efface tous les matchs de poule — fin de saison")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_saison(self, interaction: discord.Interaction):
        db.reset_poule_season(interaction.guild_id)
        await interaction.response.send_message(
            "✅ Poule LigaLabs réinitialisée. Nouvelle saison prête.", ephemeral=True)

    @app_commands.command(name="export-ligalabs",
                          description="[ADMIN] Exporte la poule LigaLabs vers website/ligalabs.json")
    @app_commands.checks.has_permissions(administrator=True)
    async def export_ligalabs(self, interaction: discord.Interaction):
        import json, os
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        guild    = interaction.guild
        matches  = db.get_poule_matches(guild_id)

        # Charger les rosters depuis teams.json
        all_rosters = []
        if os.path.exists("website/teams.json"):
            with open("website/teams.json", encoding="utf-8") as f:
                teams_data = json.load(f).get("teams", [])
            for team in teams_data:
                for roster in team.get("rosters", []):
                    all_rosters.append({
                        "team":    team["name"],
                        "roster":  roster["name"],
                        "logo":    team.get("logo", ""),
                        "role_id": team.get("role_id", ""),
                    })

        total    = len(all_rosters)
        required = max((total - 1) * 2, 0)
        seuil60  = int(required * 0.6)

        # Calculer stats par roster
        stats = {}
        for r in all_rosters:
            key = f"{r['team']}||{r['roster']}"
            stats[key] = {**r, "played": 0, "wins": 0, "losses": 0}

        for m in matches:
            t1_role = guild.get_role(int(m["team1_id"])) if m["team1_id"] else None
            t2_role = guild.get_role(int(m["team2_id"])) if m["team2_id"] else None
            t1_name = t1_role.name.lstrip("-").strip() if t1_role else m["team1_id"]
            t2_name = t2_role.name.lstrip("-").strip() if t2_role else m["team2_id"]
            k1 = f"{t1_name}||{m['roster1']}"
            k2 = f"{t2_name}||{m['roster2']}"
            for k, is_t1 in [(k1, True), (k2, False)]:
                if k in stats:
                    stats[k]["played"] += 1
                    won = (m["winner_team_id"] == m["team1_id"]) == is_t1
                    stats[k]["wins" if won else "losses"] += 1

        standings = []
        for s in stats.values():
            pct = round(s["played"] / required * 100) if required > 0 else 0
            standings.append({
                "team":      s["team"],
                "roster":    s["roster"],
                "logo":      s["logo"],
                "played":    s["played"],
                "required":  required,
                "wins":      s["wins"],
                "losses":    s["losses"],
                "pct":       pct,
                "qualified": s["played"] == 0 or s["played"] >= seuil60,
            })
        standings.sort(key=lambda x: (-x["wins"], x["losses"], x["played"]))

        output = {
            "season":    "Saison 1",
            "total_rosters":  total,
            "required_per":   required,
            "seuil_60pct":    seuil60,
            "standings":      standings,
            "match_count":    len(matches),
        }
        os.makedirs("website", exist_ok=True)
        with open("website/ligalabs.json", "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        await interaction.followup.send(
            f"✅ `website/ligalabs.json` exporté — {len(standings)} rosters, {len(matches)} matchs.",
            ephemeral=True)

async def setup(bot):
    await bot.add_cog(ClassementCog(bot))
