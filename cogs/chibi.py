import discord
import database as db

# ─── OPTIONS ──────────────────────────────────────────────

PEAU_OPTS = [
    discord.SelectOption(label="Très clair",          value="very light skin"),
    discord.SelectOption(label="Assez clair",          value="light skin"),
    discord.SelectOption(label="Bronzé légèrement",    value="slightly tanned skin"),
    discord.SelectOption(label="Bronzé",               value="tanned skin"),
    discord.SelectOption(label="Très bronzé",          value="dark tanned skin"),
    discord.SelectOption(label="Très foncé",           value="very dark skin"),
]
YEUX_OPTS = [
    discord.SelectOption(label="Brun foncé", value="dark brown eyes"),
    discord.SelectOption(label="Brun clair",  value="light brown eyes"),
    discord.SelectOption(label="Vert",        value="green eyes"),
    discord.SelectOption(label="Bleu",        value="blue eyes"),
    discord.SelectOption(label="Gris",        value="grey eyes"),
]
CHEVEUX_COULEUR_OPTS = [
    discord.SelectOption(label="Brun foncé", value="dark brown hair"),
    discord.SelectOption(label="Châtain",    value="chestnut brown hair"),
    discord.SelectOption(label="Blond",      value="blonde hair"),
    discord.SelectOption(label="Noir",       value="black hair"),
    discord.SelectOption(label="Roux",       value="red hair"),
    discord.SelectOption(label="Gris",       value="grey hair"),
]
CHEVEUX_FILLE_OPTS = [
    discord.SelectOption(label="Longs pas attachés", value="long loose hair"),
    discord.SelectOption(label="Chignon",            value="bun hairstyle"),
    discord.SelectOption(label="Courts pas attachés",value="short loose hair"),
]
CHEVEUX_GARCON_OPTS = [
    discord.SelectOption(label="Buzz cut",           value="buzz cut"),
    discord.SelectOption(label="Cheveux en bataille", value="messy spiky hair"),
    discord.SelectOption(label="Chignon",            value="man bun"),
    discord.SelectOption(label="Chauve",             value="bald"),
    discord.SelectOption(label="Coupe casquette",    value="undercut with cap"),
]


# ─── VUES STEP BY STEP ────────────────────────────────────

class ChibiGenreView(discord.ui.View):
    def __init__(self, bot, user, channel):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel

    @discord.ui.button(label="👦 Garçon", style=discord.ButtonStyle.primary)
    async def garcon(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.edit_message(content="✅ **Garçon** — Étape 2/7 : **Couleur de peau ?**",
                                                 view=ChibiPeauView(self.bot, self.user, self.channel, "boy"))

    @discord.ui.button(label="👧 Fille", style=discord.ButtonStyle.danger)
    async def fille(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.edit_message(content="✅ **Fille** — Étape 2/7 : **Couleur de peau ?**",
                                                 view=ChibiPeauView(self.bot, self.user, self.channel, "girl"))


class ChibiPeauView(discord.ui.View):
    def __init__(self, bot, user, channel, genre):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.data = {"genre": genre}
        select = discord.ui.Select(placeholder="Couleur de peau...", options=PEAU_OPTS)
        select.callback = self.on_peau
        self.add_item(select)

    async def on_peau(self, interaction: discord.Interaction):
        self.data["peau"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content="✅ Peau notée — Étape 3/7 : **Lunettes ?**",
            view=ChibiLunettesView(self.bot, self.user, self.channel, self.data))


class ChibiLunettesView(discord.ui.View):
    def __init__(self, bot, user, channel, data):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.data = data

    @discord.ui.button(label="✅ Oui", style=discord.ButtonStyle.success)
    async def oui(self, interaction: discord.Interaction, btn: discord.ui.Button):
        self.data["lunettes"] = "wearing glasses"
        await interaction.response.edit_message(
            content="✅ Avec lunettes — Étape 4/7 : **Couleur des yeux ?**",
            view=ChibiYeuxView(self.bot, self.user, self.channel, self.data))

    @discord.ui.button(label="❌ Non", style=discord.ButtonStyle.secondary)
    async def non(self, interaction: discord.Interaction, btn: discord.ui.Button):
        self.data["lunettes"] = "no glasses"
        await interaction.response.edit_message(
            content="✅ Sans lunettes — Étape 4/7 : **Couleur des yeux ?**",
            view=ChibiYeuxView(self.bot, self.user, self.channel, self.data))


class ChibiYeuxView(discord.ui.View):
    def __init__(self, bot, user, channel, data):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.data = data
        select = discord.ui.Select(placeholder="Couleur des yeux...", options=YEUX_OPTS)
        select.callback = self.on_yeux
        self.add_item(select)

    async def on_yeux(self, interaction: discord.Interaction):
        self.data["yeux"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content="✅ Yeux notés — Étape 5/7 : **Couleur des cheveux ?**",
            view=ChibiChevCouleurView(self.bot, self.user, self.channel, self.data))


class ChibiChevCouleurView(discord.ui.View):
    def __init__(self, bot, user, channel, data):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.data = data
        select = discord.ui.Select(placeholder="Couleur des cheveux...", options=CHEVEUX_COULEUR_OPTS)
        select.callback = self.on_couleur
        self.add_item(select)

    async def on_couleur(self, interaction: discord.Interaction):
        self.data["cheveux_couleur"] = interaction.data["values"][0]
        genre = self.data["genre"]
        opts = CHEVEUX_GARCON_OPTS if genre == "boy" else CHEVEUX_FILLE_OPTS
        await interaction.response.edit_message(
            content="✅ Couleur notée — Étape 6/7 : **Forme des cheveux ?**",
            view=ChibiChevFormeView(self.bot, self.user, self.channel, self.data, opts))


class ChibiChevFormeView(discord.ui.View):
    def __init__(self, bot, user, channel, data, opts):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.data = data
        select = discord.ui.Select(placeholder="Forme des cheveux...", options=opts)
        select.callback = self.on_forme
        self.add_item(select)

    async def on_forme(self, interaction: discord.Interaction):
        self.data["cheveux_forme"] = interaction.data["values"][0]
        await interaction.response.edit_message(
            content="✅ Cheveux notés — Étape 7/7 : **Logo de la team ?** (envoie-le en pièce jointe dans ce salon, ou clique sur 'Aucun')",
            view=ChibiLogoView(self.bot, self.user, self.channel, self.data))


class ChibiLogoView(discord.ui.View):
    def __init__(self, bot, user, channel, data):
        super().__init__(timeout=180)
        self.bot = bot
        self.user = user
        self.channel = channel
        self.data = data

    @discord.ui.button(label="📎 J'envoie le logo", style=discord.ButtonStyle.primary)
    async def avec_logo(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.edit_message(content="📎 Envoie le logo en pièce jointe :", view=None)
        try:
            msg = await self.bot.wait_for(
                "message",
                check=lambda m: m.author.id == self.user.id and m.channel.id == self.channel.id and m.attachments,
                timeout=120)
            self.data["logo_url"] = msg.attachments[0].url
        except Exception:
            self.data["logo_url"] = None
        await _envoyer_prompt_chibi(self.bot, self.user, self.channel, self.data)

    @discord.ui.button(label="❌ Aucun logo", style=discord.ButtonStyle.secondary)
    async def sans_logo(self, interaction: discord.Interaction, btn: discord.ui.Button):
        self.data["logo_url"] = None
        await interaction.response.edit_message(content="✅ Pas de logo.", view=None)
        await _envoyer_prompt_chibi(self.bot, self.user, self.channel, self.data)


# ─── GÉNÉRATION DU PROMPT ─────────────────────────────────

def build_chibi_prompt(data: dict) -> str:
    genre_word = "male" if data.get("genre") == "boy" else "female"
    lunettes = data.get("lunettes", "no glasses")
    peau = data.get("peau", "light skin")
    yeux = data.get("yeux", "brown eyes")
    chev_couleur = data.get("cheveux_couleur", "black hair")
    chev_forme = data.get("cheveux_forme", "short hair")

    prompt = (
        f"Chibi esport Brawl Stars style character, {genre_word}, {peau}, "
        f"{yeux}, {chev_couleur} with {chev_forme}, {lunettes}, "
        "wearing a competitive esport gaming jersey with the team logo on the chest, "
        "chibi proportions (big head, small body), vibrant colors, clean anime linework, "
        "dynamic esport pose, glowing effects, professional esport illustration, "
        "white or transparent background, high quality digital art"
    )
    if data.get("logo_url"):
        prompt += f"\n\n📎 Logo à intégrer dans le maillot : {data['logo_url']}"
    return prompt


async def _envoyer_prompt_chibi(bot, user, channel, data):
    prompt = build_chibi_prompt(data)
    guild_id = str(channel.guild.id)
    ch_id = db.cfg(guild_id, "chibi_channel")

    embed = discord.Embed(title="🎨 Prompt Chibi Généré", color=0xFF69B4)
    embed.description = f"```\n{prompt}\n```"
    embed.set_footer(text=f"Demandé par {user.display_name}")
    if data.get("logo_url"):
        embed.set_thumbnail(url=data["logo_url"])

    await channel.send(
        f"✅ **Chibi prêt !** Le prompt a été envoyé aux admins pour génération.",
        embed=embed)

    if ch_id:
        dest = channel.guild.get_channel(int(ch_id))
        if dest:
            await dest.send(
                f"🎨 **Nouveau Chibi à générer** — {user.mention}",
                embed=embed)


# ─── ENTRY POINT ──────────────────────────────────────────

async def run_chibi(bot, user: discord.Member, channel: discord.TextChannel):
    """Lance le flow chibi dans un salon (appelé depuis ticket.py)."""
    await channel.send(
        f"{user.mention} 🎨 **Chibi Bot** — Étape 1/7\n**Genre de ton personnage ?**",
        view=ChibiGenreView(bot, user, channel))
