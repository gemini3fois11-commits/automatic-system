# Matrice de traçabilité — exigence → code → test → évidence

> Générée par `python3 -m dossier.generer`. Chaque exigence du blueprint est reliée au
> code qui la met en œuvre, aux tests qui la contrôlent et au fichier d'évidence qui
> en porte la mesure. Un vide dans une colonne est une dette explicite, pas un oubli.

| Exigence | Source | Résumé | Code | Tests | Évidence |
|---|---|---|---|---|---|
| **E-1.1** | §1.1 Mission | Un refus produit une preuve vérifiable par un témoin indépendant. | `socle_preuve/gamma.py`, `socle_preuve/temoin.py`, `rinv/systeme.py` | `socle_preuve.test_gamma`, `socle_preuve.test_temoin`, `tests.test_systeme` | `socle_preuve/preuve_evidence.json`, `rinv/systeme_evidence.json` |
| **E-1.2** | §1.2 Refuser avant de croire | Allowlist exacte ; le classifieur rejette plutôt que de forcer une classe. | `agent_guard/guard.py`, `omega_hermes/bob.py` | `agent_guard.test_guard`, `omega_hermes.test_bob`, `omega_hermes.test_hermes` | `agent_guard/guard_evidence.json`, `omega_hermes/hermes_evidence.json` |
| **E-1.3** | §1.3 Étiquettes d'honnêteté | Chaque évidence porte une étiquette (VÉRIFIÉ/SIMULÉ/DÉMONTRÉ/SPÉCIFIÉ/…). | `outils/evidence.py` | — | `(toutes les évidences)` |
| **E-1.5** | §1.5 Découplage synthétique | Les modules du banc n'importent que la liste blanche (pas de socket, pas d'open). | `omega_hermes/decouplage.py`, `omega_hermes/twin.py`, `omega_hermes/alice.py`, `omega_hermes/eyes.py`, `omega_hermes/bob.py` | `omega_hermes.test_twin` | `omega_hermes/hermes_evidence.json` |
| **E-2.1** | §2.1 Écoute 127.0.0.1 seulement | Toutes les portes refusent une autre interface. | `socle_preuve/porte_http.py`, `agent_guard/guard.py`, `cryoloop_gateway/gateway.py`, `terminal_auth/server.py` | `socle_preuve.test_auth`, `socle_preuve.test_porte_http` | `outils/phase3_evidence.json` |
| **E-3.1** | §3.1 Chaîne Γ append-only SHA-256 | hash = SHA-256(prev_hash || canon(bloc)) ; vérificateur nomme le seq fautif. | `socle_preuve/gamma.py` | `socle_preuve.test_gamma` | `socle_preuve/preuve_evidence.json` |
| **E-3.2** | §3.2 Témoin indépendant | Scelle (seq, hash) hors du journal ; détecte toute réécriture. | `socle_preuve/temoin.py`, `socle_preuve/ed25519.py` | `socle_preuve.test_temoin`, `socle_preuve.test_ed25519` | `socle_preuve/preuve_evidence.json` |
| **E-3.3** | P-BYP-27 contournement | Le contrôle OCC est sous le verrou d'écriture, pas au-dessus. | `socle_preuve/gamma.py`, `rinv/gate.py` | `socle_preuve.test_gamma (OCC)`, `tests.test_rinv (test_occ_race)` | `rinv/systeme_evidence.json` |
| **E-4.3** | §4.3 BOB à deux seuils | Reproduire le défaut historique (seuil unique → ARTIFACT) puis la correction. | `omega_hermes/bob.py` | `omega_hermes.test_bob` | `omega_hermes/hermes_evidence.json` |
| **E-4.5** | §4.5 Boucle 200×5 graine 7 | Score ≥ 0,98, rejet inconnu/COVERT/DRAFT = 1,000, FPR = 0. | `omega_hermes/loop.py`, `omega_hermes/hermes.py` | `omega_hermes.test_hermes` | `omega_hermes/hermes_evidence.json` |
| **E-5.1** | §5.1 GARDIEN allowlist exacte | Allowlist sans joker, refus typés, CONNECT refusé, détection heuristique signalée. | `agent_guard/guard.py` | `agent_guard.test_guard`, `agent_guard.test_charge` | `agent_guard/guard_evidence.json` |
| **E-5.2** | §5.2 Terminal SETUP_MODE | Allowlist commandes et arguments, shell=False, délai 5 s, bac à sable, 64 Kio. | `terminal_auth/server.py`, `socle_preuve/auth.py` | `terminal_auth.test_terminal` | `outils/phase3_evidence.json` |
| **E-5.3** | §5.3 Runtime supervisé V8.1 | flock, relances bornées, SIGTERM propre, aucune persistance cachée. | `runtime/superviseur.py` | `runtime.test_superviseur` | `outils/phase3_evidence.json` |
| **E-6.1** | §6.1 Orchestrateur | 21 suites blueprint + balayage HERMÈS + Ω Q + dashboard. | `plateforme_omega/orchestrator.py`, `plateforme_omega/omega_q.py` | `plateforme_omega.test_plateforme` | `plateforme_omega/plateforme_evidence.json` |
| **E-6.4** | §6.4 Règle Ω Q | Q = S + P + R − C ; veto si l'attaquant réussit. | `plateforme_omega/omega_q.py`, `plateforme_omega/mtd.py` | `plateforme_omega.test_plateforme` | `plateforme_omega/omega_q_evidence.json` |
| **E-7.1** | §7.1 RAG extractif cité | Jamais de mémoire inventée : titre, révision, URL, ou aveu. | `rag_wiki/rag.py`, `rag_wiki/corpus.py` | `rag_wiki.test_rag` | `rag_wiki/rag_evidence.json` |
| **E-7.3** | §7.3 Épinglage TLS | SPKI SHA-256 YE2/Root YE/ISRG Root X2 ; interception fabriquée détectée. | `rag_wiki/pinning.py` | `rag_wiki.test_rag` | `rag_wiki/pinning_evidence.json` |
| **E-8.1** | §8.1 Console unifiée statique | HTML statique sans CDN, 0 erreur console, pas de débordement mobile, chiffres depuis les évidences. | `console/generer.py` | `console.test_console` | `outils/phase7_evidence.json` |
| **E-8.2** | §8.2 Télégraphe scellé | CRC-16/X-25, aller-retour exact, sceau témoin sur chaque trame reçue. | `telegraphe/afsk.py`, `telegraphe/transport.py` | `telegraphe.test_afsk`, `telegraphe.test_transport` | `outils/phase7_evidence.json` |
| **E-10.3** | §10.3 Lignes rouges | Pas d'endpoint RCE non authentifié, pas de persistance cachée, pas de keylogger. | `socle_preuve/porte_http.py`, `agent_guard/guard.py`, `terminal_auth/server.py`, `cryoloop_gateway/gateway.py`, `omega_hermes/guardian.py`, `runtime/superviseur.py` | `cryoloop_gateway.test_gateway (test_la_passerelle_ne_peut_rien_executer)`, `omega_hermes.test_phase4 (test_guardian_refuse_tout_contenu)`, `runtime.test_superviseur (test_aucune_persistance_cachee)` | `(propriété de code vérifiée statiquement)` |
