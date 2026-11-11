"""Trace les deux images du README : le graphe des liens du wiki et les résultats des cinq méthodes.

Usage : python resultats/graphiques.py
"""
import json
import sys
from pathlib import Path

import matplotlib
import matplotlib.ticker
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import networkx as nx

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
from wiki_llm.wiki import WIKI, Wiki, liens  # noqa: E402

SURFACE, TEXTE, TEXTE_2, GRILLE = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
SERIE_1, SERIE_2 = '#2a78d6', '#eb6834'


def graphe():
    wiki = Wiki(WIKI)
    g = nx.DiGraph()
    g.add_nodes_from(wiki.pages)
    for t in wiki.pages:
        for c in liens(wiki.corps(t)):
            cible = wiki.trouver(c)
            if cible and cible != t:
                g.add_edge(t, cible)
    position = nx.spring_layout(g.to_undirected(), seed=7, k=1.6 / max(len(g), 1) ** 0.5, iterations=200)
    fig, ax = plt.subplots(figsize=(12, 8), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    tailles = [120 + 90 * g.in_degree(n) for n in g]
    nx.draw_networkx_edges(g, position, ax=ax, edge_color='#c9c8c2', width=1, arrows=False)
    nx.draw_networkx_nodes(g, position, ax=ax, node_size=tailles, node_color=SERIE_1, edgecolors=SURFACE, linewidths=2)
    for n, (x, y) in position.items():
        ax.text(x, y - 0.045, n, ha='center', va='top', fontsize=8, color=TEXTE)
    ax.set_title(f'Le wiki compilé par le modèle : {g.number_of_nodes()} pages, {g.number_of_edges()} liens',
                 loc='left', color=TEXTE, fontsize=12, fontweight='bold')
    ax.axis('off')
    fig.text(0.01, 0.01, 'La taille d\'un point suit le nombre de pages qui renvoient vers lui.', color=TEXTE_2, fontsize=8)
    fig.savefig(ICI / 'graphe-wiki.png', dpi=150, bbox_inches='tight', facecolor=SURFACE)
    plt.close(fig)


def resultats():
    r = json.loads((ICI / 'resultats.json').read_text(encoding='utf-8'))
    fig, (gauche, droite) = plt.subplots(1, 2, figsize=(12, 3.6), sharey=True, facecolor=SURFACE, gridspec_kw={'wspace': 0.08})
    y = list(range(len(r)))[::-1]
    for ax in (gauche, droite):
        ax.set_facecolor(SURFACE)
        for cote in ('top', 'right', 'left'):
            ax.spines[cote].set_visible(False)
        ax.spines['bottom'].set_color(GRILLE)
        ax.tick_params(colors=TEXTE_2, length=0, labelsize=9)
        ax.grid(axis='x', color=GRILLE, linewidth=1)
        ax.set_axisbelow(True)
    for i, yi in enumerate(y):
        a, b = 100 * r[i]['bonnes_reponses'], 100 * r[i]['pieges_refuses']
        gauche.plot([min(a, b), max(a, b)], [yi, yi], color=GRILLE, linewidth=2, zorder=1)
    gauche.scatter([100 * m['bonnes_reponses'] for m in r], y, s=64, color=SERIE_1, edgecolor=SURFACE, linewidth=2, zorder=2,
                   label='Bonnes réponses (24 questions)')
    gauche.scatter([100 * m['pieges_refuses'] for m in r], y, s=64, color=SERIE_2, edgecolor=SURFACE, linewidth=2, zorder=2,
                   label='Pièges refusés (6 questions)')
    gauche.set_xlim(-2, 102)
    gauche.set_xticks(range(0, 101, 20))
    gauche.set_xticklabels([f'{x} %' for x in range(0, 101, 20)])
    gauche.set_title('Qualité des réponses', loc='left', color=TEXTE, fontsize=11, fontweight='bold', pad=26)
    gauche.legend(loc='lower left', bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=9, labelcolor=TEXTE_2, borderaxespad=0.2)
    mots = [m['mots_envoyes_par_question'] for m in r]
    droite.barh(y, mots, height=0.5, color=SERIE_1)
    for yi, v in zip(y, mots):
        droite.text(v, yi, f'  {v:,}'.replace(',', ' '), va='center', fontsize=9, color=TEXTE_2)
    droite.set_xlim(0, max(mots) * 1.18)
    droite.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f'{v:,.0f}'.replace(',', ' ')))
    droite.set_title('Coût : mots envoyés au modèle par question', loc='left', color=TEXTE, fontsize=11, fontweight='bold', pad=26)
    gauche.set_yticks(y)
    gauche.set_yticklabels([m['methode'] for m in r], color=TEXTE, fontsize=9)
    fig.savefig(ICI / 'graphique-resultats.png', dpi=150, bbox_inches='tight', facecolor=SURFACE)
    plt.close(fig)


if __name__ == '__main__':
    graphe()
    if (ICI / 'resultats.json').exists():
        resultats()
    print('Images écrites dans resultats/')
