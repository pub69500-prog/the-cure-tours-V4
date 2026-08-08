# STATICURE V4 — The Cure Live Archive

Reconstruction complète du site `the-cure-tours` avec données découplées du HTML et synchronisation quotidienne.

## Principes

- **Cure Concerts Guide est la source historique prioritaire** : dates, lieux et corrections anciennes sont mises à jour en premier depuis `cure-concerts.de`.
- **setlist.fm est une source secondaire** pour compléter rapidement les concerts/setlists récents. Une donnée de lieu déjà fournie par Cure Concerts Guide n'est pas écrasée par setlist.fm.
- Les données canoniques sont dans `data/concerts.json` et `data/setlists.json`, et ne sont plus incluses dans un bloc JSON de plusieurs Mo dans `index.html`.
- Chaque modification automatique est historisée dans `data/changelog.json`.
- Le site est statique, responsive et compatible GitHub Pages.
- Un export Excel est régénéré à chaque build.

## Arborescence

```text
.github/workflows/pages.yml      synchronisation + tests + publication quotidienne
data/concerts.json              concerts consolidés
data/setlists.json              setlists détaillées
data/changelog.json             journal de modifications
data/state.json                 état de synchronisation
scripts/seed_data.py            import initial V3 Excel/CSV
scripts/sync_cureguide.py       source principale
scripts/sync_setlistfm.py       source secondaire
scripts/build_site.py           génération de dist/
scripts/export_excel.py         export Excel
scripts/run_pipeline.py         orchestration locale
site/                            interface web
source/                          sources V3 originales
tests/                           contrôles de cohérence
```

## Installation locale

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_pipeline.py --offline
python -m http.server 8000 -d dist
```

Puis ouvrir `http://localhost:8000`.

## Synchronisation réseau

```bash
export SETLISTFM_API_KEY='...'
python scripts/run_pipeline.py
```

Par défaut, le synchroniseur Cure Concerts Guide consulte `robots.txt`. Le rythme est volontairement modéré et le script ne relit quotidiennement que les pages susceptibles d'avoir changé (page Updates + année courante/précédente).

## GitHub Pages

1. Copier ce projet dans le dépôt.
2. Dans **Settings → Secrets and variables → Actions**, créer `SETLISTFM_API_KEY`.
3. Dans **Settings → Pages**, choisir **GitHub Actions**.
4. Lancer une première fois le workflow manuellement.

Le workflow s'exécute ensuite tous les jours à 04:17 UTC, enregistre les données modifiées dans Git et déploie `dist/`.

## Règles de fusion

- Cure Concerts Guide gagne pour l'historique et les champs de lieu déjà renseignés.
- setlist.fm remplit uniquement les champs récents manquants et peut fournir une setlist communautaire lorsque le Guide n'en a pas de confirmée.
- Les valeurs vides n'écrasent jamais une valeur existante.
- Toute modification est tracée avec ancienne valeur, nouvelle valeur, type et source.
