"""Vecteurs de test RFC 8032 §7.1 (Ed25519) : TEST 1, 2, 3 et TEST SHA(abc).

TEST 1024 n'est pas repris : son message de 1 023 octets n'a pas été transcrit.
"""

import hashlib

VECTEURS = [
    ("TEST 1",
     "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("TEST 2",
     "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("TEST 3",
     "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
     "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
    ("TEST SHA(abc)",
     "833fe62409237b9d62ec77587520911e9a759cec1d19755b7da901b96dca3d42",
     "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
     hashlib.sha512(b"abc").hexdigest(),
     "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b589"
     "09351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704"),
]


def verifier_vecteurs() -> list[tuple[str, str, bool]]:
    """Trois contrôles par vecteur : clé publique, signature exacte, vérification."""
    from socle_preuve import ed25519

    res = []
    for nom, sk, pk, msg, sig in VECTEURS:
        sk, pk, msg, sig = map(bytes.fromhex, (sk, pk, msg, sig))
        res.append((nom, "cle_publique", ed25519.cle_publique(sk) == pk))
        res.append((nom, "signature", ed25519.signer(sk, msg) == sig))
        res.append((nom, "verification", ed25519.verifier(pk, msg, sig)))
    return res
