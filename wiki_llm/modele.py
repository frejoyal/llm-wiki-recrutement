"""Appels au modèle de langage local (Ollama), avec un cache publié dans le dépôt.

En mode « direct », le modèle tourne sur le poste et le cache se remplit.
En mode « cache », rien n'est calculé : chaque réponse vient du cache. C'est ce que fait la CI, sans modèle ni réseau,
pour vérifier que le wiki et les résultats publiés se reconstruisent à l'identique.
"""
import hashlib
import json
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CACHE = RACINE / 'resultats' / 'cache-modele.json'
OLLAMA = 'http://127.0.0.1:11434/api/chat'
MODELE = 'gemma4:e4b'
OPTIONS = {'temperature': 0, 'seed': 7, 'num_ctx': 32768, 'num_predict': 1500}


class Modele:
    def __init__(self, mode='cache'):
        if mode not in ('cache', 'direct'):
            raise ValueError(mode)
        self.mode = mode
        self._reponses = json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {}
        self._utilisees = set()
        self.modifie = False
        # Coût, compté de la même façon que la réponse vienne du cache ou du modèle.
        self.appels = 0
        self.mots_envoyes = 0

    def discuter(self, messages, outils=None):
        """Un tour de conversation. Retourne le message du modèle : {'content': ..., 'tool_calls': [...]}."""
        requete = {'model': MODELE, 'messages': messages, 'tools': outils or [], 'options': OPTIONS}
        cle = hashlib.sha1(json.dumps(requete, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
        self.appels += 1
        self.mots_envoyes += sum(len(str(m.get('content', '')).split()) for m in messages)
        self._utilisees.add(cle)
        if cle not in self._reponses:
            if self.mode == 'cache':
                raise RuntimeError('Réponse absente du cache : relancez en mode direct, avec Ollama démarré.')
            import requests
            r = requests.post(OLLAMA, json={**requete, 'tools': outils or None, 'stream': False, 'think': False}, timeout=900)
            r.raise_for_status()
            m = r.json()['message']
            # Les identifiants d'appel d'outil sont aléatoires : on ne garde que le nom et les arguments.
            appels = [{'function': {'name': a['function']['name'], 'arguments': a['function'].get('arguments', {})}}
                      for a in m.get('tool_calls') or []]
            self._reponses[cle] = {'content': (m.get('content') or '').strip(), 'tool_calls': appels}
            self.modifie = True
        return self._reponses[cle]

    def texte(self, invite, systeme=None):
        messages = ([{'role': 'system', 'content': systeme}] if systeme else []) + [{'role': 'user', 'content': invite}]
        return self.discuter(messages)['content']

    def enregistrer(self, elaguer=False):
        """Écrit le cache. Avec elaguer, ne garde que les réponses utilisées pendant cette exécution."""
        if elaguer:
            self._reponses = {k: v for k, v in self._reponses.items() if k in self._utilisees}
            self.modifie = True
        if self.modifie:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(dict(sorted(self._reponses.items())), ensure_ascii=False, indent=0) + '\n', encoding='utf-8')
            self.modifie = False
