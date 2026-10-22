// Démo en ligne : remplace le serveur Python de l'application (clippeur/web.py).
// La page est la vraie ; chaque appel à /api/... reçoit ici la réponse que ferait le serveur, à partir de
// résultats calculés à l'avance par l'application (donnees.js, généré par outils/construire_demo.py).
// Rien n'est envoyé nulle part : tout se passe dans le navigateur.

(() => {
  const D = window.DONNEES_DEMO;
  const clone = o => (o == null ? o : JSON.parse(JSON.stringify(o)));
  const pause = ms => new Promise(r => setTimeout(r, ms));
  const VITESSE = 1;  // durée de chaque étape simulée, en multiple de 1 seconde

  const NOMS_SONS = "rires, cris, explosions et musique";

  // --- État partagé avec la page, comme dans web.py ---
  const etat = {
    en_cours: false, tache: null, film: null, chemin: null,
    message: null, pourcentage: null, journal: [], erreur: null,
    identification: null, transcription: null, recherche: null, proposition: null, exports: null,
  };
  const RESULTATS_INVALIDES = {
    identification: ["identification", "recherche", "proposition", "exports"],
    transcription: ["transcription", "recherche", "proposition", "exports"],
    recherche: ["recherche", "proposition", "exports"],
    proposition: ["proposition", "exports"],
    exports: ["exports"],
    analyse: ["identification", "transcription", "recherche", "proposition", "exports"],
  };

  const episodeDe = chemin => D.episodes.find(e => e.chemin === chemin);

  function suivi(message, pourcentage) {
    etat.message = message;
    etat.pourcentage = pourcentage;
    if (pourcentage == null) etat.journal.push(message);
  }

  async function progression(message, duree = 1200) {
    for (let p = 0; p <= 100; p += 20) {
      suivi(message, p);
      await pause(duree / 6 * VITESSE);
    }
  }

  function lancerTache(tache, chemin, travail) {
    if (etat.en_cours) return reponse({ erreur: "Une tâche est déjà en cours." }, 409);
    const effacer = etat.chemin !== chemin ? [...RESULTATS_INVALIDES.identification, "transcription"]
                                           : RESULTATS_INVALIDES[tache];
    for (const cle of effacer) etat[cle] = null;
    Object.assign(etat, { en_cours: true, tache, film: chemin.split("\\").pop(), chemin,
                          message: "Démarrage...", pourcentage: null, journal: [], erreur: null });
    (async () => {
      try {
        const resultat = await travail();
        if (tache in etat) etat[tache] = resultat;
      } catch (e) {
        etat.erreur = String(e);
      } finally {
        etat.en_cours = false;
      }
    })();
    return reponse({ ok: true });
  }

  // Extraits proposés : les mieux notés, dans l'ordre du film, comme dans l'application.
  function proposition(episode, nombre) {
    const p = clone(episode.proposition);
    const gardes = new Set([...p.extraits].sort((a, b) => b.score - a.score).slice(0, nombre).map(e => e.numero));
    p.extraits = p.extraits.filter(e => gardes.has(e.numero));
    return p;
  }

  // Le déroulé enregistré lors du vrai traitement, rejoué en accéléré.
  async function rejouer(episode, nombre, avecSons) {
    for (const pas of episode.deroule) {
      if (pas.etape) {
        etat[pas.etape] = pas.etape === "proposition" ? proposition(episode, nombre) : clone(episode[pas.etape]);
        continue;
      }
      let message = pas.message;
      if (message.startsWith("Transcription déjà faite")) {
        if (etat.journal.some(l => l.startsWith("Lecture des sous-titres"))) continue;
        message = `Lecture des sous-titres (${episode.transcription.source}) : ${episode.transcription.segments.length > 0 ? "dialogues horodatés" : ""}.`;
      }
      if (message.startsWith("Détection des changements de plan")) {
        await progression("Détection des changements de plan (FFmpeg)...");
        suivi(`${message.replace("...", "")} : terminé.`, null);
        if (avecSons) {
          await progression(`Reconnaissance des sons (${NOMS_SONS}), modèle AST en local...`, 1800);
          suivi(`Reconnaissance des sons : ${NOMS_SONS}.`, null);
        }
        continue;
      }
      if (message.endsWith("extraits proposés.")) message = `${proposition(episode, nombre).extraits.length} extraits proposés.`;
      suivi(message, null);
      await pause(700 * VITESSE);
    }
  }

  function nomDeFichier(texte, longueurMax = 40) {
    const mots = texte.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().match(/[a-z0-9]+/g) || [];
    return mots.join("-").slice(0, longueurMax).replace(/-+$/, "") || "extrait";
  }

  // --- Les routes du serveur ---
  const routes = {
    "POST /api/choisir": () => choisirEpisode().then(chemin => reponse({ chemin })),

    "POST /api/analyser": c => {
      const episode = episodeDe(c.chemin);
      return lancerTache("analyse", c.chemin, () => rejouer(episode, Math.min(Number(c.nombre) || 10, 10), c.avec_sons !== false));
    },

    "POST /api/transcrire": c => lancerTache("transcription", c.chemin, async () => {
      const episode = episodeDe(c.chemin);
      if (c.langue === "fr") suivi("Démo : seule la transcription anglaise (langue d'origine) est disponible.", null);
      await progression(`Lecture des sous-titres (${episode.transcription.source})...`, 900);
      suivi(`${episode.transcription.segments.length} répliques horodatées.`, null);
      etat.recherche = clone(episode.recherche);
      return clone(episode.transcription);
    }),

    "POST /api/identifier": c => lancerTache("identification", c.chemin, async () => {
      const episode = episodeDe(c.chemin);
      suivi("Identification du film...", null);
      await pause(900 * VITESSE);
      const resultat = clone(episode.identification);
      if (c.correction) {
        resultat.avertissement = "Démo en ligne : la recherche Wikipédia n'est pas disponible ici, la fiche "
          + "d'origine est gardée. Dans l'application, la correction cherche la bonne fiche.";
      }
      return resultat;
    }),

    "POST /api/rechercher": c => lancerTache("recherche", c.chemin, async () => {
      const episode = episodeDe(c.chemin);
      suivi(`Recherche des citations sur Wikiquote : « ${episode.recherche.page} »...`, null);
      await progression("Correspondance avec les dialogues (RapidFuzz)...", 900);
      const resultat = clone(episode.recherche);
      if (c.page && c.page !== resultat.page) {
        resultat.avertissements.push(`Démo en ligne : seule la page « ${resultat.page} » est disponible.`);
      }
      return resultat;
    }),

    "POST /api/recherche/choix": c => {
      if (etat.en_cours) return reponse({ erreur: "Une tâche est déjà en cours." }, 409);
      const retenues = new Set((c.retenues || []).map(Number));
      etat.recherche.resultats.forEach((r, rang) => { r.retenue = retenues.has(rang); });
      return reponse({ ok: true });
    },

    "POST /api/extraits/proposer": c => lancerTache("proposition", c.chemin, async () => {
      const episode = episodeDe(c.chemin);
      const nombre = Math.max(1, Math.min(Number(c.nombre) || 10, 30));
      suivi("Mesure du volume sonore...", null);
      await pause(600 * VITESSE);
      await progression("Détection des changements de plan (FFmpeg)...", 900);
      if (c.avec_sons !== false) await progression(`Reconnaissance des sons (${NOMS_SONS})...`, 1200);
      suivi("Choix des meilleurs moments...", null);
      await pause(600 * VITESSE);
      if (nombre > 10) suivi("Démo en ligne : 10 extraits au plus ont été calculés à l'avance.", null);
      const p = proposition(episode, Math.min(nombre, 10));
      suivi(`${p.extraits.length} extraits proposés.`, null);
      return p;
    }),

    "GET /api/montage": () => reponse(D.montage),

    "POST /api/extraits/exporter": c => {
      const p = etat.proposition;
      if (!p) return reponse({ erreur: "Aucun extrait proposé." }, 400);
      const numeros = new Set(c.numeros || []);
      const choisis = p.extraits.filter(e => numeros.has(e.numero));
      if (!choisis.length) return reponse({ erreur: "Aucun extrait gardé." }, 400);
      return lancerTache("exports", p.chemin, async () => {
        const base = nomDeFichier(p.film.replace(/\.\w+$/, ""), 30);
        const suffixe = c.montage.format === "original" ? "" : "_vertical";
        const fichiers = [];
        for (const [i, e] of choisis.entries()) {
          const [debut, fin] = (c.bornes || {})[e.numero] || [e.debut, e.fin];
          await progression(`Export de l'extrait ${i + 1}/${choisis.length} (H.264 + AAC, son à -14 LUFS)...`, 500);
          fichiers.push({ ...e, debut, fin, duree: Math.round((fin - debut) * 10) / 10,
                          fichier: `${base}_${String(e.numero).padStart(2, "0")}_${nomDeFichier(e.titre)}${suffixe}.mp4` });
        }
        suivi(`${fichiers.length} extraits exportés dans output\\${nomDeFichier(p.film.replace(/\.\w+$/, ""), 60)}`, 100);
        return fichiers;
      });
    },

    "GET /api/etat": () => reponse(etat),

    "GET /api/cles": () => reponse({ tmdb: false }),
    "POST /api/cles": () => reponse({ erreur: "Démo en ligne : aucune clé n'est enregistrée ici. Dans l'application, "
                                             + "la clé est vérifiée auprès de TMDb puis gardée dans le fichier .env." }, 400),

    "GET /api/tendances": async () => {
      await pause(1200 * VITESSE);
      return D.tendances ? reponse(D.tendances) : reponse({ erreur: "Pas de séries du moment dans la démo." }, 503);
    },

    "POST /api/ouvrir_dossier": () => info("ouvre le dossier des extraits dans l'Explorateur Windows"),
    "POST /api/ouvrir_musiques": () => info("ouvre la banque de musiques, où l'on dépose ses morceaux"),
    "POST /api/file/ouvrir": () => info("ouvre le dossier « à traiter » : toute vidéo déposée y est traitée seule"),

    // --- Traitement automatique ---
    "GET /api/file": () => reponse(file),
    "POST /api/file/reglages": c => {
      if (c.surveillance && !file.reglages.surveillance) {
        info("surveille le dossier « à traiter » toutes les 15 secondes. Essayez plutôt « Traiter une saison entière »");
      }
      file.reglages = { ...file.reglages, ...c, nombre: Math.max(1, Math.min(Number(c.nombre) || 5, 30)) };
      return reponse(file.reglages);
    },
    "POST /api/file/saison": () => reponse(ajouterSaison()),
    "POST /api/file/retirer": c => {
      const avant = file.elements.length;
      file.elements = file.elements.filter(e => !(e.id === c.id && e.statut === "en attente"));
      return reponse({ ok: file.elements.length < avant });
    },
  };

  // --- File d'attente simulée : une saison entière, traitée épisode par épisode ---
  const file = { reglages: clone(D.reglages_auto), dossier_a_traiter: "a_traiter", elements: [], lots: [] };
  let fileOccupee = false;

  function ajouterSaison() {
    const lot = { id: "lot" + Date.now(), nom: D.dossier_saison.split("\\").pop(), dossier: D.dossier_saison,
                  nb: D.episodes.length, termine: false, meilleurs: [], recapitulatif: null };
    file.lots.push(lot);
    for (const [i, episode] of D.episodes.entries()) {
      file.elements.push({ id: lot.id + i, chemin: episode.chemin, fichier: episode.nom, lot: lot.id,
                           statut: "en attente", message: "", pourcentage: null, erreur: null, extraits: [] });
    }
    if (!fileOccupee) traiterLaFile();
    return lot;
  }

  async function traiterLaFile() {
    fileOccupee = true;
    let element;
    while ((element = file.elements.find(e => e.statut === "en attente"))) {
      const episode = episodeDe(element.chemin);
      element.statut = "en cours";
      for (const [message, duree] of [["Identification du film...", 700], ["Lecture des sous-titres...", 700],
                                      ["Recherche des citations sur Wikiquote...", 900],
                                      ["Détection des changements de plan...", 900],
                                      [`Reconnaissance des sons (${NOMS_SONS})...`, 1200],
                                      ["Choix des meilleurs moments...", 600], ["Export des extraits...", 1200]]) {
        for (let p = 0; p <= 100; p += 25) {
          Object.assign(element, { message, pourcentage: p });
          await pause(duree / 5 * VITESSE);
        }
      }
      const p = proposition(episode, Math.min(file.reglages.nombre, 10));
      const suffixe = file.reglages.montage.format === "original" ? "" : "_vertical";
      const base = nomDeFichier(episode.nom.replace(/\.\w+$/, ""), 30);
      Object.assign(element, {
        statut: "terminé", titre: episode.identification.fiche.titre, pourcentage: null,
        message: `${p.extraits.length} extraits exportés.`,
        extraits: p.extraits.map(e => ({
          numero: e.numero, titre: e.titre, score: e.score, duree: Math.round((e.fin - e.debut) * 10) / 10,
          fichier: `${base}_${String(e.numero).padStart(2, "0")}_${nomDeFichier(e.titre)}${suffixe}.mp4`,
        })),
      });
      const lot = file.lots.find(l => l.id === element.lot);
      const episodes = file.elements.filter(e => e.lot === lot.id);
      if (lot && !episodes.some(e => ["en attente", "en cours"].includes(e.statut))) {
        lot.termine = true;
        lot.meilleurs = episodes.flatMap(e => e.extraits.map(x => ({ ...x, episode: e.fichier })))
          .sort((a, b) => b.score - a.score).slice(0, 10);
        lot.recapitulatif = `output\\saisons\\${nomDeFichier(lot.nom, 60)}.json`;
      }
    }
    fileOccupee = false;
  }

  // --- Ce que la démo montre à la place des fenêtres Windows et des fichiers vidéo ---
  function reponse(corps, statut = 200) {
    return new Response(JSON.stringify(corps), { status: statut, headers: { "Content-Type": "application/json" } });
  }

  function info(texte) {
    const bulle = document.createElement("div");
    bulle.className = "bulle-demo";
    bulle.textContent = `Dans l'application, ce bouton ${texte}.`;
    document.body.append(bulle);
    setTimeout(() => bulle.classList.add("visible"), 10);
    setTimeout(() => { bulle.classList.remove("visible"); setTimeout(() => bulle.remove(), 400); }, 4000);
    return reponse({ ok: true });
  }

  // La fenêtre Windows de choix de fichier, remplacée par la liste des épisodes de la démo.
  function choisirEpisode() {
    return new Promise(resoudre => {
      const fenetre = document.createElement("dialog");
      fenetre.className = "choix-demo";
      const titre = document.createElement("h2");
      titre.textContent = "Choisir un film";
      const aide = document.createElement("p");
      aide.textContent = "Dans l'application, la fenêtre Windows de choix de fichier s'ouvre ici. "
        + "Pour la démo, choisissez un des films déjà analysés :";
      const liste = document.createElement("div");
      liste.className = "liste-demo";
      for (const episode of D.episodes) {
        const bouton = document.createElement("button");
        bouton.type = "button";
        const fiche = episode.identification.fiche;
        const duree = Math.round(episode.proposition.duree / 60);
        bouton.append(episode.nom.replace(/\.\w+$/, ""), Object.assign(document.createElement("small"), {
          textContent: `${fiche.titre}${fiche.annee ? `, ${fiche.annee}` : ""} · ${duree} min · ${episode.proposition.extraits.length} extraits`,
        }));
        bouton.onclick = () => { fenetre.close(); resoudre(episode.chemin); };
        liste.append(bouton);
      }
      const annuler = document.createElement("button");
      annuler.type = "button";
      annuler.className = "annuler-demo";
      annuler.textContent = "Annuler";
      annuler.onclick = () => fenetre.close();
      fenetre.addEventListener("close", () => { fenetre.remove(); resoudre(null); });
      fenetre.append(titre, aide, liste, annuler);
      document.body.append(fenetre);
      fenetre.showModal();
    });
  }

  const heure = s => [Math.floor(s / 3600), Math.floor(s % 3600 / 60), Math.floor(s % 60)]
    .map(n => String(n).padStart(2, "0")).join(":");

  window.DEMO = {
    // À la place de l'image du film : un cadre gris avec le numéro et les horaires de l'extrait.
    miniature(e) {
      if (e.image) return e.image;
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360">
        <rect width="640" height="360" fill="#2b2a28"/>
        <text x="28" y="62" font-family="system-ui,sans-serif" font-size="34" font-weight="600" fill="#e8e6e1">n° ${e.numero}</text>
        <text x="28" y="98" font-family="ui-monospace,Consolas,monospace" font-size="20" fill="#b3afa8">${heure(e.debut)} – ${heure(e.fin)}</text>
      </svg>`;
      return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    },

    // À la place de l'aperçu préparé par FFmpeg : le passage lu dans la copie publique du film (archive.org),
    // entre le début et la fin de l'extrait. Le recadrage 9:16 et la musique ne sont appliqués que dans l'application.
    apercu(video, attente, e, m) {
      if (!e.video) {
        video.controls = false;
        attente.textContent = "Aperçu indisponible pour ce film dans la démo.";
        return;
      }
      video.src = `${e.video.split("#")[0]}#t=${e.debut},${e.fin}`;
      // Le fragment #t suffit d'habitude ; on se cale aussi à la main, au cas où le serveur ou le navigateur l'ignore.
      video.addEventListener("loadedmetadata", () => { if (Math.abs(video.currentTime - e.debut) > 1) video.currentTime = e.debut; });
      video.addEventListener("timeupdate", () => { if (video.currentTime >= e.fin) video.pause(); });
      if (m.format !== "original" || m.musique) {
        const reglages = [m.format !== "original" && D.montage.formats[m.format], m.musique && `musique « ${m.musique} »`]
          .filter(Boolean).join(", ");
        setTimeout(() => {
          const note = document.createElement("span");
          note.className = "note-apercu";
          note.textContent = `Démo : passage original. Dans l'application, l'aperçu est déjà monté (${reglages}).`;
          video.parentNode?.append(note);
        });
      }
    },
  };

  // À l'ouverture, le premier film est déjà chargé : la page affiche ses résultats sans rien choisir ni attendre.
  const premier = D.episodes[0];
  Object.assign(etat, {
    film: premier.nom, chemin: premier.chemin,
    message: `${premier.proposition.extraits.length} extraits proposés.`,
    journal: premier.deroule.filter(p => p.message && p.pourcentage == null && !p.message.startsWith("Transcription déjà faite"))
      .map(p => p.message),
    identification: clone(premier.identification), transcription: clone(premier.transcription),
    recherche: clone(premier.recherche), proposition: proposition(premier, 10),
  });

  // --- Les appels de la page vers le serveur arrivent ici ---
  const fetchOrigine = window.fetch.bind(window);
  window.fetch = async (url, options = {}) => {
    const adresse = new URL(url, location.href);
    if (!adresse.pathname.includes("/api/")) return fetchOrigine(url, options);
    const cle = `${(options.method || "GET").toUpperCase()} ${adresse.pathname.slice(adresse.pathname.indexOf("/api/"))}`;
    const route = routes[cle];
    if (!route) return reponse({ erreur: `Démo : ${cle} n'est pas simulé.` }, 404);
    return route(options.body ? JSON.parse(options.body) : {});
  };
})();
