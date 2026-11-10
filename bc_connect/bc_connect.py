import reflex as rx


ACCENT = "#FF2A54"
BACKGROUND = "#0F172A"
TEXT = "#FFFFFF"
MUTED = "#CBD5E1"


class LandingState(rx.State):
    menu_open: bool = False

    def toggle_menu(self) -> None:
        self.menu_open = not self.menu_open


def nav() -> rx.Component:
    return rx.hstack(
        rx.link(
            rx.heading("BC Connect", size="5", color=TEXT),
            href="#accueil",
            text_decoration="none",
        ),
        rx.spacer(),
        rx.hstack(
            rx.link("Le concept", href="#concept", color=MUTED),
            rx.link("Communauté", href="#communaute", color=MUTED),
            rx.button(
                "Se connecter",
                color_scheme="ruby",
                background=ACCENT,
                color=TEXT,
                border_radius="9999px",
            ),
            spacing="6",
            display=["none", "none", "flex"],
        ),
        rx.button(
            "Menu",
            on_click=LandingState.toggle_menu,
            variant="soft",
            display=["flex", "flex", "none"],
        ),
        width="100%",
        align="center",
    )


def hero() -> rx.Component:
    return rx.vstack(
        rx.badge(
            "IUT-FV · Bandjoun",
            color=ACCENT,
            background="rgba(255, 42, 84, 0.12)",
            padding_x="4",
            padding_y="2",
            border_radius="9999px",
        ),
        rx.heading(
            "Les bonnes connexions commencent sur le campus.",
            size=["8", "9", "9"],
            color=TEXT,
            text_align="center",
            max_width="850px",
        ),
        rx.text(
            "BC Connect rassemble les étudiants de l’Institut Universitaire "
            "de Technologie Fotso Victor autour des affinités, de l’entraide "
            "et de la vie du campus.",
            color=MUTED,
            font_size=["1rem", "1.1rem"],
            text_align="center",
            max_width="680px",
            line_height="1.7",
        ),
        rx.hstack(
            rx.button(
                "Rejoindre BC Connect",
                color_scheme="ruby",
                background=ACCENT,
                color=TEXT,
                size="3",
                border_radius="9999px",
            ),
            rx.button(
                "Découvrir la communauté",
                variant="outline",
                color=TEXT,
                border_color="rgba(255, 255, 255, 0.3)",
                size="3",
                border_radius="9999px",
            ),
            spacing="4",
            flex_wrap="wrap",
            justify="center",
        ),
        spacing="7",
        align="center",
        padding_top=["5rem", "7rem"],
        padding_bottom=["5rem", "8rem"],
    )


def feature_card(title: str, description: str, icon: str) -> rx.Component:
    return rx.box(
        rx.text(icon, font_size="2rem"),
        rx.heading(title, size="5", color=TEXT),
        rx.text(description, color=MUTED, line_height="1.6"),
        background="rgba(255, 255, 255, 0.06)",
        border="1px solid rgba(255, 255, 255, 0.1)",
        border_radius="1.25rem",
        padding="1.5rem",
        flex="1",
        min_width=["100%", "260px"],
    )


def concept() -> rx.Component:
    return rx.vstack(
        rx.text("L’esprit BC Connect", color=ACCENT, font_weight="700"),
        rx.heading(
            "Un réseau étudiant pensé pour la vraie vie du campus.",
            color=TEXT,
            size=["7", "8"],
            text_align="center",
            max_width="720px",
        ),
        rx.text(
            "Des amphis au foyer, du terrain de volley au Club 100, "
            "crée des liens qui dépassent ta filière.",
            color=MUTED,
            text_align="center",
            max_width="640px",
        ),
        rx.hstack(
            feature_card(
                "Affinités naturelles",
                "Découvre des étudiants qui partagent tes centres d’intérêt et ton énergie.",
                "✦",
            ),
            feature_card(
                "Entraide campus",
                "Échange, révise et avance avec une communauté proche de ton quotidien.",
                "↗",
            ),
            feature_card(
                "Toutes les filières",
                "Industrielles, commerciales ou de gestion : chaque parcours a sa place.",
                "∞",
            ),
            spacing="5",
            width="100%",
            flex_wrap="wrap",
        ),
        id="concept",
        spacing="5",
        align="center",
        padding_y=["4rem", "6rem"],
    )


def index() -> rx.Component:
    return rx.box(
        rx.box(
            nav(),
            hero(),
            concept(),
            max_width="1180px",
            margin="0 auto",
            padding_x=["1.25rem", "2rem"],
        ),
        id="accueil",
        min_height="100vh",
        background=BACKGROUND,
        font_family="Inter, sans-serif",
    )


app = rx.App(
    theme=rx.theme(
        appearance="dark",
        has_background=True,
        radius="large",
        scaling="100%",
    )
)
app.add_page(index, route="/", title="BC Connect · IUT-FV")
