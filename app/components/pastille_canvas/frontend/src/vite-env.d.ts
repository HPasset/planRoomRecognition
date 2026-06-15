/// <reference types="vite/client" />

// Vite ?raw imports : retournent le contenu du fichier en string brute.
// Utilisé pour charger les SVG depuis src/planrec/assets/icons/ via l'alias @icons.
declare module '*.svg?raw' {
  const content: string;
  export default content;
}
