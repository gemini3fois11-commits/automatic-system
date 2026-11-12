// bench.c — mesures d'efficacité sur trois niveaux : mémoire, instructions, noyau.
// Chaque expérience compare deux implémentations qui calculent le même résultat.
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>

static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

// Meilleur temps sur REPS exécutions : élimine le bruit du planificateur.
#define REPS 5
#define BEST(var, expr) do { var = 1e30; for (int r_ = 0; r_ < REPS; r_++) { \
    double t0_ = now(); expr; double t_ = now() - t0_; if (t_ < var) var = t_; } } while (0)

static volatile uint64_t sink; // empêche le compilateur de supprimer les calculs

static void report(const char *name, const char *a, double ta, const char *b, double tb) {
    printf("%-30s | %-20s %10.0f us | %-20s %10.0f us | x%.1f\n",
           name, a, ta * 1e6, b, tb * 1e6, ta / tb);
}

// ---------- 1. Mémoire : disposition des données ----------
#define N_PART (1 << 22)
typedef struct { double x, y, z, vx, vy, vz, mass, charge; } particle; // 64 octets

static uint64_t sum_aos(const particle *p) {
    double s = 0; for (size_t i = 0; i < N_PART; i++) s += p[i].mass; return (uint64_t)s;
}
static uint64_t sum_soa(const double *mass) {
    double s = 0; for (size_t i = 0; i < N_PART; i++) s += mass[i]; return (uint64_t)s;
}

#define DIM 4096
static uint64_t traverse_cols(const uint32_t *m) {
    uint64_t s = 0; for (size_t j = 0; j < DIM; j++) for (size_t i = 0; i < DIM; i++) s += m[i * DIM + j]; return s;
}
static uint64_t traverse_rows(const uint32_t *m) {
    uint64_t s = 0; for (size_t i = 0; i < DIM; i++) for (size_t j = 0; j < DIM; j++) s += m[i * DIM + j]; return s;
}

// ---------- 2. Instructions : branchements ----------
#define N_VAL (1 << 24)
__attribute__((noinline)) static uint64_t filter_branchy(const uint8_t *v) {
    uint64_t s = 0;
    for (size_t i = 0; i < N_VAL; i++) {
        if (v[i] >= 128) { s += v[i]; __asm__ volatile(""); } // asm dans le if : empêche cmov, vrai saut
    }
    return s;
}
__attribute__((noinline)) static uint64_t filter_branchless(const uint8_t *v) {
    uint64_t s = 0;
    for (size_t i = 0; i < N_VAL; i++) s += v[i] & -(uint64_t)(v[i] >> 7); // masque, pas de saut
    return s;
}

// ---------- 3. Noyau : nombre d'appels système ----------
#define N_BYTES (1 << 20)
static void write_unbuffered(int fd) { char c = 'x'; for (int i = 0; i < N_BYTES; i++) if (write(fd, &c, 1) < 0) abort(); }
static void write_buffered(int fd) {
    static char buf[1 << 16]; memset(buf, 'x', sizeof buf);
    for (int i = 0; i < N_BYTES; i += sizeof buf) if (write(fd, buf, sizeof buf) < 0) abort();
}

static int cmp_u8(const void *a, const void *b) { return *(const uint8_t *)a - *(const uint8_t *)b; }

int main(void) {
    double ta, tb;
    srand(42);
    printf("%-30s | %-34s | %-34s | gain\n", "experience", "avant", "apres");

    particle *aos = malloc(sizeof(particle) * N_PART);
    double *mass = malloc(sizeof(double) * N_PART);
    for (size_t i = 0; i < N_PART; i++) { memset(&aos[i], 0, sizeof aos[i]); aos[i].mass = mass[i] = i & 7; }
    BEST(ta, sink = sum_aos(aos));
    BEST(tb, sink = sum_soa(mass));
    if (sum_aos(aos) != sum_soa(mass)) return 1;
    report("1a. struct -> tableaux", "AoS (64 o/elt)", ta, "SoA (8 o/elt)", tb);
    free(aos); free(mass);

    uint32_t *m = malloc(sizeof(uint32_t) * DIM * DIM);
    for (size_t i = 0; i < (size_t)DIM * DIM; i++) m[i] = i & 0xff;
    BEST(ta, sink = traverse_cols(m));
    BEST(tb, sink = traverse_rows(m));
    if (traverse_cols(m) != traverse_rows(m)) return 1;
    report("1b. ordre de parcours matrice", "colonnes", ta, "lignes", tb);
    free(m);

    uint8_t *v = malloc(N_VAL);
    for (size_t i = 0; i < N_VAL; i++) v[i] = rand() & 0xff; // aléatoire : prédicteur à 50 %
    BEST(ta, sink = filter_branchy(v));
    BEST(tb, sink = filter_branchless(v));
    if (filter_branchy(v) != filter_branchless(v)) return 1;
    report("2a. filtre, donnees aleatoires", "saut conditionnel", ta, "masque binaire", tb);
    // Même code, données triées : le prédicteur ne se trompe plus.
    qsort(v, N_VAL, 1, cmp_u8);
    BEST(tb, sink = filter_branchy(v));
    report("2b. meme saut, donnees triees", "aleatoire", ta, "trie", tb);
    free(v);

    int fd = open("/dev/null", O_WRONLY);
    BEST(ta, write_unbuffered(fd));
    BEST(tb, write_buffered(fd));
    close(fd);
    report("3. appels systeme (1 Mo)", "1048576 write()", ta, "16 write()", tb);
    return 0;
}
