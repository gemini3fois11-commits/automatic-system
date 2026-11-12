# Efficacité : mesures, pas métaphores

`bench.c` compare, pour trois niveaux du système, deux implémentations qui
calculent **le même résultat** (vérifié dans le programme). Seule la façon
dont le code sollicite la machine change.

```sh
gcc -O2 -march=native -Wall -Wextra -o bench bench.c && ./bench
```

## Résultats (Xeon 2,1 GHz, 4 vCPU KVM, meilleur de 5 exécutions)

| Niveau | Expérience | Avant | Après | Gain |
|---|---|---|---|---|
| Mémoire | Lire un champ : tableau de structs (AoS) → tableau dédié (SoA) | 18,4 ms | 2,6 ms | ×6–7 |
| Mémoire | Parcourir une matrice 4096² : par colonnes → par lignes | 144 ms | 3,2 ms | ×35–45 |
| Instructions | Filtre sur données aléatoires : saut conditionnel → masque binaire | 77 ms | 7,9 ms | ×10 |
| Instructions | Même saut, données triées au lieu d'aléatoires | 77 ms | 5,2 ms | ×12–15 |
| Noyau | Écrire 1 Mo : 1 octet par `write()` → tampon de 64 Ko | 100 ms | 0,003 ms | ×40 000 |

Les gains varient de ±20 % d'une exécution à l'autre ; les ordres de grandeur sont stables.

## Ce que chaque ligne montre

- **AoS → SoA** : le CPU charge des lignes de cache de 64 octets. Avec une
  struct de 64 octets, lire `mass` ramène 56 octets inutiles par élément. En
  tableau séparé, chaque octet chargé sert, et le compilateur vectorise.
- **Lignes vs colonnes** : en C, une matrice est stockée ligne par ligne. Le
  parcours par colonnes saute de 16 Ko à chaque accès : chaque lecture est un
  défaut de cache, et le préchargeur matériel ne peut rien anticiper.
- **Branchement** : sur des données aléatoires, le prédicteur se trompe une
  fois sur deux, et chaque erreur vide le pipeline (~15–20 cycles). Le masque
  `v & -(v >> 7)` remplace le saut par de l'arithmétique et se vectorise.
  La ligne « triées » prouve que c'est bien la prédiction : même code machine,
  seul l'ordre des données change.
  Piège rencontré : sans précaution, GCC transforme déjà le `if` en `cmov`
  (pas de saut). Le `asm volatile("")` dans le corps du `if` force un vrai saut.
- **Appels système** : chaque `write()` traverse la frontière utilisateur/noyau
  (~100 ns ici). Regrouper les écritures supprime ce coût fixe. C'est la même
  logique qui rend `fwrite`/`BufWriter` rapides.

## Règle générale

Avant d'optimiser un calcul, regarder dans l'ordre :
1. combien de fois on traverse le noyau (syscalls, I/O) ;
2. comment les données sont rangées en mémoire par rapport à l'ordre d'accès ;
3. seulement ensuite, les branchements et les instructions.

`perf` n'est pas disponible dans ce conteneur ; sur une machine Debian,
`perf stat -e cycles,instructions,cache-misses,branch-misses ./bench`
confirme chaque explication par les compteurs matériels.
