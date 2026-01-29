# -*- coding: utf-8 -*-
"""
game_engine.py - Moteur de Business Game Tour par Tour
=======================================================
Gère les sessions de jeu multi-joueurs avec simulation annuelle des rendements.

Fonctionnalités:
    - Création et gestion de sessions de jeu
    - Simulation annuelle (1 tirage par actif)
    - Arbitrages avec frais de transaction
    - Classement temps réel des étudiants
    - Snapshots de portfolios année par année
"""

import numpy as np
import random
from datetime import datetime
from typing import List, Dict, Tuple
from engine import Asset, get_smart_correlation
from market import get_scenario, get_asset_by_name, get_available_assets


# ==========================================
# MATRICE DE CORRÉLATION DES CHOCS MACRO
# ==========================================

# Corrélations entre chocs (GDP, INF, RATES, EQUITY)
MACRO_CORR = np.array([
    [1.00,  0.30, -0.20,  0.60],  # GDP: corrélé positivement avec equity
    [0.30,  1.00,  0.50,  0.00],  # INF: corrélé avec rates (BC réagit)
    [-0.20, 0.50,  1.00, -0.40],  # RATES: négatif avec GDP et equity
    [0.60,  0.00, -0.40,  1.00]   # EQUITY: fort lien avec GDP, négatif avec rates
])

# Écarts-types des chocs macro
MACRO_STDS = np.array([0.025, 0.015, 0.020, 0.15])  # GDP, INF, RATES, EQUITY


class MacroState:
    """
    État macroéconomique avec mémoire (processus AR(1)).

    Le modèle AR(1) permet:
    - Persistance: les niveaux évoluent graduellement
    - Mean-reversion: retour vers les moyennes long-terme
    - Cohérence: pas de yoyo irréaliste

    Formule: x(t) = mu + phi * (x(t-1) - mu) + shock
    """

    def __init__(self):
        """Initialise l'état macro avec les valeurs baseline."""
        # Niveaux actuels
        self.gdp_level = 0.02      # Croissance PIB (2% long-terme)
        self.inf_level = 0.02      # Inflation (2% cible BC)
        self.rates_level = 0.03   # Taux d'intérêt (3% nominal)
        self.equity_factor = 0.0  # Facteur equity (centré sur 0)

        # Moyennes long-terme (cibles de mean-reversion)
        self.mu_gdp = 0.02
        self.mu_inf = 0.02
        self.mu_rates = 0.03
        self.mu_equity = 0.0

        # Paramètres de persistance AR(1) (phi entre 0 et 1)
        # phi proche de 1 = très persistant, phi proche de 0 = mean-revert vite
        self.phi_gdp = 0.50      # GDP mean-revert modérément
        self.phi_inf = 0.60      # Inflation plus persistante
        self.phi_rates = 0.80    # Taux très inertes (BC prudente)
        self.phi_equity = 0.30   # Equity mean-revert rapidement

    def update(self, shock_gdp, shock_inf, shock_rates, shock_equity):
        """
        Met à jour l'état macro avec les chocs et retourne les deltas.

        Args:
            shock_gdp (float): Choc sur le PIB
            shock_inf (float): Choc sur l'inflation
            shock_rates (float): Choc sur les taux
            shock_equity (float): Choc sur le facteur equity

        Returns:
            dict: {
                'delta_gdp': variation du PIB par rapport à la moyenne,
                'delta_inf': variation de l'inflation par rapport à la moyenne,
                'delta_rates': variation absolue des taux (pour duration),
                'equity_shock': choc equity direct
            }
        """
        # Sauvegarder ancien niveau des taux pour calculer la variation
        old_rates = self.rates_level

        # Mise à jour AR(1): x(t) = mu + phi * (x(t-1) - mu) + shock
        new_gdp = self.mu_gdp + self.phi_gdp * (self.gdp_level - self.mu_gdp) + shock_gdp
        new_inf = self.mu_inf + self.phi_inf * (self.inf_level - self.mu_inf) + shock_inf
        new_rates = self.mu_rates + self.phi_rates * (self.rates_level - self.mu_rates) + shock_rates
        new_equity = self.mu_equity + self.phi_equity * self.equity_factor + shock_equity

        # Calculer les deltas (ce qu'on passe aux betas des actifs)
        delta_gdp = new_gdp - self.mu_gdp      # Écart par rapport à la moyenne
        delta_inf = new_inf - self.mu_inf      # Écart par rapport à la cible
        delta_rates = new_rates - old_rates    # Variation absolue des taux (pour duration!)
        equity_shock = new_equity              # Facteur equity direct

        # Mettre à jour l'état interne
        self.gdp_level = new_gdp
        self.inf_level = new_inf
        self.rates_level = new_rates
        self.equity_factor = new_equity

        return {
            'delta_gdp': delta_gdp,
            'delta_inf': delta_inf,
            'delta_rates': delta_rates,
            'equity_shock': equity_shock
        }

    def reset(self):
        """Remet l'état macro aux valeurs initiales."""
        self.gdp_level = self.mu_gdp
        self.inf_level = self.mu_inf
        self.rates_level = self.mu_rates
        self.equity_factor = self.mu_equity

    def to_dict(self):
        """Sérialise l'état pour persistance."""
        return {
            'gdp_level': self.gdp_level,
            'inf_level': self.inf_level,
            'rates_level': self.rates_level,
            'equity_factor': self.equity_factor
        }

    @classmethod
    def from_dict(cls, data):
        """Restaure l'état depuis un dictionnaire."""
        state = cls()
        if data:
            state.gdp_level = data.get('gdp_level', state.mu_gdp)
            state.inf_level = data.get('inf_level', state.mu_inf)
            state.rates_level = data.get('rates_level', state.mu_rates)
            state.equity_factor = data.get('equity_factor', state.mu_equity)
        return state


def generate_correlated_shocks():
    """
    Génère des chocs macro corrélés de manière réaliste.

    Utilise la décomposition de Cholesky pour créer des chocs
    qui respectent la matrice de corrélation MACRO_CORR.

    Returns:
        dict: {shock_gdp, shock_inf, shock_rates, shock_equity}
    """
    # Décomposition de Cholesky
    L = np.linalg.cholesky(MACRO_CORR)

    # Tirer 4 normales indépendantes
    Z_indep = np.random.standard_normal(4)

    # Appliquer corrélation
    Z_corr = L @ Z_indep

    # Appliquer les écarts-types
    shocks = Z_corr * MACRO_STDS

    return {
        'shock_gdp': shocks[0],
        'shock_inf': shocks[1],
        'shock_rates': shocks[2],
        'shock_equity': shocks[3]
    }


class StudentPortfolio:
    """
    Représente le portefeuille d'un étudiant dans une session de jeu.
    """

    def __init__(self, username, initial_capital=100000):
        """
        Initialise un portfolio étudiant.

        Args:
            username (str): Nom de l'étudiant
            initial_capital (float): Capital de départ
        """
        self.username = username
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.positions = {}  # {asset_name: amount_in_euros}
        self.total_fees_paid = 0
        self.history = []  # Historique des valeurs par année
        self.bankruptcy_count = 0  # Nombre de faillites

    def get_total_value(self):
        """Calcule la valeur totale du portefeuille (capital + positions)."""
        return self.current_capital + sum(self.positions.values())

    def get_performance(self):
        """Calcule la performance depuis le début (%)."""
        return ((self.get_total_value() / self.initial_capital) - 1) * 100

    def get_allocation(self):
        """
        Retourne l'allocation en pourcentage.

        Returns:
            dict: {asset_name: percentage}
        """
        total = self.get_total_value()
        if total == 0:
            return {}

        allocation = {}
        for asset_name, amount in self.positions.items():
            allocation[asset_name] = (amount / total) * 100

        # Ajouter le cash
        if self.current_capital > 0:
            allocation['Cash'] = (self.current_capital / total) * 100

        return allocation

    def apply_returns(self, asset_returns):
        """
        Applique les rendements annuels aux positions.

        Args:
            asset_returns (dict): {asset_name: annual_return_percentage}
        """
        for asset_name, amount in list(self.positions.items()):
            if asset_name in asset_returns:
                return_pct = asset_returns[asset_name]
                new_amount = amount * (1 + return_pct)

                # Si la position devient nulle ou négative, la supprimer
                if new_amount <= 0.01:
                    del self.positions[asset_name]
                else:
                    self.positions[asset_name] = new_amount

    def check_bankruptcy(self):
        """
        Vérifie si l'étudiant est en faillite (capital total <= 0).
        Si oui, donne 10k€ de secours et incrémente le compteur de faillites.

        Returns:
            bool: True si une faillite a été détectée
        """
        total_value = self.get_total_value()

        if total_value <= 0:
            # Faillite détectée!
            self.bankruptcy_count += 1
            self.current_capital = 10000  # Renflouement de 10k€
            self.positions = {}  # Liquidation de toutes les positions
            return True

        return False

    def execute_transaction(self, asset_name, action, amount, fee_percentage):
        """
        Exécute une transaction (achat/vente) avec frais.

        Args:
            asset_name (str): Nom de l'actif
            action (str): 'buy' ou 'sell'
            amount (float): Montant en euros
            fee_percentage (float): Frais en % (ex: 0.01 pour 1%)

        Returns:
            bool: True si succès, False si échec (fonds insuffisants)
        """
        fees = amount * fee_percentage

        if action == 'buy':
            total_cost = amount + fees
            if self.current_capital < total_cost:
                return False  # Fonds insuffisants

            self.current_capital -= total_cost
            self.positions[asset_name] = self.positions.get(asset_name, 0) + amount
            self.total_fees_paid += fees

        elif action == 'sell':
            if self.positions.get(asset_name, 0) < amount:
                return False  # Position insuffisante

            net_proceeds = amount - fees
            self.positions[asset_name] -= amount
            self.current_capital += net_proceeds
            self.total_fees_paid += fees

            # Nettoyer les positions vides
            if self.positions[asset_name] <= 0.01:
                del self.positions[asset_name]

        return True

    def snapshot(self, year, snapshot_type='simulation'):
        """
        Crée un snapshot du portfolio pour l'historique.

        Args:
            year (int): Année du snapshot
            snapshot_type (str): 'simulation' ou 'arbitrage'

        Returns:
            dict: Snapshot du portfolio
        """
        return {
            'year': year,
            'total_value': self.get_total_value(),
            'current_capital': self.current_capital,
            'positions': dict(self.positions),
            'allocation': self.get_allocation(),
            'performance': self.get_performance(),
            'total_fees_paid': self.total_fees_paid,
            'bankruptcies': self.bankruptcy_count,
            'snapshot_type': snapshot_type,
            'timestamp': datetime.now().isoformat()
        }


class GameSession:
    """
    Gère une session de jeu multi-joueurs.
    """

    def __init__(self, session_id, session_name, admin_username, initial_capital=100000):
        """
        Initialise une session de jeu.

        Args:
            session_id (str): Identifiant unique de la session
            session_name (str): Nom de la session
            admin_username (str): Nom de l'admin
            initial_capital (float): Capital de départ pour chaque étudiant
        """
        self.session_id = session_id
        self.session_name = session_name
        self.admin_username = admin_username
        self.initial_capital = initial_capital
        self.current_year = 0
        self.status = 'waiting'  # waiting, active, ended
        self.students = {}  # {username: StudentPortfolio}
        self.year_history = []  # Historique des simulations
        self.trading_fees = {}  # {asset_name: fee_percentage}
        self.created_at = datetime.now()

        # État macroéconomique avec mémoire AR(1)
        self.macro_state = MacroState()

        # Actifs disponibles pour cette session (par défaut tous)
        all_assets = get_available_assets()
        self.available_asset_names = [asset.name for asset in all_assets]

        # Frais par défaut
        self._init_default_fees()

    def _init_default_fees(self):
        """Initialise les frais de transaction par défaut."""
        self.trading_fees = {
            'ETF World (MSCI)': 0.005,  # 0.5%
            'ETF Europe': 0.005,
            'ETF USA (S&P500)': 0.005,
            'Gov Bonds US (10Y)': 0.003,  # 0.3%
            'Corp Bonds EUR (IG)': 0.004,
            'Private Equity Fund': 0.02,  # 2%
            'REIT (Bureaux Paris)': 0.015,  # 1.5%
            'SCPI Résidentiel': 0.015,
            'Gold (ETF)': 0.007,  # 0.7%
            'Silver (ETF)': 0.008,
            'Oil (WTI Futures)': 0.01,  # 1%
            'Wheat (Futures)': 0.01,
            'Bitcoin': 0.015,  # 1.5%
            'Ethereum': 0.015,
        }

    def add_student(self, username):
        """
        Ajoute un étudiant à la session.

        Args:
            username (str): Nom de l'étudiant
        """
        if username not in self.students:
            self.students[username] = StudentPortfolio(username, self.initial_capital)

    def start_game(self):
        """Lance le jeu (passe en mode actif)."""
        if len(self.students) > 0:
            self.status = 'active'
            self.current_year = 0

    def end_game(self):
        """Termine le jeu."""
        self.status = 'ended'

    def simulate_year(self, pib_shock, inf_shock, rates_shock, equity_shock=0.0, scenario_label="Custom"):
        """
        Simule une année complète avec les chocs macroéconomiques (MODÈLE FACTORIEL + AR(1)).
        Simule TOUS les actifs disponibles (pas seulement ceux détenus).

        Le modèle utilise:
        - Processus AR(1) pour la persistance macro
        - Duration pour le pricing des obligations
        - Facteur equity global pour synchroniser les actions

        Args:
            pib_shock (float): Choc PIB (ex: 0.03 pour +3%, -0.04 pour -4%)
            inf_shock (float): Choc inflation (ex: 0.08 pour +8%)
            rates_shock (float): Choc taux (ex: 0.05 pour +5%, -0.03 pour -3%)
            equity_shock (float): Choc marché actions global (ex: 0.10 pour +10%, -0.35 pour -35%)
            scenario_label (str): Label descriptif du scénario (pour l'historique)

        Returns:
            dict: {asset_name: annual_return}
        """
        # Mettre à jour l'état macro avec AR(1) et obtenir les deltas
        macro_deltas = self.macro_state.update(
            shock_gdp=pib_shock,
            shock_inf=inf_shock,
            shock_rates=rates_shock,
            shock_equity=equity_shock
        )

        # Récupérer TOUS les actifs disponibles dans le marché
        all_assets = get_available_assets()
        all_asset_names = [asset.name for asset in all_assets]

        # Simuler les rendements pour TOUS les actifs avec le MODÈLE FACTORIEL
        asset_returns = simulate_annual_returns(
            all_asset_names,
            macro_deltas=macro_deltas,
            macro_state=self.macro_state
        )

        # Appliquer les rendements à tous les portfolios
        for student in self.students.values():
            student.apply_returns(asset_returns)

            # Vérifier faillite et renflouer si nécessaire
            student.check_bankruptcy()

            student.history.append(student.snapshot(self.current_year))

        # Sauvegarder dans l'historique (incluant l'état macro)
        self.year_history.append({
            'year': self.current_year,
            'scenario': scenario_label,
            'pib_shock': pib_shock,
            'inf_shock': inf_shock,
            'rates_shock': rates_shock,
            'equity_shock': equity_shock,
            'macro_state': self.macro_state.to_dict(),
            'macro_deltas': macro_deltas,
            'asset_returns': asset_returns,
            'timestamp': datetime.now().isoformat()
        })

        # Incrémenter l'année
        self.current_year += 1

        return asset_returns

    def get_leaderboard(self):
        """
        Génère le classement des étudiants.

        Returns:
            list: Liste triée de dicts avec infos étudiants
        """
        leaderboard = []
        for username, portfolio in self.students.items():
            leaderboard.append({
                'username': username,
                'total_value': portfolio.get_total_value(),
                'performance': portfolio.get_performance(),
                'fees_paid': portfolio.total_fees_paid,
                'bankruptcies': portfolio.bankruptcy_count
            })

        # Trier par valeur totale décroissante
        leaderboard.sort(key=lambda x: x['total_value'], reverse=True)

        # Ajouter les rangs
        for i, entry in enumerate(leaderboard):
            entry['rank'] = i + 1

        return leaderboard

    def get_student_portfolio(self, username):
        """Retourne le portfolio d'un étudiant."""
        return self.students.get(username)

    def set_trading_fee(self, asset_name, fee_percentage):
        """
        Définit les frais de transaction pour un actif.

        Args:
            asset_name (str): Nom de l'actif
            fee_percentage (float): Frais en décimal (0.01 = 1%)
        """
        self.trading_fees[asset_name] = fee_percentage

    def get_trading_fee(self, asset_name):
        """Retourne les frais de transaction pour un actif."""
        return self.trading_fees.get(asset_name, 0.01)  # 1% par défaut

    def set_available_assets(self, asset_names):
        """
        Définit la liste des actifs disponibles pour cette session.

        Args:
            asset_names (list): Liste des noms d'actifs disponibles
        """
        self.available_asset_names = asset_names

    def get_available_assets(self):
        """
        Retourne la liste des objets Asset disponibles pour cette session.

        Returns:
            list: Liste des Asset disponibles
        """
        all_assets = get_available_assets()
        return [asset for asset in all_assets if asset.name in self.available_asset_names]

    def is_asset_available(self, asset_name):
        """
        Vérifie si un actif est disponible dans cette session.

        Args:
            asset_name (str): Nom de l'actif

        Returns:
            bool: True si l'actif est disponible
        """
        return asset_name in self.available_asset_names


def simulate_annual_returns(asset_names, macro_deltas=None, macro_state=None):
    """
    Simule les rendements annuels pour une liste d'actifs avec le MODÈLE FACTORIEL COHÉRENT.

    Formules:
        - Actifs standards:
            Return = E[R] + (beta_GDP × delta_gdp) + (beta_INF × delta_inf)
                   + (beta_RATES × delta_rates) + (beta_EQUITY × equity_shock) + bruit

        - Obligations (avec duration):
            Return = yield + duration_effect + spread_component + bruit
            où duration_effect = -duration × delta_rates

    Les rendements sont bornés entre -90% et +300% pour éviter les cas extrêmes.

    Args:
        asset_names (list): Liste des noms d'actifs
        macro_deltas (dict): {delta_gdp, delta_inf, delta_rates, equity_shock}
        macro_state (MacroState): État macro actuel (pour yield des bonds)

    Returns:
        dict: {asset_name: annual_return_as_decimal}
    """
    if not asset_names:
        return {}

    # Valeurs par défaut si pas de macro_deltas
    if macro_deltas is None:
        macro_deltas = {
            'delta_gdp': 0.0,
            'delta_inf': 0.0,
            'delta_rates': 0.0,
            'equity_shock': 0.0
        }

    # Récupérer les objets Asset
    assets = []
    for name in asset_names:
        try:
            asset = get_asset_by_name(name)
            assets.append(asset)
        except ValueError:
            # Actif inconnu, on skip
            continue

    if not assets:
        return {}

    n = len(assets)

    # Construire la matrice de corrélation pour le bruit résiduel
    corr_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            corr_matrix[i, j] = get_smart_correlation(assets[i], assets[j])

    # Décomposition de Cholesky
    try:
        L = np.linalg.cholesky(corr_matrix)
    except np.linalg.LinAlgError:
        # Matrice non définie positive, utiliser corrélation diagonale
        L = np.eye(n)

    # Générer des variables aléatoires indépendantes pour le bruit
    Z = np.random.standard_normal(n)

    # Appliquer la corrélation au bruit
    Z_correlated = L @ Z

    # Extraire les deltas
    delta_gdp = macro_deltas['delta_gdp']
    delta_inf = macro_deltas['delta_inf']
    delta_rates = macro_deltas['delta_rates']
    equity_shock = macro_deltas['equity_shock']

    # Calculer les rendements annuels avec le MODÈLE FACTORIEL
    returns = {}
    for i, asset in enumerate(assets):
        # Bruit idiosyncratique corrélé
        noise = asset.sigma * Z_correlated[i]

        # TRAITEMENT SPÉCIAL: Obligations avec duration
        if asset.category == "Bonds" and asset.duration > 0:
            # Formule mécanique: return = yield + duration_effect + spread + noise
            # duration_effect = -duration × Δrates (hausse des taux → baisse du prix)

            # Yield component: le taux de rendement courant
            if macro_state:
                yield_component = macro_state.rates_level
            else:
                yield_component = asset.mu  # Fallback

            # Duration effect: impact mécanique des variations de taux
            duration_effect = -asset.duration * delta_rates

            # Spread component: impact du risque crédit (lié au GDP)
            spread_component = asset.beta_gdp * delta_gdp

            # Effet equity pour les bonds HY (corrélé au marché)
            equity_effect = asset.beta_equity * equity_shock

            # Rendement total pour obligation
            annual_return = yield_component + duration_effect + spread_component + equity_effect + noise

        else:
            # TRAITEMENT STANDARD: Actions, Crypto, Commodities, etc.
            # Formule: E[R] + beta impacts + noise

            # Impact macro via les betas
            macro_impact = (
                asset.beta_gdp * delta_gdp +
                asset.beta_inf * delta_inf +
                asset.beta_rates * delta_rates +
                asset.beta_equity * equity_shock
            )

            # Rendement total = E[R] + impact macro + bruit
            annual_return = asset.mu + macro_impact + noise

        # BORNER les rendements pour éviter les cas extrêmes
        # Min: -90% (perte maximale), Max: +300% (gain exceptionnel)
        annual_return = max(-0.90, min(3.0, annual_return))

        returns[asset.name] = annual_return

    return returns


def estimate_transaction_fees(portfolio, transactions, session):
    """
    Estime les frais totaux pour une liste de transactions.

    Args:
        portfolio (StudentPortfolio): Portfolio de l'étudiant
        transactions (list): Liste de {'asset_name': str, 'action': 'buy'/'sell', 'amount': float}
        session (GameSession): Session de jeu

    Returns:
        float: Frais totaux estimés
    """
    total_fees = 0
    for tx in transactions:
        asset_name = tx['asset_name']
        amount = tx['amount']
        fee_pct = session.get_trading_fee(asset_name)
        total_fees += amount * fee_pct

    return total_fees


# ==========================================
# TESTS
# ==========================================

if __name__ == "__main__":
    print("=== TEST GAME ENGINE ===\n")

    # Créer une session
    session = GameSession(
        session_id="FINEVA_2025_S1",
        session_name="Fineva Spring 2025",
        admin_username="prof_martin",
        initial_capital=100000
    )
    print(f"[OK] Session creee: {session.session_name}")

    # Ajouter des étudiants
    session.add_student("alice")
    session.add_student("bob")
    session.add_student("charlie")
    print(f"[OK] 3 etudiants ajoutes")

    # Démarrer le jeu
    session.start_game()
    print(f"[OK] Jeu demarre - Status: {session.status}")

    # Les étudiants achètent des actifs (année 0)
    alice = session.get_student_portfolio("alice")
    alice.execute_transaction("ETF World (MSCI)", "buy", 50000, session.get_trading_fee("ETF World (MSCI)"))
    alice.execute_transaction("Gov Bonds US (10Y)", "buy", 30000, session.get_trading_fee("Gov Bonds US (10Y)"))
    print(f"[OK] Alice a investi - Cash restant: {alice.current_capital:.2f}€")

    bob = session.get_student_portfolio("bob")
    bob.execute_transaction("ETF World (MSCI)", "buy", 40000, session.get_trading_fee("ETF World (MSCI)"))
    bob.execute_transaction("Gold (ETF)", "buy", 40000, session.get_trading_fee("Gold (ETF)"))
    print(f"[OK] Bob a investi - Cash restant: {bob.current_capital:.2f}€")

    charlie = session.get_student_portfolio("charlie")
    charlie.execute_transaction("Bitcoin", "buy", 70000, session.get_trading_fee("Bitcoin"))
    print(f"[OK] Charlie a investi - Cash restant: {charlie.current_capital:.2f}€")

    # Simuler année 1 (scénario normal)
    print("\n--- SIMULATION ANNEE 1 (Scenario Normal) ---")
    returns_y1 = session.simulate_year("Normale (Historique)")
    print("Rendements generes:")
    for asset_name, ret in returns_y1.items():
        print(f"  • {asset_name}: {ret*100:.2f}%")

    # Afficher classement
    print("\nClassement apres annee 1:")
    leaderboard = session.get_leaderboard()
    for entry in leaderboard:
        print(f"  {entry['rank']}. {entry['username']}: {entry['total_value']:.2f}€ ({entry['performance']:+.2f}%)")

    # Simuler année 2 (scénario crise)
    print("\n--- SIMULATION ANNEE 2 (Scenario Crise) ---")
    returns_y2 = session.simulate_year("Crise (Type 2008)")
    print("Rendements generes:")
    for asset_name, ret in returns_y2.items():
        print(f"  • {asset_name}: {ret*100:.2f}%")

    # Afficher classement final
    print("\nClassement apres annee 2:")
    leaderboard = session.get_leaderboard()
    for entry in leaderboard:
        print(f"  {entry['rank']}. {entry['username']}: {entry['total_value']:.2f}€ ({entry['performance']:+.2f}%)")

    print("\n=== TEST TERMINE ===")
