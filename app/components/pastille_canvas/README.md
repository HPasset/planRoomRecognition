# Pastille Canvas — Streamlit Custom Component

Custom component React + TypeScript pour drag-and-drop des pastilles
(labels de pièces) sur le plan dans l'app Streamlit.

## État (Phase 1)

✅ Phase 1 : scaffold + pastilles statiques rendues aux positions OCR
🔜 Phase 2 : drag des pastilles existantes
🔜 Phase 3 : drag depuis palette → nouvelle pastille
🔜 Phase 4 : boundary detection (out of bbox = remove)
🔜 Phase 5 : touch + polish tablette

## Architecture

```
pastille_canvas/
├── __init__.py           # Python wrapper Streamlit
├── README.md             # ce fichier
├── .gitignore
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── index.html
    ├── src/
    │   ├── main.tsx
    │   ├── PastilleCanvas.tsx
    │   └── styles.css
    ├── node_modules/     # gitignored
    └── dist/             # commité (Streamlit sert depuis ici)
```

## Build / Dev

```bash
# Première fois : install dependencies
cd frontend && npm install

# Build production (génère dist/ que Streamlit utilise)
npm run build

# Dev avec hot reload (port 5173 ; nécessite pointer declare_component vers url)
npm run dev
```

## Stack

- React 18 + TypeScript 5 + Vite 6
- `streamlit-component-lib` pour la communication bidirectionnelle avec Streamlit
- (Phase 2+) `@dnd-kit/core` pour drag-and-drop tactile

## Communication Python ↔ React

**Python → React** (props via `args`) :
- `image_data` : data URL base64 du plan
- `image_width`, `image_height` : dimensions originales (mapping coordonnées)
- `initial_pastilles` : list de `{id, type, label, x, y, color}`
- `palette` : list de `{type, label, color}` pour les types dispo

**React → Python** (via `Streamlit.setComponentValue`) :
- `{ pastilles: [...] }` : état mis à jour à chaque modification
