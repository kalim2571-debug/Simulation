# 🔧 Refactoring: Modèle Factoriel Cohérent

**Date:** 27 janvier 2025
**Objectif:** Corriger les incohérences du modèle factoriel actuel

---

## 🎯 Problèmes Identifiés

### A. Pas de facteur equity global
- **Symptôme:** MSCI World peut monter alors que Tech US et Value Europe baissent
- **Cause:** Pas de facteur commun pour synchroniser les actions
- **Solution:** Ajouter `beta_equity` (facteur "risk-on")

### B. Chocs i.i.d. (pas de mémoire)
- **Symptôme:** PIB +5% puis -6% puis +4% (incohérent)
- **Cause:** Chocs indépendants année après année
- **Solution:** Processus AR(1) avec mean-reversion

### C. Chocs macro non corrélés
- **Symptôme:** PIB +5% avec INF -2% (impossible)
- **Cause:** Tirages indépendants
- **Solution:** Matrice de corrélation des chocs macro

### D. Obligations sans duration
- **Symptôme:** Gov Bonds +15% sans baisse de taux
- **Cause:** Pas de lien mécanique taux→prix
- **Solution:** Formule `return ≈ yield - duration × Δrates + noise`

---

## ✅ Solutions à Implémenter

### Solution A: Facteur Equity Global

#### Modification 1: Classe Asset ([engine.py:29-43](engine.py#L29-L43))

```python
def __init__(self, name, category, sub_category, exp_return, volatility,
             beta_gdp=0.0, beta_inf=0.0, beta_rates=0.0, beta_equity=0.0,  # ← NOUVEAU
             duration=0.0,  # ← NOUVEAU pour obligations
             liquidity_lockup=0, exit_penalty=0.0):
    self.name = name
    self.category = category
    self.sub_category = sub_category
    self.mu = exp_return
    self.sigma = volatility
    self.beta_gdp = beta_gdp
    self.beta_inf = beta_inf
    self.beta_rates = beta_rates
    self.beta_equity = beta_equity  # ← NOUVEAU
    self.duration = duration  # ← NOUVEAU
    self.lockup = liquidity_lockup
    self.penalty = exit_penalty
```

#### Modification 2: Actifs dans market.py

**Actions (beta_equity élevé):**
```python
Asset("ETF World (MSCI)", "Equity", "ETF", 0.07, 0.15,
      beta_gdp=1.0, beta_inf=0.10, beta_rates=-0.45,
      beta_equity=1.0),  # ← Facteur commun

Asset("Actions Tech US", "Equity", "Direct", 0.10, 0.25,
      beta_gdp=1.2, beta_inf=0.00, beta_rates=-0.70,
      beta_equity=1.2),  # ← Plus sensible

Asset("Actions Value Europe", "Equity", "Direct", 0.06, 0.16,
      beta_gdp=0.9, beta_inf=0.25, beta_rates=-0.25,
      beta_equity=0.9),  # ← Moins sensible
```

**Obligations (duration):**
```python
Asset("Gov Bonds US (10Y)", "Bonds", "Souverain AAA", 0.035, 0.06,
      beta_gdp=-0.10, beta_inf=-0.60, beta_rates=-0.90,
      beta_equity=0.0, duration=8.5),  # ← Duration 10Y

Asset("Corp Bonds IG", "Bonds", "Corporate IG", 0.045, 0.06,
      beta_gdp=0.30, beta_inf=-0.20, beta_rates=-0.60,
      beta_equity=0.20, duration=5.0),  # ← Duration plus courte + un peu d'equity

Asset("High Yield Bonds", "Bonds", "Corporate HY", 0.065, 0.13,
      beta_gdp=0.70, beta_inf=-0.10, beta_rates=-0.40,
      beta_equity=0.50, duration=3.0),  # ← Forte expo equity (crédit)
```

**Crypto:**
```python
Asset("Bitcoin", "Crypto", "BTC", 0.15, 0.70,
      beta_gdp=0.50, beta_inf=0.25, beta_rates=-0.90,
      beta_equity=0.80),  # ← Fort "risk-on"

Asset("Ethereum", "Crypto", "ETH", 0.20, 0.80,
      beta_gdp=0.50, beta_inf=0.10, beta_rates=-1.00,
      beta_equity=0.90),  # ← Encore plus "risk-on"
```

**Or (anti-equity):**
```python
Asset("Gold Bullion", "Metals", "Or Physique", 0.045, 0.15,
      beta_gdp=-0.20, beta_inf=0.80, beta_rates=-0.35,
      beta_equity=-0.15),  # ← Safe haven (négatif)
```

---

### Solution B: Processus AR(1) avec Mean-Reversion

#### Modification: game_engine.py

**Nouvelle classe pour l'état macro:**
```python
class MacroState:
    """État macroéconomique avec mémoire (AR(1))"""

    def __init__(self):
        # Valeurs actuelles
        self.gdp_level = 0.02      # Niveau de croissance du PIB (2% long-terme)
        self.inf_level = 0.02      # Niveau d'inflation (2% cible)
        self.rates_level = 0.03    # Niveau des taux (3%)
        self.equity_factor = 0.0   # Facteur equity (centré 0)

        # Paramètres AR(1): x(t) = mu + phi*(x(t-1) - mu) + shock
        self.mu_gdp = 0.02
        self.mu_inf = 0.02
        self.mu_rates = 0.03
        self.mu_equity = 0.0

        self.phi_gdp = 0.50      # Persistance GDP
        self.phi_inf = 0.60      # Persistance inflation
        self.phi_rates = 0.80    # Persistance taux (très inerte)
        self.phi_equity = 0.30   # Persistance equity factor

    def update(self, shock_gdp, shock_inf, shock_rates, shock_equity):
        """
        Met à jour l'état macro avec les chocs.

        Returns:
            dict: Variations (pour beta)
        """
        # AR(1) update
        new_gdp = self.mu_gdp + self.phi_gdp * (self.gdp_level - self.mu_gdp) + shock_gdp
        new_inf = self.mu_inf + self.phi_inf * (self.inf_level - self.mu_inf) + shock_inf
        new_rates = self.mu_rates + self.phi_rates * (self.rates_level - self.mu_rates) + shock_rates
        new_equity = self.mu_equity + self.phi_equity * self.equity_factor + shock_equity

        # Calculer les variations (ce qu'on passe aux betas)
        delta_gdp = new_gdp - self.mu_gdp
        delta_inf = new_inf - self.mu_inf
        delta_rates = new_rates - self.rates_level  # Variation de taux (pour duration)
        equity_shock = new_equity

        # Mettre à jour l'état
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
```

**Ajouter MacroState à GameSession:**
```python
class GameSession:
    def __init__(self, ...):
        # ... code existant ...
        self.macro_state = MacroState()  # ← NOUVEAU
```

---

### Solution C: Corrélations entre Chocs Macro

#### Modification: simulate_annual_returns()

**Matrice de corrélation des chocs macro:**
```python
# Corrélations entre chocs (GDP, INF, RATES, EQUITY)
macro_corr = np.array([
    [1.00,  0.30, -0.20,  0.60],  # GDP: corrélé positivement avec equity
    [0.30,  1.00,  0.50,  0.00],  # INF: corrélé avec rates (BC réagit)
    [-0.20, 0.50,  1.00, -0.40],  # RATES: négatif avec GDP et equity
    [0.60,  0.00, -0.40,  1.00]   # EQUITY: fort lien avec GDP, négatif avec rates
])

# Cholesky
L_macro = np.linalg.cholesky(macro_corr)

# Tirer chocs indépendants
Z_indep = np.random.standard_normal(4)

# Corrélés
Z_corr = L_macro @ Z_indep

shock_gdp = Z_corr[0] * 0.025      # Std 2.5%
shock_inf = Z_corr[1] * 0.015      # Std 1.5%
shock_rates = Z_corr[2] * 0.020    # Std 2%
shock_equity = Z_corr[3] * 0.15    # Std 15%
```

**Nouvelle interface admin:**
```python
# Au lieu de curseurs PIB/INF/RATES absolus, l'admin choisit:
# 1. Un preset (qui fixe des chocs)
# 2. OU laisse le modèle générer des chocs aléatoires corrélés
# 3. OU ajuste des "multipliers" sur les chocs

# Preset Goldilocks:
presets["Goldilocks"] = {
    "shock_gdp": +0.01,      # Choc positif GDP
    "shock_inf": 0.0,        # Inflation stable
    "shock_rates": 0.0,      # Taux stable
    "shock_equity": +0.10    # Risk-on
}

# Preset Stagflation:
presets["Stagflation"] = {
    "shock_gdp": -0.04,
    "shock_inf": +0.06,
    "shock_rates": +0.03,
    "shock_equity": -0.20    # Risk-off
}
```

---

### Solution D: Duration pour Obligations

#### Modification: simulate_annual_returns()

**Calcul spécial pour obligations:**
```python
def simulate_annual_returns(asset_names, macro_deltas, macro_state):
    """
    Args:
        macro_deltas (dict): {'delta_gdp', 'delta_inf', 'delta_rates', 'equity_shock'}
        macro_state (MacroState): État macro actuel
    """
    returns = {}

    for asset in assets:
        # Impact macro standard
        macro_impact = (
            asset.beta_gdp * macro_deltas['delta_gdp'] +
            asset.beta_inf * macro_deltas['delta_inf'] +
            asset.beta_rates * macro_deltas['delta_rates'] +
            asset.beta_equity * macro_deltas['equity_shock']
        )

        # SPECIAL: Obligations avec duration
        if asset.category == "Bonds" and asset.duration > 0:
            # Formule prix obligation: ΔP/P ≈ -Duration × Δrates
            duration_effect = -asset.duration * macro_deltas['delta_rates']

            # Return total = yield + effet duration + spread + noise
            yield_component = macro_state.rates_level  # Carry
            spread_component = asset.beta_gdp * macro_deltas['delta_gdp']  # Crédit spread

            annual_return = yield_component + duration_effect + spread_component + noise
        else:
            # Actifs non-obligations: formule standard
            annual_return = asset.mu + macro_impact + noise

        # Borner
        annual_return = max(-0.90, min(3.0, annual_return))
        returns[asset.name] = annual_return

    return returns
```

---

## 📊 Exemple Complet d'une Simulation

### Année 0 (initialisation)
```
Macro State:
  GDP: 2.0%
  INF: 2.0%
  RATES: 3.0%
  EQUITY: 0.0
```

### Année 1: Preset Goldilocks
```
Admin choisit: Goldilocks

Chocs appliqués (avec corrélations):
  shock_gdp    = +0.01
  shock_inf    = 0.0
  shock_rates  = 0.0
  shock_equity = +0.10

AR(1) update:
  GDP(1)   = 0.02 + 0.50*(0.02 - 0.02) + 0.01 = 3.0%
  INF(1)   = 0.02 + 0.60*(0.02 - 0.02) + 0.0  = 2.0%
  RATES(1) = 0.03 + 0.80*(0.03 - 0.03) + 0.0  = 3.0%
  EQUITY(1)= 0.0  + 0.30*0.0 + 0.10 = +10%

Deltas pour betas:
  delta_gdp = 3.0% - 2.0% = +1.0%
  delta_inf = 2.0% - 2.0% = 0.0%
  delta_rates = 3.0% - 3.0% = 0.0%
  equity_shock = +10%

Rendements:
  ETF World = 7% + 1.0*1% + 0.10*0% + (-0.45)*0% + 1.0*10% + noise
            = 7% + 1% + 10% + noise ≈ 18% + noise

  Gov Bonds US (10Y):
    yield = 3.0%
    duration_effect = -8.5 × 0.0% = 0%
    spread = -0.10 × 1% = -0.1%
    return = 3.0% + 0% - 0.1% + noise ≈ 2.9% + noise

  Bitcoin = 15% + 0.50*1% + 0.25*0% + (-0.90)*0% + 0.80*10% + noise
          = 15% + 0.5% + 8% + noise ≈ 23.5% + noise

  Gold = 4.5% + (-0.20)*1% + 0.80*0% + (-0.35)*0% + (-0.15)*10% + noise
       = 4.5% - 0.2% - 1.5% + noise ≈ 2.8% + noise
```

### Année 2: Continuation (mémoire AR(1))
```
Chocs aléatoires corrélés générés:
  shock_gdp = -0.005 (légère baisse)
  shock_inf = +0.010 (inflation monte)
  shock_rates = +0.015 (BC réagit)
  shock_equity = -0.05 (risk-off léger)

AR(1) update (avec phi):
  GDP(2)   = 0.02 + 0.50*(0.03 - 0.02) + (-0.005) = 2.0%  (mean-reversion)
  INF(2)   = 0.02 + 0.60*(0.02 - 0.02) + 0.010 = 3.0%
  RATES(2) = 0.03 + 0.80*(0.03 - 0.03) + 0.015 = 4.5%
  EQUITY(2)= 0.0 + 0.30*0.10 + (-0.05) = -2%

Deltas:
  delta_gdp = 2.0% - 2.0% = 0.0%
  delta_inf = 3.0% - 2.0% = +1.0%
  delta_rates = 4.5% - 3.0% = +1.5%  ← Hausse des taux!
  equity_shock = -2%  ← Risk-off

Rendements:
  ETF World = 7% + 1.0*0% + 0.10*1% + (-0.45)*1.5% + 1.0*(-2%) + noise
            = 7% + 0.1% - 0.675% - 2% + noise ≈ 4.4% + noise

  Gov Bonds US:
    yield = 4.5%
    duration_effect = -8.5 × 1.5% = -12.75%  ← Forte baisse!
    spread = -0.10 × 0% = 0%
    return = 4.5% - 12.75% + noise ≈ -8.25% + noise  ← Cohérent!

  Bitcoin = 15% + 0.50*0% + 0.25*1% + (-0.90)*1.5% + 0.80*(-2%) + noise
          = 15% + 0.25% - 1.35% - 1.6% + noise ≈ 12.3% + noise

  Gold = 4.5% + (-0.20)*0% + 0.80*1% + (-0.35)*1.5% + (-0.15)*(-2%) + noise
       = 4.5% + 0.8% - 0.525% + 0.3% + noise ≈ 5.1% + noise  ← Hedge inflation
```

---

## 🎨 Nouvelle Interface Admin

### Onglet Simulation

**Mode 1: Presets (simplifié)**
```
[Goldilocks] [Stagflation] [Pivot] [Crise]

↓ Applique des chocs prédéfinis cohérents
```

**Mode 2: Chocs Personnalisés (avancé)**
```
🎚️ Choc GDP:    [-0.05 ←→ +0.05]   (shock, pas niveau)
🎚️ Choc INF:    [-0.03 ←→ +0.08]
🎚️ Choc RATES:  [-0.04 ←→ +0.06]
🎚️ Choc EQUITY: [-0.30 ←→ +0.30]

💡 Les chocs sont corrélés automatiquement
💡 L'état macro a de la mémoire (AR(1))
```

**Mode 3: Aléatoire (simulation réaliste)**
```
☑️ Générer des chocs aléatoires corrélés

[SIMULER ANNÉE]
```

---

## 🔄 Flux de Simulation Mis à Jour

```python
def simulate_year(self, shocks=None, mode="preset"):
    """
    Simule une année.

    Args:
        shocks (dict): {'shock_gdp', 'shock_inf', 'shock_rates', 'shock_equity'}
                       Si None, génère aléatoire
        mode (str): 'preset', 'custom', 'random'
    """
    # 1. Générer ou récupérer les chocs
    if shocks is None:
        # Générer chocs corrélés
        shocks = self._generate_correlated_shocks()

    # 2. Mettre à jour l'état macro (AR(1))
    macro_deltas = self.macro_state.update(
        shocks['shock_gdp'],
        shocks['shock_inf'],
        shocks['shock_rates'],
        shocks['shock_equity']
    )

    # 3. Simuler rendements des actifs
    all_assets = get_available_assets()
    all_asset_names = [a.name for a in all_assets]

    asset_returns = simulate_annual_returns(
        all_asset_names,
        macro_deltas,
        self.macro_state
    )

    # 4. Appliquer aux portfolios
    for student in self.students.values():
        student.apply_returns(asset_returns)
        student.check_bankruptcy()
        student.history.append(student.snapshot(self.current_year))

    # 5. Sauvegarder historique avec état macro
    self.year_history.append({
        'year': self.current_year,
        'shocks': shocks,
        'macro_state': {
            'gdp': self.macro_state.gdp_level,
            'inf': self.macro_state.inf_level,
            'rates': self.macro_state.rates_level,
            'equity': self.macro_state.equity_factor
        },
        'asset_returns': asset_returns,
        'timestamp': datetime.now().isoformat()
    })

    self.current_year += 1
    return asset_returns
```

---

## ✅ Checklist d'Implémentation

### Phase 1: Facteur Equity (A)
- [ ] Modifier `Asset.__init__()` pour ajouter `beta_equity` et `duration`
- [ ] Mettre à jour tous les actifs dans market.py avec `beta_equity`
- [ ] Modifier `simulate_annual_returns()` pour inclure `beta_equity`

### Phase 2: AR(1) (B)
- [ ] Créer classe `MacroState` avec processus AR(1)
- [ ] Ajouter `macro_state` à `GameSession`
- [ ] Modifier `simulate_year()` pour utiliser `macro_state.update()`

### Phase 3: Corrélations Chocs (C)
- [ ] Implémenter `_generate_correlated_shocks()` avec matrice corrélation
- [ ] Modifier presets pour inclure `shock_equity`

### Phase 4: Duration (D)
- [ ] Ajouter `duration` aux actifs obligations
- [ ] Implémenter logique spéciale bonds dans `simulate_annual_returns()`
- [ ] Tester: hausse taux → baisse prix bonds

### Phase 5: Interface
- [ ] Mettre à jour interface admin simulation
- [ ] Afficher état macro dans dashboards
- [ ] Sauvegarder état macro dans DB

---

## 📊 Résultats Attendus

### Cohérences Retrouvées

✅ **Actions synchronisées:**
- Si equity_shock = +10%, TOUS les actions montent ensemble
- World, Tech, Value varient selon leur beta_equity mais même direction

✅ **Macro cohérente:**
- GDP +5% → inflation monte aussi (corrélation positive)
- Inflation +8% → taux montent (BC réagit)
- Taux montent → equity baisse (corrélation négative)

✅ **Obligations réalistes:**
- Taux +1.5% → Gov 10Y baisse de ~12.75% (duration 8.5)
- Taux stables → Gov 10Y rend ~3% (yield)

✅ **Persistence:**
- GDP ne fait pas yoyo (AR(1) avec phi=0.5)
- Taux bougent lentement (phi=0.8)

---

**Prêt à implémenter!** 🚀

Les modifications sont importantes mais critiques pour la cohérence du modèle.
