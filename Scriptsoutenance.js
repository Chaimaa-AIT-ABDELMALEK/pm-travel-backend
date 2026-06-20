const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, LevelFormat, PageBreak,
  TabStopType, TabStopPosition
} = require("docx");
const fs = require("fs");

// ── COLORS ──────────────────────────────────────────────────
const NAVY   = "0D1B3E";
const TEAL   = "00B4D8";
const GOLD   = "C8950A";
const GRAY   = "6B7280";
const LGRAY  = "E8EFF8";
const WHITE  = "FFFFFF";

// ── HELPERS ─────────────────────────────────────────────────
const border0 = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const borders0 = { top: border0, bottom: border0, left: border0, right: border0 };
const borderAccent = { style: BorderStyle.SINGLE, size: 12, color: TEAL };
const thinBorder = { style: BorderStyle.SINGLE, size: 4, color: "D1D5DB" };
const thinBorders = { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder };

function sp(before = 0, after = 0) {
  return { before, after };
}

function rule(color = TEAL, size = 8) {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size, color, space: 1 } },
    spacing: sp(40, 160),
  });
}

function spacer(pts = 120) {
  return new Paragraph({ spacing: sp(0, pts) });
}

// Heading styles
function h1(text) {
  return new Paragraph({
    children: [new TextRun({ text, font: "Cambria", size: 32, bold: true, color: WHITE })],
    shading: { fill: NAVY, type: ShadingType.CLEAR },
    spacing: sp(0, 0),
    indent: { left: 360, right: 360 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 10, color: TEAL, space: 1 } },
  });
}

function sectionTitle(num, title, color = TEAL) {
  return new Paragraph({
    children: [
      new TextRun({ text: `${num}  `, font: "Cambria", size: 24, bold: true, color }),
      new TextRun({ text: title, font: "Cambria", size: 24, bold: true, color: NAVY }),
    ],
    spacing: sp(320, 80),
    border: { left: { style: BorderStyle.SINGLE, size: 24, color, space: 1 } },
    indent: { left: 180 },
  });
}

function timeBadge(time) {
  return new Paragraph({
    children: [
      new TextRun({ text: `⏱  ${time}`, font: "Calibri", size: 18, color: GOLD, bold: true }),
    ],
    spacing: sp(0, 60),
  });
}

function slideLabel(label) {
  return new Paragraph({
    children: [
      new TextRun({ text: `📊  Slide : `, font: "Calibri", size: 17, color: GRAY, bold: true }),
      new TextRun({ text: label, font: "Calibri", size: 17, color: GRAY, italics: true }),
    ],
    spacing: sp(0, 80),
  });
}

function scriptLine(text, highlight = false) {
  return new Paragraph({
    children: [
      new TextRun({
        text,
        font: "Calibri",
        size: 22,
        color: highlight ? NAVY : "1F2937",
        bold: highlight,
      }),
    ],
    spacing: sp(40, 40),
  });
}

function keywordLine(keyword, text) {
  return new Paragraph({
    children: [
      new TextRun({ text: `${keyword} : `, font: "Calibri", size: 20, bold: true, color: TEAL }),
      new TextRun({ text, font: "Calibri", size: 20, color: "374151", italics: true }),
    ],
    spacing: sp(20, 20),
    indent: { left: 360 },
  });
}

function tip(text) {
  return new Paragraph({
    children: [
      new TextRun({ text: "💡  Conseil : ", font: "Calibri", size: 18, bold: true, color: GOLD }),
      new TextRun({ text, font: "Calibri", size: 18, color: "6B4C00", italics: true }),
    ],
    shading: { fill: "FFFBEC", type: ShadingType.CLEAR },
    spacing: sp(40, 40),
    indent: { left: 200, right: 200 },
    border: {
      left: { style: BorderStyle.SINGLE, size: 16, color: GOLD, space: 1 },
    },
  });
}

function bullet(text, color = NAVY) {
  return new Paragraph({
    children: [
      new TextRun({ text: "▸  ", font: "Calibri", size: 20, bold: true, color: TEAL }),
      new TextRun({ text, font: "Calibri", size: 20, color }),
    ],
    spacing: sp(20, 20),
    indent: { left: 360 },
  });
}

function pageBreakPara() {
  return new Paragraph({ children: [new PageBreak()] });
}

// ── HEADER ──────────────────────────────────────────────────
function makeHeader() {
  return new Header({
    children: [
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [6000, 3360],
        rows: [
          new TableRow({
            children: [
              new TableCell({
                borders: { top: border0, bottom: { style: BorderStyle.SINGLE, size: 4, color: TEAL }, left: border0, right: border0 },
                children: [
                  new Paragraph({
                    children: [
                      new TextRun({ text: "SCRIPT DE SOUTENANCE  —  PFE 2025–2026", font: "Calibri", size: 16, color: NAVY, bold: true }),
                    ],
                    spacing: sp(0, 40),
                  }),
                ],
                width: { size: 6000, type: WidthType.DXA },
              }),
              new TableCell({
                borders: { top: border0, bottom: { style: BorderStyle.SINGLE, size: 4, color: TEAL }, left: border0, right: border0 },
                children: [
                  new Paragraph({
                    children: [
                      new TextRun({ text: "PM Travel CRM", font: "Calibri", size: 16, color: TEAL, italics: true }),
                    ],
                    alignment: AlignmentType.RIGHT,
                    spacing: sp(0, 40),
                  }),
                ],
                width: { size: 3360, type: WidthType.DXA },
              }),
            ],
          }),
        ],
      }),
    ],
  });
}

// ── DOCUMENT ────────────────────────────────────────────────
async function build() {

  const children = [

    // ═══════════════════════════════════════════════════════
    // COVER
    // ═══════════════════════════════════════════════════════
    new Paragraph({
      children: [new TextRun({ text: "SCRIPT DE SOUTENANCE", font: "Cambria", size: 52, bold: true, color: WHITE })],
      alignment: AlignmentType.CENTER,
      shading: { fill: NAVY, type: ShadingType.CLEAR },
      spacing: sp(480, 0),
    }),
    new Paragraph({
      children: [new TextRun({ text: "Projet de Fin d'Études — Filière SIR", font: "Cambria", size: 28, color: TEAL, italics: true })],
      alignment: AlignmentType.CENTER,
      shading: { fill: NAVY, type: ShadingType.CLEAR },
      spacing: sp(0, 0),
    }),
    new Paragraph({
      children: [new TextRun({ text: "Automatisation de la Prospection & Communication Digitale pour une Agence de Tourisme B2B", font: "Cambria", size: 24, color: "C8D6F0", italics: true })],
      alignment: AlignmentType.CENTER,
      shading: { fill: NAVY, type: ShadingType.CLEAR },
      spacing: sp(60, 0),
    }),
    new Paragraph({
      children: [new TextRun({ text: " ", size: 24 })],
      shading: { fill: NAVY, type: ShadingType.CLEAR },
      spacing: sp(0, 0),
    }),
    new Paragraph({
      children: [new TextRun({ text: "Chaimaa AIT ABDELMALEK  ·  Zakia AZIZI", font: "Calibri", size: 22, color: "8099C3", bold: true })],
      alignment: AlignmentType.CENTER,
      shading: { fill: NAVY, type: ShadingType.CLEAR },
      spacing: sp(0, 0),
    }),
    new Paragraph({
      children: [new TextRun({ text: "FSTG Marrakech — Université Cadi Ayyad  ·  2025–2026", font: "Calibri", size: 20, color: "5A708B" })],
      alignment: AlignmentType.CENTER,
      shading: { fill: NAVY, type: ShadingType.CLEAR },
      spacing: sp(0, 480),
    }),

    rule(TEAL, 12),

    // Timing overview table
    new Paragraph({
      children: [new TextRun({ text: "MINUTAGE GLOBAL", font: "Cambria", size: 24, bold: true, color: NAVY })],
      alignment: AlignmentType.CENTER,
      spacing: sp(200, 120),
    }),

    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [3800, 2780, 2780],
      rows: [
        new TableRow({
          tableHeader: true,
          children: [
            ...[["SECTION", 3800], ["DURÉE", 2780], ["SLIDES", 2780]].map(([t, w]) =>
              new TableCell({
                borders: thinBorders,
                shading: { fill: NAVY, type: ShadingType.CLEAR },
                width: { size: w, type: WidthType.DXA },
                margins: { top: 80, bottom: 80, left: 150, right: 150 },
                children: [new Paragraph({
                  children: [new TextRun({ text: t, font: "Calibri", size: 19, bold: true, color: WHITE })],
                  alignment: AlignmentType.CENTER,
                })],
              })
            ),
          ],
        }),
        ...[
          ["Introduction & Contexte", "~1 min 30 s", "1–4"],
          ["Étude Préliminaire", "~1 min", "5–6"],
          ["Analyse & Conception", "~1 min 30 s", "7–8"],
          ["Outils & Technologies", "~1 min", "9–10"],
          ["Implémentation + Démo vidéo", "~3 min 30 s", "11–16"],
          ["Conclusion & Perspectives", "~1 min 30 s", "17–19"],
          ["TOTAL", "~10 min", "19 slides"],
        ].map(([s, d, sl], i) =>
          new TableRow({
            children: [
              new TableCell({
                borders: thinBorders,
                shading: { fill: i % 2 === 0 ? WHITE : LGRAY, type: ShadingType.CLEAR },
                width: { size: 3800, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 150, right: 150 },
                children: [new Paragraph({
                  children: [new TextRun({ text: s, font: "Calibri", size: 19, bold: s === "TOTAL", color: s === "TOTAL" ? NAVY : "374151" })],
                })],
              }),
              new TableCell({
                borders: thinBorders,
                shading: { fill: i % 2 === 0 ? WHITE : LGRAY, type: ShadingType.CLEAR },
                width: { size: 2780, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 150, right: 150 },
                children: [new Paragraph({
                  children: [new TextRun({ text: d, font: "Calibri", size: 19, bold: s === "TOTAL", color: s === "TOTAL" ? TEAL : GOLD })],
                  alignment: AlignmentType.CENTER,
                })],
              }),
              new TableCell({
                borders: thinBorders,
                shading: { fill: i % 2 === 0 ? WHITE : LGRAY, type: ShadingType.CLEAR },
                width: { size: 2780, type: WidthType.DXA },
                margins: { top: 60, bottom: 60, left: 150, right: 150 },
                children: [new Paragraph({
                  children: [new TextRun({ text: sl, font: "Calibri", size: 19, bold: s === "TOTAL", color: s === "TOTAL" ? NAVY : GRAY })],
                  alignment: AlignmentType.CENTER,
                })],
              }),
            ],
          })
        ),
      ],
    }),

    spacer(200),
    tip("Parler lentement et distinctement. Ne pas lire le script mot pour mot — s'en servir comme guide. Maintenir le contact visuel avec le jury."),
    spacer(100),

    rule(TEAL, 8),

    // ═══════════════════════════════════════════════════════
    // SECTION 0 — INTRODUCTION (Slide 1)
    // ═══════════════════════════════════════════════════════
    pageBreakPara(),
    h1("  OUVERTURE  ·  Introduction"),
    spacer(80),

    timeBadge("⏱  Durée : ~1 min 30 s  (Slides 1–4)"),
    slideLabel("Slide 1 — Page de titre"),
    spacer(40),

    sectionTitle("", "Ce que vous dites en entrant", TEAL),
    spacer(60),

    scriptLine(`Bonjour. Permettez-moi de me présenter : je suis Chaimaa AIT ABDELMALEK, et voici ma binôme Zakia AZIZI. Nous sommes étudiantes en quatrième année de la filière Systèmes Informatiques Répartis à la FSTG de Marrakech.`),
    spacer(40),
    scriptLine(`Nous avons l'honneur de vous présenter aujourd'hui notre Projet de Fin d'Études, réalisé au sein de PM Travel Agency, une agence de voyage marocaine basée à Marrakech.`),
    spacer(40),
    scriptLine(`Notre projet s'intitule : "Automatisation de la prospection et de la communication digitale pour une agence de tourisme B2B".`, true),
    spacer(80),

    slideLabel("Slide 2 — Plan"),
    spacer(40),

    scriptLine(`Notre présentation s'articule autour de six grandes parties :`),
    bullet("D'abord le contexte général et la présentation de l'organisme d'accueil."),
    bullet("Ensuite l'étude préliminaire, avec l'analyse des besoins."),
    bullet("Puis la conception et l'architecture de la solution."),
    bullet("Suivi des outils et technologies utilisés."),
    bullet("L'implémentation, illustrée par une démonstration vidéo."),
    bullet("Et enfin, notre conclusion et les perspectives d'évolution."),
    spacer(80),

    // ─── Slide 3–4 ──────────────────────────────────────────
    slideLabel("Slides 3–4 — Contexte & PM Travel Agency"),
    spacer(40),

    sectionTitle("01", "Contexte & Organisme d'accueil", TEAL),
    spacer(60),

    scriptLine(`PM Travel Agency, ou Prestige Majestic Travel, est une agence de voyage basée à Marrakech. Elle opère dans un marché touristique très concurrentiel, en ciblant aussi bien une clientèle professionnelle — le B2B — que le grand public.`),
    spacer(40),
    scriptLine(`Avant notre intervention, l'agence gérait l'ensemble de ses activités commerciales de façon entièrement manuelle :`),
    bullet("La prospection de nouveaux partenaires — hôtels, riads, tour-opérateurs — se faisait par recherche directe et contact téléphonique."),
    bullet("Les emails étaient rédigés et envoyés un par un, sans modèle, sans suivi."),
    bullet("La gestion des réseaux sociaux était irrégulière, sans calendrier éditorial."),
    bullet("Les données étaient dispersées dans des fichiers Excel, sans outil centralisé."),
    spacer(40),
    scriptLine(`Face à ces limites, l'agence nous a confié une mission claire :`, true),
    scriptLine(`Concevoir et développer une plateforme CRM intelligente capable d'automatiser la prospection B2B, le marketing email, et la gestion des publications sur les réseaux sociaux.`),
    spacer(40),
    tip("Marquer une pause après avoir énoncé la mission. Laisser le jury absorber l'enjeu avant de continuer."),
    spacer(80),

    rule(NAVY, 4),

    // ═══════════════════════════════════════════════════════
    // SECTION 02 — ÉTUDE PRÉLIMINAIRE (Slides 5–6)
    // ═══════════════════════════════════════════════════════
    pageBreakPara(),
    h1("  02  ·  Étude Préliminaire"),
    spacer(80),

    timeBadge("⏱  Durée : ~1 min  (Slides 5–6)"),
    slideLabel("Slide 5 — Transition section"),
    spacer(40),

    scriptLine(`Passons maintenant à l'étude préliminaire.`),
    spacer(60),

    slideLabel("Slide 6 — Spécification des besoins"),
    spacer(40),

    sectionTitle("02", "Besoins fonctionnels — 4 modules", TEAL),
    spacer(60),

    scriptLine(`Après une analyse approfondie des processus de l'agence, nous avons identifié quatre modules fonctionnels principaux :`),
    spacer(40),

    keywordLine("M1 — Prospection & Scraping B2B", "Collecter automatiquement des prospects qualifiés via Google Maps et l'API OpenAI, avec déduplication automatique et scoring."),
    keywordLine("M2 — Email Marketing Automatisé", "Générer des campagnes personnalisées par intelligence artificielle, avec des séquences de relance à J+0, J+3 et J+7."),
    keywordLine("M3 — Réseaux Sociaux & IA", "Créer et planifier automatiquement du contenu sur Instagram, Facebook et LinkedIn, avec génération de texte et d'images par IA."),
    keywordLine("M4 — Agents IA via n8n", "Orchestrer tous ces processus via des workflows automatisés, avec un tableau de bord centralisé pour le suivi des KPIs."),
    spacer(40),

    scriptLine(`Côté besoins non fonctionnels, nous avons particulièrement veillé à la sécurité — authentification JWT, chiffrement Fernet —, la performance grâce à Redis, et la maintenabilité grâce à une architecture modulaire.`),
    spacer(80),

    rule(NAVY, 4),

    // ═══════════════════════════════════════════════════════
    // SECTION 03 — CONCEPTION (Slides 7–8)
    // ═══════════════════════════════════════════════════════
    pageBreakPara(),
    h1("  03  ·  Analyse & Conception"),
    spacer(80),

    timeBadge("⏱  Durée : ~1 min 30 s  (Slides 7–8)"),
    slideLabel("Slide 7 — Transition section"),
    spacer(40),

    scriptLine(`Voyons maintenant la phase d'analyse et de conception.`),
    spacer(60),

    slideLabel("Slide 8 — Architecture MVC"),
    spacer(40),

    sectionTitle("03", "Architecture & Modélisation UML", TEAL),
    spacer(60),

    scriptLine(`Notre solution repose sur une architecture client-serveur, organisée selon le modèle MVC — Modèle, Vue, Contrôleur.`),
    spacer(40),

    keywordLine("La Vue", "c'est l'interface utilisateur développée avec React.js. C'est ce que voit et utilise l'équipe de PM Travel Agency au quotidien."),
    keywordLine("Le Contrôleur", "c'est la couche backend assurée par FastAPI. Elle reçoit les requêtes, applique la logique métier, et communique avec les services externes."),
    keywordLine("Le Modèle", "c'est la base de données MySQL, qui contient seize tables couvrant l'ensemble des fonctionnalités du système. Redis complète cette couche pour les données temporaires et la gestion des files d'attente."),
    spacer(40),

    scriptLine(`Pour la modélisation, nous avons réalisé plusieurs diagrammes UML : un diagramme de cas d'utilisation, trois diagrammes de séquence — pour le scraping, l'envoi d'email, et la génération du calendrier éditorial — ainsi qu'un diagramme de classes.`),
    spacer(40),

    scriptLine(`L'orchestration des processus automatisés est assurée par n8n, que vous pouvez voir ici comme une couche d'automatisation entre notre backend et les services externes.`, true),
    spacer(40),

    tip("Pointer l'architecture sur le slide. Insister sur la séparation des responsabilités — c'est ce que le jury attend d'une architecture bien conçue."),
    spacer(80),

    rule(NAVY, 4),

    // ═══════════════════════════════════════════════════════
    // SECTION 04 — TECHNOLOGIES (Slides 9–10)
    // ═══════════════════════════════════════════════════════
    pageBreakPara(),
    h1("  04  ·  Outils & Technologies"),
    spacer(80),

    timeBadge("⏱  Durée : ~1 min  (Slides 9–10)"),
    slideLabel("Slide 9 — Transition section"),
    spacer(40),

    scriptLine(`Parlons maintenant des technologies que nous avons choisies.`),
    spacer(60),

    slideLabel("Slide 10 — Stack technologique"),
    spacer(40),

    sectionTitle("04", "Stack technologique", TEAL),
    spacer(60),

    scriptLine(`Nos choix technologiques ont été guidés par trois critères : la performance, la maintenabilité, et la facilité d'intégration avec les services tiers.`),
    spacer(40),

    new Paragraph({
      children: [new TextRun({ text: "Backend & Infrastructure :", font: "Calibri", size: 20, bold: true, color: TEAL })],
      spacing: sp(60, 20),
    }),
    bullet("FastAPI (Python) pour le backend — performances élevées et documentation Swagger automatique."),
    bullet("MySQL pour la persistance des données, avec seize tables et une contrainte UNIQUE pour la déduplication."),
    bullet("Redis pour le cache et les files d'attente asynchrones."),
    bullet("Docker pour déployer Redis de manière simple et isolée."),
    spacer(40),

    new Paragraph({
      children: [new TextRun({ text: "Frontend & IA :", font: "Calibri", size: 20, bold: true, color: TEAL })],
      spacing: sp(60, 20),
    }),
    bullet("React.js avec Tailwind CSS pour une interface moderne, modulaire et responsive."),
    bullet("OpenAI GPT-4o-mini pour la génération de contenu email et réseaux sociaux."),
    bullet("DALL-E 3 pour la génération d'images associées aux posts."),
    bullet("SendGrid pour l'envoi et le tracking des emails."),
    bullet("n8n pour l'orchestration de l'ensemble des workflows automatisés."),
    spacer(40),

    tip("Ne pas s'attarder sur chaque technologie. L'objectif est de montrer la cohérence de l'ensemble, pas d'expliquer chaque outil en détail."),
    spacer(80),

    rule(NAVY, 4),

    // ═══════════════════════════════════════════════════════
    // SECTION 05 — IMPLÉMENTATION (Slides 11–16)
    // ═══════════════════════════════════════════════════════
    pageBreakPara(),
    h1("  05  ·  Implémentation & Démonstration"),
    spacer(80),

    timeBadge("⏱  Durée : ~3 min 30 s  (Slides 11–16)  —  dont 1 min de narration + 2 min 30 de démo vidéo + 1 min de commentaire"),
    slideLabel("Slide 11 — Transition section"),
    spacer(40),

    scriptLine(`Nous allons maintenant vous présenter notre plateforme CRM telle qu'elle a été réalisée.`),
    spacer(60),

    // ── Dashboard & Auth ──
    slideLabel("Slide 12 — Dashboard & Authentification"),
    spacer(40),

    sectionTitle("", "Module 1 · Authentification & Dashboard", TEAL),
    spacer(60),

    scriptLine(`L'accès à la plateforme est sécurisé par une authentification JWT. Une fois connecté, l'utilisateur arrive sur le tableau de bord centralisé, qui affiche en temps réel les indicateurs clés de performance :`),
    bullet("1 367 contacts collectés et centralisés."),
    bullet("49 emails envoyés, avec un taux de réponse de 67%."),
    bullet("4 deals actifs dans le pipeline commercial."),
    bullet("L'ensemble des modules accessibles depuis le menu latéral."),
    spacer(80),

    // ── Scraping ──
    slideLabel("Slide 13 — Scraping & Prospection B2B"),
    spacer(40),

    sectionTitle("", "Module 2 · Scraping & Prospection B2B", TEAL),
    spacer(60),

    scriptLine(`Le module de prospection est l'un des plus innovants de notre plateforme. Il intègre deux scrapers complémentaires :`),
    spacer(40),
    keywordLine("Scraper Google Maps", "Il interroge l'API Google Places pour collecter automatiquement les coordonnées de partenaires potentiels — hôtels, riads, tour-opérateurs — dans neuf villes marocaines et à l'international. Une barre de progression indique en temps réel le nombre de nouveaux prospects trouvés et les doublons éliminés."),
    spacer(20),
    keywordLine("Scraper OpenAI Web Search", "Il utilise l'API OpenAI pour synthétiser des informations de prospects depuis le web, avec déduplication automatique via une contrainte UNIQUE en base de données."),
    spacer(60),

    // ── Email Marketing ──
    slideLabel("Slide 14 — Email Marketing Automatisé"),
    spacer(40),

    sectionTitle("", "Module 3 · Email Marketing Automatisé", TEAL),
    spacer(60),

    scriptLine(`Le module email permet d'envoyer des campagnes entièrement personnalisées par intelligence artificielle. Pour chaque prospect sélectionné, GPT-4o-mini génère un email adapté au secteur d'activité, à la ville et au nom de l'établissement.`),
    spacer(40),
    scriptLine(`Les emails sont envoyés via SendGrid et peuvent être suivis depuis la boîte de conversations intégrée, qui synchronise automatiquement les réponses via IMAP.`),
    spacer(40),
    scriptLine(`Le workflow n8n orchestre la chaîne complète : déclenchement planifié, génération par IA, envoi SMTP, pause, puis relance automatique.`, true),
    spacer(80),

    // ── Démo vidéo ──
    new Paragraph({
      children: [
        new TextRun({ text: "🎬  DÉMONSTRATION VIDÉO  (environ 2 min 30)", font: "Cambria", size: 26, bold: true, color: WHITE }),
      ],
      shading: { fill: "1A2D5A", type: ShadingType.CLEAR },
      alignment: AlignmentType.CENTER,
      spacing: sp(160, 160),
    }),

    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [9360],
      rows: [
        new TableRow({
          children: [
            new TableCell({
              borders: { top: { style: BorderStyle.SINGLE, size: 8, color: TEAL }, bottom: { style: BorderStyle.SINGLE, size: 8, color: TEAL }, left: border0, right: border0 },
              shading: { fill: "F0F7FF", type: ShadingType.CLEAR },
              margins: { top: 120, bottom: 120, left: 200, right: 200 },
              width: { size: 9360, type: WidthType.DXA },
              children: [
                new Paragraph({
                  children: [new TextRun({ text: "Séquence recommandée pour la vidéo :", font: "Calibri", size: 20, bold: true, color: NAVY })],
                  spacing: sp(0, 60),
                }),
                ...[
                  ["0:00 → 0:20", "Interface principale — menu navigation, 8 modules"],
                  ["0:20 → 0:45", "Scraper Google Maps en cours (progression temps réel)"],
                  ["0:45 → 1:10", "Gestion des contacts — filtrage New York, envoi email groupé"],
                  ["1:10 → 1:40", "Email généré par GPT-4o-mini + réception dans Gmail via SendGrid"],
                  ["1:40 → 2:05", "Génération calendrier éditorial (21 posts) + post Instagram publié"],
                  ["2:05 → 2:30", "Dashboard KPIs + pipeline de vente + rapports analytics"],
                ].map(([t, d]) =>
                  new Paragraph({
                    children: [
                      new TextRun({ text: `${t}  `, font: "Calibri", size: 19, bold: true, color: GOLD }),
                      new TextRun({ text: d, font: "Calibri", size: 19, color: "374151" }),
                    ],
                    spacing: sp(20, 20),
                  })
                ),
              ],
            }),
          ],
        }),
      ],
    }),

    spacer(80),

    // ── Après la vidéo ──
    new Paragraph({
      children: [new TextRun({ text: "APRÈS LA VIDÉO — Ce que vous dites :", font: "Calibri", size: 20, bold: true, color: TEAL })],
      spacing: sp(80, 40),
      border: { left: { style: BorderStyle.SINGLE, size: 20, color: TEAL, space: 1 } },
      indent: { left: 180 },
    }),
    spacer(20),

    slideLabel("Slides 15–16 — Réseaux Sociaux & BDD"),
    spacer(40),

    scriptLine(`Comme vous venez de le voir dans la démonstration, notre CRM couvre l'ensemble du cycle commercial de PM Travel Agency.`),
    spacer(40),
    scriptLine(`Pour les réseaux sociaux, notre système génère chaque semaine 21 posts automatiquement — 3 par jour, sur Instagram, Facebook et LinkedIn. Le contenu textuel est produit par GPT-4o-mini, l'image par DALL-E 3, et la publication est orchestrée par un workflow n8n avec un Switch Node qui gère les spécificités de chaque plateforme.`, true),
    spacer(40),
    scriptLine(`La base de données MySQL pm_travel centralise tout : 16 tables couvrant les prospects, les campagnes, les emails, les posts sociaux, le calendrier éditorial et les logs de scraping.`),
    spacer(80),

    rule(NAVY, 4),

    // ═══════════════════════════════════════════════════════
    // SECTION 06 — CONCLUSION (Slides 17–19)
    // ═══════════════════════════════════════════════════════
    pageBreakPara(),
    h1("  06  ·  Conclusion & Perspectives"),
    spacer(80),

    timeBadge("⏱  Durée : ~1 min 30 s  (Slides 17–19)"),
    slideLabel("Slide 17 — Transition section"),
    spacer(40),

    scriptLine(`Permettez-moi de conclure notre présentation.`),
    spacer(60),

    slideLabel("Slide 18 — Conclusion & Perspectives"),
    spacer(40),

    sectionTitle("06", "Objectifs atteints", TEAL),
    spacer(60),

    scriptLine(`Ce projet nous a permis de concevoir et de déployer une plateforme CRM complète, opérationnelle et utilisée par PM Travel Agency. Voici les résultats concrets que nous avons obtenus :`),
    spacer(40),

    bullet("1 367 prospects collectés et centralisés automatiquement."),
    bullet("Un taux de réponse de 67% sur les campagnes email générées par IA."),
    bullet("21 posts publiés chaque semaine sur trois réseaux sociaux sans intervention manuelle."),
    bullet("4 workflows n8n automatisés en production."),
    bullet("Une sécurité assurée par JWT et Fernet, avec une architecture modulaire FastAPI/React."),
    spacer(40),

    sectionTitle("", "Défis relevés", GOLD),
    spacer(40),

    scriptLine(`Ce projet n'a pas été sans difficultés. Nous avons notamment dû gérer :`),
    bullet("L'intégration simultanée de six APIs externes — Google Places, OpenAI, SendGrid, Instagram, Facebook, LinkedIn."),
    bullet("La publication Instagram qui nécessite un processus en deux étapes via l'API Graph."),
    bullet("Les politiques anti-spam qui compliquent le tracking des emails ouverts."),
    spacer(40),

    sectionTitle("", "Perspectives d'évolution", "9B59B6"),
    spacer(40),

    scriptLine(`Pour les évolutions futures, nous envisageons :`),
    bullet("L'extension du scraping vers LinkedIn, Booking.com et TripAdvisor."),
    bullet("Le développement d'une application mobile pour permettre une gestion en déplacement."),
    bullet("L'intégration d'un module d'analyse prédictive pour anticiper le comportement des prospects et optimiser les campagnes."),
    spacer(80),

    // ── Slide 19 ──
    slideLabel("Slide 19 — Merci & Questions"),
    spacer(40),

    sectionTitle("", "Clôture", TEAL),
    spacer(60),

    scriptLine(`Pour conclure, ce projet représente pour nous bien plus qu'un exercice académique. Il nous a permis de mettre en pratique deux années de formation en développement full-stack, d'intégrer des technologies modernes d'intelligence artificielle, et de livrer une solution réelle à un client réel.`, true),
    spacer(40),

    scriptLine(`Nous espérons avoir répondu aux exigences de votre jury, et nous vous remercions de l'attention que vous avez portée à notre travail.`),
    spacer(40),

    scriptLine(`Nous sommes maintenant disponibles pour répondre à vos questions.`),
    spacer(80),

    rule(TEAL, 8),

    // ═══════════════════════════════════════════════════════
    // ANNEXE — QUESTIONS JURY
    // ═══════════════════════════════════════════════════════
    pageBreakPara(),
    new Paragraph({
      children: [new TextRun({ text: "ANNEXE — QUESTIONS FRÉQUENTES DU JURY", font: "Cambria", size: 26, bold: true, color: WHITE })],
      shading: { fill: NAVY, type: ShadingType.CLEAR },
      alignment: AlignmentType.CENTER,
      spacing: sp(160, 160),
    }),
    new Paragraph({
      children: [new TextRun({ text: "(Préparez ces réponses — ne pas lire pendant la soutenance)", font: "Calibri", size: 18, color: "8099C3", italics: true })],
      alignment: AlignmentType.CENTER,
      shading: { fill: NAVY, type: ShadingType.CLEAR },
      spacing: sp(0, 200),
    }),

    ...[
      {
        q: "Pourquoi FastAPI plutôt que Django ou Spring Boot ?",
        r: "FastAPI offre des performances nettement supérieures grâce à son architecture asynchrone (ASGI). Il génère automatiquement la documentation Swagger, ce qui a facilité les tests d'API avec Postman. Son typage statique Python réduit les erreurs en développement. Django aurait ajouté de la complexité inutile pour un backend REST pur.",
      },
      {
        q: "Comment garantissez-vous la sécurité des données ?",
        r: "Plusieurs couches de sécurité : authentification JWT avec expiration, mots de passe hashés en bcrypt, clés API chiffrées avec Fernet (AES-128), communication HTTPS, et accès contrôlé par rôle via la table role_permissions.",
      },
      {
        q: "Comment fonctionne la déduplication des prospects ?",
        r: "Nous utilisons une contrainte UNIQUE composite sur les colonnes email et téléphone dans la table prospects. À chaque insertion, MySQL lève une IntegrityError que FastAPI intercepte pour incrémenter le compteur de doublons. Cela garantit l'unicité sans vérification applicative coûteuse.",
      },
      {
        q: "Pourquoi n8n pour l'orchestration ?",
        r: "n8n est open-source, auto-hébergeable, et dispose d'un éditeur visuel de workflows. Il s'intègre nativement avec des HTTP Requests vers notre API FastAPI, gère les déclencheurs planifiés, et permet de visualiser les exécutions — ce qui facilite le debugging. C'est une alternative professionnelle à Apache Airflow, mais bien plus simple à configurer.",
      },
      {
        q: "Quelles sont les limites actuelles du système ?",
        r: "Le système est actuellement déployé localement. Le passage en production nécessiterait une configuration serveur (VPS, Docker Compose, reverse proxy). De plus, les APIs des réseaux sociaux imposent des quotas journaliers — Instagram notamment limite les publications via API. Enfin, le tracking email est partial car certains clients bloquent le pixel de tracking.",
      },
      {
        q: "Comment avez-vous géré les erreurs des APIs externes ?",
        r: "Nous avons implémenté une gestion d'exceptions structurée dans FastAPI avec des try/catch autour de chaque appel externe. En cas d'échec, l'erreur est loggée dans la base de données (table logs_scraping ou logs_sociaux) et un message clair est retourné au frontend. n8n dispose également d'un mécanisme de retry natif.",
      },
      {
        q: "Comment vous êtes-vous réparti le travail en binôme ?",
        r: "Nous avons travaillé en pair programming sur l'architecture et la base de données. Chaimaa s'est principalement concentrée sur le backend FastAPI et les modules de scraping et email. Zakia s'est focalisée sur le frontend React et les modules de réseaux sociaux. Nous avons utilisé GitHub pour la gestion des versions et les code reviews croisées.",
      },
    ].flatMap(({ q, r }, i) => [
      new Paragraph({
        children: [
          new TextRun({ text: `Q${i + 1}  `, font: "Cambria", size: 22, bold: true, color: TEAL }),
          new TextRun({ text: q, font: "Cambria", size: 22, bold: true, color: NAVY }),
        ],
        spacing: sp(240, 60),
        border: { left: { style: BorderStyle.SINGLE, size: 20, color: TEAL, space: 1 } },
        indent: { left: 200 },
      }),
      new Paragraph({
        children: [new TextRun({ text: r, font: "Calibri", size: 20, color: "374151" })],
        spacing: sp(20, 120),
        indent: { left: 400 },
      }),
    ]),

    rule(TEAL, 6),
    new Paragraph({
      children: [new TextRun({ text: "Bonne chance pour votre soutenance ! 🎓", font: "Cambria", size: 24, bold: true, color: TEAL })],
      alignment: AlignmentType.CENTER,
      spacing: sp(200, 200),
    }),
  ];

  const doc = new Document({
    styles: {
      default: {
        document: { run: { font: "Calibri", size: 22, color: "1F2937" } },
      },
    },
    sections: [{
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 },
        },
      },
      headers: { default: makeHeader() },
      children,
    }],
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync("/mnt/user-data/outputs/Script_Soutenance_PFE_PM_Travel.docx", buffer);
  console.log("✅  Script saved.");
}

build().catch(console.error);