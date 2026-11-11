"""Ω Q — la porte qualité des modules (blueprint §6.4).

Q = S + P + R − C
  S = 1 − taux d'échec            P = 1 − 1 / gain mesuré (0 si le gain n'est pas mesuré)
  R = taux de reprise (0, avec drapeau, si non mesuré)
  C = min(0,5 × LOC/1000 + 0,5 × runtime/60, 1)   ou un coût direct déclaré
Décision : Q > 0 ACCEPTER · Q = 0 REVOIR · Q < 0 REJETER, même si le module est « valide ».
Veto : si l'attaquant réussit, REJETER quel que soit Q.
"""

from plateforme_omega.commun import conclure, sortir


def evaluer(*, taux_echec: float, gain: float | None, reprise: float | None, loc: int, runtime_s: float,
            cout_direct: float | None = None, attaquant_reussi: bool = False) -> dict:
    drapeaux = []
    S = 1 - taux_echec
    if gain is None or gain <= 0:
        P, _ = 0.0, drapeaux.append("gain_non_mesure")
    else:
        P = 1 - 1 / gain
    if reprise is None:
        R, _ = 0.0, drapeaux.append("reprise_non_mesuree")
    else:
        R = reprise
    C = cout_direct if cout_direct is not None else min(0.5 * loc / 1000 + 0.5 * runtime_s / 60, 1.0)
    Q = round(S + P + R - C, 6)
    if attaquant_reussi:
        decision = "REJETER"
        drapeaux.append("veto_attaquant")
    else:
        decision = "ACCEPTER" if Q > 0 else ("REVOIR" if Q == 0 else "REJETER")
    return {"S": S, "P": P, "R": R, "C": C, "Q": Q, "decision": decision, "drapeaux": drapeaux}


def main() -> int:
    cas = {
        "module valide, rien de mesuré, coûteux": evaluer(taux_echec=0.1, gain=None, reprise=None, loc=1200, runtime_s=60),
        "module à l'équilibre": evaluer(taux_echec=0.5, gain=None, reprise=None, loc=0, runtime_s=0, cout_direct=0.5),
        "module qui démontre sa reprise": evaluer(taux_echec=0.0, gain=4.0, reprise=1.0, loc=200, runtime_s=2),
        "attaquant réussi, Q élevé": evaluer(taux_echec=0.0, gain=10.0, reprise=1.0, loc=10, runtime_s=1,
                                             attaquant_reussi=True),
    }
    return conclure("omega_q", [
        ("valide mais instable (10 % d'échecs), coûteux, sans mesure : Q < 0, REJETER (R non mesuré compte 0)",
         cas["module valide, rien de mesuré, coûteux"]["decision"] == "REJETER"
         and "reprise_non_mesuree" in cas["module valide, rien de mesuré, coûteux"]["drapeaux"],
         f"Q = {cas['module valide, rien de mesuré, coûteux']['Q']}"),
        ("Q = 0 : REVOIR", cas["module à l'équilibre"]["decision"] == "REVOIR", ""),
        ("la reprise démontrée paie : Q > 1, ACCEPTER", cas["module qui démontre sa reprise"]["Q"] > 1
         and cas["module qui démontre sa reprise"]["decision"] == "ACCEPTER",
         f"Q = {cas['module qui démontre sa reprise']['Q']}"),
        ("veto : attaquant réussi → REJETER malgré Q > 0", cas["attaquant réussi, Q élevé"]["decision"] == "REJETER"
         and cas["attaquant réussi, Q élevé"]["Q"] > 0, ""),
    ], {"cas": cas}, ["Les poids de la formule sont ceux du blueprint ; ils ne sont pas étalonnés sur un historique."],
        etiquette="DÉMONTRÉ")


if __name__ == "__main__":
    sortir(main())
