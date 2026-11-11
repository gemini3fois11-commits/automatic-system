// PRNG CryoLoop : xoshiro256** (Blackman & Vigna), état initialisé par SplitMix64.
// Usage : cryoloop_prng GRAINE N [--brut]  → N flottants dans [0, 1), ou N entiers 64 bits en hexadécimal.
// Non cryptographique : pour la simulation et les bancs d'essai uniquement.
#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {

uint64_t splitmix64(uint64_t &x) {
    uint64_t z = (x += 0x9e3779b97f4a7c15ULL);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}

inline uint64_t rotl(uint64_t x, int k) { return (x << k) | (x >> (64 - k)); }

struct Xoshiro256 {
    uint64_t s[4];
    explicit Xoshiro256(uint64_t graine) {
        for (auto &v : s) v = splitmix64(graine);
    }
    uint64_t suivant() {
        const uint64_t resultat = rotl(s[1] * 5, 7) * 9;
        const uint64_t t = s[1] << 17;
        s[2] ^= s[0];
        s[3] ^= s[1];
        s[1] ^= s[2];
        s[0] ^= s[3];
        s[2] ^= t;
        s[3] = rotl(s[3], 45);
        return resultat;
    }
};

}  // namespace

int main(int argc, char **argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage : %s GRAINE N [--brut|--splitmix]\n", argv[0]);
        return 2;
    }
    char *fin = nullptr;
    const uint64_t graine = std::strtoull(argv[1], &fin, 10);
    if (*fin != '\0') return 2;
    const long n = std::strtol(argv[2], &fin, 10);
    if (*fin != '\0' || n < 0 || n > 100000000L) return 2;
    const bool brut = argc > 3 && std::strcmp(argv[3], "--brut") == 0;
    if (argc > 3 && std::strcmp(argv[3], "--splitmix") == 0) {
        uint64_t x = graine;
        for (long i = 0; i < n; ++i) std::printf("%016" PRIx64 "\n", splitmix64(x));
        return 0;
    }
    Xoshiro256 g(graine);
    for (long i = 0; i < n; ++i) {
        const uint64_t v = g.suivant();
        if (brut)
            std::printf("%016" PRIx64 "\n", v);
        else
            std::printf("%.17g\n", static_cast<double>(v >> 11) * 0x1.0p-53);
    }
    return 0;
}
