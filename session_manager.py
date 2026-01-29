# -*- coding: utf-8 -*-
"""
session_manager.py - Gestion des Sessions Multi-Utilisateurs
=============================================================
Gère la persistance des portefeuilles des élèves et les décisions de l'Admin
via une base de données SQLite simple.

Fonctionnalités:
    - Stockage des allocations par utilisateur
    - Historique des décisions
    - Partage de paramètres macro par l'Admin
    - Export/Import de sessions
"""

import sqlite3
import json
import os
import hashlib
from datetime import datetime
from contextlib import contextmanager


class SessionManager:
    """
    Gestionnaire de sessions pour environnement multi-utilisateurs.

    Utilise SQLite pour stocker:
        - Profils utilisateurs
        - Allocations de portefeuille
        - Paramètres de simulation
        - Résultats de simulations
    """

    def __init__(self, db_path="fineva_sessions.db"):
        """
        Initialise le gestionnaire de sessions.

        Args:
            db_path (str): Chemin vers le fichier SQLite
        """
        self.db_path = db_path
        self._init_database()

    @staticmethod
    def _hash_password(password):
        """
        Hash un mot de passe avec SHA256 + salt.

        Args:
            password (str): Mot de passe en clair

        Returns:
            str: Hash hexadécimal
        """
        # Simple hash avec salt statique (pour MVP, utiliser bcrypt en prod)
        salt = "fineva_secure_salt_2025"
        return hashlib.sha256((password + salt).encode()).hexdigest()

    @staticmethod
    def verify_password(password, password_hash):
        """
        Vérifie un mot de passe contre son hash.

        Args:
            password (str): Mot de passe en clair
            password_hash (str): Hash stocké

        Returns:
            bool: True si le mot de passe correspond
        """
        return SessionManager._hash_password(password) == password_hash

    @contextmanager
    def get_connection(self):
        """Context manager pour gérer les connexions SQLite proprement."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Permet l'accès par nom de colonne
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_database(self):
        """Crée les tables nécessaires si elles n'existent pas."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Migration: vérifier si la colonne password_hash existe
            cursor.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]

            if columns and 'password_hash' not in columns:
                # Migration nécessaire: supprimer et recréer la table users
                print("[MIGRATION] Mise à jour du schéma de la table users...")
                cursor.execute("DROP TABLE IF EXISTS users")
                cursor.execute("DROP TABLE IF EXISTS portfolios")
                cursor.execute("DROP TABLE IF EXISTS simulation_params")
                cursor.execute("DROP TABLE IF EXISTS simulation_results")
                print("[MIGRATION] Tables recréées avec support des mots de passe")

            # Table des utilisateurs (élèves)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'student',  -- 'student' ou 'admin'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)

            # Table des portefeuilles
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolios (
                    portfolio_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    portfolio_name TEXT DEFAULT 'Mon Portefeuille',
                    portfolio_data TEXT NOT NULL,  -- JSON: [{'asset_name': str, 'amount': float}]
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Table des paramètres de simulation
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulation_params (
                    param_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    scenario_name TEXT NOT NULL,
                    years INTEGER DEFAULT 10,
                    n_simulations INTEGER DEFAULT 1000,
                    life_events TEXT,  -- JSON: {year: cash_flow}
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Table des résultats (optionnel, pour historique)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS simulation_results (
                    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    portfolio_id INTEGER NOT NULL,
                    param_id INTEGER NOT NULL,
                    median_final REAL,
                    pessimist_final REAL,
                    optimist_final REAL,
                    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id),
                    FOREIGN KEY (param_id) REFERENCES simulation_params(param_id)
                )
            """)

            # Table des configurations Admin (partagées à tous)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_config (
                    config_key TEXT PRIMARY KEY,
                    config_value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ==========================================
            # TABLES POUR LE BUSINESS GAME
            # ==========================================

            # Table des sessions de jeu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS game_sessions (
                    session_id TEXT PRIMARY KEY,
                    session_name TEXT NOT NULL,
                    admin_user_id INTEGER NOT NULL,
                    current_year INTEGER DEFAULT 0,
                    initial_capital REAL DEFAULT 100000,
                    status TEXT DEFAULT 'waiting',  -- waiting, active, ended
                    available_assets_json TEXT,  -- JSON: liste des actifs disponibles
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (admin_user_id) REFERENCES users(user_id)
                )
            """)

            # Migration: ajouter available_assets_json si manquant
            cursor.execute("PRAGMA table_info(game_sessions)")
            game_columns = [row[1] for row in cursor.fetchall()]

            if game_columns and 'available_assets_json' not in game_columns:
                cursor.execute("ALTER TABLE game_sessions ADD COLUMN available_assets_json TEXT")
                print("[MIGRATION] Colonne 'available_assets_json' ajoutée à game_sessions")

            # Migration: ajouter macro_state_json pour AR(1) model
            if game_columns and 'macro_state_json' not in game_columns:
                cursor.execute("ALTER TABLE game_sessions ADD COLUMN macro_state_json TEXT")
                print("[MIGRATION] Colonne 'macro_state_json' ajoutée à game_sessions (AR(1) state)")

            # Table des participants à une session
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_participants (
                    participant_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES game_sessions(session_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    UNIQUE(session_id, user_id)
                )
            """)

            # Table de l'historique année par année
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS year_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    scenario_applied TEXT NOT NULL,
                    asset_returns TEXT NOT NULL,  -- JSON: {asset_name: return_value}
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES game_sessions(session_id)
                )
            """)

            # Table des snapshots de portfolios par année
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    year INTEGER NOT NULL,
                    total_value REAL NOT NULL,
                    current_capital REAL NOT NULL,
                    positions TEXT NOT NULL,  -- JSON: {asset_name: amount}
                    allocation TEXT,  -- JSON: {asset_name: percentage}
                    performance REAL,
                    fees_paid REAL DEFAULT 0,
                    bankruptcies INTEGER DEFAULT 0,
                    snapshot_type TEXT DEFAULT 'simulation',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES game_sessions(session_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Migration: ajouter bankruptcies et snapshot_type si manquants
            cursor.execute("PRAGMA table_info(portfolio_snapshots)")
            snapshot_columns = [row[1] for row in cursor.fetchall()]

            if snapshot_columns and 'bankruptcies' not in snapshot_columns:
                cursor.execute("ALTER TABLE portfolio_snapshots ADD COLUMN bankruptcies INTEGER DEFAULT 0")
                print("[MIGRATION] Colonne 'bankruptcies' ajoutée à portfolio_snapshots")

            if snapshot_columns and 'snapshot_type' not in snapshot_columns:
                cursor.execute("ALTER TABLE portfolio_snapshots ADD COLUMN snapshot_type TEXT DEFAULT 'simulation'")
                print("[MIGRATION] Colonne 'snapshot_type' ajoutée à portfolio_snapshots")

            # Table des frais de trading configurables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_fees (
                    fee_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    asset_name TEXT NOT NULL,
                    fee_percentage REAL DEFAULT 0.01,
                    FOREIGN KEY (session_id) REFERENCES game_sessions(session_id),
                    UNIQUE(session_id, asset_name)
                )
            """)

            # Table des news/journal
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    news_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES game_sessions(session_id)
                )
            """)

    # ==========================================
    # GESTION DES UTILISATEURS
    # ==========================================

    def create_user(self, username, password, role='student'):
        """
        Crée un nouvel utilisateur.

        Args:
            username (str): Nom d'utilisateur unique
            password (str): Mot de passe en clair (sera hashé)
            role (str): 'student' ou 'admin'

        Returns:
            int: user_id du nouvel utilisateur

        Raises:
            sqlite3.IntegrityError: Si l'username existe déjà
        """
        password_hash = self._hash_password(password)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role)
            )
            return cursor.lastrowid

    def get_user(self, username):
        """
        Récupère les informations d'un utilisateur.

        Args:
            username (str): Nom d'utilisateur

        Returns:
            dict: Informations utilisateur ou None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def authenticate(self, username, password):
        """
        Authentifie un utilisateur.

        Args:
            username (str): Nom d'utilisateur
            password (str): Mot de passe en clair

        Returns:
            dict: Informations utilisateur si authentification réussie, None sinon
        """
        user = self.get_user(username)
        if not user:
            return None

        if self.verify_password(password, user['password_hash']):
            self.update_last_login(username)
            return user
        return None

    def update_last_login(self, username):
        """Met à jour le timestamp de dernière connexion."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?",
                (username,)
            )

    # ==========================================
    # GESTION DES PORTEFEUILLES
    # ==========================================

    def save_portfolio(self, username, portfolio_data, portfolio_name='Mon Portefeuille'):
        """
        Sauvegarde ou met à jour le portefeuille d'un utilisateur.

        Args:
            username (str): Nom d'utilisateur
            portfolio_data (list): Liste de {'asset_name': str, 'amount': float}
            portfolio_name (str): Nom du portefeuille

        Returns:
            int: portfolio_id
        """
        user = self.get_user(username)
        if not user:
            raise ValueError(f"Utilisateur '{username}' introuvable")

        portfolio_json = json.dumps(portfolio_data)

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Vérifier si un portefeuille existe déjà
            cursor.execute(
                "SELECT portfolio_id FROM portfolios WHERE user_id = ? AND portfolio_name = ?",
                (user['user_id'], portfolio_name)
            )
            existing = cursor.fetchone()

            if existing:
                # Mise à jour
                cursor.execute(
                    """UPDATE portfolios
                       SET portfolio_data = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE portfolio_id = ?""",
                    (portfolio_json, existing['portfolio_id'])
                )
                return existing['portfolio_id']
            else:
                # Création
                cursor.execute(
                    """INSERT INTO portfolios (user_id, portfolio_name, portfolio_data)
                       VALUES (?, ?, ?)""",
                    (user['user_id'], portfolio_name, portfolio_json)
                )
                return cursor.lastrowid

    def load_portfolio(self, username, portfolio_name='Mon Portefeuille'):
        """
        Charge le portefeuille d'un utilisateur.

        Args:
            username (str): Nom d'utilisateur
            portfolio_name (str): Nom du portefeuille

        Returns:
            list: Portfolio data ou None
        """
        user = self.get_user(username)
        if not user:
            return None

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT portfolio_data FROM portfolios
                   WHERE user_id = ? AND portfolio_name = ?""",
                (user['user_id'], portfolio_name)
            )
            row = cursor.fetchone()
            return json.loads(row['portfolio_data']) if row else None

    def list_user_portfolios(self, username):
        """
        Liste tous les portefeuilles d'un utilisateur.

        Args:
            username (str): Nom d'utilisateur

        Returns:
            list[dict]: Liste des portefeuilles
        """
        user = self.get_user(username)
        if not user:
            return []

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT portfolio_id, portfolio_name, created_at, updated_at
                   FROM portfolios WHERE user_id = ?""",
                (user['user_id'],)
            )
            return [dict(row) for row in cursor.fetchall()]

    # ==========================================
    # GESTION DES PARAMÈTRES DE SIMULATION
    # ==========================================

    def save_simulation_params(self, username, scenario_name, years, n_simulations, life_events):
        """
        Sauvegarde les paramètres de simulation d'un utilisateur.

        Args:
            username (str): Nom d'utilisateur
            scenario_name (str): Nom du scénario macro
            years (int): Horizon de simulation
            n_simulations (int): Nombre de trajectoires
            life_events (dict): {année: flux_cash}

        Returns:
            int: param_id
        """
        user = self.get_user(username)
        if not user:
            raise ValueError(f"Utilisateur '{username}' introuvable")

        life_events_json = json.dumps(life_events) if life_events else None

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO simulation_params
                   (user_id, scenario_name, years, n_simulations, life_events)
                   VALUES (?, ?, ?, ?, ?)""",
                (user['user_id'], scenario_name, years, n_simulations, life_events_json)
            )
            return cursor.lastrowid

    def load_last_simulation_params(self, username):
        """
        Charge les derniers paramètres de simulation utilisés.

        Args:
            username (str): Nom d'utilisateur

        Returns:
            dict: Paramètres ou None
        """
        user = self.get_user(username)
        if not user:
            return None

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM simulation_params
                   WHERE user_id = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (user['user_id'],)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result['life_events'] = json.loads(result['life_events']) if result['life_events'] else {}
                return result
            return None

    # ==========================================
    # GESTION DES RÉSULTATS
    # ==========================================

    def save_simulation_result(self, username, portfolio_id, param_id,
                               median_final, pessimist_final, optimist_final):
        """
        Sauvegarde les résultats d'une simulation.

        Args:
            username (str): Nom d'utilisateur
            portfolio_id (int): ID du portefeuille
            param_id (int): ID des paramètres
            median_final (float): Valeur médiane finale
            pessimist_final (float): Valeur pessimiste (P5)
            optimist_final (float): Valeur optimiste (P95)

        Returns:
            int: result_id
        """
        user = self.get_user(username)
        if not user:
            raise ValueError(f"Utilisateur '{username}' introuvable")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO simulation_results
                   (user_id, portfolio_id, param_id, median_final, pessimist_final, optimist_final)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user['user_id'], portfolio_id, param_id, median_final, pessimist_final, optimist_final)
            )
            return cursor.lastrowid

    def get_user_history(self, username, limit=10):
        """
        Récupère l'historique des simulations d'un utilisateur.

        Args:
            username (str): Nom d'utilisateur
            limit (int): Nombre max de résultats

        Returns:
            list[dict]: Historique des résultats
        """
        user = self.get_user(username)
        if not user:
            return []

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM simulation_results
                   WHERE user_id = ?
                   ORDER BY computed_at DESC LIMIT ?""",
                (user['user_id'], limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    # ==========================================
    # CONFIGURATION ADMIN (Partagée)
    # ==========================================

    def set_admin_config(self, config_key, config_value):
        """
        Définit une configuration globale (Admin uniquement).

        Args:
            config_key (str): Clé de configuration
            config_value (str): Valeur (peut être JSON)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO admin_config (config_key, config_value, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)""",
                (config_key, config_value)
            )

    def get_admin_config(self, config_key, default=None):
        """
        Récupère une configuration globale.

        Args:
            config_key (str): Clé de configuration
            default: Valeur par défaut si inexistante

        Returns:
            str: Valeur de configuration
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT config_value FROM admin_config WHERE config_key = ?",
                (config_key,)
            )
            row = cursor.fetchone()
            return row['config_value'] if row else default

    # ==========================================
    # UTILITAIRES
    # ==========================================

    def delete_user(self, username):
        """Supprime un utilisateur et toutes ses données (CASCADE)."""
        user = self.get_user(username)
        if not user:
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user['user_id'],))
            cursor.execute("DELETE FROM portfolios WHERE user_id = ?", (user['user_id'],))
            cursor.execute("DELETE FROM simulation_params WHERE user_id = ?", (user['user_id'],))
            cursor.execute("DELETE FROM simulation_results WHERE user_id = ?", (user['user_id'],))

    def export_user_data(self, username):
        """
        Exporte toutes les données d'un utilisateur (JSON).

        Args:
            username (str): Nom d'utilisateur

        Returns:
            dict: Toutes les données de l'utilisateur
        """
        user = self.get_user(username)
        if not user:
            return None

        return {
            'user_info': user,
            'portfolios': self.list_user_portfolios(username),
            'last_params': self.load_last_simulation_params(username),
            'history': self.get_user_history(username, limit=50)
        }

    # ==========================================
    # GESTION DES SESSIONS DE JEU
    # ==========================================

    def create_game_session(self, session_id, session_name, admin_username, initial_capital=100000, available_asset_names=None):
        """
        Crée une nouvelle session de jeu.

        Args:
            session_id (str): Identifiant unique de la session
            session_name (str): Nom de la session
            admin_username (str): Username de l'admin
            initial_capital (float): Capital initial par étudiant
            available_asset_names (list): Liste des actifs disponibles (None = tous)

        Returns:
            bool: True si succès
        """
        user = self.get_user(admin_username)
        if not user:
            raise ValueError(f"Admin '{admin_username}' introuvable")

        # Si aucune liste fournie, tous les actifs sont disponibles
        if available_asset_names is None:
            from market import get_available_assets
            all_assets = get_available_assets()
            available_asset_names = [asset.name for asset in all_assets]

        available_assets_json = json.dumps(available_asset_names)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO game_sessions (session_id, session_name, admin_user_id, initial_capital, available_assets_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, session_name, user['user_id'], initial_capital, available_assets_json)
            )
        return True

    def get_game_session(self, session_id):
        """
        Récupère les informations d'une session de jeu.

        Args:
            session_id (str): Identifiant de la session

        Returns:
            dict: Informations de la session ou None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM game_sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                session_dict = dict(row)
                # Parser le JSON des actifs disponibles
                if session_dict.get('available_assets_json'):
                    session_dict['available_asset_names'] = json.loads(session_dict['available_assets_json'])
                else:
                    # Par défaut, tous les actifs sont disponibles
                    from market import get_available_assets
                    all_assets = get_available_assets()
                    session_dict['available_asset_names'] = [asset.name for asset in all_assets]
                return session_dict
            return None

    def update_game_session(self, session_id, **kwargs):
        """
        Met à jour une session de jeu.

        Args:
            session_id (str): Identifiant de la session
            **kwargs: Champs à mettre à jour (current_year, status, etc.)
        """
        if not kwargs:
            return

        fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [session_id]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE game_sessions SET {fields} WHERE session_id = ?",
                values
            )

    def join_game_session(self, session_id, username):
        """
        Ajoute un étudiant à une session de jeu.

        Args:
            session_id (str): Identifiant de la session
            username (str): Nom de l'étudiant

        Returns:
            bool: True si succès
        """
        user = self.get_user(username)
        if not user:
            raise ValueError(f"Utilisateur '{username}' introuvable")

        session = self.get_game_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' introuvable")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO session_participants (session_id, user_id) VALUES (?, ?)",
                    (session_id, user['user_id'])
                )
            return True
        except sqlite3.IntegrityError:
            # Déjà participant
            return False

    def get_session_participants(self, session_id):
        """
        Liste les participants d'une session.

        Args:
            session_id (str): Identifiant de la session

        Returns:
            list[dict]: Liste des participants avec infos user
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT u.user_id, u.username, u.role, sp.joined_at
                   FROM session_participants sp
                   JOIN users u ON sp.user_id = u.user_id
                   WHERE sp.session_id = ?""",
                (session_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def save_year_history(self, session_id, year, scenario_name, asset_returns, macro_shocks=None):
        """
        Sauvegarde l'historique d'une année simulée.

        Args:
            session_id (str): Identifiant de la session
            year (int): Numéro de l'année
            scenario_name (str): Nom du scénario appliqué
            asset_returns (dict): {asset_name: return_value}
            macro_shocks (dict): {pib_shock, inf_shock, rates_shock, equity_shock}
        """
        returns_json = json.dumps(asset_returns)

        # Inclure les chocs macro dans les données sauvegardées
        if macro_shocks:
            # Fusionner asset_returns avec macro_shocks pour stockage unifié
            full_data = {
                'asset_returns': asset_returns,
                'pib_shock': macro_shocks.get('pib_shock', 0.0),
                'inf_shock': macro_shocks.get('inf_shock', 0.0),
                'rates_shock': macro_shocks.get('rates_shock', 0.0),
                'equity_shock': macro_shocks.get('equity_shock', 0.0)
            }
            returns_json = json.dumps(full_data)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO year_history (session_id, year, scenario_applied, asset_returns)
                   VALUES (?, ?, ?, ?)""",
                (session_id, year, scenario_name, returns_json)
            )

    def get_year_history(self, session_id):
        """
        Récupère l'historique complet d'une session.

        Args:
            session_id (str): Identifiant de la session

        Returns:
            list[dict]: Historique année par année
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM year_history WHERE session_id = ? ORDER BY year",
                (session_id,)
            )
            history = []
            for row in cursor.fetchall():
                entry = dict(row)
                stored_data = json.loads(entry['asset_returns'])

                # Vérifier si les données sont dans le nouveau format (avec macro_shocks)
                if isinstance(stored_data, dict) and 'asset_returns' in stored_data:
                    # Nouveau format: extraire asset_returns et macro_shocks
                    entry['asset_returns'] = stored_data['asset_returns']
                    entry['pib_shock'] = stored_data.get('pib_shock', 0.0)
                    entry['inf_shock'] = stored_data.get('inf_shock', 0.0)
                    entry['rates_shock'] = stored_data.get('rates_shock', 0.0)
                    entry['equity_shock'] = stored_data.get('equity_shock', 0.0)
                else:
                    # Ancien format: stored_data est directement asset_returns
                    entry['asset_returns'] = stored_data
                    # Pas de macro_shocks disponibles
                    entry['pib_shock'] = 0.0
                    entry['inf_shock'] = 0.0
                    entry['rates_shock'] = 0.0
                    entry['equity_shock'] = 0.0

                history.append(entry)
            return history

    def save_portfolio_snapshot(self, session_id, username, year, portfolio_data):
        """
        Sauvegarde un snapshot du portfolio d'un étudiant.

        Args:
            session_id (str): Identifiant de la session
            username (str): Nom de l'étudiant
            year (int): Année du snapshot
            portfolio_data (dict): Données du portfolio (from StudentPortfolio.snapshot())
        """
        user = self.get_user(username)
        if not user:
            raise ValueError(f"Utilisateur '{username}' introuvable")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO portfolio_snapshots
                   (session_id, user_id, year, total_value, current_capital, positions, allocation, performance, fees_paid, bankruptcies, snapshot_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    user['user_id'],
                    year,
                    portfolio_data['total_value'],
                    portfolio_data['current_capital'],
                    json.dumps(portfolio_data['positions']),
                    json.dumps(portfolio_data['allocation']),
                    portfolio_data['performance'],
                    portfolio_data['total_fees_paid'],
                    portfolio_data.get('bankruptcies', 0),
                    portfolio_data.get('snapshot_type', 'simulation')
                )
            )

    def get_portfolio_snapshots(self, session_id, username):
        """
        Récupère tous les snapshots d'un étudiant dans une session.

        Args:
            session_id (str): Identifiant de la session
            username (str): Nom de l'étudiant

        Returns:
            list[dict]: Snapshots ordonnés par année
        """
        user = self.get_user(username)
        if not user:
            return []

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM portfolio_snapshots
                   WHERE session_id = ? AND user_id = ?
                   ORDER BY year""",
                (session_id, user['user_id'])
            )
            snapshots = []
            for row in cursor.fetchall():
                snap = dict(row)
                snap['positions'] = json.loads(snap['positions'])
                snap['allocation'] = json.loads(snap['allocation'])
                snapshots.append(snap)
            return snapshots

    def set_trading_fee(self, session_id, asset_name, fee_percentage):
        """
        Définit les frais de trading pour un actif dans une session.

        Args:
            session_id (str): Identifiant de la session
            asset_name (str): Nom de l'actif
            fee_percentage (float): Frais en décimal (0.01 = 1%)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO trading_fees (session_id, asset_name, fee_percentage)
                   VALUES (?, ?, ?)""",
                (session_id, asset_name, fee_percentage)
            )

    def get_trading_fees(self, session_id):
        """
        Récupère tous les frais de trading d'une session.

        Args:
            session_id (str): Identifiant de la session

        Returns:
            dict: {asset_name: fee_percentage}
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT asset_name, fee_percentage FROM trading_fees WHERE session_id = ?",
                (session_id,)
            )
            return {row['asset_name']: row['fee_percentage'] for row in cursor.fetchall()}

    def update_available_assets(self, session_id, available_asset_names):
        """
        Met à jour la liste des actifs disponibles pour une session.

        Args:
            session_id (str): Identifiant de la session
            available_asset_names (list): Liste des noms d'actifs disponibles
        """
        available_assets_json = json.dumps(available_asset_names)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE game_sessions SET available_assets_json = ? WHERE session_id = ?",
                (available_assets_json, session_id)
            )

    def list_all_game_sessions(self):
        """
        Liste toutes les sessions de jeu.

        Returns:
            list[dict]: Liste des sessions
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM game_sessions ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    # ==========================================
    # GESTION DES NEWS/JOURNAL
    # ==========================================

    def add_news(self, session_id, year, title, content):
        """
        Ajoute une news au journal de la session.

        Args:
            session_id (str): ID de la session
            year (int): Année de la news
            title (str): Titre de la news
            content (str): Contenu de la news
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO news (session_id, year, title, content)
                VALUES (?, ?, ?, ?)
            """, (session_id, year, title, content))

    def get_news(self, session_id, year=None):
        """
        Récupère les news d'une session.

        Args:
            session_id (str): ID de la session
            year (int, optional): Filtrer par année. Si None, toutes les news.

        Returns:
            list[dict]: Liste des news
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if year is not None:
                cursor.execute("""
                    SELECT * FROM news
                    WHERE session_id = ? AND year = ?
                    ORDER BY created_at DESC
                """, (session_id, year))
            else:
                cursor.execute("""
                    SELECT * FROM news
                    WHERE session_id = ?
                    ORDER BY year DESC, created_at DESC
                """, (session_id,))

            return [dict(row) for row in cursor.fetchall()]

    def get_all_news_history(self, session_id):
        """
        Récupère tout l'historique des news groupé par année.

        Args:
            session_id (str): ID de la session

        Returns:
            dict: {year: [news]}
        """
        news_list = self.get_news(session_id)
        history = {}
        for news in news_list:
            year = news['year']
            if year not in history:
                history[year] = []
            history[year].append(news)
        return history


if __name__ == "__main__":
    # Test rapide
    print("=== TEST SESSION MANAGER ===\n")

    # Créer une instance
    sm = SessionManager("test_sessions.db")

    # Créer un utilisateur
    try:
        user_id = sm.create_user("alice_student", "password123", role='student')
        print(f"[OK] Utilisateur cree: alice_student (ID: {user_id})")
    except sqlite3.IntegrityError:
        print("[OK] Utilisateur alice_student deja existant")

    # Tester l'authentification
    auth_result = sm.authenticate("alice_student", "password123")
    if auth_result:
        print(f"[OK] Authentification reussie pour {auth_result['username']}")
    else:
        print("[ERREUR] Authentification echouee")

    # Tester un mauvais mot de passe
    auth_fail = sm.authenticate("alice_student", "wrong_password")
    if auth_fail is None:
        print("[OK] Mauvais mot de passe correctement refuse")

    # Sauvegarder un portefeuille
    portfolio_data = [
        {'asset_name': 'ETF World (MSCI)', 'amount': 10000},
        {'asset_name': 'Gov Bonds US (10Y)', 'amount': 5000}
    ]
    portfolio_id = sm.save_portfolio("alice_student", portfolio_data)
    print(f"[OK] Portefeuille sauvegarde (ID: {portfolio_id})")

    # Charger le portefeuille
    loaded = sm.load_portfolio("alice_student")
    print(f"[OK] Portefeuille charge: {loaded}")

    # Sauvegarder des paramètres
    life_events = {5: 20000, 10: -50000}
    param_id = sm.save_simulation_params(
        "alice_student", "Normale (Historique)", 15, 1000, life_events
    )
    print(f"[OK] Parametres sauvegardes (ID: {param_id})")

    # Sauvegarder un résultat
    result_id = sm.save_simulation_result(
        "alice_student", portfolio_id, param_id,
        median_final=22000, pessimist_final=15000, optimist_final=35000
    )
    print(f"[OK] Resultat sauvegarde (ID: {result_id})")

    # Export complet
    export = sm.export_user_data("alice_student")
    print(f"\n[OK] Export utilisateur:\n{json.dumps(export, indent=2, default=str)}")

    print("\n=== TEST TERMINÉ ===")
