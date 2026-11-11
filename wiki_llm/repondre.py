"""Cinq façons de répondre à une question sur le cabinet, avec le même modèle local.

- Agent dans le wiki : le modèle part de l'index, lit des pages et suit des liens avec des outils (pattern LLM Wiki).
- Agent dans les sources : le même agent, mais dans les documents bruts, sans wiki.
  Chaque agent existe en deux versions. Sans amorce, il doit lui-même ouvrir l'index (ou lister les documents) ; un petit
  modèle répond alors souvent sans rien lire. Avec amorce, le point d'entrée est déjà lu au départ, et un agent qui veut
  répondre sans avoir rien lu est renvoyé une fois à ses outils.
- Wiki entier en contexte : toutes les pages du wiki sont données au modèle avec la question.
- Sources entières en contexte : tous les documents bruts sont donnés au modèle avec la question.
- RAG BM25 sur le wiki : les 3 pages les plus proches de la question, trouvées par BM25.

Usage : python -m wiki_llm.repondre "Combien de références faut-il vérifier ?" [--methode agent-wiki]
"""
import argparse
import difflib
import re
import sys
import unicodedata

from rank_bm25 import BM25Okapi

from .modele import RACINE, Modele
from .wiki import WIKI, Wiki, charger_sources, lire_entete

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
ETAPES_MAX = 8
MOTS_VIDES = set("""
a au aux avec ce ces cet cette d dans de des du elle en et il ils je l la le les leur lui ma mais me mes mon n ne nos notre nous on ou
par pas pour qu que qui s sa se ses son sur un une vos votre vous y est sont quel quelle quels quelles combien comment faut
""".split())


def jetons(texte):
    texte = ''.join(c for c in unicodedata.normalize('NFD', texte.lower()) if unicodedata.category(c) != 'Mn')
    return [m for m in re.findall(r'[a-z0-9]+(?:-[a-z0-9]+)*', texte) if m not in MOTS_VIDES and len(m) > 1]


def consigne(quoi):
    return (
        "Tu es l'assistant interne de Recrutement Élite inc., un cabinet de recrutement en TI. Tu ne connais rien du cabinet "
        f"par toi-même : tu réponds seulement avec ce que disent {quoi}. Réponds en français, en une à trois phrases, "
        "et cite chaque page ou document utilisé entre doubles crochets, par exemple [[Titre]]. "
        "Si l'information demandée n'y est pas, réponds exactement INCONNU."
    )


class Corpus:
    """Des textes nommés (pages du wiki ou documents sources), avec un index BM25."""

    def __init__(self, textes):
        self.textes = textes
        self.noms = list(textes)
        self.bm25 = BM25Okapi([jetons(n + ' ' + t) for n, t in textes.items()])

    def chercher(self, requete, n=5):
        scores = self.bm25.get_scores(jetons(requete))
        ordre = sorted(range(len(self.noms)), key=lambda i: (-round(float(scores[i]), 6), i))
        return [self.noms[i] for i in ordre[:n] if scores[i] > 0]

    def trouver(self, nom):
        cible = nom.strip().strip('[]').lower().removesuffix('.md')
        return next((n for n in self.noms if n.lower().removesuffix('.md') == cible), None)


def corpus_wiki():
    wiki = Wiki(WIKI)
    textes = {t: wiki.pages[t] for t in wiki.pages}
    return wiki, Corpus(textes)


def corpus_sources():
    return Corpus(dict(charger_sources()))


def outil(nom, description, parametre=None, aide=''):
    proprietes = {parametre: {'type': 'string', 'description': aide}} if parametre else {}
    return {'type': 'function', 'function': {'name': nom, 'description': description,
            'parameters': {'type': 'object', 'properties': proprietes, 'required': [parametre] if parametre else []}}}


def executer(appel, corpus, dans_wiki, index, lus):
    """Exécute un appel d'outil du modèle et retourne le texte du résultat."""
    nom, args = appel['function']['name'], appel['function'].get('arguments') or {}
    valeur = str(next(iter(args.values()), '')) if isinstance(args, dict) and args else ''
    if nom == 'chercher':
        return '\n'.join(corpus.chercher(valeur)) or 'Aucun résultat.'
    if nom == 'lister_documents':
        return '\n'.join(f"{n} : {corpus.textes[n].splitlines()[0].lstrip('# ')}" for n in corpus.noms)
    if nom in ('lire_page', 'lire_document'):
        if dans_wiki and valeur.strip().lower() in ('index', 'index.md'):
            return index
        trouve = corpus.trouver(valeur)
        if not trouve:
            proches = difflib.get_close_matches(valeur, corpus.noms, n=3, cutoff=0.4)
            return 'Introuvable.' + (f" Noms proches : {', '.join(proches)}" if proches else '')
        if trouve not in lus:
            lus.append(trouve)
        return corpus.textes[trouve]
    return f'Outil inconnu : {nom}'


def agent(modele, question, corpus, dans_wiki, amorce=True):
    """Boucle d'outils. Avec amorce, le point d'entrée (index ou liste des documents) est déjà lu au départ,
    et un agent qui veut répondre sans avoir rien lu est renvoyé une fois à ses outils."""
    index = (WIKI / 'index.md').read_text(encoding='utf-8') if dans_wiki else ''
    if dans_wiki:
        outils = [
            outil('lire_page', "Lit une page du wiki. La page « index » liste toutes les pages avec leur résumé.", 'titre', 'Titre exact de la page'),
            outil('chercher', 'Cherche des mots dans tout le wiki et retourne les titres des 5 pages les plus pertinentes.', 'mots', 'Mots à chercher'),
        ]
        systeme = consigne('les pages du wiki du cabinet') + " Tu lis le wiki avec tes outils : commence par lire la page index, puis lis les pages utiles."
        premier = {'function': {'name': 'lire_page', 'arguments': {'titre': 'index'}}}
    else:
        outils = [
            outil('lister_documents', 'Liste tous les documents du cabinet, avec leur titre.'),
            outil('lire_document', 'Lit un document du cabinet.', 'nom', 'Nom du fichier, par exemple 2026-01-12-politique-recrutement.md'),
            outil('chercher', 'Cherche des mots dans tous les documents et retourne les noms des 5 documents les plus pertinents.', 'mots', 'Mots à chercher'),
        ]
        systeme = consigne('les documents du cabinet') + " Tu lis les documents avec tes outils : commence par les lister, puis lis les documents utiles."
        premier = {'function': {'name': 'lister_documents', 'arguments': {}}}
    messages = [{'role': 'system', 'content': systeme}, {'role': 'user', 'content': question}]
    lus, relance = [], False
    if amorce:
        messages.append({'role': 'assistant', 'content': '', 'tool_calls': [premier]})
        messages.append({'role': 'tool', 'tool_name': premier['function']['name'], 'content': executer(premier, corpus, dans_wiki, index, lus)})
    for _ in range(ETAPES_MAX):
        reponse = modele.discuter(messages, outils)
        if not reponse['tool_calls']:
            if amorce and not lus and not relance:
                relance = True
                messages.append({'role': 'assistant', 'content': reponse['content']})
                messages.append({'role': 'user', 'content': "Tu n'as encore lu aucune page. Lis les pages utiles avec tes outils avant de répondre."})
                continue
            return reponse['content'], lus
        messages.append({'role': 'assistant', 'content': reponse['content'], 'tool_calls': reponse['tool_calls']})
        for appel in reponse['tool_calls']:
            messages.append({'role': 'tool', 'tool_name': appel['function']['name'], 'content': executer(appel, corpus, dans_wiki, index, lus)})
    messages.append({'role': 'user', 'content': 'Réponds maintenant à la question avec ce que tu as lu.'})
    return modele.discuter(messages)['content'], lus


def en_contexte(modele, question, textes, quoi, balise):
    contenu = '\n\n'.join(f'<{balise} nom="{n}">\n{t.strip()}\n</{balise}>' for n, t in textes.items())
    invite = f'{contenu}\n\nQuestion : {question}'
    return modele.texte(invite, systeme=consigne(quoi))


def repondre(modele, question, methode, wiki_corpus=None, sources=None):
    """Retourne (réponse, pages ou documents lus)."""
    if methode in ('agent-wiki', 'agent-wiki-sans-amorce'):
        return agent(modele, question, wiki_corpus, dans_wiki=True, amorce=methode == 'agent-wiki')
    if methode in ('agent-sources', 'agent-sources-sans-amorce'):
        return agent(modele, question, sources, dans_wiki=False, amorce=methode == 'agent-sources')
    if methode == 'contexte-wiki':
        textes = {t: lire_entete(x)[1] for t, x in wiki_corpus.textes.items()}
        return en_contexte(modele, question, textes, 'les pages du wiki ci-dessus', 'page'), list(textes)
    if methode == 'contexte-sources':
        return en_contexte(modele, question, sources.textes, 'les documents ci-dessus', 'document'), list(sources.textes)
    if methode == 'bm25-wiki':
        choisis = wiki_corpus.chercher(question, n=3)
        textes = {t: lire_entete(wiki_corpus.textes[t])[1] for t in choisis}
        return en_contexte(modele, question, textes, 'les pages du wiki ci-dessus', 'page'), choisis
    raise ValueError(methode)


METHODES = [
    ('agent-wiki-sans-amorce', 'Agent dans le wiki, sans amorce'),
    ('agent-sources-sans-amorce', 'Agent dans les sources, sans amorce'),
    ('agent-wiki', 'Agent dans le wiki'),
    ('agent-sources', 'Agent dans les sources'),
    ('contexte-wiki', 'Wiki entier en contexte'),
    ('contexte-sources', 'Sources entières en contexte'),
    ('bm25-wiki', 'RAG BM25 sur le wiki (3 pages)'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('question')
    parser.add_argument('--methode', choices=[m for m, _ in METHODES], default='agent-wiki')
    parser.add_argument('--mode', choices=['cache', 'direct'], default='direct')
    args = parser.parse_args()
    modele = Modele(args.mode)
    _, wc = corpus_wiki()
    reponse, lus = repondre(modele, args.question, args.methode, wc, corpus_sources())
    modele.enregistrer()
    print(reponse)
    print(f"\n(lu : {', '.join(lus) if lus else 'rien'} ; {modele.appels} appel(s) au modèle)")


if __name__ == '__main__':
    main()
