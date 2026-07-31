# claude-code-toolkit

[![CI](https://github.com/VFK00/claude-code-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/VFK00/claude-code-toolkit/actions/workflows/ci.yml)

**Gardez honnête le contexte de vos agents.**

Tous les outils de ce domaine mesurent ce que les agents *consomment* — jetons,
dollars, sessions. Aucun ne mesure la qualité de ce qu'on leur *donne à lire*.

Un `CLAUDE.md` qui ment dégrade chaque session qui le charge, en silence. Ces
outils le trouvent.

## Les outils

| Commande | Ce qu'elle répond |
|----------|-------------------|
| `cc-drift` | Mon `CLAUDE.md` correspond-il encore au code ? |
| `cc-memory` | Que contiennent réellement mes mémoires d'agent ? |
| `cc-spend` | Combien Claude Code a-t-il coûté, par projet et par modèle ? |
| `cc-run` | Lancer une commande sur plusieurs projets, en parallèle. |

`cc-drift` et `cc-memory` sont la raison d'être de ce dépôt. `cc-spend` et
`cc-run` sont des utilitaires — pour le seul suivi de coût,
[ccusage](https://ccusage.com) en fait davantage.

## Installation

```bash
uv tool install git+https://github.com/VFK00/claude-code-toolkit#subdirectory=packages/cc-drift
```

Répéter avec `cc-memory`, `cc-spend`, `cc-run` selon les besoins.

Les options globales (`--db`, `--base`, `--match`…) se placent **avant** la
sous-commande : `cc-spend --db autre.db scan`, et non l'inverse.

## À quoi ça ressemble

Un projet dont le `CLAUDE.md` annonce huit routes et douze tests, face à un
code qui en contient trois et deux :

```console
$ cc-drift check --project demo-app
         demo-app (threshold 25%)
┏━━━━━━━━┳━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ Signal ┃ Doc ┃ Code ┃ Drift % ┃ Status ┃
┡━━━━━━━━╇━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ routes │   8 │    3 │      62 │ DRIFT  │
│ models │   - │    2 │       - │ no doc │
│ tests  │  12 │    2 │      83 │ DRIFT  │
└────────┴─────┴──────┴─────────┴────────┘
  Docs read: CLAUDE.md
  Source files scanned: 3

$ echo $?
2
```

Le code de sortie `2` signale un écart au-delà du seuil — de quoi alimenter un
hook de pré-commit ou une étape de CI. `cc-drift install-hook` écrit ce hook
pour vous.

Le coût, par modèle, depuis vos transcripts locaux :

```console
$ cc-spend scan
OK transcripts scanned: 2 | entries added: 6
Discarded: 1 entry
  - invalid JSON x1
  e.g. ~/.claude/projects/demo/session.jsonl:3 (invalid JSON)

$ cc-spend report --by model
                  Claude Code cost by model
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ model             ┃  Input ┃ Output ┃ Cache read ┃ Cost USD ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━┩
│ claude-opus-4-5   │ 48,000 │ 13,600 │    192,000 │    $2.03 │
│ claude-sonnet-4-5 │ 10,000 │  1,800 │          0 │    $0.06 │
├───────────────────┼────────┼────────┼────────────┼──────────┤
│ TOTAL             │        │        │            │    $2.08 │
└───────────────────┴────────┴────────┴────────────┴──────────┘
```

Les sorties des commandes sont en anglais.

Regardez le second bloc du scan. Une ligne était illisible : elle est donc
**comptée et affichée**, avec son motif et l'endroit où la trouver. Un outil
qui abandonne discrètement une partie de son entrée et sort en `0` produit un
résultat faux — voir plus bas.

Même principe pour les tarifs : un modèle absent de la table est compté zéro,
et `cc-spend report` le dit, avec le volume de jetons concerné.

## Pourquoi ce dépôt existe

Constats réels d'une seule session d'audit sur un espace de travail de seize
projets :

- un `CLAUDE.md` annonçant **25 scripts** quand il en existait 24
- une pile LLM locale documentée comme vivante, **morte depuis 28 jours**
- **6 fichiers mémoire** décrivant 8 binaires supprimés, toujours injectés au
  rappel
- une commande documentée comme fonctionnelle, déléguant à un binaire
  **supprimé depuis des semaines**

Chacun coûte du contexte et produit de mauvaises réponses, à chaque session,
jusqu'à ce que quelqu'un le trouve à la main.

Deux règles gouvernent ici toute ingestion :

- **Ne jamais échouer sur une entrée fautive.** Une ligne malformée coûte cette
  ligne, jamais le fichier, jamais l'exécution.
- **Ne jamais écarter en silence.** Ce qui est sauté est signalé avec son motif.

Elles ne sont pas théoriques : chaque chemin d'ingestion est éprouvé sur un
corpus réel de plusieurs centaines de transcripts, entrées malformées
comprises. Les transcripts sont écrits par d'autres programmes, à travers des
versions de schéma successives, et peuvent être tronqués — un outil qui les lit
doit le supposer.

C'est ce qui distingue ces outils : un scan partiel ne ressemble jamais à un
scan complet. Ce qui est écarté est compté, motivé et localisé ; un modèle sans
tarif connu est signalé avec son volume plutôt que compté zéro en silence.

## Projet voisin

[panelize-code](https://github.com/VFK00/panelize-code) — tableaux de bord de
terminal pilotés par configuration. Même auteur, outil distinct.

## Licence

MIT
