# Règles du wiki de Recrutement Élite

Ce fichier est le schéma du wiki. Il s'adresse au modèle de langage qui l'entretient, et à toute personne ou tout agent qui l'ouvre (Claude Code, Claude Desktop avec le serveur MCP de fichiers, Obsidian).

## Les trois dossiers

- `sources/` : les documents bruts du cabinet (politiques, procédures, fiches clients, comptes rendus, courriels). On ne les modifie jamais.
- `wiki/` : les pages écrites et tenues à jour par le modèle à partir des sources. C'est ce qu'on consulte.
- `wiki/index.md` et `wiki/journal.md` : l'index de toutes les pages, et le journal de chaque ingestion. Ils sont produits par le code.

## Une page du wiki

- Une page traite d'un seul sujet : une règle (« Conservation des dossiers »), une procédure, un client, un domaine de recrutement ou une décision.
- Le titre est court, en français, sans le nom du cabinet. Le fichier porte le même nom que le titre.
- Le texte est factuel : des chiffres, des délais, des noms de rôles, des conditions. Pas d'opinion, pas de remplissage.
- Les faits sont écrits en phrases courtes ou en listes. Les chiffres sont recopiés exactement.
- Une page renvoie vers les pages liées avec des liens Obsidian `[[Titre exact]]`, seulement vers des pages qui existent ou qui sont créées dans la même ingestion.
- La provenance est notée dans l'en-tête de la page (liste des sources), par le code.

## Quand une source contredit le wiki

Une source plus récente l'emporte. La page donne la règle en vigueur, avec sa date d'entrée en vigueur, et garde l'ancienne valeur dans une section « Historique ». Une exception propre à un client va dans la page du client, et la page de la règle générale la mentionne.

## Répondre à une question

- Partir de l'index, lire les pages utiles, suivre les liens au besoin.
- Répondre seulement avec ce que disent les pages, et citer chaque page utilisée sous la forme `[[Titre]]`.
- Si le wiki ne contient pas la réponse, répondre exactement `INCONNU`.
