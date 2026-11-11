"use strict";
const $ = (id) => document.getElementById(id);
async function api(methode, chemin, corps) {
  const r = await fetch(chemin, { method: methode, headers: { "Content-Type": "application/json" },
    body: corps === undefined ? undefined : JSON.stringify(corps), credentials: "same-origin" });
  let donnees = null;
  if ((r.headers.get("Content-Type") || "").startsWith("application/json")) donnees = await r.json();
  return { code: r.status, donnees };
}
function montrer(section) {
  for (const s of ["setup", "login", "console"]) $(s).hidden = s !== section;
  if (section === "console") $("commande").focus();
}
function message(texte) { $("message").textContent = texte; }
async function rafraichir() {
  const { donnees } = await api("GET", "/api/etat");
  montrer(donnees.setup_mode ? "setup" : donnees.session ? "console" : "login");
}
$("form-setup").addEventListener("submit", async (e) => {
  e.preventDefault();
  const r = await api("POST", "/api/setup", { mot_de_passe: $("mdp-setup").value });
  $("mdp-setup").value = "";
  message(r.code === 200 ? "Mot de passe enregistré. Connectez-vous." : "Refus : " + r.donnees.erreur);
  rafraichir();
});
$("form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const r = await api("POST", "/api/login", { mot_de_passe: $("mdp-login").value });
  $("mdp-login").value = "";
  message(r.code === 200 ? "" : "Refus : " + r.donnees.erreur);
  rafraichir();
});
$("form-exec").addEventListener("submit", async (e) => {
  e.preventDefault();
  const commande = $("commande").value;
  $("commande").value = "";
  const r = await api("POST", "/api/exec", { commande });
  const texte = r.code === 200 ? r.donnees.sortie : "[refus : " + (r.donnees.refus || r.donnees.erreur) + "]\n";
  $("sortie").textContent += "$ " + commande + "\n" + texte;
  $("sortie").scrollTop = $("sortie").scrollHeight;
  if (r.code === 401) rafraichir();
});
$("logout").addEventListener("click", async () => { await api("POST", "/api/logout", {}); rafraichir(); });
rafraichir();
