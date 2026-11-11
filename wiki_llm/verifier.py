"""Vérification du wiki (l'opération « lint » du pattern) : des contrôles faits par le code, sans modèle.

Usage :
    python -m wiki_llm.verifier              # affiche le rapport et l'écrit dans resultats/verification-wiki.json
    python -m wiki_llm.verifier --verifier   # s'arrête en erreur si le rapport diffère de celui publié (utilisé par la CI)

Contrôles :
- liens brisés : un lien [[Titre]] vers une page qui n'existe pas ;
- pages orphelines : aucune autre page ne renvoie vers elles (l'index ne compte pas) ;
- pages sans source, ou qui citent une source inexistante ;
- sources jamais citées : aucune page ne dit en provenir ;
- pages absentes de l'index ;
- doublons probables : deux titres presque identiques.
"""
import argparse
import json
import sys
from difflib import SequenceMatcher

from .modele import RACINE
from .wiki import SOURCES, WIKI, Wiki, liens, normaliser

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
RAPPORT = RACINE / 'resultats' / 'verification-wiki.json'


def verifier(wiki):
    sources = {f.name for f in SOURCES.glob('*.md')}
    entrants = {t: set() for t in wiki.pages}
    brises = []
    for titre in wiki.pages:
        for cible in liens(wiki.corps(titre)):
            trouve = wiki.trouver(cible)
            if trouve is None:
                brises.append({'page': titre, 'lien': cible})
            elif trouve != titre:
                entrants[trouve].add(titre)
    citees = set()
    sans_source, source_inconnue = [], []
    for titre in wiki.pages:
        s = wiki.entete(titre).get('sources', [])
        citees |= set(s)
        if not s:
            sans_source.append(titre)
        source_inconnue += [{'page': titre, 'source': x} for x in s if x not in sources]
    index = (wiki.dossier / 'index.md').read_text(encoding='utf-8') if (wiki.dossier / 'index.md').exists() else ''
    dans_index = {wiki.trouver(c) for c in liens(index)}
    titres = sorted(wiki.pages)
    doublons = [[a, b] for i, a in enumerate(titres) for b in titres[i + 1:]
                if SequenceMatcher(None, normaliser(a), normaliser(b)).ratio() >= 0.85]
    return {
        'pages': len(wiki.pages),
        'liens': sum(len(liens(wiki.corps(t))) for t in wiki.pages),
        'liens_brises': brises,
        'pages_orphelines': sorted(t for t, e in entrants.items() if not e),
        'pages_sans_source': sans_source,
        'sources_inconnues': source_inconnue,
        'sources_jamais_citees': sorted(sources - citees),
        'pages_absentes_de_l_index': sorted(t for t in wiki.pages if t not in dans_index),
        'doublons_probables': doublons,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verifier', action='store_true')
    args = parser.parse_args()
    rapport = verifier(Wiki(WIKI))
    print(f"{rapport['pages']} pages, {rapport['liens']} liens")
    for cle, valeur in rapport.items():
        if isinstance(valeur, list):
            print(f"- {cle.replace('_', ' ')} : {len(valeur)}")
            for v in valeur:
                print(f'    {v}')
    if args.verifier:
        identique = rapport == json.loads(RAPPORT.read_text(encoding='utf-8'))
        print('Rapport identique à celui publié.' if identique else 'ERREUR : le rapport diffère de celui publié.')
        sys.exit(0 if identique else 1)
    RAPPORT.parent.mkdir(parents=True, exist_ok=True)
    RAPPORT.write_text(json.dumps(rapport, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
