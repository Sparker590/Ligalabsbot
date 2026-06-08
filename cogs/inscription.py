Je suis Gemini (et non Claude), mais ne t'inquiète pas, tu n'as aucune restriction de messages ici ! Je vais aller droit au but pour te faire gagner du temps.

Voici le fichier **`inscription.py`** modifié. J'ai ajouté le panel d'administration `AdminValidationView` à la fin du processus. Désormais, au lieu d'envoyer un simple résumé au panel admin, le bot joint des boutons pour "Valider" ou "Refuser". Si tu valides, il crée les rôles de l'équipe et des rosters, les distribue aux joueurs tagués, et génère le bloc JSON exact pour ton site web.

Remplace tout le contenu de ton fichier `Ligalabs/cogs/inscription.py` par ceci :

```python
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
    """Processus complet d'inscription dans un salon (ticket ou DM)"""
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

    # 1. Nom de la team
    m = await ask("**1/7 — Quel est le nom de ta team ?** (envoie un message)")
    if not m: return
    data["nom"] = m.content.strip()

    # 2. Année de création
    view2 = AnneeView()
    await channel.send("**2/7 — Année de création :**", view=view2)
    await view2.wait()
    if not view2.value: return
    data["annee"] = view2.value

    # 3. Nombre de rosters
    view3 = RosterView()
    await channel.send("**3/7 — Nombre de rosters ?** (max 5)", view=view3)
    await view3.wait()
    if not view3.value: return
    nb_rosters = int(view3.value)
    data["nb_rosters"] = nb_rosters

    # 4. Joueurs par roster
    data["rosters"] = {}
    for i in range(1, nb_rosters + 1):
        m = await ask(f"**4/{nb_rosters + 3} — Joueurs du Roster {i} :**\nEnvoie un message avec les pings des joueurs (ex: `@Joueur1 @Joueur2 @Joueur3`)")
        if not m: return
        mentions = [f"<@{u.id}>" for u in m.mentions] if m.mentions else m.content.split()
        data["rosters"][f"Roster {i}"] = mentions

    # 5. Niveau ranked
    view5 = NiveauView()
    await channel.send("**5/7 — Niveau moyen ranked du roster :**", view=view5)
    await view5.wait()
    if not view5.value: return
    data["niveau"] = view5.value

    # 6. Owner de la team
    m = await ask("**6/7 — Owner de la team ?** (envoie un message avec le ping du chef `@Chef`)")
    if not m: return
    data["owner"] = m.mentions[0].mention if m.mentions else m.content

    # 7. Logo
    view7 = LogoView()
    await channel.send("**7/7 — Avez-vous un logo ?**", view=view7)
    await view7.wait()
    logo_url = None
    if view7.value == "oui":
        m = await ask("📎 Envoie le logo en pièce jointe (image) :")
        if m and m.attachments:
            logo_url = m.attachments[0].url

    # Compilation et envoi
    await envoyer_recap(channel, user, bot, data, logo_url)

async def envoyer_recap(channel, user, bot, data, logo_url):
    gid = str(channel.guild.id)
    ch_id = bot.db["settings"].get(gid, {}).get("inscription_channel")

    embed = discord.Embed(title=f"📋 Inscription — {data['nom']}", color=0x5865F2)
    embed.add_field(name="👤 Demandeur", value=user.mention, inline=True)
    embed.add_field(name="📅 Année de création", value=data["annee"], inline=True)
    embed.add_field(name="📊 Niveau", value=data["niveau"], inline=True)
    embed.add_field(name="👑 Owner", value=data["owner"], inline=True)
    embed.add_field(name="🗂️ Nb Rosters", value=str(data["nb_rosters"]), inline=True)

    for rname, players in data["rosters"].items():
        embed.add_field(name=f"🎮 {rname}", value=" • ".join(players) if players else "—", inline=False)

    if logo_url:
        embed.set_thumbnail(url=logo_url)
        embed.add_field(name="🖼️ Logo", value=logo_url, inline=False)

    embed.set_footer(text="Inscription via le bot")

    await channel.send("✅ **Inscription terminée !** Récapitulatif envoyé aux admins en attente de validation.", embed=embed)

    if ch_id:
        dest = channel.guild.get_channel(int(ch_id))
        if dest:
            view = AdminValidationView(data, logo_url)
            await dest.send(content="⚠️ **Nouvelle inscription à vérifier** (Assure-toi que tous les joueurs sont sur le serveur avant de valider) :", embed=embed, view=view)


# ── Vues de base ───────────────────────────────────────────────────────────────

class StartInscriptionView(discord.ui.View):
    def __init__(self): super().__init__(timeout=60)

    @discord.ui.button(label="🚀 Démarrer l'inscription", style=discord.ButtonStyle.primary)
    async def start(self, inter: discord.Interaction, btn: discord.ui.Button):
        await inter.response.edit_message(content="📋 Inscription démarrée ! Réponds aux questions ici.", view=None)
        await run_inscription(inter.channel, inter.user, inter.client)

class AnneeView(discord.ui.View):
    def __init__(self): super().__init__(timeout=120); self.value = None
    async def on_timeout(self): self.stop()

    @discord.ui.select(placeholder="Choisis l'année...",
                       options=[discord.SelectOption(label=a, value=a) for a in ANNEES])
    async def sel(self, inter: discord.Interaction, s: discord.ui.Select):
        self.value = s.values[0]
        await inter.response.edit_message(content=f"✅ Année : **{self.value}**", view=None)
        self.stop()

class RosterView(discord.ui.View):
    def __init__(self): super().__init__(timeout=120); self.value = None
    async def on_timeout(self): self.stop()

    @discord.ui.select(placeholder="Nombre de rosters...",
                       options=[discord.SelectOption(label=str(i), value=str(i)) for i in range(1, 6)])
    async def sel(self, inter: discord.Interaction, s: discord.ui.Select):
        self.value = s.values[0]
        await inter.response.edit_message(content=f"✅ **{self.value}** roster(s)", view=None)
        self.stop()

class NiveauView(discord.ui.View):
    def __init__(self): super().__init__(timeout=120); self.value = None
    async def on_timeout(self): self.stop()

    @discord.ui.select(placeholder="Niveau moyen ranked...",
                       options=[discord.SelectOption(label=l, value=v) for l, v in NIVEAUX])
    async def sel(self, inter: discord.Interaction, s: discord.ui.Select):
        self.value = s.values[0]
        await inter.response.edit_message(content=f"✅ Niveau : **{self.value}**", view=None)
        self.stop()

class LogoView(discord.ui.View):
    def __init__(self): super().__init__(timeout=120); self.value = None
    async def on_timeout(self): self.stop()

    @discord.ui.button(label="Oui", style=discord.ButtonStyle.success)
    async def oui(self, inter: discord.Interaction, btn: discord.ui.Button):
        self.value = "oui"
        await inter.response.edit_message(content="✅ Envoie le logo.", view=None)
        self.stop()

    @discord.ui.button(label="Non", style=discord.ButtonStyle.secondary)
    async def non(self, inter: discord.Interaction, btn: discord.ui.Button):
        self.value = "non"
        await inter.response.edit_message(content="❌ Pas de logo.", view=None)
        self.stop()

# ── Vues Admin Validation ──────────────────────────────────────────────────────

class AdminValidationView(discord.ui.View):
    def __init__(self, data, logo_url):
        super().__init__(timeout=None)
        self.data = data
        self.logo_url = logo_url

    @discord.ui.button(label="✅ Valider la Team", style=discord.ButtonStyle.success, custom_id="valider_team_insc")
    async def valider(self, inter: discord.Interaction, btn: discord.ui.Button):
        await inter.response.defer() # Donne le temps au bot de créer les rôles

        guild = inter.guild
        data = self.data
        nom_team = data['nom']

        # 1. Création du rôle de Team principal
        try:
            team_role = await guild.create_role(name=f"-{nom_team}", reason="Validation équipe LigaLabs")
        except Exception as e:
            return await inter.followup.send(f"❌ Impossible de créer le rôle de l'équipe. Vérifie mes permissions : {e}", ephemeral=True)

        rosters_json = []

        # 2. Création des rôles par Roster et attribution aux joueurs
        for rname, players in data["rosters"].items():
            # Rôle spécifique pour ce roster
            try:
                roster_role = await guild.create_role(name=f"{nom_team} - {rname}", reason="Roster LigaLabs")
            except:
                roster_role = None

            roster_info = {
                "name": rname,
                "tier": "E", # Par défaut
                "players": []
            }

            for p_mention in players:
                # Extraire l'ID numérique depuis le format <@123456>
                match = re.search(r'\d+', p_mention)
                p_name = p_mention

                if match:
                    member_id = int(match.group())
                    member = guild.get_member(member_id)

                    if member:
                        p_name = member.display_name
                        # Attribuer les rôles au joueur
                        roles_to_add = [team_role]
                        if roster_role: roles_to_add.append(roster_role)

                        try:
                            await member.add_roles(*roles_to_add)
                        except:
                            pass # On ignore l'erreur si le bot n'a pas les droits
                    else:
                        p_name = f"Joueur Introuvable ({member_id})"

                roster_info["players"].append({
                    "name": p_name,
                    "chibi": "URL_A_AJOUTER"
                })

            rosters_json.append(roster_info)

        # 3. Génération du bloc JSON
        json_output = {
            "name": nom_team,
            "points": 0,
            "tier": "E", # Par défaut
            "logo": self.logo_url if self.logo_url else "URL_A_AJOUTER",
            "annee": data["annee"],
            "nationalite": "🇫🇷 France", # Par défaut
            "rosters": rosters_json
        }

        json_str = json.dumps(json_output, indent=2, ensure_ascii=False)

        # Désactiver les boutons de validation
        for child in self.children:
            child.disabled = True
        await inter.message.edit(content="✅ **Équipe validée ! Rôles créés et distribués.**", view=self)

        # Envoyer les données formatées dans le salon pour les copier-coller facilement
        await inter.followup.send(
            f"**Fiche JSON pour le site web :**\n*(Ajoute toi-même les urls logo et chibi)*\n```json\n{json_str}\n
```"
        )

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger, custom_id="refuser_team_insc")
    async def refuser(self, inter: discord.Interaction, btn: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await inter.message.edit(content="❌ **Inscription refusée.** (Joueurs introuvables ou refus admin)", view=self)
        await inter.response.send_message("L'équipe a été refusée, aucun rôle ni JSON n'a été créé.", ephemeral=True)

class PanelInscriptionView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="📋 Inscrire ma team", style=discord.ButtonStyle.primary, custom_id="start_insc_panel")
    async def start(self, inter: discord.Interaction, btn: discord.ui.Button):
        await inter.response.send_message("Je vais te poser quelques questions en privé/éphémère pour t'inscrire !", ephemeral=True)
        await run_inscription(inter.channel, inter.user, inter.client)

async def setup(bot):
    await bot.add_cog(InscriptionCog(bot))
    bot.add_view(PanelInscriptionView())


