import discord, asyncio, json, re
from discord.ext import commands
from discord import app_commands

NIVEAUX = [
    ("🟦 Diamant 💎", "diamant"), ("🟪 Mythique 👑", "mythique"),
    ("🟥 Légendaire 👿", "legendaire"), ("🟧 Master ⭐", "master"), ("🟩 Pro 🏆", "pro")
]
ANNEES = ["2022", "2023", "2024", "2025", "2026"]

class InscriptionCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="setup-inscription", description="Lance le processus d'inscription d'une team ici")
    async def launch_insc(self, inter: discord.Interaction):
        await inter.response.send_message(
            "📋 **Inscription de team** — Lance le formulaire :",
            view=StartInscriptionView(), ephemeral=True)

async def run_inscription(channel: discord.TextChannel, user: discord.Member, bot):
    async def ask(msg, timeout=180):
        await channel.send(msg)
        try:
            m = await bot.wait_for("message",
                check=lambda x: x.author.id == user.id and x.channel.id == channel.id,
                timeout=timeout)
            return m
        except asyncio.TimeoutError:
            await channel.send("⏱️ Temps écoulé. Recommence avec `/setup-inscription`.")
            return None

    data = {}
    m = await ask("**1/7 — Quel est le nom de ta team ?**")
    if not m: return
    data["nom"] = m.content.strip()

    view2 = AnneeView()
    await channel.send("**2/7 — Année de création :**", view=view2)
    await view2.wait()
    if not view2.value: return
    data["annee"] = view2.value

    view3 = RosterView()
    await channel.send("**3/7 — Nombre de rosters ?** (max 5)", view=view3)
    await view3.wait()
    if not view3.value: return
    nb_rosters = int(view3.value)
    data["nb_rosters"] = nb_rosters

    data["rosters"] = {}
    for i in range(1, nb_rosters + 1):
        m = await ask(f"**4/{nb_rosters + 3} — Joueurs du Roster {i} :**\nEnvoie les mentions des joueurs (ex: @Joueur1 @Joueur2)")
        if not m: return
        data["rosters"][f"Roster {i}"] = [f"<@{u.id}>" for u in m.mentions] if m.mentions else m.content.split()

    view5 = NiveauView()
    await channel.send("**5/7 — Niveau moyen ranked du roster :**", view=view5)
    await view5.wait()
    if not view5.value: return
    data["niveau"] = view5.value

    m = await ask("**6/7 — Owner de la team ?** (ping du chef)")
    if not m: return
    data["owner"] = m.mentions[0].mention if m.mentions else m.content

    view7 = LogoView()
    await channel.send("**7/7 — Avez-vous un logo ?**", view=view7)
    await view7.wait()
    logo_url = None
    if view7.value == "oui":
        m = await ask("📎 Envoie le logo en pièce jointe :")
        if m and m.attachments: logo_url = m.attachments[0].url

    await envoyer_recap(channel, user, bot, data, logo_url)

async def envoyer_recap(channel, user, bot, data, logo_url):
    gid = str(channel.guild.id)
    ch_id = bot.db["settings"].get(gid, {}).get("inscription_channel")
    
    embed = discord.Embed(title=f"📋 Inscription — {data['nom']}", color=0x5865F2)
    embed.add_field(name="👤 Demandeur", value=user.mention, inline=True)
    embed.add_field(name="📅 Année", value=data["annee"], inline=True)
    embed.add_field(name="📊 Niveau", value=data["niveau"], inline=True)
    embed.add_field(name="👑 Owner", value=data["owner"], inline=True)
    for rname, players in data["rosters"].items():
        embed.add_field(name=f"🎮 {rname}", value=" ".join(players), inline=False)
    if logo_url: embed.set_thumbnail(url=logo_url)
    
    await channel.send("✅ **Inscription terminée !** Envoyée aux admins.", embed=embed)

    if ch_id:
        dest = channel.guild.get_channel(int(ch_id))
        if dest:
            await dest.send(content="⚠️ **Nouvelle inscription à valider :**", embed=embed, view=AdminValidationView(data, logo_url))

class AdminValidationView(discord.ui.View):
    def __init__(self, data, logo_url):
        super().__init__(timeout=None)
        self.data = data
        self.logo_url = logo_url

    @discord.ui.button(label="✅ Valider", style=discord.ButtonStyle.success)
    async def valider(self, inter: discord.Interaction, btn: discord.ui.Button):
        await inter.response.defer()
        guild = inter.guild
        nom_team = self.data['nom']
        team_role = await guild.create_role(name=f"-{nom_team}")
        rosters_json = []

        for rname, players in self.data["rosters"].items():
            roster_role = await guild.create_role(name=f"{nom_team} - {rname}")
            roster_info = {"name": rname, "tier": "E", "players": []}
            for p_mention in players:
                match = re.search(r'\d+', p_mention)
                if match:
                    member = guild.get_member(int(match.group()))
                    if member:
                        await member.add_roles(team_role, roster_role)
                        roster_info["players"].append({"name": member.display_name, "chibi": ""})
            rosters_json.append(roster_info)

        json_output = json.dumps({
            "name": nom_team, "points": 0, "tier": "E", "logo": self.logo_url or "",
            "annee": self.data["annee"], "nationalite": "🇫🇷 France", "rosters": rosters_json
        }, indent=2, ensure_ascii=False)

        await inter.message.edit(content="✅ **Validée.**", view=None)
        await inter.followup.send(f"```json\n{json_output}\n```")

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def refuser(self, inter: discord.Interaction, btn: discord.ui.Button):
        await inter.message.edit(content="❌ **Refusée.**", view=None)
        await inter.response.send_message("Inscription refusée.", ephemeral=True)

class StartInscriptionView(discord.ui.View):
    @discord.ui.button(label="Démarrer", style=discord.ButtonStyle.primary)
    async def start(self, inter, btn):
        await inter.response.edit_message(content="C'est parti !", view=None)
        await run_inscription(inter.channel, inter.user, inter.client)

class AnneeView(discord.ui.View):
    def __init__(self): super().__init__(timeout=120); self.value = None
    @discord.ui.select(options=[discord.SelectOption(label=a, value=a) for a in ANNEES])
    async def s(self, i, s): self.value = s.values[0]; await i.response.edit_message(content=f"Annee: {self.value}", view=None); self.stop()

class RosterView(discord.ui.View):
    def __init__(self): super().__init__(timeout=120); self.value = None
    @discord.ui.select(options=[discord.SelectOption(label=str(i), value=str(i)) for i in range(1, 6)])
    async def s(self, i, s): self.value = s.values[0]; await i.response.edit_message(content=f"Rosters: {self.value}", view=None); self.stop()

class NiveauView(discord.ui.View):
    def __init__(self): super().__init__(timeout=120); self.value = None
    @discord.ui.select(options=[discord.SelectOption(label=l, value=v) for l, v in NIVEAUX])
    async def s(self, i, s): self.value = s.values[0]; await i.response.edit_message(content=f"Niveau: {self.value}", view=None); self.stop()

class LogoView(discord.ui.View):
    def __init__(self): super().__init__(timeout=120); self.value = None
    @discord.ui.button(label="Oui", style=discord.ButtonStyle.success)
    async def o(self, i, b): self.value = "oui"; await i.response.edit_message(content="Logo oui.", view=None); self.stop()
    @discord.ui.button(label="Non", style=discord.ButtonStyle.secondary)
    async def n(self, i, b): self.value = "non"; await i.response.edit_message(content="Logo non.", view=None); self.stop()

async def setup(bot):
    await bot.add_cog(InscriptionCog(bot))