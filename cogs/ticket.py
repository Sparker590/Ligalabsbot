import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import database as db
from cogs.chibi import run_chibi

# ─── VUE DE SÉLECTION DU MOTIF ────────────────────────────

class MotifView(discord.ui.View):
    def __init__(self, bot, user, channel):
        super().__init__(timeout=120)
        self.bot   = bot
        self.user  = user
        self.channel = channel

        select = discord.ui.Select(
            placeholder="Motif du ticket...",
            options=[
                discord.SelectOption(
                    label="📋 Inscrire ma team",
                    value="inscription",
                    description="Remplir le formulaire d'inscription LigaLabs"),
                discord.SelectOption(
                    label="🎨 Obtenir mon Chibi",
                    value="chibi",
                    description="Générer ton personnage chibi esport"),
                discord.SelectOption(
                    label="⚠️ Signaler un problème",
                    value="probleme",
                    description="Contacter les modérateurs"),
            ])
        select.callback = self.on_motif
        self.add_item(select)

    async def on_motif(self, interaction: discord.Interaction):
        motif = interaction.data["values"][0]

        if motif == "inscription":
            await interaction.response.edit_message(
                content="📋 **Inscription de team** — Le formulaire démarre ici 👇", view=None)
            insc_cog = self.bot.cogs.get("InscriptionCog")
            if insc_cog:
                await insc_cog.start_inscription(self.channel, self.user)
            else:
                await self.channel.send("❌ Bot d'inscription indisponible. Contacte un admin.")

        elif motif == "chibi":
            await interaction.response.edit_message(
                content="🎨 **Chibi Bot** — Réponds aux questions 👇", view=None)
            await run_chibi(self.bot, self.user, self.channel)

        else:
            await interaction.response.edit_message(
                content=("⚠️ **Ticket de support ouvert.**\n"
                         "Décris ton problème ici et un modérateur te répondra."),
                view=None)


# ─── PANEL PERMANENT D'OUVERTURE DE TICKET ────────────────

class OuvrirTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ouvrir un ticket",
                       style=discord.ButtonStyle.primary,
                       custom_id="open_ticket_ligalabs")
    async def ouvrir(self, interaction: discord.Interaction, btn: discord.ui.Button):
        guild = interaction.guild
        user  = interaction.user

        # Ticket déjà ouvert ?
        nom_salon = f"ticket-{user.name[:18].lower().replace(' ', '-')}"
        existing = discord.utils.get(guild.text_channels, name=nom_salon)
        if existing:
            return await interaction.response.send_message(
                f"❌ Tu as déjà un ticket ouvert : {existing.mention}", ephemeral=True)

        # Créer la catégorie si besoin
        cat = discord.utils.get(guild.categories, name="🎫 Tickets")
        if not cat:
            cat = await guild.create_category("🎫 Tickets")

        # Permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        for role in guild.roles:
            if role.permissions.administrator or role.permissions.manage_channels:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True)

        ticket_ch = await cat.create_text_channel(nom_salon, overwrites=overwrites)

        # Message d'accueil
        embed = discord.Embed(
            title="🎫 Ticket LigaLabs",
            description=(f"Bienvenue {user.mention} !\n\n"
                         "Choisis le **motif** de ton ticket ci-dessous.\n"
                         "Un modérateur peut rejoindre à tout moment."),
            color=0x5865F2)
        embed.set_footer(text="LigaLabs — Ferme le ticket quand tu as terminé")

        await ticket_ch.send(
            content=f"{user.mention}",
            embed=embed,
            view=MotifView(interaction.client, user, ticket_ch))

        await ticket_ch.send("─────────────────────────", view=FermerTicketView())

        await interaction.response.send_message(
            f"✅ Ton ticket est ouvert : {ticket_ch.mention}", ephemeral=True)


# ─── BOUTON DE FERMETURE ──────────────────────────────────

class FermerTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket",
                       style=discord.ButtonStyle.danger,
                       custom_id="fermer_ticket_ligalabs")
    async def fermer(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_message("🔒 Fermeture dans 5 secondes...")
        await asyncio.sleep(5)
        await interaction.channel.delete(reason="Ticket fermé")


# ─── COG ──────────────────────────────────────────────────

class TicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(OuvrirTicketView())
        bot.add_view(FermerTicketView())

    @app_commands.command(name="setup-tickets",
                          description="Affiche le panel d'ouverture de tickets")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def setup_tickets(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎫 Support LigaLabs",
            description=("Ouvre un ticket pour :\n\n"
                         "📋 **Inscrire ta team** à la LigaLabs\n"
                         "🎨 **Générer ton chibi** esport personnalisé\n"
                         "⚠️ **Signaler** un problème ou contacter les mods"),
            color=0x5865F2)
        embed.set_footer(text="LigaLabs • Un seul ticket par utilisateur")
        await interaction.channel.send(embed=embed, view=OuvrirTicketView())
        await interaction.response.send_message("✅ Panel de tickets créé.", ephemeral=True)

    @app_commands.command(name="set-chibi-channel",
                          description="Salon de destination pour les prompts chibi")
    @app_commands.describe(channel="Salon de destination")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_chibi_ch(self, interaction: discord.Interaction,
                           channel: discord.TextChannel):
        db.set_cfg(interaction.guild_id, "chibi_channel", channel.id)
        await interaction.response.send_message(
            f"✅ Prompts chibi → {channel.mention}", ephemeral=True)




async def setup(bot):
    await bot.add_cog(TicketCog(bot))

