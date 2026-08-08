# STATICURE V4.5 — frontend compatible

Cette version est dérivée directement du `index.html` V3 fourni.

## Fichiers
- `index.html` : structure HTML et bibliothèques cartographiques existantes.
- `assets/style.css` : styles extraits sans suppression fonctionnelle.
- `assets/app.js` : logique JavaScript originale.
- `assets/hero-banner.png` : bannière extraite du Base64.
- `data/concerts.json` : données concerts/setlists extraites du HTML.

## Installation
Copier le contenu de ce dossier dans le dossier publié par GitHub Pages (`dist/` si le workflow publie `./dist`).

IMPORTANT : `data/concerts.json` doit ensuite être produit/remplacé par le build automatique V4 afin que Cure Guide + setlist.fm alimentent cette interface. Le fichier fourni ici contient les données de l'ancien HTML de référence.

Le site doit être servi en HTTP/HTTPS (GitHub Pages convient), car les données sont chargées avec `fetch()`.
