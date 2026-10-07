# Relecteurs

Ce fichier donne le modèle à employer pour la revue indépendante définie dans
`WORKFLOW_ENGINEERING.md`. Il fait partie du corpus : son contenu est identique
dans tous les dépôts. Le dépôt choisit seulement le fournisseur qu'il utilise,
par la clé `review.reviewer_provider` de `project.config.yml`.

## Un modèle par fournisseur

| Clé | Fournisseur | Modèle | Contrainte d'invocation |
| --- | --- | --- | --- |
| `claude` | Anthropic | `claude fable 5.1 high` | Session distincte, lecture seule, invocation non interactive et bornée. |
| `codex` | OpenAI | `gpt 5.6 astra high` | Les outils MCP n'apparaissent pas dans la liste visible du modèle et restent appelables par leur nom ; voir les règles d'emploi. |
| `llmaas` | Cloud Temple LLMaaS (SecNumCloud) | `nemotron-3-super:120b` | Modèle de raisonnement avancé, endpoint `api.ai.cloud-temple.com`. |

Un seul modèle par fournisseur, pour que la revue soit reproductible et que deux
dépôts ne produisent pas des verdicts issus de configurations différentes.

## Règles d'emploi

- Le relecteur est un modèle différent du pilote. Si le pilote et le relecteur
  configuré désignent le même modèle, la revue n'est pas indépendante : changer
  de fournisseur ou signaler la revue comme indisponible.
- Le modèle réellement exécuté provient de la configuration de l'outil, pas de
  ce tableau. Vérifier l'identité retournée par l'outil et la conserver avec le
  verdict. Ne jamais déduire le modèle exécuté du nom écrit ici.
- Un fournisseur absent de la configuration locale n'est pas un fournisseur
  indisponible tant que cela n'a pas été vérifié. Une indisponibilité constatée
  se signale, elle ne se contourne pas par une auto-relecture présentée comme
  indépendante.
- **Ne pas forcer le niveau de raisonnement du relecteur.** Laisser le niveau haut
  défini par le modèle retenu. Un niveau bas produit des verdicts rendus sans que
  les règles du dépôt aient été ouvertes, et parfois un blocage annoncé sans qu'un
  seul appel ait été tenté, ce qui est indiscernable d'un vrai blocage. Si une
  contrainte technique existe pour un usage précis, la nommer avec son périmètre
  exact plutôt que de la généraliser à toutes les revues.
- **Les outils MCP de `codex` sont différés.** Ils n'apparaissent pas dans la
  liste que le modèle introspecte, et ils restent appelables par leur nom.
  Un relecteur qui se fie à sa liste conclut honnêtement qu'il n'a pas de
  mémoire, et le prérequis bloquant de `MAIN_RULES.md` arrête la revue avant
  qu'elle commence. Ce que l'on fournit au relecteur doit donc dire que l'absence
  d'un outil de la liste ne prouve pas son indisponibilité, qu'il faut l'appeler
  par son nom, et qu'il lui revient de constater son propre accès. Ne jamais l'en
  dispenser au motif que la session qui délègue l'a déjà fait : ce serait lui
  demander d'ignorer une règle pour pouvoir juger si elle est tenue.
- **La lecture seule du relecteur porte aussi sur la mémoire.** Il n'écrit aucune
  note : une revue n'a pas à laisser de trace dans la banque du projet, et son
  verdict revient par le pilote. Il établit donc son accès **en lecture**, en
  lisant réellement l'espace du projet, et il en rend compte. Il n'établit pas la
  moitié écriture du prérequis mémoire et ne l'affirme pas : `MAIN_RULES.md`
  nomme cette exception et la borne à ce seul rôle. Ne pas la remplacer par un
  droit déclaré. Un jeton porte ses permissions globalement et ses espaces dans
  une liste à plat, sans les croiser : y lire `write` n'établit pas le droit
  d'écrire sur un espace donné.
- **Nommer le serveur mémoire et l'espace** parmi les éléments de contexte
  fournis au relecteur, quand plusieurs serveurs exposent des outils homonymes.
  Le relecteur travaille en session non interactive : il ne peut pas exécuter la
  branche de « Trouver l'espace du projet », dans `PROJECT_RULES.md`, qui demande
  à l'utilisateur de choisir entre deux espaces homonymes. Lever l'ambiguïté en
  amont l'en dispense. Sans cette précision, il adresse le mauvais serveur et
  rend « accès refusé » : une erreur d'adressage qui se lit comme une panne. Si
  l'ambiguïté l'atteint quand même, il n'attend pas une réponse qu'une invocation
  bornée ne recevra jamais : c'est un blocage mémoire, il le signale et s'arrête
  sans rendre de verdict.

## Mise à jour

Les modèles évoluent souvent. Ce fichier change par une PR sur ce dépôt, suivie
d'un tag. Les dépôts consommateurs reçoivent le changement par le script de mise
à jour ; leur job de conformité signale l'écart tant qu'ils ne l'ont pas pris.
Ne pas modifier ce tableau dans un dépôt consommateur : la modification locale
sera détectée comme une dérive et écrasée à la mise à jour suivante.
