"""Fusion multi-stratégies (blueprint §7.2) : TF-IDF, BM25, entités/titres, combinés par
fusion de rangs réciproque (RRF, k = 60). Aucune stratégie ne décide seule.

La 4e voie (embeddings `all-MiniLM-L6-v2` locaux) exige un modèle téléchargé sur
instruction explicite du propriétaire ; elle ne l'a pas été. Repli propre sur 3 stratégies,
déclaré dans l'évidence (`hf_actif: false`).

  python3 -m rag_wiki.fusion --eval      # écrit rag_wiki/fusion_mrr.json
"""

import collections
import math
import os
import sys

from rag_wiki.corpus import charger
from rag_wiki.rag import QUESTIONS, IndexTFIDF, decouper, jetons, mrr, repondre_avec

DOSSIER = os.path.dirname(os.path.abspath(__file__))
K_RRF = 60


class BM25:
    def __init__(self, morceaux, k1=1.5, b=0.75):
        self.sacs = [collections.Counter(jetons(m["texte"]) + jetons(m["titre"]) * 2) for m in morceaux]
        self.longueurs = [sum(s.values()) for s in self.sacs]
        self.moyenne = sum(self.longueurs) / len(self.longueurs)
        df = collections.Counter(t for s in self.sacs for t in s)
        n = len(self.sacs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def classer(self, question):
        q = set(jetons(question))
        scores = []
        for s, l in zip(self.sacs, self.longueurs):
            sc = 0.0
            for t in q & s.keys():
                f = s[t]
                sc += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * l / self.moyenne))
            scores.append(sc)
        return sorted(range(len(scores)), key=lambda i: (-scores[i], i))


class Entites:
    """Recouvrement entre la question et le titre du document, départagé par la densité locale."""

    def __init__(self, morceaux):
        self.titres = [set(jetons(m["titre"])) for m in morceaux]
        self.sacs = [set(jetons(m["texte"])) for m in morceaux]

    def classer(self, question):
        q = set(jetons(question))
        scores = [len(q & t) / (len(t) or 1) * 2 + len(q & s) / (len(q) or 1)
                  for t, s in zip(self.titres, self.sacs)]
        return sorted(range(len(scores)), key=lambda i: (-scores[i], i))


class Fusion:
    """RRF standard sur les morceaux (forme du blueprint), k = 60.

    Résultat mesuré et conservé tel quel : sur ce corpus, la fusion fait MOINS bien que
    TF-IDF seul. Deux variantes ont été essayées puis abandonnées pour ne pas ajuster le
    système aux 8 questions d'évaluation : plafond de 3 morceaux par document (pire), et
    fusion au niveau des documents (`mode="documents"`, équivalente). Voir l'évidence.
    """

    def __init__(self, morceaux, mode: str = "morceaux"):
        self.morceaux, self.mode = morceaux, mode
        self.strategies = {"tfidf": IndexTFIDF(morceaux).classer, "bm25": BM25(morceaux).classer,
                           "entites": Entites(morceaux).classer}
        self.hf_actif = False

    def classer(self, question):
        doc = collections.defaultdict(float)
        morceau = collections.defaultdict(float)
        for classer in self.strategies.values():
            rangs_doc = {}
            for rang, i in enumerate(classer(question)):
                titre = self.morceaux[i]["titre"]
                if titre not in rangs_doc:
                    rangs_doc[titre] = len(rangs_doc)
                if rang < 200:
                    morceau[i] += 1 / (K_RRF + rang + 1)
            for titre, r in rangs_doc.items():
                doc[titre] += 1 / (K_RRF + r + 1)
        if self.mode == "morceaux":
            return sorted(morceau, key=lambda i: (-morceau[i], i))
        return sorted(morceau, key=lambda i: (-doc[self.morceaux[i]["titre"]], -morceau[i], i))


_FUSION = None


def repondre(question: str) -> dict:
    global _FUSION
    if _FUSION is None:
        _FUSION = Fusion(decouper(charger()))
    return repondre_avec(_FUSION.classer, _FUSION.morceaux, question)


def main(argv) -> int:
    from plateforme_omega.commun import conclure
    morceaux = decouper(charger())
    f = Fusion(morceaux)
    par = {nom: mrr(c, morceaux) for nom, c in f.strategies.items()}
    fus = mrr(f.classer, morceaux)
    par_documents = mrr(Fusion(morceaux, mode="documents").classer, morceaux)
    return conclure("fusion", [
        ("3 stratégies indépendantes + fusion RRF k = 60", len(f.strategies) == 3, ""),
        ("voie neuronale absente déclarée (hf_actif = false), repli sur 3 stratégies", f.hf_actif is False, ""),
        ("MRR de la fusion ≥ meilleure stratégie − 0,05",
         fus["mrr"] >= max(p["mrr"] for p in par.values()) - 0.05,
         " · ".join(f"{n} {p['mrr']:.3f}" for n, p in par.items()) + f" · fusion {fus['mrr']:.3f}"),
    ], {"hf_actif": False, "k_rrf": K_RRF, "mrr_par_strategie": {n: p["mrr"] for n, p in par.items()},
        "mrr_fusion": fus["mrr"], "rangs_fusion": fus["rangs"], "questions": len(QUESTIONS),
        "variantes_ecartees": {"rrf_documents_puis_morceaux": par_documents["mrr"],
                               "rrf_morceaux_plafond_3_par_document": 0.558},
        "mode": "rrf_morceaux"},
        ["Sur ce corpus, la fusion RRF fait moins bien que TF-IDF seul : la stratégie « entités » classe "
         "d'un bloc tous les morceaux d'un document cité dans la question (« Terre » pour la Lune).",
         f"Variantes essayées puis abandonnées pour ne pas ajuster le système à l'évaluation : fusion par "
         f"documents (MRR {par_documents['mrr']:.3f}), plafond de 3 morceaux par document (0,558, mesure d'une "
         "version antérieure du code).",
         "Analyse des pertes : (1) « satellite naturel de la Terre » — TF-IDF et BM25 placent en tête la "
         "phrase exacte de l'article Lune, mais la stratégie entités vote pour l'article Terre et la fusion "
         "la suit ; (2) « étoile au centre du système solaire » — toutes les stratégies ratent le rang 1, le "
         "boost du titre attirant vers l'article Système solaire.",
         "La mesure par titre de document est elle-même imparfaite : pour « Qui a inventé le code Morse ? », "
         "TF-IDF répond juste depuis l'article Télégraphie électrique (« inventé par Samuel Morse en 1838 ») "
         "et la mesure le compte au rang 2. Une mesure par présence de la réponse serait plus juste ; elle "
         "n'a pas été substituée après coup au critère fixé d'avance.",
         "Embeddings non utilisés : le téléchargement du modèle exige une instruction explicite.",
         "8 questions fixées à l'avance ; échantillon trop petit pour conclure sur la généralisation."],
        dossier=DOSSIER, phase=6) if argv and argv[0] == "--eval" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
