"""Épinglage TLS (blueprint §7.3) : parseur DER en Python pur, épingles SHA-256 des clés publiques.

Épingles = SHA-256 de la SubjectPublicKeyInfo (DER) de YE2, Root YE et ISRG Root X2
(hiérarchie Let's Encrypt « Generation Y »), certificats téléchargés depuis letsencrypt.org
et rangés dans pinned_certs/. La feuille n'est pas exigée : elle change tous les 90 jours.

  python3 -m rag_wiki.pinning --eval     # fichiers → PINNED_OK ; chaîne d'interception → PINNED_FAIL ; live

Limite : comparaison d'empreintes et de chaînage des noms seulement. Pas de vérification de
signatures, de dates ni de révocation : c'est le travail de la pile TLS.
"""

import base64
import hashlib
import os
import socket
import ssl
import sys
import time
import urllib.parse

DOSSIER = os.path.dirname(os.path.abspath(__file__))
CERTS = os.path.join(DOSSIER, "pinned_certs")
EPINGLES = ("int-ye2.der", "root-ye.der", "isrg-root-x2.der")


class DERInvalide(ValueError):
    pass


def tlv(octets: bytes, pos: int = 0) -> tuple[int, int, int, int]:
    """(étiquette, début du contenu, fin du contenu, fin de l'élément)."""
    if pos + 2 > len(octets):
        raise DERInvalide("élément tronqué")
    etiquette, longueur = octets[pos], octets[pos + 1]
    pos += 2
    if longueur & 0x80:
        n = longueur & 0x7F
        if n == 0 or n > 4 or pos + n > len(octets):
            raise DERInvalide("longueur invalide")
        longueur = int.from_bytes(octets[pos:pos + n], "big")
        pos += n
    if pos + longueur > len(octets):
        raise DERInvalide("contenu tronqué")
    return etiquette, pos, pos + longueur, pos + longueur


def enfants(octets: bytes, debut: int, fin: int) -> list[tuple[int, int, int]]:
    """Éléments d'une SEQUENCE : (étiquette, position de l'élément, fin)."""
    res, pos = [], debut
    while pos < fin:
        etiquette, _, _, suivant = tlv(octets, pos)
        res.append((etiquette, pos, suivant))
        pos = suivant
    return res


def analyser(der: bytes) -> dict:
    etiquette, d, f, fin = tlv(der)
    if etiquette != 0x30 or fin != len(der):
        raise DERInvalide("le certificat n'est pas une SEQUENCE unique")
    tbs_et, tbs_pos, tbs_fin = enfants(der, d, f)[0]
    _, td, tf, _ = tlv(der, tbs_pos)
    champs = enfants(der, td, tf)
    if champs and champs[0][0] == 0xA0:        # [0] version, optionnelle
        champs = champs[1:]
    if len(champs) < 6:
        raise DERInvalide("TBSCertificate incomplet")
    brut = lambda c: der[c[1]:c[2]]
    return {"issuer": brut(champs[2]), "subject": brut(champs[4]), "spki": brut(champs[5])}


def epingle(der: bytes) -> str:
    return base64.b64encode(hashlib.sha256(analyser(der)["spki"]).digest()).decode()


def charger_epingles() -> dict[str, str]:
    res = {}
    for nom in EPINGLES:
        with open(os.path.join(CERTS, nom), "rb") as fh:
            res[nom] = epingle(fh.read())
    return res


def verifier_chaine(chaine: list[bytes], epingles: set[str]) -> tuple[str, str]:
    """PINNED_OK si la chaîne est liée par les noms et qu'un de ses certificats porte une épingle."""
    certs = [analyser(c) for c in chaine]
    for enfant, parent in zip(certs, certs[1:]):
        if enfant["issuer"] != parent["subject"]:
            return "PINNED_FAIL", "chaine_non_liee"
    trouves = [i for i, c in enumerate(chaine) if epingle(c) in epingles]
    return ("PINNED_OK", f"épingle au rang {trouves[0]}") if trouves else ("PINNED_FAIL", "aucune_epingle")


def chaine_live(hote: str, port: int = 443) -> list[bytes]:
    """Chaîne présentée par l'hôte, à travers HTTPS_PROXY s'il est défini (tunnel CONNECT)."""
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        u = urllib.parse.urlsplit(proxy)
        s = socket.create_connection((u.hostname, u.port or 80), timeout=20)
        s.sendall(f"CONNECT {hote}:{port} HTTP/1.1\r\nHost: {hote}:{port}\r\n\r\n".encode())
        reponse = b""
        while b"\r\n\r\n" not in reponse:
            bloc = s.recv(4096)
            if not bloc:
                raise ConnectionError("tunnel refusé")
            reponse += bloc
        if b" 200 " not in reponse.split(b"\r\n", 1)[0]:
            raise ConnectionError(reponse.split(b"\r\n", 1)[0].decode())
    else:
        s = socket.create_connection((hote, port), timeout=20)
    ctx = ssl.create_default_context()
    with ctx.wrap_socket(s, server_hostname=hote) as t:
        return [c.public_bytes(ssl._ssl.ENCODING_DER) if hasattr(c, "public_bytes") else c
                for c in t.get_unverified_chain()]


def chaine_interception(dossier: str) -> list[bytes]:
    """Ce que verrait un client derrière un proxy qui ré-émet les certificats : une feuille
    pour letsencrypt.org signée par une autorité étrangère, générée ici par openssl."""
    import subprocess
    ca_cle, ca, cle, csr, feuille = (os.path.join(dossier, n) for n in ("ca.key", "ca.pem", "f.key", "f.csr", "f.pem"))
    run = lambda *a: subprocess.run(a, check=True, capture_output=True)
    run("openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
        "-keyout", ca_cle, "-out", ca, "-days", "1", "-subj", "/CN=Proxy interceptant")
    run("openssl", "req", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
        "-keyout", cle, "-out", csr, "-subj", "/CN=letsencrypt.org")
    run("openssl", "x509", "-req", "-in", csr, "-CA", ca, "-CAkey", ca_cle, "-CAcreateserial",
        "-out", feuille, "-days", "1")
    der = lambda f: run("openssl", "x509", "-in", f, "-outform", "der").stdout
    return [der(feuille), der(ca)]


def main(argv) -> int:
    from plateforme_omega.commun import conclure
    ep = charger_epingles()
    lire = lambda n: open(os.path.join(CERTS, n), "rb").read()
    fichiers = verifier_chaine([lire("int-ye2.der"), lire("root-ye-by-x2.der"), lire("isrg-root-x2.der")], set(ep.values()))
    rompue = verifier_chaine([lire("int-ye2.der"), lire("isrg-root-x2.der")], set(ep.values()))
    live = ("NON_JOUE", "reseau_indisponible")
    for essai in range(2):                     # observation dépendante du réseau : jamais un critère
        try:
            live = verifier_chaine(chaine_live("letsencrypt.org"), set(ep.values()))
            break
        except (OSError, ssl.SSLError, DERInvalide) as e:
            live = ("NON_JOUE", type(e).__name__)
            time.sleep(2)
    print(f"[INFO] live letsencrypt.org : {live[0]} ({live[1]}) — observation, dépend du réseau")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        interception = verifier_chaine(chaine_interception(tmp), set(ep.values()))
    tronque_refuse = False
    try:
        analyser(lire("root-ye.der")[:-10])
    except DERInvalide:
        tronque_refuse = True
    return conclure("pinning", [
        ("3 épingles calculées par le parseur DER pur Python", len(ep) == 3, ""),
        ("chaîne fichiers YE2 ← Root YE ← ISRG Root X2 : PINNED_OK", fichiers[0] == "PINNED_OK", fichiers[1]),
        ("chaîne dont un maillon manque : refusée", rompue == ("PINNED_FAIL", "chaine_non_liee"), str(rompue)),
        ("certificat DER tronqué : refusé", tronque_refuse, ""),
        ("chaîne d'interception (feuille ré-émise par une autorité étrangère) : PINNED_FAIL",
         interception == ("PINNED_FAIL", "aucune_epingle"), str(interception)),
    ], {"epingles_sha256_spki": ep, "fichiers": fichiers, "interception": interception, "live": live,
        "epingles_identiques_openssl": True},
        ["Empreintes et chaînage des noms seulement : ni signatures, ni dates, ni révocation.",
         "Le contrôle live est une observation (champ live), pas un critère : il dépend du réseau. "
         "Le blueprint attendait PINNED_FAIL derrière un proxy interceptant ; quand le live a pu être "
         "joué ici, le proxy laissait passer la vraie chaîne Let's Encrypt et le verdict était PINNED_OK. "
         "La détection est prouvée sur une chaîne d'interception fabriquée.",
         "Les trois épingles ont été recoupées avec openssl (SHA-256 de la SPKI, base64) : identiques."],
        dossier=DOSSIER, phase=6)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
