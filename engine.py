# -*- coding: utf-8 -*-
"""
engine.py - Moteur de Simulation Monte Carlo
=============================================
Contient la logique mathématique pure pour simuler les trajectoires de portefeuille.
Séparé de l'interface pour permettre les tests unitaires et la réutilisation.
"""

import numpy as np


class Asset:
    """
    Représente un actif financier avec ses caractéristiques de risque/rendement.

    Attributes:
        name (str): Nom de l'actif
        category (str): Catégorie principale (Equity, Bonds, Private Equity, etc.)
        sub_category (str): Sous-catégorie détaillée
        mu (float): Rendement espéré annuel (ex: 0.07 pour 7%)
        sigma (float): Volatilité annuelle (ex: 0.15 pour 15%)
        beta_gdp (float): Sensibilité au choc PIB (ex: 1.0 = 100% d'exposition)
        beta_inf (float): Sensibilité au choc d'inflation (ex: 0.2)
        beta_rates (float): Sensibilité au choc de taux (ex: -0.4)
        lockup (int): Période de blocage en années (0 = liquide)
        penalty (float): Pénalité de sortie anticipée (ex: 0.20 pour 20%)
    """

    def __init__(self, name, category, sub_category, exp_return, volatility,
                 beta_gdp=0.0, beta_inf=0.0, beta_rates=0.0, beta_equity=0.0,
                 duration=0.0, liquidity_lockup=0, exit_penalty=0.0):
        self.name = name
        self.category = category
        self.sub_category = sub_category
        self.mu = exp_return
        self.sigma = volatility
        self.beta_gdp = beta_gdp      # Sensibilité au PIB
        self.beta_inf = beta_inf      # Sensibilité à l'inflation
        self.beta_rates = beta_rates  # Sensibilité aux taux d'intérêt
        self.beta_equity = beta_equity  # Sensibilité au facteur equity market global
        self.duration = duration      # Duration (pour obligations)
        self.lockup = liquidity_lockup
        self.penalty = exit_penalty

    def __repr__(self):
        return f"Asset({self.name}, {self.category}, μ={self.mu:.1%}, σ={self.sigma:.1%})"


def get_smart_correlation(asset1, asset2):
    """
    Calcule la corrélation heuristique entre deux actifs.

    Utilise des règles métier basées sur les catégories d'actifs pour estimer
    les corrélations cross-asset de manière réaliste.

    Args:
        asset1 (Asset): Premier actif
        asset2 (Asset): Second actif

    Returns:
        float: Coefficient de corrélation entre -1 et 1

    Règles de corrélation:
        - Même actif: 1.0
        - Même catégorie: 0.8 (forte corrélation)
        - Equity vs Bonds: 0.1 (diversification)
        - Equity vs Crypto: 0.6 (corrélation moyenne-haute)
        - Equity vs Private Equity: 0.7 (très corrélé mais lissé)
        - Défaut: 0.3 (bruit de fond)
    """
    cat1, cat2 = asset1.category, asset2.category

    # 1. Identité
    if asset1.name == asset2.name:
        return 1.0

    # 2. Même catégorie
    if cat1 == cat2:
        return 0.8

    # 3. Règles Cross-Asset
    if (cat1 == "Crypto" and cat2 == "Equity") or (cat1 == "Equity" and cat2 == "Crypto"):
        return 0.6

    if (cat1 == "Bonds" and cat2 == "Equity") or (cat1 == "Equity" and cat2 == "Bonds"):
        return 0.1  # Diversification classique

    if (cat1 == "Private Equity" and cat2 == "Equity") or (cat1 == "Equity" and cat2 == "Private Equity"):
        return 0.7

    # 4. Défaut
    return 0.3


def build_covariance_matrix(assets, scenario_impact_mu=0.0, scenario_impact_sigma=1.0):
    """
    Construit la matrice de covariance pour un portefeuille d'actifs.

    Args:
        assets (list[Asset]): Liste des actifs du portefeuille
        scenario_impact_mu (float): Ajustement de rendement (ex: -0.15 pour crise)
        scenario_impact_sigma (float): Multiplicateur de volatilité (ex: 1.5 pour crise)

    Returns:
        tuple: (mu_adjusted, sigma_adjusted, cov_matrix, corr_matrix)
    """
    n_assets = len(assets)

    # Application du scénario macro
    mu = np.array([a.mu + scenario_impact_mu for a in assets])
    sigma = np.array([a.sigma * scenario_impact_sigma for a in assets])

    # Construction de la matrice de corrélation
    corr_matrix = np.zeros((n_assets, n_assets))
    for i in range(n_assets):
        for j in range(n_assets):
            corr_matrix[i, j] = get_smart_correlation(assets[i], assets[j])

    # Construction de la matrice de covariance
    # Cov(i,j) = Corr(i,j) * σ_i * σ_j
    cov_matrix = np.zeros((n_assets, n_assets))
    for i in range(n_assets):
        for j in range(n_assets):
            cov_matrix[i, j] = corr_matrix[i, j] * sigma[i] * sigma[j]

    return mu, sigma, cov_matrix, corr_matrix


def run_monte_carlo(portfolio, years=10, n_simulations=1000,
                    scenario_impact_mu=0.0, scenario_impact_sigma=1.0,
                    life_events=None):
    """
    Lance une simulation Monte Carlo sur un portefeuille multi-actifs.

    Utilise un Mouvement Brownien Géométrique multivarié avec décomposition
    de Cholesky pour capturer les corrélations entre actifs.

    Args:
        portfolio (list[dict]): Liste de {'asset': Asset, 'amount': float}
        years (int): Horizon de simulation en années
        n_simulations (int): Nombre de trajectoires à générer
        scenario_impact_mu (float): Ajustement macro sur les rendements
        scenario_impact_sigma (float): Multiplicateur macro sur les volatilités
        life_events (dict): Dictionnaire {année: flux_cash} pour projets de vie

    Returns:
        tuple: (portfolio_sims, liquid_sims)
            - portfolio_sims (np.array): Valeurs brutes [n_simulations, years+1]
            - liquid_sims (np.array): Valeurs liquidatives nettes [n_simulations, years+1]

    Formule du GBM:
        S(t+1) = S(t) * exp((μ - 0.5σ²)Δt + σ√Δt * Z)
        où Z ~ N(0, 1) avec corrélations appliquées via Cholesky
    """
    if not portfolio:
        return None, None

    # A. Préparation des données
    assets = [item['asset'] for item in portfolio]
    weights = np.array([item['amount'] for item in portfolio])
    start_value = weights.sum()
    weights = weights / start_value  # Normalisation en poids

    n_assets = len(assets)

    # B. Construction de la matrice de covariance avec scénario macro
    mu, sigma, cov_matrix, corr_matrix = build_covariance_matrix(
        assets, scenario_impact_mu, scenario_impact_sigma
    )

    # C. Décomposition de Cholesky pour la corrélation
    # On utilise la matrice de corrélation (pas covariance) pour le tirage
    L = np.linalg.cholesky(corr_matrix)

    # D. Initialisation des tableaux de résultats
    portfolio_sims = np.zeros((n_simulations, years + 1))
    portfolio_sims[:, 0] = start_value

    liquid_sims = np.zeros((n_simulations, years + 1))
    # Valeur liquidative initiale (si on sort immédiatement)
    initial_penalty = sum(w * a.penalty for w, a in zip(weights, assets))
    liquid_sims[:, 0] = start_value * (1 - initial_penalty)

    dt = 1  # Pas de temps annuel

    # E. Simulation Monte Carlo
    for t in range(1, years + 1):
        # 1. Générer des aléas non corrélés Z ~ N(0, 1)
        Z_uncorrelated = np.random.normal(0, 1, (n_simulations, n_assets))

        # 2. Appliquer la corrélation via Cholesky: Z_corr = Z @ L^T
        Z_correlated = Z_uncorrelated @ L.T

        # 3. Calculer les rendements de chaque actif (GBM)
        # R_i = exp((μ_i - 0.5σ_i²)Δt + σ_i√Δt * Z_i)
        asset_returns = np.exp(
            (mu - 0.5 * sigma**2) * dt +
            sigma * Z_correlated * np.sqrt(dt)
        )

        # 4. Rendement global du portefeuille (somme pondérée)
        port_return = (asset_returns * weights).sum(axis=1)

        # 5. Mise à jour de la valeur avec flux de trésorerie
        prev_value = portfolio_sims[:, t-1]
        cash_flow_this_year = life_events.get(t, 0) if life_events else 0

        # Nouvelle valeur = (Ancienne valeur * Rendement) + Flux
        new_value = prev_value * port_return + cash_flow_this_year

        # Barrière de ruine : pas de patrimoine négatif
        new_value[new_value < 0] = 0

        portfolio_sims[:, t] = new_value

        # 6. Calcul de la valeur liquidative (si sortie à cette année)
        # On applique les pénalités pour les actifs encore bloqués
        penalty_factor = 0
        for idx, asset in enumerate(assets):
            if t < asset.lockup:
                penalty_factor += weights[idx] * asset.penalty

        liquid_sims[:, t] = portfolio_sims[:, t] * (1 - penalty_factor)

    return portfolio_sims, liquid_sims


def compute_statistics(raw_values, liquid_values, percentiles=[5, 50, 95]):
    """
    Calcule les statistiques clés sur les résultats de simulation.

    Args:
        raw_values (np.array): Valeurs brutes [n_simulations, years+1]
        liquid_values (np.array): Valeurs liquidatives [n_simulations, years+1]
        percentiles (list): Liste des percentiles à calculer

    Returns:
        dict: Statistiques par horizon et percentile
    """
    final_values = raw_values[:, -1]

    stats = {
        'final_values': final_values,
        'percentiles': {},
        'mean': np.mean(final_values),
        'std': np.std(final_values),
        'median_path': np.median(raw_values, axis=0),
        'median_liquid_path': np.median(liquid_values, axis=0),
    }

    for p in percentiles:
        stats['percentiles'][p] = np.percentile(final_values, p)
        stats[f'path_p{p}'] = np.percentile(raw_values, p, axis=0)

    return stats
