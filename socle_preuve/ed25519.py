"""Ed25519 pur Python, RFC 8032 §5.1, en coordonnées projectives étendues.

Aucune inversion modulaire hors de l'encodage d'un point. Vérification
cofactorless (équation [S]B = R + [k]A), comme le code de référence du RFC.

Ce module n'est pas à temps constant : il convient à la vérification et à une
démonstration, pas à la signature avec une clé de valeur sur une machine partagée.
"""

import hashlib

p = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
d = -121665 * pow(121666, p - 2, p) % p
_SQRT_M1 = pow(2, (p - 1) // 4, p)

_IDENTITE = (0, 1, 1, 0)


def _sha512_mod_l(*parts: bytes) -> int:
    return int.from_bytes(hashlib.sha512(b"".join(parts)).digest(), "little") % L


def _add(P, Q):
    X1, Y1, Z1, T1 = P
    X2, Y2, Z2, T2 = Q
    A = (Y1 - X1) * (Y2 - X2) % p
    B = (Y1 + X1) * (Y2 + X2) % p
    C = 2 * T1 * T2 * d % p
    D = 2 * Z1 * Z2 % p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % p, G * H % p, F * G % p, E * H % p)


def _double(P):
    X1, Y1, Z1, _ = P
    A = X1 * X1 % p
    B = Y1 * Y1 % p
    C = 2 * Z1 * Z1 % p
    H = A + B
    E = H - (X1 + Y1) ** 2
    G = A - B
    F = C + G
    return (E * F % p, G * H % p, F * G % p, E * H % p)


def _mul(s: int, P):
    Q = _IDENTITE
    while s:
        if s & 1:
            Q = _add(Q, P)
        P = _double(P)
        s >>= 1
    return Q


def _egal(P, Q) -> bool:
    X1, Y1, Z1, _ = P
    X2, Y2, Z2, _ = Q
    return (X1 * Z2 - X2 * Z1) % p == 0 and (Y1 * Z2 - Y2 * Z1) % p == 0


def _recover_x(y: int, signe: int) -> int | None:
    if y >= p:
        return None
    x2 = (y * y - 1) * pow(d * y * y + 1, p - 2, p) % p
    if x2 == 0:
        return None if signe else 0
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p:
        x = x * _SQRT_M1 % p
    if (x * x - x2) % p:
        return None
    if x & 1 != signe:
        x = p - x
    return x


def _encoder(P) -> bytes:
    X, Y, Z, _ = P
    zinv = pow(Z, p - 2, p)
    x, y = X * zinv % p, Y * zinv % p
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decoder(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    signe = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, signe)
    if x is None:
        return None
    return (x, y, 1, x * y % p)


_gy = 4 * pow(5, p - 2, p) % p
B = (_recover_x(_gy, 0), _gy, 1, _recover_x(_gy, 0) * _gy % p)


def _etendre(graine: bytes) -> tuple[int, bytes]:
    if len(graine) != 32:
        raise ValueError("la clé privée Ed25519 fait 32 octets")
    h = hashlib.sha512(graine).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def cle_publique(graine: bytes) -> bytes:
    a, _ = _etendre(graine)
    return _encoder(_mul(a, B))


def signer(graine: bytes, message: bytes) -> bytes:
    a, prefixe = _etendre(graine)
    A = _encoder(_mul(a, B))
    r = _sha512_mod_l(prefixe, message)
    R = _encoder(_mul(r, B))
    k = _sha512_mod_l(R, A, message)
    s = (r + k * a) % L
    return R + s.to_bytes(32, "little")


def verifier(publique: bytes, message: bytes, signature: bytes) -> bool:
    if len(publique) != 32 or len(signature) != 64:
        return False
    A = _decoder(publique)
    R = _decoder(signature[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= L:  # refus de la malléabilité de S (RFC 8032 §5.1.7)
        return False
    k = _sha512_mod_l(signature[:32], publique, message)
    return _egal(_mul(s, B), _add(R, _mul(k, A)))
