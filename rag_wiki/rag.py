"""RAG Wikipédia de base (blueprint §7.1) : découpage, TF-IDF, réponse EXTRACTIVE citée.

Aucun modèle génératif : la réponse est faite de phrases du corpus, chacune citée
(titre, révision, URL). Si rien ne correspond, la réponse le dit au lieu d'inventer.

  python3 -m rag_wiki.rag "question"      # réponse citée
  python3 -m rag_wiki.rag --eval          # MRR sur les 8 questions, écrit rag_evidence.json
"""

import collections
import math
import os
import re
import sys
import unicodedata

from rag_wiki.corpus import charger, nettoyer

DOSSIER = os.path.dirname(os.path.abspath(__file__))
TAILLE, CHEVAUCHEMENT = 500, 100
MOTS_MIN = 20          # un morceau plus pauvre (débris de formule) n'est pas indexé
VIDES = set("""le la les l un une des du de d et ou en à a au aux ce cet cette ces se sa son ses
qui que quoi qu est sont été être par pour sur dans avec sans plus moins ne pas il elle ils elles
on nous vous leur leurs y comme mais donc or ni car quel quelle quels quelles lui c s n j m t
est-ce sert""".split())
# Questions fixées avant toute mesure, avec le document attendu.
QUESTIONS = (
    ("Quel est le satellite naturel de la Terre ?", "Lune"),
    ("Quelle étoile se trouve au centre du système solaire ?", "Soleil"),
    ("Quelle planète est surnommée la planète rouge ?", "Mars (planète)"),
    ("Qu'est-ce qu'une fonction de hachage cryptographique ?", "Fonction de hachage"),
    ("Quelles fonctions composent la famille SHA-2 ?", "SHA-2"),
    ("Qui a inventé le code Morse ?", "Code Morse international"),
    ("À quoi sert le filtre de Kalman ?", "Filtre de Kalman"),
    ("Quelle est la complexité de la transformation de Fourier rapide ?", "Transformation de Fourier rapide"),
)


def jetons(texte: str) -> list[str]:
    t = unicodedata.normalize("NFKD", texte.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return [m for m in re.findall(r"[a-z0-9]+", t) if m not in VIDES and len(m) > 1]


def decouper(corpus: dict) -> list[dict]:
    morceaux = []
    for d in corpus["documents"]:
        texte = nettoyer(d["texte"])
        for debut in range(0, max(len(texte) - CHEVAUCHEMENT, 1), TAILLE - CHEVAUCHEMENT):
            morceau = texte[debut:debut + TAILLE]
            if len(jetons(morceau)) >= MOTS_MIN:
                morceaux.append({"titre": d["titre"], "revision": d["revision"], "url": d["url"],
                                 "texte": morceau})
    return morceaux


class IndexTFIDF:
    def __init__(self, morceaux, boost_titre: int = 2):
        self.morceaux = morceaux
        # Boost du titre ×2 (§7.2) : sans lui, « Terre » est volée par « Lune ».
        self.sacs = [collections.Counter(jetons(m["texte"]) + jetons(m["titre"]) * boost_titre) for m in morceaux]
        df = collections.Counter(t for s in self.sacs for t in s)
        n = len(self.sacs)
        self.idf = {t: math.log((1 + n) / (1 + f)) + 1 for t, f in df.items()}
        self.vecteurs = []
        for s in self.sacs:
            v = {t: (1 + math.log(c)) * self.idf[t] for t, c in s.items()}
            norme = math.sqrt(sum(x * x for x in v.values())) or 1.0
            self.vecteurs.append({t: x / norme for t, x in v.items()})

    def classer(self, question: str) -> list[int]:
        q = collections.Counter(jetons(question))
        v = {t: (1 + math.log(c)) * self.idf.get(t, 0) for t, c in q.items()}
        norme = math.sqrt(sum(x * x for x in v.values())) or 1.0
        scores = [sum(v.get(t, 0) * x for t, x in vec.items() if t in v) / norme for vec in self.vecteurs]
        return sorted(range(len(scores)), key=lambda i: (-scores[i], i))


def mrr(classeur, morceaux, questions=QUESTIONS) -> dict:
    rangs = {}
    for q, attendu in questions:
        ordre = classeur(q)
        rang = next((r + 1 for r, i in enumerate(ordre) if morceaux[i]["titre"] == attendu), None)
        rangs[q] = rang
    return {"mrr": sum(1 / r for r in rangs.values() if r) / len(questions), "rangs": rangs}


def repondre_avec(classeur, morceaux, question: str, k: int = 3) -> dict:
    ordre = classeur(question)[:k]
    termes = set(jetons(question))
    citations = []
    for i in ordre:
        m = morceaux[i]
        phrases = re.split(r"(?<=[.!?])\s+", m["texte"])
        meilleure = max(phrases, key=lambda p: len(termes & set(jetons(p))))
        if termes & set(jetons(meilleure)):
            citations.append({"extrait": meilleure.strip(), "titre": m["titre"], "revision": m["revision"],
                              "url": m["url"]})
    if not citations:
        return {"question": question, "reponse": None, "motif": "aucune_source_pertinente", "citations": []}
    return {"question": question, "reponse": citations[0]["extrait"], "citations": citations}


def annees_par_document(corpus: dict) -> dict[str, int]:
    """Nombre d'années à 4 chiffres par document : un texte aux dates effacées en aurait zéro."""
    return {d["titre"]: len(re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", d["texte"]))
            for d in corpus["documents"]}


def main(argv) -> int:
    corpus = charger()
    morceaux = decouper(corpus)
    index = IndexTFIDF(morceaux)
    if argv and argv[0] == "--eval":
        from plateforme_omega.commun import conclure
        m = mrr(index.classer, morceaux)
        vocab = len(index.idf)
        annees = annees_par_document(corpus)
        return conclure("rag", [
            ("corpus réel : 12 documents tracés (révision, URL)", len(corpus["documents"]) == 12
             and all(d["revision"] and d["url"] for d in corpus["documents"]), corpus["collecte"]),
            ("chiffres et dates conservés dans chaque document (≥ 3 années à 4 chiffres)",
             min(annees.values()) >= 3, f"minimum {min(annees.values())}, total {sum(annees.values())}"),
            ("découpage ~500 caractères, chevauchement 100", len(morceaux) > 0, f"{len(morceaux)} morceaux, {vocab} termes"),
            ("MRR TF-IDF sur 8 questions ≥ 0,75", m["mrr"] >= 0.75, f"{m['mrr']:.3f}"),
            ("réponse extractive citée, jamais inventée",
             all(c["url"] for c in repondre_avec(index.classer, morceaux, QUESTIONS[0][0])["citations"])
             and repondre_avec(index.classer, morceaux, "zzzz qwxv")["reponse"] is None, ""),
        ], {"documents": len(corpus["documents"]), "morceaux": len(morceaux), "vocabulaire": vocab,
            "methode_collecte": corpus.get("methode"), "annees_par_document": annees} | m,
            ["Le MRR du corpus fixe ne se transfère pas à une recherche live.",
             "Source : Wikipédia en français par l'Action API. Le jeu Hugging Face wikimedia/wikipedia "
             "(20231101.fr) et Wikidata ne sont pas utilisés ; aucun modèle n'est entraîné sur ces textes.",
             "Les débris de formules mathématiques de l'extraction Wikipédia sont nettoyés et les morceaux "
             "de moins de 20 mots écartés : sans cela, le boost du titre plaçait des morceaux vides en tête.",
             "8 questions : échantillon minuscule ; un MRR de 1,000 ne prouve pas la généralisation.",
             "Texte CC BY-SA 4.0 des contributeurs de Wikipédia, à la révision indiquée."],
            dossier=DOSSIER, phase=6)
    r = repondre_avec(index.classer, morceaux, " ".join(argv))
    print(r["reponse"] or f"[{r['motif']}]")
    for c in r["citations"]:
        print(f"  — {c['titre']} (révision {c['revision']}) {c['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
