"""Mesure les cinq façons de répondre sur les 30 questions de evaluation/questions.json.

Usage :
    python -m wiki_llm.evaluer --mode direct   # répond avec le modèle local et remplit le cache
    python -m wiki_llm.evaluer                 # recalcule à partir du cache, sans modèle
    python -m wiki_llm.evaluer --verifier      # s'arrête en erreur si les résultats diffèrent de ceux publiés (utilisé par la CI)

Correction automatique :
- une question avec réponse est réussie si la réponse contient, pour chaque groupe de « attendu », au moins une des formes
  acceptées (minuscules, sans accents, mot entier) et si elle ne commence pas par INCONNU. Elle compte comme refusée à tort
  si elle n'est pas réussie et qu'elle dit que l'information manque ;
- une question piège est réussie si la réponse est un refus : INCONNU, ou une phrase qui dit clairement que
  l'information manque (« je ne trouve aucune information », « n'est pas précisé », etc.) ;
- une citation est valide si elle nomme une page ou un document qui existe.
"""
import argparse
import json
import re
import sys

from .modele import RACINE, Modele
from .repondre import METHODES, corpus_sources, corpus_wiki, repondre
from .wiki import liens, normaliser

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
RESULTATS = RACINE / 'resultats' / 'resultats.json'


# Un refus : INCONNU, ou une phrase qui dit clairement que l'information manque.
REFUS = re.compile(
    r"\binconnu\b|aucune information|je ne trouve (pas d'|pas de|pas l')information|n'ai (pas )?trouve|"
    r"je ne peux pas repondre|(n'est|ne sont) pas (disponible|precise|mentionne|detaille|specifie|indique)|"
    r"ne (mentionne|precise|specifie|detaille|indique)(nt)? pas|il n'est pas specifie|aucune (page|mention)")


def refus(reponse):
    return REFUS.search(normaliser(reponse)) is not None


def contient(texte, forme):
    """Forme trouvée comme mot entier. Un nombre ne compte pas s'il fait partie d'une date ou d'un autre nombre."""
    avant = r'(?<![\w-])' if forme[0].isdigit() else r'(?<!\w)'
    return re.search(avant + re.escape(forme) + r'(?!\w)', texte) is not None


def reussie(question, reponse):
    if not question['attendu']:
        return refus(reponse)
    texte = normaliser(reponse)
    return not texte.strip(' *.`"').startswith('inconnu') and all(any(contient(texte, f) for f in groupe) for groupe in question['attendu'])


def evaluer(mode):
    questions = json.loads((RACINE / 'evaluation' / 'questions.json').read_text(encoding='utf-8'))
    modele = Modele(mode)
    _, wc = corpus_wiki()
    sources = corpus_sources()
    noms_valides = {normaliser(n) for n in wc.noms} | {normaliser(n.removesuffix('.md')) for n in sources.noms} | {'index'}
    resultats = []
    for methode, nom in METHODES:
        modele.appels = modele.mots_envoyes = 0
        details = {}
        for q in questions:
            reponse, lus = repondre(modele, q['question'], methode, wc, sources)
            citees = liens(reponse)
            details[q['id']] = {
                'reponse': reponse,
                'lus': lus if methode.startswith('agent') or methode == 'bm25-wiki' else [],
                'reussie': reussie(q, reponse),
                'citations_valides': all(normaliser(c.removesuffix('.md')) in noms_valides for c in citees),
                'cite': bool(citees),
            }
        modele.enregistrer()
        repondables = [q for q in questions if q['attendu']]
        pieges = [q for q in questions if not q['attendu']]
        par_type = {}
        for t in dict.fromkeys(q['type'] for q in repondables):
            l = [q for q in repondables if q['type'] == t]
            par_type[t] = round(sum(details[q['id']]['reussie'] for q in l) / len(l), 3)
        refusees = [q for q in repondables if not details[q['id']]['reussie'] and refus(details[q['id']]['reponse'])]
        avec_reponse = [q for q in repondables if q not in refusees]
        resultats.append({
            'methode': nom,
            'bonnes_reponses': round(sum(details[q['id']]['reussie'] for q in repondables) / len(repondables), 3),
            'bonnes_reponses_par_type': par_type,
            'pieges_refuses': round(sum(details[q['id']]['reussie'] for q in pieges) / len(pieges), 3),
            'refus_a_tort': round(len(refusees) / len(repondables), 3),
            'reponses_avec_citation': round(sum(details[q['id']]['cite'] for q in avec_reponse) / max(len(avec_reponse), 1), 3),
            'citations_valides': round(sum(details[q['id']]['citations_valides'] for q in avec_reponse) / max(len(avec_reponse), 1), 3),
            'appels_llm_par_question': round(modele.appels / len(questions), 2),
            'mots_envoyes_par_question': round(modele.mots_envoyes / len(questions)),
            'details': details,
        })
        r = resultats[-1]
        print(f"{nom} : bonnes réponses {r['bonnes_reponses']:.0%}, pièges refusés {r['pieges_refuses']:.0%}, "
              f"refus à tort {r['refus_a_tort']:.0%}, {r['appels_llm_par_question']} appels, {r['mots_envoyes_par_question']} mots", flush=True)
    return resultats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['cache', 'direct'], default='cache')
    parser.add_argument('--verifier', action='store_true')
    args = parser.parse_args()
    resultats = evaluer(args.mode)
    if args.verifier:
        identique = resultats == json.loads(RESULTATS.read_text(encoding='utf-8'))
        print('Résultats identiques à ceux publiés.' if identique else 'ERREUR : les résultats diffèrent de ceux publiés.')
        sys.exit(0 if identique else 1)
    RESULTATS.write_text(json.dumps(resultats, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'Résultats écrits dans {RESULTATS.relative_to(RACINE)}')


if __name__ == '__main__':
    main()
