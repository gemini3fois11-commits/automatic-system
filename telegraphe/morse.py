"""Manipulateur Morse à unité de temps adaptative (blueprint §8.2).

Code international. Une unité = durée du point. Point = 1, trait = 3,
espace intra-caractère = 1, espace inter-caractère = 3, espace entre mots = 7.

Le décodeur est **adaptatif** : il n'est pas informé de l'unité. Il l'estime
depuis les durées observées (les appuis courts et longs se séparent autour de
2 unités, les silences autour de 2 et de 5), puis classe chaque durée. Un
aller-retour reste exact même quand l'unité varie dans le temps, tant que le
contraste court/long tient. Ce qu'il ne fait pas : récupérer un signal noyé
dans le bruit, ou deviner entre deux cadences si l'opérateur hésite exactement
à la frontière.
"""

CODE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.", "!": "-.-.--",
    "/": "-..-.", "(": "-.--.", ")": "-.--.-", "&": ".-...", ":": "---...",
    ";": "-.-.-.", "=": "-...-", "+": ".-.-.", "-": "-....-", "_": "..--.-",
    '"': ".-..-.", "@": ".--.-.",
}
INVERSE = {v: k for k, v in CODE.items()}


class MorseInvalide(ValueError):
    def __init__(self, raison: str):
        super().__init__(raison)
        self.raison = raison


def encoder(texte: str) -> str:
    """Texte → code Morse : symboles séparés par un espace, mots par ` / `."""
    mots = []
    for mot in texte.upper().split():
        lettres = []
        for car in mot:
            if car not in CODE:
                raise MorseInvalide(f"caractere_hors_code:{car!r}")
            lettres.append(CODE[car])
        mots.append(" ".join(lettres))
    return " / ".join(mots)


def decoder(code: str) -> str:
    """Code Morse (format de `encoder`) → texte."""
    mots = []
    for mot in code.strip().split(" / "):
        lettres = []
        for sym in mot.split():
            if sym not in INVERSE:
                raise MorseInvalide(f"symbole_inconnu:{sym!r}")
            lettres.append(INVERSE[sym])
        mots.append("".join(lettres))
    return " ".join(mots)


def vers_durees(texte: str, unite: int = 1) -> list[tuple[int, int]]:
    """Texte → liste d'événements (etat, duree) : etat 1 = clé baissée (son), 0 = silence.

    Les durées sont en unités × `unite`. Pas de silence en tête ni en queue.
    """
    evenements: list[tuple[int, int]] = []
    for mot_index, mot in enumerate(encoder(texte).split(" / ")):
        if mot_index > 0:
            evenements.append((0, 7 * unite))                  # espace entre mots
        for lettre_index, sym in enumerate(mot.split(" ")):
            if lettre_index > 0:
                evenements.append((0, 3 * unite))              # espace inter-caractère
            for signe_index, signe in enumerate(sym):
                if signe_index > 0:
                    evenements.append((0, 1 * unite))          # espace intra-caractère
                evenements.append((1, (3 if signe == "-" else 1) * unite))
    return evenements


def _estimer_unite(durees: list[int]) -> float:
    """Unité ≈ moyenne du plus bas groupe de durées (points et silences intra, ~1 unité).

    Le plus bas groupe s'arrête au premier écart marqué (saut vers le groupe ~3
    unités). Moyenner le groupe annule la gigue par élément, là où prendre le
    minimum la propageait. Hypothèse : le signal contient au moins un élément
    d'une unité (un point ou un silence intra-caractère) ; sinon l'unité est
    surestimée — limite assumée.
    """
    s = sorted(durees)
    groupe = [s[0]]
    for a, b in zip(s, s[1:]):
        if b - a > 0.6 * a:      # saut de cluster (1 → 3 unités)
            break
        groupe.append(b)
    return sum(groupe) / len(groupe)


def depuis_durees(evenements: list[tuple[int, int]]) -> str:
    """Événements (etat, duree) → texte, en estimant l'unité sur place (adaptatif).

    L'unité est la durée du plus court événement (un point ou un silence
    intra-caractère valent une unité). Les sons se séparent à 2 unités
    (point/trait), les silences à 2 et 5 unités (intra / inter / mot) — les
    milieux des rapports 1-3 et 3-7. Lève MorseInvalide si la structure manque.
    """
    if not evenements:
        raise MorseInvalide("vide")
    sons = [d for e, d in evenements if e == 1]
    if not sons:
        raise MorseInvalide("aucun_son")
    if min(d for _, d in evenements) <= 0:
        raise MorseInvalide("duree_nulle")
    unite = _estimer_unite([d for _, d in evenements])

    symboles, courant = [], []           # symboles : "<code lettre>" et "/" (mot)
    for etat, duree in evenements:
        if etat == 1:
            courant.append("-" if duree >= 2 * unite else ".")
        elif duree >= 5 * unite:         # silence entre mots
            symboles.append("".join(courant)); courant = []
            symboles.append("/")
        elif duree >= 2 * unite:         # silence inter-caractère
            symboles.append("".join(courant)); courant = []
        # sinon : silence intra-caractère, on ne coupe pas
    symboles.append("".join(courant))

    mots, mot = [], []
    for p in symboles:
        if p == "/":
            mots.append(" ".join(mot)); mot = []
        elif p:
            mot.append(p)
    if mot:
        mots.append(" ".join(mot))
    return decoder(" / ".join(m for m in mots if m))
