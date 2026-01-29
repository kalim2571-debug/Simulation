# -*- coding: utf-8 -*-
"""
market.py - Univers d'Investissement et Scénarios Macro
========================================================
Gère la base de données des actifs disponibles et l'application
des scénarios macroéconomiques (ajustements de μ et σ).

ADMIN: C'est ici que vous modifiez les paramètres de marché pour vos élèves.
"""

from engine import Asset


# ==========================================
# BASE DE DONNÉES DES ACTIFS DISPONIBLES
# ==========================================

def get_available_assets():
    """
    Univers d'investissement (rendements annuels).

    Notes Admin:
    - exp_return et volatility sont des hypothèses long-terme prudentes
    - beta_* : sensibilités aux facteurs macro (PIB, inflation, taux)
    """
    return [
        # ============================================
        # EQUITY (Actions)
        # ============================================
        Asset(
            name="ETF World (MSCI)",
            category="Equity",
            sub_category="ETF",
            exp_return=0.07,
            volatility=0.15,
            beta_gdp=1.0,
            beta_inf=0.10,        # plus neutre (inflation élevée pénalise souvent via taux)
            beta_rates=-0.45,
            beta_equity=1.0       # Référence du marché actions
        ),
        Asset(
            name="Actions Tech US",
            category="Equity",
            sub_category="Direct",
            exp_return=0.10,       # ↓ plus prudent que 12%
            volatility=0.25,
            beta_gdp=1.2,
            beta_inf=0.00,         # la tech souffre souvent des chocs d'inflation (via taux)
            beta_rates=-0.70,      # ↑ plus sensible aux taux
            beta_equity=1.2        # Plus volatile que le marché (growth)
        ),
        Asset(
            name="Actions Value Europe",
            category="Equity",
            sub_category="Direct",
            exp_return=0.06,
            volatility=0.16,       # ↓ légèrement (18% était un peu haut si "value" large)
            beta_gdp=0.9,
            beta_inf=0.25,         # ↑ value résiste mieux / secteurs "réels"
            beta_rates=-0.25,
            beta_equity=0.9        # Moins volatile que le marché (defensive)
        ),

        # ============================================
        # BONDS (Obligations)
        # ============================================
        Asset(
            name="Gov Bonds US (10Y)",
            category="Bonds",
            sub_category="Souverain AAA",
            exp_return=0.035,
            volatility=0.06,       # ↑ un peu, pour refléter que les taux peuvent bouger
            beta_gdp=-0.10,        # safe haven (récession => bonds montent)
            beta_inf=-0.60,
            beta_rates=-0.90,      # légèrement moins extrême que -1.0
            beta_equity=0.0,       # Décorrélé du marché actions (safe haven)
            duration=7.0           # Duration ~7 ans pour 10Y
        ),
        Asset(
            name="Gov Bonds Euro (10Y)",
            category="Bonds",
            sub_category="Souverain AA",
            exp_return=0.030,
            volatility=0.05,
            beta_gdp=-0.10,
            beta_inf=-0.50,
            beta_rates=-0.80,
            beta_equity=0.0,       # Décorrélé du marché actions
            duration=7.0           # Duration ~7 ans
        ),
        Asset(
            name="Corp Bonds IG",
            category="Bonds",
            sub_category="Corporate IG",
            exp_return=0.045,
            volatility=0.06,
            beta_gdp=0.30,
            beta_inf=-0.20,
            beta_rates=-0.60,
            beta_equity=0.25,      # Légère corrélation (spreads de crédit)
            duration=5.0           # Duration moyenne
        ),
        Asset(
            name="High Yield Bonds",
            category="Bonds",
            sub_category="Corporate HY",
            exp_return=0.065,
            volatility=0.13,
            beta_gdp=0.70,
            beta_inf=-0.10,
            beta_rates=-0.40,
            beta_equity=0.50,      # Forte corrélation (risque crédit ~ equity)
            duration=4.0           # Duration plus courte (spreads élevés)
        ),

        # ============================================
        # PRIVATE EQUITY (Illiquide)
        # ============================================
        Asset(
            name="LBO Fund Vintage 2024",
            category="Private Equity",
            sub_category="LBO",
            exp_return=0.13,       # ↓ plus prudent que 15%
            volatility=0.20,
            beta_gdp=1.3,          # très cyclique mais un cran sous 1.5
            beta_inf=0.25,         # ↓ un peu (inflation peut aider nominalement, pas toujours)
            beta_rates=-0.80,
            beta_equity=1.1,       # Corrélé aux marchés actions (leveraged equity)
            liquidity_lockup=5,
            exit_penalty=0.30
        ),
        Asset(
            name="Infra Green Fund",
            category="Private Equity",
            sub_category="Infrastructure",
            exp_return=0.08,
            volatility=0.10,
            beta_gdp=0.35,
            beta_inf=0.50,         # ↑ infra souvent indexée inflation
            beta_rates=-0.50,
            beta_equity=0.4,       # Moins corrélé (revenus régulés/contractuels)
            liquidity_lockup=10,
            exit_penalty=0.20
        ),
        Asset(
            name="Private Debt Senior",
            category="Private Equity",
            sub_category="Private Debt",
            exp_return=0.07,
            volatility=0.08,
            beta_gdp=0.50,
            beta_inf=-0.15,
            beta_rates=-0.50,
            beta_equity=0.35,      # Similaire aux bonds HY
            duration=3.0,          # Duration courte (floating rate souvent)
            liquidity_lockup=3,
            exit_penalty=0.10
        ),

        # ============================================
        # REAL ESTATE (Immobilier)
        # ============================================
        Asset(
            name="SCPI Bureaux Paris",
            category="Real Estate",
            sub_category="Retail Bureau",
            exp_return=0.045,
            volatility=0.04,
            beta_gdp=0.50,
            beta_inf=0.50,
            beta_rates=-0.45,
            beta_equity=0.5,       # Corrélation modérée (cyclique économie)
            liquidity_lockup=1,
            exit_penalty=0.05
        ),
        Asset(
            name="Immo Résidentiel Direct",
            category="Real Estate",
            sub_category="Résidentiel",
            exp_return=0.04,
            volatility=0.03,
            beta_gdp=0.30,         # ↓ moins cyclique que bureaux
            beta_inf=0.60,
            beta_rates=-0.60,      # ↑ plus sensible aux taux (crédit immo)
            beta_equity=0.3,       # Moins corrélé (besoin fondamental)
            liquidity_lockup=0,
            exit_penalty=0.08
        ),

        # ============================================
        # COMMODITIES & METALS
        # ============================================
        Asset(
            name="Gold Bullion",
            category="Metals",
            sub_category="Or Physique",
            exp_return=0.045,      # ↓ léger
            volatility=0.15,
            beta_gdp=-0.20,
            beta_inf=0.80,
            beta_rates=-0.35,
            beta_equity=-0.15      # Safe haven: corrélation négative en crise
        ),
        Asset(
            name="Silver",
            category="Metals",
            sub_category="Argent",
            exp_return=0.06,
            volatility=0.25,
            beta_gdp=0.20,         # ↓ un peu (mi-précieux mi-industriel)
            beta_inf=0.70,
            beta_rates=-0.20,
            beta_equity=0.25       # Mi-précieux mi-industriel => légère corrélation
        ),
        Asset(
            name="Oil ETC",
            category="Commodities",
            sub_category="Énergie",
            exp_return=0.05,
            volatility=0.30,
            beta_gdp=0.80,
            beta_inf=1.00,
            beta_rates=0.00,       # taux ~ effet indirect via PIB, pas direct
            beta_equity=0.4        # Corrélé à l'activité économique
        ),

        # ============================================
        # CRYPTO
        # ============================================
        Asset(
            name="Bitcoin",
            category="Crypto",
            sub_category="BTC",
            exp_return=0.15,       # ↓ très important (prudence)
            volatility=0.70,
            beta_gdp=0.50,
            beta_inf=0.25,         # ↓ (hedge inflation pas fiable à court terme)
            beta_rates=-0.90,      # ↑ très sensible à la liquidité/taux
            beta_equity=0.85       # Forte corrélation risk-on
        ),
        Asset(
            name="Ethereum",
            category="Crypto",
            sub_category="ETH",
            exp_return=0.20,       # ↓ important
            volatility=0.80,
            beta_gdp=0.50,
            beta_inf=0.10,         # encore plus "risk-on tech" que hedge inflation
            beta_rates=-1.00,
            beta_equity=0.90       # Très risk-on (proche tech)
        ),
    ]


# ==========================================
# PRESETS MACROÉCONOMIQUES (MODÈLE FACTORIEL)
# ==========================================

PRESETS_ADMIN = {
    "Scénario Goldilocks (Idéal)": {
        "pib": 0.03,
        "inf": 0.02,
        "rates": 0.0,
        "equity": 0.10,            # Marché actions en hausse (+10%)
        "desc": "Croissance forte, inflation stable, taux neutres. Conditions idéales."
    },
    "Choc Pétrolier (Stagflation)": {
        "pib": -0.04,
        "inf": 0.08,
        "rates": 0.05,
        "equity": -0.15,           # Marché actions en baisse (-15%)
        "desc": "Inflation record (8%), récession (-4%), taux élevés (5%). Années 1970."
    },
    "Pivot de la Fed (Baisse Taux)": {
        "pib": 0.02,
        "inf": 0.01,
        "rates": -0.03,
        "equity": 0.15,            # Rally obligataire + actions (+15%)
        "desc": "Croissance modérée, inflation maîtrisée, baisse de 300 points de base."
    },
    "Crise Financière (Type 2008)": {
        "pib": -0.06,
        "inf": -0.01,
        "rates": -0.02,
        "equity": -0.35,           # Effondrement marché actions (-35%)
        "desc": "Récession sévère (-6%), déflation (-1%), taux bas mais credit crunch."
    }
}


# ==========================================
# BIBLIOTHÈQUE DE NEWS (SYSTÈME DE JOURNAL)
# ==========================================

NEWS_LIBRARY = {
    "Scénario Goldilocks (Idéal)": [
        {
            "title": "📈 Économie robuste: +3% de croissance attendue",
            "content": "Les indicateurs économiques affichent une croissance solide de 3% portée par la consommation des ménages et l'investissement des entreprises. L'inflation reste maîtrisée autour de 2%, permettant aux banques centrales de maintenir une politique accommodante."
        },
        {
            "title": "🏭 Secteur manufacturier en pleine forme",
            "content": "Les commandes industrielles explosent avec +5% ce trimestre. Les entreprises technologiques et pharmaceutiques mènent la danse, poussées par l'innovation et une demande internationale soutenue."
        },
        {
            "title": "💼 Marché de l'emploi au beau fixe",
            "content": "Le taux de chômage atteint son plus bas niveau depuis 10 ans à 4.2%. Les salaires progressent de 2.5% en moyenne, soutenant le pouvoir d'achat sans créer de pressions inflationnistes excessives."
        }
    ],
    "Choc Pétrolier (Stagflation)": [
        {
            "title": "⛽ Flambée du pétrole: le baril dépasse 140$",
            "content": "Suite aux tensions géopolitiques au Moyen-Orient, le prix du baril de Brent bondit de 45% en 3 mois. Les analystes anticipent une inflation à 8% et un ralentissement brutal de la croissance. Les secteurs transport et logistique sont les premiers touchés."
        },
        {
            "title": "🔥 Inflation record: 8% sur un an",
            "content": "L'inflation atteint des sommets inédits depuis les années 1970, tirée par l'énergie (+30%) et l'alimentation (+12%). Les banques centrales annoncent des hausses de taux de 500 points de base pour tenter de juguler la spirale prix-salaires."
        },
        {
            "title": "📉 Récession technique: le PIB recule de 4%",
            "content": "L'économie entre officiellement en récession avec une contraction de 4% du PIB. Les entreprises réduisent leurs investissements face à la hausse des coûts et l'incertitude. Le chômage bondit à 9.5%."
        }
    ],
    "Pivot de la Fed (Baisse Taux)": [
        {
            "title": "🔔 La Fed pivote: baisse historique de 300 bps",
            "content": "Dans un revirement majeur, la Réserve Fédérale annonce une baisse de 3 points de pourcentage de ses taux directeurs. Cette décision vise à soutenir une croissance modérée de 2% et une inflation maîtrisée à 1%. Les marchés saluent cette décision accommodante."
        },
        {
            "title": "💵 Marchés obligataires en effervescence",
            "content": "Suite à l'annonce de la Fed, les rendements des obligations d'État chutent de 300 bps. Les investisseurs se ruent sur les actifs à duration longue, anticipant un environnement de taux bas durablement. Le Trésor US 10 ans passe sous 2%."
        },
        {
            "title": "🚀 Actions tech en forte hausse",
            "content": "Les valeurs technologiques à forte croissance bondissent de +15% en séance. Les taux bas réduisent le coût d'opportunité et rendent les actifs risqués plus attractifs. Le Nasdaq bat des records historiques."
        }
    ],
    "Crise Financière (Type 2008)": [
        {
            "title": "🏦 Crise bancaire: LehBank fait faillite",
            "content": "La quatrième plus grande banque d'investissement du pays dépose le bilan après des pertes massives sur produits dérivés. Les marchés plongent de -25% en 48h. Le système financier mondial vacille face à une crise de confiance sans précédent."
        },
        {
            "title": "💔 Récession sévère: -6% de PIB",
            "content": "L'économie s'effondre avec une contraction record de 6% du PIB. Les entreprises licencient massivement, le chômage explose à 12%. Le crédit se tarit complètement malgré les interventions d'urgence des banques centrales."
        },
        {
            "title": "🆘 Plans de sauvetage gouvernementaux",
            "content": "Face à l'effondrement du système bancaire, les gouvernements déploient des plans de sauvetage historiques de 2 000 milliards de dollars. Nationalisations, garanties d'État et rachats de créances toxiques tentent d'enrayer la spirale déflationniste."
        }
    ]
}


def get_news_suggestions(pib_shock, inf_shock, rates_shock):
    """
    Suggère des news appropriées selon les chocs macro.

    Args:
        pib_shock (float): Choc PIB
        inf_shock (float): Choc inflation
        rates_shock (float): Choc taux

    Returns:
        list: Liste de news suggérées (dict avec title et content)
    """
    suggestions = []

    # Déterminer le scénario le plus proche
    scenarios = {
        "Goldilocks": abs(pib_shock - 0.03) + abs(inf_shock - 0.02) + abs(rates_shock - 0.0),
        "Stagflation": abs(pib_shock + 0.04) + abs(inf_shock - 0.08) + abs(rates_shock - 0.05),
        "Pivot": abs(pib_shock - 0.02) + abs(inf_shock - 0.01) + abs(rates_shock + 0.03),
        "Crise": abs(pib_shock + 0.06) + abs(inf_shock + 0.01) + abs(rates_shock + 0.02)
    }

    closest_scenario = min(scenarios, key=scenarios.get)

    # Mapping des noms courts vers les clés NEWS_LIBRARY
    scenario_mapping = {
        "Goldilocks": "Scénario Goldilocks (Idéal)",
        "Stagflation": "Choc Pétrolier (Stagflation)",
        "Pivot": "Pivot de la Fed (Baisse Taux)",
        "Crise": "Crise Financière (Type 2008)"
    }

    scenario_key = scenario_mapping[closest_scenario]

    if scenario_key in NEWS_LIBRARY:
        suggestions = NEWS_LIBRARY[scenario_key]

    return suggestions


# ==========================================
# SCÉNARIOS MACROÉCONOMIQUES (ANCIEN MODÈLE)
# ==========================================

class MarketScenario:
    """
    Représente un scénario macroéconomique avec ses impacts.

    Attributes:
        name (str): Nom du scénario
        impact_mu (float): Ajustement sur les rendements (ex: -0.15 = -15%)
        impact_sigma (float): Multiplicateur sur les volatilités (ex: 1.5 = +50%)
        description (str): Description narrative du scénario
    """

    def __init__(self, name, impact_mu, impact_sigma, description):
        self.name = name
        self.impact_mu = impact_mu
        self.impact_sigma = impact_sigma
        self.description = description

    def __repr__(self):
        return f"Scenario({self.name}, Δμ={self.impact_mu:+.1%}, σx{self.impact_sigma})"


def get_market_scenarios():
    """
    Retourne les scénarios macroéconomiques disponibles.

    Returns:
        dict: {nom_scenario: MarketScenario}

    Notes pour l'Admin:
        - Ajustez les impacts (impact_mu, impact_sigma) selon vos hypothèses pédagogiques
        - Créez de nouveaux scénarios pour vos exercices (ex: "Stagflation", "Guerre Commerciale")
    """
    return {
        "Normale (Historique)": MarketScenario(
            name="Normale (Historique)",
            impact_mu=0.0,
            impact_sigma=1.0,
            description="Conditions de marché historiques moyennes (baseline)"
        ),

        "Crise (Type 2008)": MarketScenario(
            name="Crise (Type 2008)",
            impact_mu=-0.15,      # -15% sur les rendements espérés
            impact_sigma=1.5,     # Volatilité multipliée par 1.5
            description="Crise financière majeure : baisse des rendements, volatilité accrue"
        ),

        "Inflation Forte & Taux Hauts": MarketScenario(
            name="Inflation Forte & Taux Hauts",
            impact_mu=-0.05,      # -5% (taux réels comprimés)
            impact_sigma=1.2,     # Volatilité modérément accrue
            description="Environnement inflationniste avec hausse des taux directeurs"
        ),

        "Euphorique (Bull Market)": MarketScenario(
            name="Euphorique (Bull Market)",
            impact_mu=+0.05,      # +5% de rendements supplémentaires
            impact_sigma=0.8,     # Volatilité réduite (VIX bas)
            description="Marché haussier soutenu, euphorie des investisseurs"
        ),

        # Exemple de scénario supplémentaire (décommentez pour activer)
        # "Stagflation": MarketScenario(
        #     name="Stagflation",
        #     impact_mu=-0.10,
        #     impact_sigma=1.3,
        #     description="Croissance faible + inflation élevée (années 1970)"
        # ),
    }


def get_scenario(scenario_name):
    """
    Récupère un scénario par son nom.

    Args:
        scenario_name (str): Nom du scénario

    Returns:
        MarketScenario: Scénario correspondant

    Raises:
        KeyError: Si le scénario n'existe pas
    """
    scenarios = get_market_scenarios()
    if scenario_name not in scenarios:
        raise KeyError(f"Scénario '{scenario_name}' introuvable. Disponibles: {list(scenarios.keys())}")
    return scenarios[scenario_name]


# ==========================================
# UTILITAIRES POUR L'ADMIN
# ==========================================

def get_asset_by_name(asset_name):
    """
    Récupère un actif par son nom.

    Args:
        asset_name (str): Nom de l'actif

    Returns:
        Asset: Actif correspondant

    Raises:
        ValueError: Si l'actif n'existe pas
    """
    assets = get_available_assets()
    for asset in assets:
        if asset.name == asset_name:
            return asset
    raise ValueError(f"Actif '{asset_name}' introuvable")


def get_assets_by_category(category):
    """
    Filtre les actifs par catégorie.

    Args:
        category (str): Catégorie à filtrer (Equity, Bonds, etc.)

    Returns:
        list[Asset]: Liste des actifs de cette catégorie
    """
    assets = get_available_assets()
    return [a for a in assets if a.category == category]


def get_all_categories():
    """
    Retourne la liste unique des catégories disponibles.

    Returns:
        list[str]: Liste des catégories
    """
    assets = get_available_assets()
    return sorted(list(set(a.category for a in assets)))


# ==========================================
# FONCTIONS D'ADMINISTRATION
# ==========================================

def apply_custom_shock(assets, custom_mu_shock=0.0, custom_sigma_multiplier=1.0):
    """
    Applique un choc personnalisé à tous les actifs (pour tests/exercices).

    Args:
        assets (list[Asset]): Liste des actifs à modifier
        custom_mu_shock (float): Ajustement de rendement
        custom_sigma_multiplier (float): Multiplicateur de volatilité

    Returns:
        list[Asset]: Nouveaux actifs avec paramètres ajustés (copie profonde)
    """
    shocked_assets = []
    for a in assets:
        shocked = Asset(
            name=a.name,
            category=a.category,
            sub_category=a.sub_category,
            exp_return=a.mu + custom_mu_shock,
            volatility=a.sigma * custom_sigma_multiplier,
            liquidity_lockup=a.lockup,
            exit_penalty=a.penalty
        )
        shocked_assets.append(shocked)
    return shocked_assets


if __name__ == "__main__":
    # Tests rapides pour l'Admin
    print("=== UNIVERS D'ACTIFS ===")
    assets = get_available_assets()
    print(f"Nombre d'actifs disponibles: {len(assets)}")
    print(f"Catégories: {get_all_categories()}\n")

    print("=== SCÉNARIOS MACRO ===")
    scenarios = get_market_scenarios()
    for name, scenario in scenarios.items():
        print(f"- {scenario}")

    print("\n=== TEST FILTRAGE ===")
    equities = get_assets_by_category("Equity")
    print(f"Actifs Equity: {[a.name for a in equities]}")
