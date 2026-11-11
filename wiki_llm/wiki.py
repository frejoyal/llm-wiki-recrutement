"""Lecture et écriture des pages du wiki (fichiers Markdown au format Obsidian)."""
import re
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SOURCES = RACINE / 'sources'
WIKI = RACINE / 'wiki'
PAGES_SPECIALES = {'index', 'journal'}
LIEN = re.compile(r'\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]')
INTERDITS_TITRE = re.compile(r'[\\/:*?"<>|#\[\]^]')


def normaliser(texte):
    """Minuscules, sans accents ni ponctuation superflue : sert à comparer des titres et des réponses."""
    texte = ''.join(c for c in unicodedata.normalize('NFD', texte.lower()) if unicodedata.category(c) != 'Mn')
    texte = texte.replace('’', "'").replace(' ', ' ')
    return re.sub(r'\s+', ' ', texte).strip()


def titre_propre(titre):
    titre = INTERDITS_TITRE.sub(' ', titre).replace('\u2013', '-').replace('\u2014', '-')
    return re.sub(r'\s+', ' ', titre).strip(' .')


def liens(texte):
    return [m.group(1).strip() for m in LIEN.finditer(texte)]


def lire_entete(texte):
    """Retourne (entête, corps). L'entête est un petit YAML écrit par le code : clés simples et listes."""
    if not texte.startswith('---\n'):
        return {}, texte
    fin = texte.index('\n---\n', 4)
    entete, cle = {}, None
    for ligne in texte[4:fin].splitlines():
        if ligne.startswith('  - ') and cle:
            entete.setdefault(cle, []).append(ligne[4:].strip())
        elif ':' in ligne:
            cle, valeur = ligne.split(':', 1)
            cle, valeur = cle.strip(), valeur.strip()
            entete[cle] = valeur if valeur else []
    return entete, texte[fin + 5:]


def ecrire_entete(entete):
    lignes = ['---']
    for cle, valeur in entete.items():
        if isinstance(valeur, list):
            lignes.append(f'{cle}:')
            lignes += [f'  - {v}' for v in valeur]
        else:
            lignes.append(f'{cle}: {valeur}')
    return '\n'.join(lignes + ['---', ''])


class Wiki:
    """Les pages d'un dossier de wiki, indexées par titre."""

    def __init__(self, dossier=WIKI):
        self.dossier = Path(dossier)
        self.pages = {}
        for f in sorted(self.dossier.glob('*.md')):
            if f.stem not in PAGES_SPECIALES:
                self.pages[f.stem] = f.read_text(encoding='utf-8')

    def trouver(self, titre):
        """Titre exact d'une page à partir d'un titre approximatif (casse, accents, crochets), ou None."""
        cible = normaliser(titre.strip().strip('[]'))
        if cible.endswith('.md'):
            cible = cible[:-3]
        return next((t for t in self.pages if normaliser(t) == cible), None)

    def entete(self, titre):
        return lire_entete(self.pages[titre])[0]

    def corps(self, titre):
        return lire_entete(self.pages[titre])[1]

    def ecrire(self, titre, entete, corps):
        texte = ecrire_entete(entete) + corps.strip() + '\n'
        self.pages[titre] = texte
        (self.dossier / f'{titre}.md').write_text(texte, encoding='utf-8', newline='\n')


def charger_sources():
    """Les sources dans l'ordre chronologique (le nom de fichier commence par la date)."""
    return [(f.name, f.read_text(encoding='utf-8')) for f in sorted(SOURCES.glob('*.md'))]
