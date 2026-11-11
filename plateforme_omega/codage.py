"""Codage et entrelacement (blueprint §6.2) : Hamming (7,4) avec et sans entrelaceur.

Sur un bruit blanc (canal binaire symétrique), l'entrelacement est neutre : BER
comparable. Sur un canal à rafales (Gilbert-Elliott), il disperse les rafales et le
code de Hamming redevient efficace. Les deux faits sont mesurés, pas affirmés.
"""

import numpy as np

from plateforme_omega.commun import conclure, sortir

G = np.array([[1, 0, 0, 0, 1, 1, 0], [0, 1, 0, 0, 1, 0, 1], [0, 0, 1, 0, 0, 1, 1], [0, 0, 0, 1, 1, 1, 1]])
H = np.array([[1, 1, 0, 1, 1, 0, 0], [1, 0, 1, 1, 0, 1, 0], [0, 1, 1, 1, 0, 0, 1]])
SYNDROME = {tuple(H[:, i]): i for i in range(7)}
PROFONDEUR = 49


def coder(bits):
    return (bits.reshape(-1, 4) @ G % 2).ravel()


def decoder(mots):
    mots = mots.reshape(-1, 7).copy()
    for m in mots:
        s = tuple(H @ m % 2)
        if any(s):
            m[SYNDROME[s]] ^= 1
    return mots[:, :4].ravel()


def entrelacer(x, d=PROFONDEUR):
    return x.reshape(-1, d, 7).transpose(0, 2, 1).ravel()


def desentrelacer(x, d=PROFONDEUR):
    return x.reshape(-1, 7, d).transpose(0, 2, 1).ravel()


def bsc(rng, x, p):
    return x ^ (rng.random(x.size) < p)


def rafales(rng, x, p_entree=0.004, p_sortie=0.2, p_mauvais=0.5):
    erreurs, mauvais = np.zeros(x.size, dtype=int), False
    for i in range(x.size):
        mauvais = (rng.random() > p_sortie) if mauvais else (rng.random() < p_entree)
        erreurs[i] = mauvais and rng.random() < p_mauvais
    return x ^ erreurs


def ber(rng, canal, entrelace, n_bits=4 * PROFONDEUR * 200):
    bits = rng.integers(0, 2, n_bits)
    c = coder(bits)
    if entrelace:
        c = entrelacer(c)
    r = canal(rng, c)
    if entrelace:
        r = desentrelacer(r)
    return float((decoder(r) != bits).mean())


def z_deux_proportions(p1, p2, n):
    p = (p1 + p2) / 2
    return abs(p1 - p2) / max(np.sqrt(2 * p * (1 - p) / n), 1e-12)


def mesurer(graine=7):
    rng = np.random.default_rng(graine)
    blanc = lambda r, x: bsc(r, x, 0.01)
    n_blanc = 4 * PROFONDEUR * 2000
    sans, avec = ber(rng, blanc, False, n_blanc), ber(rng, blanc, True, n_blanc)
    return {"blanc_sans": sans, "blanc_avec": avec, "blanc_bits": n_blanc,
            "blanc_z": float(z_deux_proportions(sans, avec, n_blanc)),
            "rafales_sans": ber(rng, rafales, False), "rafales_avec": ber(rng, rafales, True),
            "correction_unique_exhaustive": all(
                np.array_equal(decoder(coder(np.array(m)) ^ np.eye(7, dtype=int)[i]), np.array(m))
                for m in np.ndindex(2, 2, 2, 2) for i in range(7))}


def main() -> int:
    m = mesurer()
    return conclure("codage", [
        ("Hamming (7,4) corrige toute erreur simple (16 mots × 7 positions)", m["correction_unique_exhaustive"], ""),
        ("bruit blanc : entrelacement neutre (écart non significatif, |z| < 3)", m["blanc_z"] < 3,
         f"{m['blanc_sans']:.5f} sans / {m['blanc_avec']:.5f} avec sur {m['blanc_bits']} bits, z = {m['blanc_z']:.2f}"),
        ("rafales : l'entrelacement divise le BER par au moins 2", m["rafales_avec"] * 2 <= m["rafales_sans"],
         f"{m['rafales_sans']:.4f} sans / {m['rafales_avec']:.4f} avec"),
    ], m, ["Canaux simulés (binaire symétrique, Gilbert-Elliott) ; aucune liaison réelle."], etiquette="SIMULÉ")


if __name__ == "__main__":
    sortir(main())
