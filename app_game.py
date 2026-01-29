# -*- coding: utf-8 -*-
"""
app_game.py - Interface Streamlit pour le Business Game Tour par Tour
======================================================================
Nouvelle interface utilisant game_engine.py au lieu de Monte Carlo.

Deux vues:
- STUDENT: Rejoindre session, gérer portfolio, arbitrages
- ADMIN: Créer session, simuler années, voir classement
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from session_manager import SessionManager
from game_engine import GameSession, StudentPortfolio
from market import get_available_assets, get_market_scenarios, get_asset_by_name, PRESETS_ADMIN, NEWS_LIBRARY, get_news_suggestions

# Configuration de la page
st.set_page_config(
    page_title="Fineva Business Game",
    page_icon="🎮",
    layout="wide"
)

# Initialisation du session manager
if 'session_manager' not in st.session_state:
    st.session_state.session_manager = SessionManager("fineva_game.db")

if 'username' not in st.session_state:
    st.session_state.username = None

if 'user_role' not in st.session_state:
    st.session_state.user_role = None

if 'current_session_id' not in st.session_state:
    st.session_state.current_session_id = None

if 'game_session' not in st.session_state:
    st.session_state.game_session = None


# ==========================================
# PAGE DE CONNEXION
# ==========================================

def show_login_page():
    """Affiche la page de connexion"""
    st.title("🎮 Fineva Business Game")
    st.markdown("### Simulateur de Portefeuille Tour par Tour")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔐 Connexion")
        username = st.text_input("Nom d'utilisateur", key="login_user")
        password = st.text_input("Mot de passe", type="password", key="login_pass")

        if st.button("Se connecter", use_container_width=True):
            if username and password:
                sm = st.session_state.session_manager
                user = sm.authenticate(username, password)

                if user:
                    st.session_state.username = username
                    st.session_state.user_role = user['role']
                    st.success(f"✓ Connecté: {username} ({user['role']})")
                    st.rerun()
                else:
                    st.error("❌ Identifiants incorrects")
            else:
                st.error("Veuillez remplir tous les champs")

    with col2:
        st.subheader("📝 Créer un compte")
        new_username = st.text_input("Nom d'utilisateur", key="signup_user")
        new_password = st.text_input("Mot de passe", type="password", key="signup_pass")
        role = st.selectbox("Rôle", ["student", "admin"], key="signup_role")

        if st.button("Créer compte", use_container_width=True):
            if new_username and new_password:
                sm = st.session_state.session_manager
                try:
                    sm.create_user(new_username, new_password, role=role)
                    st.success(f"✓ Compte créé! Connectez-vous maintenant.")
                except Exception as e:
                    st.error(f"Erreur: {e}")
            else:
                st.error("Veuillez remplir tous les champs")


# ==========================================
# INTERFACE STUDENT
# ==========================================

def show_student_interface():
    """Interface pour les étudiants"""
    st.title(f"👨‍🎓 Espace Étudiant - {st.session_state.username}")

    sm = st.session_state.session_manager

    # Sidebar: Sélection/Rejoindre session
    with st.sidebar:
        st.subheader("📚 Ma Session")

        # Liste des sessions disponibles
        all_sessions = sm.list_all_game_sessions()
        active_sessions = [s for s in all_sessions if s['status'] in ['waiting', 'active']]

        if active_sessions:
            session_options = {f"{s['session_id']} - {s['session_name']}": s['session_id']
                             for s in active_sessions}

            selected = st.selectbox(
                "Choisir une session",
                options=list(session_options.keys()),
                key="session_select"
            )

            session_id = session_options[selected]

            # Vérifier si déjà participant
            participants = sm.get_session_participants(session_id)
            is_participant = any(p['username'] == st.session_state.username for p in participants)

            if not is_participant:
                if st.button("🚀 Rejoindre cette session"):
                    sm.join_game_session(session_id, st.session_state.username)
                    st.session_state.current_session_id = session_id
                    st.success(f"✓ Vous avez rejoint {session_id}")
                    st.rerun()
            else:
                st.session_state.current_session_id = session_id
                st.success(f"✓ Membre de {session_id}")
        else:
            st.warning("Aucune session active disponible")
            st.info("Attendez qu'un admin crée une session")

        st.markdown("---")
        if st.button("🚪 Déconnexion"):
            st.session_state.username = None
            st.session_state.user_role = None
            st.session_state.current_session_id = None
            st.session_state.game_session = None
            st.rerun()

    # Contenu principal
    if not st.session_state.current_session_id:
        st.info("👈 Choisissez une session dans la barre latérale")
        return

    session_id = st.session_state.current_session_id
    session_info = sm.get_game_session(session_id)

    # Charger ou créer GameSession en mémoire
    if st.session_state.game_session is None or st.session_state.game_session.session_id != session_id:
        game = GameSession(
            session_id=session_id,
            session_name=session_info['session_name'],
            admin_username="",  # Pas important pour étudiant
            initial_capital=session_info['initial_capital']
        )

        # Charger les participants
        participants = sm.get_session_participants(session_id)
        for p in participants:
            game.add_student(p['username'])

        # Charger les snapshots pour reconstruire les portfolios
        for p in participants:
            snapshots = sm.get_portfolio_snapshots(session_id, p['username'])
            if snapshots:
                # Prendre le dernier snapshot
                last_snap = snapshots[-1]
                portfolio = game.get_student_portfolio(p['username'])
                portfolio.current_capital = last_snap['current_capital']
                portfolio.positions = last_snap['positions']
                portfolio.total_fees_paid = last_snap['fees_paid']
                portfolio.bankruptcy_count = last_snap.get('bankruptcies', 0)

        game.current_year = session_info['current_year']
        game.status = session_info['status']

        # Charger la liste des actifs disponibles
        if 'available_asset_names' in session_info:
            game.available_asset_names = session_info['available_asset_names']

        # Restaurer l'état macro AR(1) si disponible
        if session_info.get('macro_state_json'):
            import json
            from game_engine import MacroState
            macro_data = json.loads(session_info['macro_state_json'])
            game.macro_state = MacroState.from_dict(macro_data)

        st.session_state.game_session = game

    game = st.session_state.game_session
    portfolio = game.get_student_portfolio(st.session_state.username)

    # Header avec infos
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📅 Année", game.current_year)
    with col2:
        st.metric("💰 Capital", f"{portfolio.get_total_value():.0f}€")
    with col3:
        st.metric("📈 Performance", f"{portfolio.get_performance():.1f}%")
    with col4:
        leaderboard = game.get_leaderboard()
        my_rank = next((i+1 for i, e in enumerate(leaderboard) if e['username'] == st.session_state.username), "N/A")
        st.metric("🏆 Rang", f"{my_rank}/{len(leaderboard)}")

    st.markdown("---")

    # Onglets
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["💼 Mon Portfolio", "🔄 Arbitrages", "📊 Classement", "📜 Historique", "📰 Journal"])

    with tab1:
        show_student_portfolio(game, portfolio)

    with tab2:
        show_student_arbitrage(game, portfolio, sm, session_id)

    with tab3:
        show_leaderboard(game)

    with tab5:
        show_student_journal(sm, session_id, game)

    with tab4:
        show_history(sm, session_id, st.session_state.username)


def show_student_portfolio(game, portfolio):
    """Affiche le portfolio de l'étudiant"""
    st.subheader("💼 Mon Portfolio Actuel")

    if not portfolio.positions:
        st.info("Votre portfolio est vide. Achetez des actifs dans l'onglet 'Arbitrages'.")
        return

    # Table des positions
    positions_data = []
    for asset_name, amount in portfolio.positions.items():
        try:
            asset = get_asset_by_name(asset_name)
            positions_data.append({
                'Actif': asset_name,
                'Catégorie': asset.category,
                'Montant': f"{amount:.0f}€",
                'Allocation': f"{(amount/portfolio.get_total_value())*100:.1f}%"
            })
        except ValueError:
            continue

    if positions_data:
        df = pd.DataFrame(positions_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Cash
    st.metric("💵 Cash Disponible", f"{portfolio.current_capital:.0f}€")
    st.caption(f"Frais totaux payés: {portfolio.total_fees_paid:.0f}€")

    # Graphique
    if portfolio.positions:
        allocation = portfolio.get_allocation()
        fig = go.Figure(data=[go.Pie(
            labels=list(allocation.keys()),
            values=list(allocation.values()),
            hole=0.4
        )])
        fig.update_layout(title="Répartition du Portfolio", height=400)
        st.plotly_chart(fig, use_container_width=True)


def show_student_arbitrage(game, portfolio, sm, session_id):
    """Affiche l'interface d'arbitrage"""
    st.subheader("🔄 Arbitrages")

    if game.status == 'waiting':
        st.warning("⏳ La session n'a pas encore démarré. Attendez que l'admin lance le jeu.")
        return

    st.info(f"Année actuelle: {game.current_year} - Faites vos arbitrages avant la prochaine simulation")

    # Utiliser uniquement les actifs disponibles dans cette session
    available_assets = game.get_available_assets()

    if not available_assets:
        st.warning("⚠️ Aucun actif n'est actuellement disponible. Contactez l'admin.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 📤 Vendre")
        if portfolio.positions:
            sell_asset = st.selectbox(
                "Actif à vendre",
                options=list(portfolio.positions.keys()),
                key="sell_asset"
            )
            max_sell = portfolio.positions.get(sell_asset, 0)
            sell_amount = st.number_input(
                "Montant à vendre (€)",
                min_value=0.0,
                max_value=float(max_sell),
                value=0.0,
                step=1000.0,
                key="sell_amount"
            )
            sell_fee = game.get_trading_fee(sell_asset)
            st.caption(f"Frais: {sell_fee*100:.2f}% = {sell_amount*sell_fee:.0f}€")

            if st.button("💸 Vendre", use_container_width=True):
                if sell_amount > 0:
                    success = portfolio.execute_transaction(sell_asset, "sell", sell_amount, sell_fee)
                    if success:
                        # Sauvegarder snapshot d'arbitrage
                        snapshot = portfolio.snapshot(game.current_year, snapshot_type='arbitrage')
                        sm.save_portfolio_snapshot(session_id, st.session_state.username, game.current_year, snapshot)
                        st.success(f"✓ Vendu {sell_amount:.0f}€ de {sell_asset}")
                        st.rerun()
                    else:
                        st.error("Position insuffisante")
        else:
            st.info("Pas d'actifs à vendre")

    with col2:
        st.markdown("#### 📥 Acheter")
        buy_asset_name = st.selectbox(
            "Actif à acheter",
            options=[a.name for a in available_assets],
            key="buy_asset"
        )
        buy_amount = st.number_input(
            "Montant à acheter (€)",
            min_value=0.0,
            max_value=float(portfolio.current_capital),
            value=0.0,
            step=1000.0,
            key="buy_amount"
        )
        buy_fee = game.get_trading_fee(buy_asset_name)
        total_cost = buy_amount * (1 + buy_fee)
        st.caption(f"Frais: {buy_fee*100:.2f}% = {buy_amount*buy_fee:.0f}€")
        st.caption(f"Coût total: {total_cost:.0f}€")

        if st.button("💰 Acheter", use_container_width=True):
            if buy_amount > 0:
                success = portfolio.execute_transaction(buy_asset_name, "buy", buy_amount, buy_fee)
                if success:
                    # Sauvegarder snapshot d'arbitrage
                    snapshot = portfolio.snapshot(game.current_year, snapshot_type='arbitrage')
                    sm.save_portfolio_snapshot(session_id, st.session_state.username, game.current_year, snapshot)
                    st.success(f"✓ Acheté {buy_amount:.0f}€ de {buy_asset_name}")
                    st.rerun()
                else:
                    st.error("Fonds insuffisants")


def show_leaderboard(game):
    """Affiche le classement"""
    st.subheader("🏆 Classement")

    leaderboard = game.get_leaderboard()

    if not leaderboard:
        st.info("Pas encore de classement")
        return

    leaderboard_data = []
    for entry in leaderboard:
        medal = ""
        if entry['rank'] == 1:
            medal = "🥇"
        elif entry['rank'] == 2:
            medal = "🥈"
        elif entry['rank'] == 3:
            medal = "🥉"

        # Afficher les faillites
        bankruptcy_marker = ""
        if entry['bankruptcies'] > 0:
            bankruptcy_marker = f" 💀×{entry['bankruptcies']}"

        leaderboard_data.append({
            'Rang': f"{medal} {entry['rank']}",
            'Étudiant': entry['username'] + bankruptcy_marker,
            'Valeur': f"{entry['total_value']:.0f}€",
            'Performance': f"{entry['performance']:+.1f}%",
            'Frais': f"{entry['fees_paid']:.0f}€"
        })

    df = pd.DataFrame(leaderboard_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    if any(e['bankruptcies'] > 0 for e in leaderboard):
        st.caption("💀 = Nombre de faillites (renflouement de 10k€)")


def show_history(sm, session_id, username):
    """Affiche l'historique"""
    st.subheader("📜 Historique de mes Performances")

    snapshots = sm.get_portfolio_snapshots(session_id, username)

    if not snapshots:
        st.info("Pas encore d'historique")
        return

    # Filtrer pour ne garder que les snapshots de simulation pour le graphique
    simulation_snapshots = [s for s in snapshots if s.get('snapshot_type') == 'simulation']

    if simulation_snapshots:
        # Toggle pour mode annualisé
        show_annualized_student = st.checkbox("Afficher en mode annualisé", value=False, key="student_annualized_toggle")

        # Récupérer l'historique des rendements des actifs
        year_history = sm.get_year_history(session_id)

        # Graphique d'évolution avec MA performance (BLEU) + performances des actifs
        years = [s['year'] for s in simulation_snapshots]
        values = [s['total_value'] for s in simulation_snapshots]

        # Calculer les performances cumulées
        initial_value = simulation_snapshots[0]['total_value'] if simulation_snapshots else 100000
        my_performances_cumul = [(v / initial_value - 1) * 100 for v in values]

        # Calculer performances annualisées si demandé
        if show_annualized_student:
            my_performances = []
            for idx, cumul_perf in enumerate(my_performances_cumul):
                if idx == 0:
                    my_performances.append(cumul_perf)
                else:
                    n_years = idx + 1
                    annualized = (((1 + cumul_perf/100) ** (1/n_years)) - 1) * 100
                    my_performances.append(annualized)
            y_label = "Performance Annualisée (%)"
            title_suffix = "Annualisée"
        else:
            my_performances = my_performances_cumul
            y_label = "Performance Cumulée (%)"
            title_suffix = "Cumulée"

        fig = go.Figure()

        # MA PERFORMANCE en BLEU (ligne épaisse)
        fig.add_trace(go.Scatter(
            x=years,
            y=my_performances,
            mode='lines+markers',
            name='Ma Performance',
            line=dict(color='blue', width=4),
            marker=dict(size=8)
        ))

        # PERFORMANCES DES ACTIFS en couleurs différentes
        if year_history:
            # Calculer les performances cumulées par actif
            asset_cumul_returns = {}
            colors = ['red', 'green', 'orange', 'purple', 'brown', 'pink', 'gray', 'cyan',
                     'magenta', 'lime', 'navy', 'teal', 'maroon', 'olive', 'coral', 'gold', 'indigo']

            for year_data in year_history:
                for asset_name, ret in year_data['asset_returns'].items():
                    if asset_name not in asset_cumul_returns:
                        asset_cumul_returns[asset_name] = []

                    # Calculer le rendement cumulé
                    if len(asset_cumul_returns[asset_name]) == 0:
                        asset_cumul_returns[asset_name].append((1 + ret) * 100 - 100)
                    else:
                        prev_cumul = asset_cumul_returns[asset_name][-1]
                        new_cumul = (1 + prev_cumul/100) * (1 + ret) * 100 - 100
                        asset_cumul_returns[asset_name].append(new_cumul)

            # Ajouter une trace pour chaque actif (limiter à 10 actifs pour lisibilité)
            asset_names_sorted = sorted(asset_cumul_returns.keys())[:10]
            for i, asset_name in enumerate(asset_names_sorted):
                asset_years = list(range(len(asset_cumul_returns[asset_name])))

                # Calculer performances annualisées si demandé
                if show_annualized_student:
                    asset_perfs_annualized = []
                    for idx, cumul_perf in enumerate(asset_cumul_returns[asset_name]):
                        if idx == 0:
                            asset_perfs_annualized.append(cumul_perf)
                        else:
                            n_years = idx + 1
                            annualized = (((1 + cumul_perf/100) ** (1/n_years)) - 1) * 100
                            asset_perfs_annualized.append(annualized)
                    y_data_asset = asset_perfs_annualized
                else:
                    y_data_asset = asset_cumul_returns[asset_name]

                fig.add_trace(go.Scatter(
                    x=asset_years,
                    y=y_data_asset,
                    mode='lines',
                    name=asset_name,
                    line=dict(color=colors[i % len(colors)], width=1.5, dash='dot'),
                    opacity=0.6
                ))

        fig.update_layout(
            title=f"Ma Performance {title_suffix} vs Actifs Disponibles",
            xaxis_title="Année",
            yaxis_title=y_label,
            height=500,
            hovermode='x unified',
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02
            )
        )
        st.plotly_chart(fig, use_container_width=True)

    # Table détaillée (tous les snapshots avec distinction)
    history_data = []
    for s in snapshots:
        snapshot_type = s.get('snapshot_type', 'simulation')
        type_icon = "🎯" if snapshot_type == 'simulation' else "🔄"

        bankruptcies = s.get('bankruptcies', 0)
        bankruptcy_icon = f" 💀×{bankruptcies}" if bankruptcies > 0 else ""

        history_data.append({
            'Type': type_icon,
            'Année': s['year'],
            'Valeur': f"{s['total_value']:.0f}€",
            'Performance': f"{s['performance']:.1f}%",
            'Cash': f"{s['current_capital']:.0f}€",
            'Frais': f"{s['fees_paid']:.0f}€",
            'Status': bankruptcy_icon if bankruptcies > 0 else ""
        })

    df = pd.DataFrame(history_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption("🎯 = Snapshot après simulation | 🔄 = Snapshot après arbitrage | 💀 = Faillite")


def show_student_journal(sm, session_id, game):
    """Affiche le journal des news pour l'étudiant"""
    st.subheader("📰 Journal Économique")
    st.caption("Actualités économiques publiées par l'administrateur")

    # Récupérer toutes les news
    news_history = sm.get_all_news_history(session_id)

    if not news_history:
        st.info("Aucune actualité publiée pour le moment")
        return

    # Afficher les news groupées par année (ordre décroissant)
    for year in sorted(news_history.keys(), reverse=True):
        news_list = news_history[year]

        with st.expander(f"📅 Année {year} - {len(news_list)} actualité(s)", expanded=(year == game.current_year)):
            for news in news_list:
                st.markdown(f"### {news['title']}")
                st.write(news['content'])
                st.caption(f"*Publié le {news['created_at']}*")
                st.markdown("---")


# ==========================================
# INTERFACE ADMIN
# ==========================================

def show_admin_interface():
    """Interface pour les admins"""
    st.title(f"👨‍💼 Espace Admin - {st.session_state.username}")

    sm = st.session_state.session_manager

    # Sidebar
    with st.sidebar:
        st.subheader("⚙️ Administration")

        admin_mode = st.radio(
            "Mode",
            ["Créer Session", "Gérer Session"],
            key="admin_mode"
        )

        st.markdown("---")
        if st.button("🚪 Déconnexion"):
            st.session_state.username = None
            st.session_state.user_role = None
            st.session_state.current_session_id = None
            st.session_state.game_session = None
            st.rerun()

    if admin_mode == "Créer Session":
        show_admin_create_session(sm)
    else:
        show_admin_manage_session(sm)


def show_admin_create_session(sm):
    """Interface de création de session"""
    st.subheader("🆕 Créer une Nouvelle Session")

    col1, col2 = st.columns(2)

    with col1:
        session_id = st.text_input("ID de la session", placeholder="FINEVA_2025_S1")
        session_name = st.text_input("Nom de la session", placeholder="Fineva Spring 2025")

    with col2:
        initial_capital = st.number_input("Capital initial (€)", value=100000, step=10000)

    if st.button("🚀 Créer la Session", use_container_width=True):
        if session_id and session_name:
            try:
                sm.create_game_session(
                    session_id=session_id,
                    session_name=session_name,
                    admin_username=st.session_state.username,
                    initial_capital=initial_capital
                )
                st.success(f"✓ Session '{session_id}' créée!")
                st.balloons()
            except Exception as e:
                st.error(f"Erreur: {e}")
        else:
            st.error("Veuillez remplir tous les champs")

    st.markdown("---")
    st.subheader("📋 Sessions Existantes")
    all_sessions = sm.list_all_game_sessions()
    if all_sessions:
        for s in all_sessions:
            with st.expander(f"{s['session_id']} - {s['session_name']} ({s['status']})"):
                st.write(f"**Année:** {s['current_year']}")
                st.write(f"**Capital initial:** {s['initial_capital']:.0f}€")
                st.write(f"**Créée le:** {s['created_at']}")

                participants = sm.get_session_participants(s['session_id'])
                st.write(f"**Participants:** {len(participants)}")
                if participants:
                    st.write(", ".join([p['username'] for p in participants]))
    else:
        st.info("Aucune session créée")


def show_admin_manage_session(sm):
    """Interface de gestion de session"""
    st.subheader("🎮 Gérer une Session")

    # Sélection de session
    all_sessions = sm.list_all_game_sessions()
    if not all_sessions:
        st.warning("Aucune session disponible. Créez-en une d'abord.")
        return

    session_options = {f"{s['session_id']} - {s['session_name']}": s['session_id'] for s in all_sessions}
    selected = st.selectbox("Choisir une session", options=list(session_options.keys()))
    session_id = session_options[selected]

    st.session_state.current_session_id = session_id
    session_info = sm.get_game_session(session_id)

    # Charger GameSession
    if st.session_state.game_session is None or st.session_state.game_session.session_id != session_id:
        game = GameSession(
            session_id=session_id,
            session_name=session_info['session_name'],
            admin_username=st.session_state.username,
            initial_capital=session_info['initial_capital']
        )

        participants = sm.get_session_participants(session_id)
        for p in participants:
            game.add_student(p['username'])

        # Charger snapshots
        for p in participants:
            snapshots = sm.get_portfolio_snapshots(session_id, p['username'])
            if snapshots:
                last_snap = snapshots[-1]
                portfolio = game.get_student_portfolio(p['username'])
                portfolio.current_capital = last_snap['current_capital']
                portfolio.positions = last_snap['positions']
                portfolio.total_fees_paid = last_snap['fees_paid']
                portfolio.bankruptcy_count = last_snap.get('bankruptcies', 0)

        game.current_year = session_info['current_year']
        game.status = session_info['status']

        # Charger la liste des actifs disponibles
        if 'available_asset_names' in session_info:
            game.available_asset_names = session_info['available_asset_names']

        # Restaurer l'état macro AR(1) si disponible
        if session_info.get('macro_state_json'):
            import json
            from game_engine import MacroState
            macro_data = json.loads(session_info['macro_state_json'])
            game.macro_state = MacroState.from_dict(macro_data)

        st.session_state.game_session = game

    game = st.session_state.game_session

    # Header
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📅 Année Actuelle", game.current_year)
    with col2:
        st.metric("👥 Participants", len(game.students))
    with col3:
        status_emoji = {"waiting": "⏳", "active": "▶️", "ended": "🏁"}
        st.metric("Statut", f"{status_emoji.get(game.status, '')} {game.status}")

    st.markdown("---")

    # Onglets
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "👥 Participants",
        "🎯 Simulation",
        "💰 Frais",
        "📦 Actifs",
        "🏆 Classement",
        "📊 Allocations",
        "📈 Performances",
        "📉 Rendements Actifs",
        "📰 News"
    ])

    with tab1:
        show_admin_participants(game, sm, session_id)

    with tab2:
        show_admin_simulation(game, sm, session_id)

    with tab3:
        show_admin_fees(game, sm, session_id)

    with tab4:
        show_admin_assets(game, sm, session_id)

    with tab5:
        show_leaderboard(game)

    with tab6:
        show_admin_allocations(game, sm, session_id)

    with tab7:
        show_admin_performances(game, sm, session_id)

    with tab9:
        show_admin_news(game, sm, session_id)

    with tab8:
        show_admin_asset_returns(game, sm, session_id)


def show_admin_participants(game, sm, session_id):
    """Affiche les participants"""
    st.subheader("👥 Participants de la Session")

    if game.status == 'waiting':
        if st.button("🚀 DÉMARRER LE JEU", use_container_width=True):
            game.start_game()
            sm.update_game_session(session_id, status='active')
            st.success("✓ Jeu démarré!")
            st.rerun()

    participants = sm.get_session_participants(session_id)

    if not participants:
        st.info("Aucun participant pour le moment")
        return

    participants_data = []
    for p in participants:
        portfolio = game.get_student_portfolio(p['username'])
        if portfolio:
            participants_data.append({
                'Étudiant': p['username'],
                'Rejoint le': p['joined_at'],
                'Valeur': f"{portfolio.get_total_value():.0f}€",
                'Performance': f"{portfolio.get_performance():.1f}%"
            })

    if participants_data:
        df = pd.DataFrame(participants_data)
        st.dataframe(df, use_container_width=True, hide_index=True)


def show_admin_fees(game, sm, session_id):
    """Interface de configuration des frais"""
    st.subheader("💰 Configuration des Frais de Transaction")

    st.info("Ajustez les frais de transaction pour chaque actif. Ces frais sont appliqués lors des arbitrages des étudiants.")

    available_assets = get_available_assets()

    # Afficher les frais actuels
    st.markdown("### Frais Actuels")

    fees_data = []
    for asset in available_assets:
        current_fee = game.get_trading_fee(asset.name)
        fees_data.append({
            'Actif': asset.name,
            'Catégorie': asset.category,
            'Frais Actuels': f"{current_fee*100:.2f}%"
        })

    df = pd.DataFrame(fees_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("### Modifier les Frais")

    # Sélection par actif
    col1, col2 = st.columns([2, 1])

    with col1:
        selected_asset_name = st.selectbox(
            "Choisir un actif",
            options=[a.name for a in available_assets]
        )

    with col2:
        current_fee = game.get_trading_fee(selected_asset_name)
        new_fee = st.number_input(
            "Nouveau frais (%)",
            min_value=0.0,
            max_value=10.0,
            value=current_fee * 100,
            step=0.1,
            format="%.2f"
        ) / 100

        if st.button("✅ Appliquer", use_container_width=True):
            game.set_trading_fee(selected_asset_name, new_fee)
            sm.set_trading_fee(session_id, selected_asset_name, new_fee)
            st.success(f"✓ Frais mis à jour: {new_fee*100:.2f}%")
            st.rerun()

    st.markdown("---")
    st.markdown("### Préréglages Rapides")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📉 Frais Faibles (0.3%)", use_container_width=True):
            for asset in available_assets:
                game.set_trading_fee(asset.name, 0.003)
                sm.set_trading_fee(session_id, asset.name, 0.003)
            st.success("✓ Frais réglés à 0.3% pour tous les actifs")
            st.rerun()

    with col2:
        if st.button("📊 Frais Moyens (1%)", use_container_width=True):
            for asset in available_assets:
                game.set_trading_fee(asset.name, 0.01)
                sm.set_trading_fee(session_id, asset.name, 0.01)
            st.success("✓ Frais réglés à 1% pour tous les actifs")
            st.rerun()

    with col3:
        if st.button("📈 Frais Élevés (2.5%)", use_container_width=True):
            for asset in available_assets:
                game.set_trading_fee(asset.name, 0.025)
                sm.set_trading_fee(session_id, asset.name, 0.025)
            st.success("✓ Frais réglés à 2.5% pour tous les actifs")
            st.rerun()


def show_admin_assets(game, sm, session_id):
    """Interface de gestion des actifs disponibles"""
    st.subheader("📦 Gestion des Actifs Disponibles")

    st.info("💡 Contrôlez quels actifs sont disponibles pour les étudiants. Idéal pour une approche pédagogique progressive.")

    all_assets = get_available_assets()

    # Afficher le statut actuel
    st.markdown("### Actifs Actuellement Disponibles")

    current_available = game.available_asset_names
    available_count = len(current_available)
    total_count = len(all_assets)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Actifs Disponibles", f"{available_count}/{total_count}")
    with col2:
        categories = set([asset.category for asset in all_assets if asset.name in current_available])
        st.metric("Catégories", len(categories))
    with col3:
        disabled_count = total_count - available_count
        st.metric("Actifs Désactivés", disabled_count)

    st.markdown("---")

    # Grouper les actifs par catégorie
    assets_by_category = {}
    for asset in all_assets:
        if asset.category not in assets_by_category:
            assets_by_category[asset.category] = []
        assets_by_category[asset.category].append(asset)

    st.markdown("### Activer/Désactiver les Actifs")

    # Sélection par catégorie
    selected_assets = set(current_available)

    for category, assets in assets_by_category.items():
        with st.expander(f"📁 {category} ({len([a for a in assets if a.name in selected_assets])}/{len(assets)})", expanded=True):
            col_count = 2
            cols = st.columns(col_count)

            for idx, asset in enumerate(assets):
                with cols[idx % col_count]:
                    is_available = asset.name in selected_assets

                    if st.checkbox(
                        f"{asset.name}",
                        value=is_available,
                        key=f"asset_{asset.name}",
                        help=f"μ={asset.mu*100:.1f}%, σ={asset.sigma*100:.1f}%"
                    ):
                        selected_assets.add(asset.name)
                    else:
                        selected_assets.discard(asset.name)

    st.markdown("---")

    # Boutons d'action rapide
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("✅ Tous", use_container_width=True):
            selected_assets = set([asset.name for asset in all_assets])
            st.rerun()

    with col2:
        if st.button("❌ Aucun", use_container_width=True):
            selected_assets = set()
            st.rerun()

    with col3:
        if st.button("📊 Basiques Seulement", use_container_width=True, help="Actions & Obligations uniquement"):
            selected_assets = set([asset.name for asset in all_assets if asset.category in ['Equity', 'Bonds']])
            st.rerun()

    with col4:
        if st.button("🚀 Avancés", use_container_width=True, help="Crypto, PE, Commodities"):
            selected_assets = set([asset.name for asset in all_assets if asset.category in ['Crypto', 'Private Equity', 'Commodities']])
            st.rerun()

    st.markdown("---")

    # Sauvegarder les changements
    if st.button("💾 Sauvegarder les Modifications", type="primary", use_container_width=True):
        if len(selected_assets) == 0:
            st.error("⚠️ Vous devez avoir au moins un actif disponible!")
        else:
            game.set_available_assets(list(selected_assets))
            sm.update_available_assets(session_id, list(selected_assets))
            st.success(f"✓ Actifs mis à jour: {len(selected_assets)} actifs disponibles")
            st.balloons()
            st.rerun()

    st.caption("💡 Les étudiants verront uniquement les actifs activés dans leur interface d'arbitrages.")


def show_admin_allocations(game, sm, session_id):
    """Vue des allocations d'actifs par élève"""
    st.subheader("📊 Allocations d'Actifs par Élève")

    if not game.students:
        st.info("Aucun participant dans cette session")
        return

    # Pour chaque élève, afficher son allocation
    for username, portfolio in game.students.items():
        with st.expander(f"👤 {username} - Valeur: {portfolio.get_total_value():.0f}€", expanded=False):
            allocation = portfolio.get_allocation()

            if not allocation:
                st.info("Pas d'allocation (100% cash)")
                continue

            # Créer un pie chart avec Plotly
            labels = list(allocation.keys())
            values = list(allocation.values())

            fig = go.Figure(data=[go.Pie(
                labels=labels,
                values=values,
                hole=0.3,
                textinfo='label+percent',
                marker=dict(
                    colors=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                           '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
                           '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5']
                )
            )])

            fig.update_layout(
                title=f"Allocation de {username}",
                height=400,
                showlegend=True
            )

            st.plotly_chart(fig, use_container_width=True)

            # Table détaillée
            alloc_data = []
            for asset_name, pct in allocation.items():
                if asset_name == 'Cash':
                    amount = portfolio.current_capital
                else:
                    amount = portfolio.positions.get(asset_name, 0)

                alloc_data.append({
                    'Actif': asset_name,
                    'Montant': f"{amount:.0f}€",
                    'Allocation': f"{pct:.1f}%"
                })

            df = pd.DataFrame(alloc_data)
            st.dataframe(df, use_container_width=True, hide_index=True)


def show_admin_performances(game, sm, session_id):
    """Vue des performances des élèves à chaque tour"""
    st.subheader("📈 Performances des Élèves à Chaque Tour")

    if not game.students:
        st.info("Aucun participant dans cette session")
        return

    # Récupérer les snapshots de tous les élèves
    all_student_data = {}
    for username in game.students.keys():
        snapshots = sm.get_portfolio_snapshots(session_id, username)
        simulation_snapshots = [s for s in snapshots if s.get('snapshot_type') == 'simulation']
        if simulation_snapshots:
            all_student_data[username] = simulation_snapshots

    if not all_student_data:
        st.info("Aucun historique disponible")
        return

    # Créer un graphique avec une ligne par élève
    fig = go.Figure()

    colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown', 'pink', 'gray',
             'cyan', 'magenta', 'lime', 'navy', 'teal', 'maroon', 'olive']

    for i, (username, snapshots) in enumerate(all_student_data.items()):
        years = [s['year'] for s in snapshots]
        performances = [s['performance'] for s in snapshots]

        fig.add_trace(go.Scatter(
            x=years,
            y=performances,
            mode='lines+markers',
            name=username,
            line=dict(color=colors[i % len(colors)], width=3),
            marker=dict(size=8)
        ))

    fig.update_layout(
        title="Évolution des Performances par Élève",
        xaxis_title="Année",
        yaxis_title="Performance (%)",
        height=500,
        hovermode='x unified',
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02
        )
    )

    st.plotly_chart(fig, use_container_width=True)

    # Table détaillée année par année
    st.markdown("---")
    st.subheader("📋 Détail Année par Année")

    # Trouver toutes les années simulées
    all_years = set()
    for snapshots in all_student_data.values():
        for s in snapshots:
            all_years.add(s['year'])

    for year in sorted(all_years):
        with st.expander(f"Année {year}", expanded=False):
            year_data = []
            for username, snapshots in all_student_data.items():
                snapshot = next((s for s in snapshots if s['year'] == year), None)
                if snapshot:
                    year_data.append({
                        'Élève': username,
                        'Valeur': f"{snapshot['total_value']:.0f}€",
                        'Performance': f"{snapshot['performance']:+.1f}%",
                        'Cash': f"{snapshot['current_capital']:.0f}€",
                        'Frais Payés': f"{snapshot['fees_paid']:.0f}€",
                        'Faillites': snapshot.get('bankruptcies', 0)
                    })

            if year_data:
                df = pd.DataFrame(year_data)
                st.dataframe(df, use_container_width=True, hide_index=True)


def show_admin_asset_returns(game, sm, session_id):
    """Vue de l'évolution des rendements des actifs"""
    st.subheader("📉 Évolution des Rendements des Actifs")

    # Récupérer l'historique des rendements
    year_history = sm.get_year_history(session_id)

    if not year_history:
        st.info("Aucun historique de simulation disponible")
        return

    # Calculer les performances cumulées par actif
    asset_cumul_returns = {}

    for year_data in year_history:
        for asset_name, ret in year_data['asset_returns'].items():
            if asset_name not in asset_cumul_returns:
                asset_cumul_returns[asset_name] = {'years': [], 'returns': [], 'cumul': []}

            year = year_data['year']
            asset_cumul_returns[asset_name]['years'].append(year)
            asset_cumul_returns[asset_name]['returns'].append(ret * 100)

            # Calculer le rendement cumulé
            if len(asset_cumul_returns[asset_name]['cumul']) == 0:
                asset_cumul_returns[asset_name]['cumul'].append((1 + ret) * 100 - 100)
            else:
                prev_cumul = asset_cumul_returns[asset_name]['cumul'][-1]
                new_cumul = (1 + prev_cumul/100) * (1 + ret) * 100 - 100
                asset_cumul_returns[asset_name]['cumul'].append(new_cumul)

    # Onglets pour différentes vues
    view_tab1, view_tab2, view_tab3 = st.tabs([
        "📈 Performances Cumulées",
        "📊 Rendements Annuels",
        "📉 Rendements Année N vs N-1"
    ])

    with view_tab1:
        # Toggle pour mode annualisé
        show_annualized = st.checkbox("Afficher en mode annualisé", value=False, key="annualized_toggle")

        # Graphique des performances cumulées ou annualisées
        fig_cumul = go.Figure()

        colors = ['red', 'green', 'blue', 'orange', 'purple', 'brown', 'pink', 'gray',
                 'cyan', 'magenta', 'lime', 'navy', 'teal', 'maroon', 'olive', 'coral', 'gold']

        for i, (asset_name, data) in enumerate(sorted(asset_cumul_returns.items())):
            if show_annualized:
                # Calculer le rendement annualisé
                annualized_returns = []
                for idx, year in enumerate(data['years']):
                    if idx == 0:
                        annualized_returns.append(data['returns'][idx])
                    else:
                        # Formule: ((1 + cumul/100)^(1/n_years) - 1) * 100
                        cumul_val = data['cumul'][idx]
                        n_years = idx + 1
                        annualized = (((1 + cumul_val/100) ** (1/n_years)) - 1) * 100
                        annualized_returns.append(annualized)

                y_data = annualized_returns
                title_suffix = "Annualisées"
                y_label = "Rendement Annualisé (%)"
            else:
                y_data = data['cumul']
                title_suffix = "Cumulées"
                y_label = "Performance Cumulée (%)"

            fig_cumul.add_trace(go.Scatter(
                x=data['years'],
                y=y_data,
                mode='lines+markers',
                name=asset_name,
                line=dict(color=colors[i % len(colors)], width=2),
                marker=dict(size=6)
            ))

        fig_cumul.update_layout(
            title=f"Performances {title_suffix} des Actifs",
            xaxis_title="Année",
            yaxis_title=y_label,
            height=600,
            hovermode='x unified',
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02
            )
        )

        st.plotly_chart(fig_cumul, use_container_width=True)

    with view_tab2:
        # Table des rendements annuels
        st.markdown("### Rendements Annuels par Actif")

        for year_data in year_history:
            with st.expander(f"Année {year_data['year']} - {year_data.get('scenario_applied', 'N/A')}", expanded=False):
                # Afficher les chocs macro si disponibles
                if 'pib_shock' in year_data:
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Choc PIB", f"{year_data['pib_shock']*100:+.1f}%")
                    with col2:
                        st.metric("Choc Inflation", f"{year_data['inf_shock']*100:+.1f}%")
                    with col3:
                        st.metric("Choc Taux", f"{year_data['rates_shock']*100:+.1f}%")
                    with col4:
                        equity = year_data.get('equity_shock', 0.0)
                        st.metric("Choc Equity", f"{equity*100:+.1f}%")

                # Table des rendements
                returns_data = []
                for asset_name, ret in sorted(year_data['asset_returns'].items()):
                    returns_data.append({
                        'Actif': asset_name,
                        'Rendement': f"{ret*100:+.2f}%"
                    })

                df = pd.DataFrame(returns_data)
                st.dataframe(df, use_container_width=True, hide_index=True)

    with view_tab3:
        # Graphique rendements année N vs N-1
        st.markdown("### Évolution des Rendements Année après Année")
        st.caption("Ce graphique montre le rendement de chaque année comparé à l'année précédente (à partir de l'année 1)")

        if len(year_history) < 2:
            st.info("Au moins 2 années simulées nécessaires pour ce graphique")
        else:
            fig_yoy = go.Figure()

            colors = ['red', 'green', 'blue', 'orange', 'purple', 'brown', 'pink', 'gray',
                     'cyan', 'magenta', 'lime', 'navy', 'teal', 'maroon', 'olive', 'coral', 'gold']

            for i, (asset_name, data) in enumerate(sorted(asset_cumul_returns.items())):
                if len(data['returns']) >= 2:
                    # Prendre les rendements à partir de l'année 1
                    years_yoy = data['years'][1:]  # Années 1, 2, 3, ...
                    returns_yoy = data['returns'][1:]  # Rendements de ces années

                    fig_yoy.add_trace(go.Scatter(
                        x=years_yoy,
                        y=returns_yoy,
                        mode='lines+markers',
                        name=asset_name,
                        line=dict(color=colors[i % len(colors)], width=2),
                        marker=dict(size=6)
                    ))

            # Ligne à 0% pour référence
            if year_history:
                years_range = [y['year'] for y in year_history[1:]]
                fig_yoy.add_trace(go.Scatter(
                    x=years_range,
                    y=[0] * len(years_range),
                    mode='lines',
                    name='0%',
                    line=dict(color='black', width=1, dash='dash'),
                    showlegend=False
                ))

            fig_yoy.update_layout(
                title="Rendements Annuels par Actif (Année N)",
                xaxis_title="Année",
                yaxis_title="Rendement Annuel (%)",
                height=600,
                hovermode='x unified',
                legend=dict(
                    orientation="v",
                    yanchor="top",
                    y=1,
                    xanchor="left",
                    x=1.02
                )
            )

            st.plotly_chart(fig_yoy, use_container_width=True)


def show_admin_news(game, sm, session_id):
    """Interface de gestion des news pour l'admin"""
    st.subheader("📰 Gestion des News & Journal")

    # Onglets pour différentes sections
    news_tab1, news_tab2, news_tab3 = st.tabs([
        "➕ Publier une News",
        "📚 Bibliothèque de News",
        "📜 Historique"
    ])

    with news_tab1:
        st.markdown("### ✍️ Rédiger une News Manuelle")

        col1, col2 = st.columns([1, 3])

        with col1:
            news_year = st.number_input(
                "Année",
                min_value=0,
                max_value=game.current_year,
                value=game.current_year,
                step=1
            )

        with col2:
            news_title = st.text_input("Titre de la news", placeholder="Ex: La Fed annonce une hausse des taux")

        news_content = st.text_area(
            "Contenu de la news (2-3 phrases)",
            placeholder="Rédigez le contenu de l'actualité...",
            height=150
        )

        if st.button("📤 Publier la News", use_container_width=True, type="primary"):
            if news_title and news_content:
                sm.add_news(session_id, news_year, news_title, news_content)
                st.success(f"✓ News publiée pour l'année {news_year}")
                st.rerun()
            else:
                st.error("Veuillez remplir le titre et le contenu")

    with news_tab2:
        st.markdown("### 📚 Suggestions de News par Scénario")
        st.caption("Sélectionnez un scénario pour voir les news suggérées, puis publiez-les")

        # Récupérer l'historique des années pour suggérer des news
        year_history = sm.get_year_history(session_id)

        if year_history:
            # Prendre les chocs de la dernière année
            last_year_data = year_history[-1]
            pib_shock = last_year_data.get('pib_shock', 0.0)
            inf_shock = last_year_data.get('inf_shock', 0.0)
            rates_shock = last_year_data.get('rates_shock', 0.0)
            equity_shock_hist = last_year_data.get('equity_shock', 0.0)

            st.info(f"💡 Derniers chocs: PIB {pib_shock*100:+.1f}%, INF {inf_shock*100:+.1f}%, RATES {rates_shock*100:+.1f}%, EQUITY {equity_shock_hist*100:+.1f}%")

            # Obtenir suggestions
            suggestions = get_news_suggestions(pib_shock, inf_shock, rates_shock)

            if suggestions:
                st.markdown(f"**📌 {len(suggestions)} news suggérées:**")

                for idx, news in enumerate(suggestions):
                    with st.expander(f"News {idx+1}: {news['title']}", expanded=False):
                        st.markdown(f"**Titre:** {news['title']}")
                        st.write(news['content'])

                        year_for_news = st.number_input(
                            "Publier pour l'année",
                            min_value=0,
                            max_value=game.current_year,
                            value=game.current_year,
                            step=1,
                            key=f"year_news_{idx}"
                        )

                        if st.button(f"📤 Publier cette news", key=f"publish_{idx}"):
                            sm.add_news(session_id, year_for_news, news['title'], news['content'])
                            st.success(f"✓ News publiée pour l'année {year_for_news}")
                            st.rerun()
            else:
                st.warning("Aucune suggestion disponible pour ces chocs macro")
        else:
            st.info("Simulez au moins une année pour obtenir des suggestions de news")

        st.markdown("---")
        st.markdown("### 📖 Bibliothèque Complète")
        st.caption("Toutes les news disponibles par scénario")

        for scenario_name, news_list in NEWS_LIBRARY.items():
            with st.expander(f"📁 {scenario_name} ({len(news_list)} news)", expanded=False):
                for idx, news in enumerate(news_list):
                    st.markdown(f"**{idx+1}. {news['title']}**")
                    st.write(news['content'])
                    st.markdown("---")

    with news_tab3:
        st.markdown("### 📜 Historique des News Publiées")

        news_history = sm.get_all_news_history(session_id)

        if not news_history:
            st.info("Aucune news publiée pour le moment")
        else:
            total_news = sum(len(news_list) for news_list in news_history.values())
            st.write(f"**Total: {total_news} news publiées**")

            for year in sorted(news_history.keys(), reverse=True):
                news_list = news_history[year]

                with st.expander(f"📅 Année {year} - {len(news_list)} news", expanded=(year == game.current_year)):
                    for news in news_list:
                        st.markdown(f"### {news['title']}")
                        st.write(news['content'])
                        st.caption(f"*Publié le {news['created_at']}*")
                        st.markdown("---")


def show_admin_simulation(game, sm, session_id):
    """Interface de simulation avec MODÈLE FACTORIEL + AR(1)"""
    st.subheader("🎯 Simulation Annuelle (Modèle Factoriel Cohérent)")

    if game.status != 'active':
        st.warning("Le jeu doit être en mode 'active' pour simuler")
        return

    # Afficher l'état macro actuel (AR(1) avec mémoire)
    st.markdown("#### 📊 État Macroéconomique Actuel")
    macro_cols = st.columns(4)
    with macro_cols[0]:
        st.metric(
            "📈 PIB",
            f"{game.macro_state.gdp_level*100:.1f}%",
            delta=f"{(game.macro_state.gdp_level - game.macro_state.mu_gdp)*100:+.1f}%" if game.current_year > 0 else None
        )
    with macro_cols[1]:
        st.metric(
            "🔥 Inflation",
            f"{game.macro_state.inf_level*100:.1f}%",
            delta=f"{(game.macro_state.inf_level - game.macro_state.mu_inf)*100:+.1f}%" if game.current_year > 0 else None
        )
    with macro_cols[2]:
        st.metric(
            "💵 Taux",
            f"{game.macro_state.rates_level*100:.1f}%",
            delta=f"{(game.macro_state.rates_level - game.macro_state.mu_rates)*100:+.1f}%" if game.current_year > 0 else None
        )
    with macro_cols[3]:
        st.metric(
            "📊 Facteur Equity",
            f"{game.macro_state.equity_factor*100:+.1f}%",
            delta=None
        )
    st.caption("💡 Ces niveaux évoluent avec un processus AR(1) - les chocs ont une mémoire et reviennent vers la moyenne")
    st.markdown("---")

    st.markdown(f"### Configuration Macroéconomique pour l'Année {game.current_year + 1}")

    # Section 1: Presets rapides
    st.markdown("#### 📋 Préréglages Macroéconomiques")
    preset_cols = st.columns(4)

    # Initialiser les valeurs dans session_state si nécessaire
    if 'pib_shock' not in st.session_state:
        st.session_state.pib_shock = 0.0
    if 'inf_shock' not in st.session_state:
        st.session_state.inf_shock = 0.0
    if 'rates_shock' not in st.session_state:
        st.session_state.rates_shock = 0.0
    if 'equity_shock' not in st.session_state:
        st.session_state.equity_shock = 0.0
    if 'scenario_label' not in st.session_state:
        st.session_state.scenario_label = "Custom"

    for i, (preset_name, preset_data) in enumerate(PRESETS_ADMIN.items()):
        with preset_cols[i]:
            if st.button(preset_name, use_container_width=True):
                st.session_state.pib_shock = preset_data['pib']
                st.session_state.inf_shock = preset_data['inf']
                st.session_state.rates_shock = preset_data['rates']
                st.session_state.equity_shock = preset_data.get('equity', 0.0)
                st.session_state.scenario_label = preset_name
                st.rerun()

    st.caption("💡 Cliquez sur un préréglage pour charger ses valeurs dans les curseurs ci-dessous")
    st.markdown("---")

    # Section 2: Curseurs personnalisés
    st.markdown("#### 🎚️ Curseurs Personnalisés")
    st.caption("Ajustez manuellement les quatre facteurs macro (valeurs en décimal)")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        pib_shock = st.slider(
            "📈 Choc PIB",
            min_value=-0.10,
            max_value=0.10,
            value=st.session_state.pib_shock,
            step=0.01,
            format="%.2f",
            help="Choc de croissance du PIB (ex: 0.03 = +3%, -0.04 = -4%)"
        )
        st.caption(f"**{pib_shock*100:+.1f}%** choc PIB")

    with col2:
        inf_shock = st.slider(
            "🔥 Choc Inflation",
            min_value=-0.05,
            max_value=0.15,
            value=st.session_state.inf_shock,
            step=0.01,
            format="%.2f",
            help="Choc d'inflation (ex: 0.08 = +8%)"
        )
        st.caption(f"**{inf_shock*100:+.1f}%** choc inflation")

    with col3:
        rates_shock = st.slider(
            "💵 Choc Taux",
            min_value=-0.05,
            max_value=0.10,
            value=st.session_state.rates_shock,
            step=0.005,
            format="%.3f",
            help="Choc de taux d'intérêt (ex: 0.05 = +500 bps, -0.03 = -300 bps)"
        )
        st.caption(f"**{rates_shock*100:+.1f}%** ({rates_shock*10000:.0f} bps)")

    with col4:
        equity_shock = st.slider(
            "📊 Choc Equity",
            min_value=-0.50,
            max_value=0.30,
            value=st.session_state.equity_shock,
            step=0.05,
            format="%.2f",
            help="Choc marché actions global (ex: 0.10 = +10%, -0.35 = -35% en crise)"
        )
        st.caption(f"**{equity_shock*100:+.1f}%** marché actions")

    # Mise à jour du session_state
    st.session_state.pib_shock = pib_shock
    st.session_state.inf_shock = inf_shock
    st.session_state.rates_shock = rates_shock
    st.session_state.equity_shock = equity_shock

    # Label personnalisé
    scenario_label = st.text_input(
        "🏷️ Label du scénario (optionnel)",
        value=st.session_state.scenario_label,
        help="Nom descriptif pour l'historique"
    )
    st.session_state.scenario_label = scenario_label

    st.markdown("---")

    # Section 3: Bouton de simulation
    col_sim, col_end = st.columns([3, 1])

    with col_sim:
        if st.button("⚡ SIMULER ANNÉE", use_container_width=True, type="primary"):
            with st.spinner("Simulation en cours..."):
                # Simuler avec le modèle factoriel
                returns = game.simulate_year(
                    pib_shock=pib_shock,
                    inf_shock=inf_shock,
                    rates_shock=rates_shock,
                    equity_shock=equity_shock,
                    scenario_label=scenario_label
                )

                # Sauvegarder historique avec les chocs macro
                macro_shocks = {
                    'pib_shock': pib_shock,
                    'inf_shock': inf_shock,
                    'rates_shock': rates_shock,
                    'equity_shock': equity_shock
                }
                sm.save_year_history(session_id, game.current_year - 1, scenario_label, returns, macro_shocks)
                # Sauvegarder état macro pour persistence AR(1)
                import json
                macro_state_json = json.dumps(game.macro_state.to_dict())
                sm.update_game_session(session_id, current_year=game.current_year, macro_state_json=macro_state_json)

                # Sauvegarder snapshots
                for username in game.students.keys():
                    portfolio = game.get_student_portfolio(username)
                    snapshot = portfolio.snapshot(game.current_year - 1)
                    sm.save_portfolio_snapshot(session_id, username, game.current_year - 1, snapshot)

                st.success(f"✓ Année {game.current_year - 1} simulée avec le modèle factoriel!")
                st.balloons()
                st.rerun()

    with col_end:
        if st.button("🏁 Terminer le jeu", use_container_width=True):
            game.end_game()
            sm.update_game_session(session_id, status='ended')
            st.success("Jeu terminé!")
            st.rerun()

    # Section 4: Résultats de la dernière simulation
    history = sm.get_year_history(session_id)
    if history:
        st.markdown("---")
        st.subheader("📊 Dernière Simulation")
        last = history[-1]
        st.write(f"**Année:** {last['year']} | **Scénario:** {last['scenario_applied']}")

        returns_data = []
        for asset_name, ret in last['asset_returns'].items():
            returns_data.append({
                'Actif': asset_name,
                'Rendement': f"{ret*100:.2f}%"
            })

        if returns_data:
            df = pd.DataFrame(returns_data)
            st.dataframe(df, use_container_width=True, hide_index=True)


# ==========================================
# MAIN
# ==========================================

if st.session_state.username is None:
    show_login_page()
else:
    if st.session_state.user_role == 'admin':
        show_admin_interface()
    else:
        show_student_interface()
