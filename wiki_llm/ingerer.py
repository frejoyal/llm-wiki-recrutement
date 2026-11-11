"""Ingestion : le modèle de langage compile les sources en pages de wiki, une source à la fois, dans l'ordre des dates.

Usage :
    python -m wiki_llm.ingerer --mode direct   # reconstruit wiki/ avec le modèle local (Ollama) et remplit le cache
    python -m wiki_llm.ingerer                 # reconstruit wiki/ à partir du cache, sans modèle
    python -m wiki_llm.ingerer --verifier      # reconstruit dans un dossier temporaire et compare à wiki/ (utilisé par la CI)

Pour chaque source, deux étapes guidées plutôt qu'un agent libre, ce qui convient mieux à un petit modèle local :
1. le plan : le modèle lit l'index et la source, et choisit 1 à 4 pages à créer ou à modifier ;
2. la rédaction : pour chaque page, le modèle lit la page actuelle et la source, et réécrit la page au complet.
Le code tient l'en-tête de chaque page (sources, date), l'index et le journal : le modèle n'écrit que le contenu.
"""
import argparse
import filecmp
import json
import re
import sys
import tempfile
from pathlib import Path

from .modele import RACINE, Modele
from .wiki import WIKI, Wiki, charger_sources, titre_propre

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
REGLES = (RACINE / 'AGENTS.md').read_text(encoding='utf-8')
PAGES_MAX = 4


def texte_index(wiki):
    if not wiki.pages:
        return '(aucune page pour l\'instant)'
    return '\n'.join(f"- {t} : {wiki.entete(t).get('resume', '')}" for t in wiki.pages)


def planifier(modele, wiki, nom, source):
    invite = (
        f"{REGLES}\n\n# Pages existantes du wiki\n{texte_index(wiki)}\n\n# Nouvelle source : {nom}\n<source>\n{source}\n</source>\n\n"
        f"Décide quelles pages du wiki cette source doit créer ou modifier : de 1 à {PAGES_MAX} pages. "
        "Modifie une page existante quand la source porte sur son sujet ; crée une page seulement pour un sujet qui n'en a pas. "
        "Pour une page existante, recopie son titre exactement. "
        'Réponds seulement avec du JSON, sous cette forme : {"pages": [{"titre": "...", "action": "creer"}, {"titre": "...", "action": "modifier"}]}'
    )
    reponse = modele.texte(invite)
    trouve = re.search(r'\{.*\}', reponse, flags=re.S)
    try:
        pages = json.loads(trouve.group(0))['pages'] if trouve else []
    except (json.JSONDecodeError, KeyError, TypeError):
        pages = []
    titres = []
    for p in pages:
        if not isinstance(p, dict) or not isinstance(p.get('titre'), str):
            continue
        titre = wiki.trouver(p['titre']) or titre_propre(p['titre'])
        if titre and titre not in titres:
            titres.append(titre)
    return titres[:PAGES_MAX]


def rediger(modele, wiki, nom, source, titre, prevus):
    existe = titre in wiki.pages
    titres = sorted(set(wiki.pages) | set(prevus))
    invite = (
        f"{REGLES}\n\n# Titres des pages du wiki (pour les liens)\n" + '\n'.join(f'- {t}' for t in titres) +
        f"\n\n# Source : {nom}\n<source>\n{source}\n</source>\n\n"
        f"# Page à {'mettre à jour' if existe else 'créer'} : {titre}\n<page_actuelle>\n"
        f"{wiki.corps(titre).strip() if existe else '(nouvelle page)'}\n</page_actuelle>\n\n"
        f"Écris le contenu complet de la page « {titre} » une fois cette source ajoutée. "
        "Garde toutes les informations de la page actuelle qui restent vraies. "
        "Si la source change une règle ou une valeur, applique la règle « Quand une source contredit le wiki ». "
        f"N'écris que les faits qui concernent le sujet « {titre} » : ne recopie pas le reste de la source, qui va dans d'autres pages. "
        "Ajoute des liens [[Titre]] vers les pages liées, seulement avec des titres de la liste. "
        "N'ajoute pas de section sur la provenance ou les sources : le code l'écrit dans l'en-tête.\n"
        "Format de la réponse : la première ligne commence par « Résumé : » et résume la page en une phrase. "
        "Ensuite vient le corps de la page en Markdown, sans titre de niveau 1 et sans en-tête YAML."
    )
    reponse = re.sub(r'^```(?:markdown|md)?\s*\n|\n```\s*$', '', modele.texte(invite).strip())
    lignes = reponse.splitlines()
    resume = ''
    if lignes and re.match(r'^\**\s*R[ée]sum[ée]\s*\**\s*:', lignes[0], flags=re.I):
        resume = lignes[0].split(':', 1)[1].strip(' *')
        lignes = lignes[1:]
    corps = '\n'.join(lignes).strip()
    corps = re.sub(r'^#\s+.*\n+', '', corps)  # le titre de niveau 1 est ajouté par le code
    return resume, corps


def ecrire_index_et_journal(wiki, journal):
    index = ['# Index du wiki', '', 'Toutes les pages du wiki, avec leur résumé. Cette page est produite par le code après chaque ingestion.', '']
    index += [f"- [[{t}]] : {wiki.entete(t).get('resume', '')}" for t in sorted(wiki.pages, key=str.lower)]
    (wiki.dossier / 'index.md').write_text('\n'.join(index) + '\n', encoding='utf-8', newline='\n')
    (wiki.dossier / 'journal.md').write_text('# Journal des ingestions\n\n' + '\n\n'.join(journal) + '\n', encoding='utf-8', newline='\n')


def ingerer(modele, dossier):
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    for f in dossier.glob('*.md'):
        f.unlink()
    wiki, journal = Wiki(dossier), []
    for nom, source in charger_sources():
        date = nom[:10]
        prevus = planifier(modele, wiki, nom, source)
        crees, modifiees = [], []
        for titre in prevus:
            existe = titre in wiki.pages
            resume, corps = rediger(modele, wiki, nom, source, titre, prevus)
            if not corps:
                continue
            ancien = wiki.entete(titre) if existe else {}
            sources = [s for s in ancien.get('sources', []) if s != nom] + [nom]
            entete = {'titre': titre, 'resume': resume or ancien.get('resume', ''), 'sources': sources, 'mis_a_jour': date}
            wiki.ecrire(titre, entete, f'# {titre}\n\n{corps}')
            (modifiees if existe else crees).append(titre)
        entree = [f'## {date} · {nom}']
        entree += [f'- page créée : [[{t}]]' for t in crees] + [f'- page modifiée : [[{t}]]' for t in modifiees]
        journal.append('\n'.join(entree))
        modele.enregistrer()
        print(f"{nom} : {len(crees)} créée(s), {len(modifiees)} modifiée(s)", flush=True)
    ecrire_index_et_journal(wiki, journal)
    from .verifier import verifier
    avant = verifier(wiki)
    ajoutes = entretenir(modele, wiki)
    journal.append('## Entretien · pages orphelines\n' + '\n'.join(f'- lien ajouté : [[{a}]] vers [[{b}]]' for a, b in ajoutes))
    ecrire_index_et_journal(wiki, journal)
    modele.enregistrer()
    print(f'Entretien : {len(ajoutes)} lien(s) ajouté(s) vers {len(avant["pages_orphelines"])} page(s) orpheline(s)', flush=True)
    return wiki, avant


def entretenir(modele, wiki):
    """Entretien après la vérification : chaque page orpheline reçoit des liens entrants choisis par le modèle.
    Le code ajoute une ligne « Voir aussi » aux pages choisies. Retourne le nombre de liens ajoutés."""
    from .verifier import verifier
    ajoutes = []
    for orpheline in verifier(wiki)['pages_orphelines']:
        autres = [t for t in wiki.pages if t != orpheline]
        invite = (
            "Voici les pages d'un wiki interne, avec leur résumé :\n" +
            '\n'.join(f"- {t} : {wiki.entete(t).get('resume', '')}" for t in autres) +
            f"\n\nLa page « {orpheline} » ({wiki.entete(orpheline).get('resume', '')}) n'a aucun lien entrant : "
            "aucune page ne renvoie vers elle. Quelles pages de la liste devraient renvoyer vers elle ? "
            "Choisis de 1 à 3 pages dont le sujet est directement lié. "
            'Réponds seulement avec du JSON, sous cette forme : {"pages": ["Titre", "Titre"]}'
        )
        trouve = re.search(r'\{.*\}', modele.texte(invite), flags=re.S)
        try:
            choisies = json.loads(trouve.group(0))['pages'] if trouve else []
        except (json.JSONDecodeError, KeyError, TypeError):
            choisies = []
        for c in choisies[:3]:
            source = wiki.trouver(c) if isinstance(c, str) else None
            if not source or source == orpheline:
                continue
            entete, corps = wiki.entete(source), wiki.corps(source).rstrip()
            if corps.splitlines()[-1].startswith('Voir aussi :'):
                corps += f', [[{orpheline}]]'
            else:
                corps += f'\n\nVoir aussi : [[{orpheline}]]'
            wiki.ecrire(source, entete, corps)
            ajoutes.append((source, orpheline))
    return ajoutes


def comparer(a, b):
    fa = sorted(p.name for p in Path(a).glob('*.md'))
    fb = sorted(p.name for p in Path(b).glob('*.md'))
    if fa != fb:
        return False
    return all(filecmp.cmp(Path(a) / f, Path(b) / f, shallow=False) for f in fa)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['cache', 'direct'], default='cache')
    parser.add_argument('--verifier', action='store_true')
    args = parser.parse_args()
    modele = Modele(args.mode)
    if args.verifier:
        with tempfile.TemporaryDirectory() as tmp:
            ingerer(modele, tmp)
            identique = comparer(tmp, WIKI)
        print('Wiki identique à celui publié.' if identique else 'ERREUR : le wiki reconstruit diffère de celui publié.')
        sys.exit(0 if identique else 1)
    wiki, avant = ingerer(modele, WIKI)
    modele.enregistrer()
    (RACINE / 'resultats' / 'verification-avant-entretien.json').write_text(
        json.dumps(avant, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{len(wiki.pages)} pages dans wiki/ ; {modele.appels} appels au modèle.')


if __name__ == '__main__':
    main()
