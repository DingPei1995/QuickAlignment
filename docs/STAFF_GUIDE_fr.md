# QuickAlignment — Guide du personnel de la ligne

Ligne ANTARES (SOLEIL) · étalonner le modèle de la platine avec InitialCalibration, et entretenir le programme

## Sommaire

1. [Ce dont le personnel est responsable](#ce-dont-le-personnel-est-responsable)
2. [Le modèle de la platine et ses constantes](#le-modèle-de-la-platine-et-ses-constantes)
3. [Quand réétalonner](#quand-réétalonner)
4. [Lancer InitialCalibration](#lancer-initialcalibration)
5. [Optique seule (cas habituel)](#optique-seule-cas-habituel)
6. [Optique + moteurs (étalonnage complet)](#optique--moteurs-étalonnage-complet)
7. [Points de test : vérifier et corriger](#points-de-test--vérifier-et-corriger)
8. [Enregistrer, et comment QuickAlignment utilise le fichier](#enregistrer-et-comment-quickalignment-utilise-le-fichier)
9. [Entretien du programme](#entretien-du-programme)
10. [Dépannage](#dépannage)

---

## Ce dont le personnel est responsable

Les utilisateurs ne font que *lire* l'étalonnage de la platine : QuickAlignment charge le **fichier de configuration**
le plus récent de l'optique choisie et ne peut pas le modifier. La configuration est faite par le personnel avec le
programme séparé **InitialCalibration** et rangée dans `configs/` :

```
configs/calibration_YYYY-MM-DD_HHMMSS_<optic>.json      optic : zone_plate ou capillary
```

Un fichier par étalonnage, jamais écrasé. Ce qui reste pour un utilisateur (surtout l'erreur du dessin d'un
échantillon sur la plaquette) est corrigé par *Found here* dans l'onglet Stage & Optics.

## Le modèle de la platine et ses constantes

Empilement, de bas en haut : translations ST / SN / SZ → SRz → SRn → piézo PIX / PIY → plaquette. Vue de dessus : le
faisceau suit +y, le plan focal de l'analyseur est à 45°, ST le long de ce plan et SN perpendiculaire.

| constante | signification | déterminée par |
|---|---|---|
| ST0, SZ0 | ST / SZ mettant le centre de la plaquette sous le faisceau (SRn 120°, SRz 0°) | série 1 |
| SN_f | SN mettant la surface de la rehausse standard (5,0 mm) dans le plan focal de l'analyseur | série 1 |
| axe SRn x, y | position de l'axe de rotation SRn sur la plaquette | une série avec SRn tourné |
| décalage SRz ST, SN | décalage de l'axe SRz par rapport à la ligne centrale de la surface | une série avec SRz tourné |
| référence optique | position de l'optique mettant le foyer au foyer de l'analyseur | positions d'optique notées |

SRn = 120° (plaquette verticale, languette en haut) est la référence mécanique ; PIX = PIY = 150 µm pendant
l'étalonnage. L'optique est modélisée comme un foyer qui se déplace le long du faisceau : ST, SZ et SRn ne changent
pas le plan de la surface et ne demandent pas de déplacer l'optique ; SN, SRz et la hauteur de l'échantillon si
(1 mm en SN déplace le spot de √2 mm le long du faisceau).

## Quand réétalonner

| situation | mode |
|---|---|
| capillaire ou zone plate réaligné (le faisceau touche la plaquette ailleurs, le foyer a bougé) | **optique seule** |
| moteurs réinitialisés, maintenance du manipulateur, réceptacle changé | **optique + moteurs** |
| première utilisation, ou pas encore de configuration pour cette optique | **optique + moteurs** |
| corrections *Found here* des utilisateurs au-delà de ~0,3 mm, même décalage pour plusieurs échantillons | vérifier avec optique seule ; complet si les résidus restent grands |

## Lancer InitialCalibration

Double-cliquer sur **`InitialCalibration.py`** (Windows : `InitialCalibration.pyw`). La première question est ce qui a
été réétalonné :

![Mode au démarrage](images/guide/ic_mode.png)

*Optique seule* n'est proposé que si une configuration existe déjà (la mécanique en est reprise).

Dans les deux modes, entrer d'abord l'**élément de référence** : un petit élément net que l'on retrouve avec le
faisceau (coin d'un échantillon de référence, une marque), proche du centre de la plaquette pour rester atteignable
en tournant. Entrer ses coordonnées x, y sur la plaquette (mm, depuis le centre de la plaquette, vue de face,
languette en haut) et sa hauteur H au-dessus de la surface, et choisir l'**optique**. **Show front / side view**
dessine la plaquette avec l'élément et indique où chaque série devrait le trouver avec la configuration actuelle
(courses vérifiées) :

![Vue de face et de côté de l'élément de référence](images/guide/ic_feature.png)

Utiliser **le même élément dans chaque série**.

## Optique seule (cas habituel)

![Réétalonnage de l'optique](images/guide/ic_optics.png)

Ajustés : ST0, SZ0 et la référence optique. Repris de la configuration la plus récente de l'optique : SN_f, l'axe SRn
et les décalages de l'axe SRz. Pour chaque série, comme la platine est utilisée d'habitude :

1. Régler SRn et SRz de la série ; PIX = PIY = 150 µm.
2. **Laisser SN tel quel** (il n'a pas à être au foyer de l'analyseur).
3. Amener l'élément sous le faisceau avec ST / SZ.
4. Refocaliser l'optique sur l'élément.
5. Noter ST, SZ, SN et la position de l'optique.

La série 1 (SRn 120°, SRz 0°) suffit. Les séries 2–3 (SRn et SRz tournés) sont recommandées : elles vérifient les
axes repris. Si leurs résidus restent au-dessus de ~0,05 mm, la mécanique a changé : relancer le programme et
choisir *optique + moteurs*.

## Optique + moteurs (étalonnage complet)

Les 7 constantes et la référence optique sont ajustées. L'élément est mis **au foyer de l'analyseur** à chaque série.

| série | SRn | SRz | rôle |
|---|---|---|---|
| 1 | 120 | 0 | ST0, SZ0, SN_f, référence optique |
| 2 | 140 | 0 | axe SRn |
| 3 | 120 | −10 | axe SRz |
| 4 | 100 | 0 | contrôle (recommandé) |
| 5 | 120 | +10 | contrôle (recommandé) |

**Au moins 3 séries** (chacune donne ST, SZ, SN) ; **5 recommandées**, pour qu'une mesure fausse se voie dans les
résidus. Des rotations plus grandes donnent des axes plus précis (|SRn − 120| ≥ 20°, |SRz| ≥ 10° autant que la
géométrie le permet). Décocher une série non mesurée ; *Add set* en ajoute une à d'autres angles.

Pour chaque série :

1. Régler SRn et SRz ; PIX = PIY = 150 µm.
2. Amener l'élément sous le faisceau avec ST / SZ (balayer, prendre le centre du bord ou de l'élément).
3. L'amener au foyer de l'analyseur avec SN.
4. Répéter 2–3 jusqu'à stabilité ; noter ST, SZ, SN.
5. Optimiser la focalisation sur l'élément et noter la position de l'optique : au moins en série 1, de préférence
   à chaque série (+ rapproche l'optique de l'échantillon).

Appuyer sur **Compute** :

![Résultats de l'ajustement](images/guide/ic_window.png)

- **Constantes ajustées** avec leur incertitude à 1σ, la valeur de la configuration la plus récente et l'écart.
- **Résidus** par série (modèle − mesure, mm) pour ST, SZ, SN et l'optique. Avec 5 séries ils doivent être
  ≲ 0,01–0,02 mm. Un grand résidu isolé signifie en général que la série a été mesurée sur un autre point ou hors
  foyer : la remesurer ou la décocher.
- Avertissements : *Not enough data* (constantes que les séries ne déterminent pas), *minimum data set* (erreurs
  indétectables), résidus au-delà de 0,05 mm, aucune position d'optique (référence optique non étalonnée).
- Un ajustement sur des nombres impossibles (fautes de frappe, NaN) est signalé au lieu d'être enregistré.

## Points de test : vérifier et corriger

Après *Compute*, l'onglet **Test points** prédit des rotations non utilisées dans les séries (SRn ± 30°, SRz ± 15°,
SRn et SRz combinés) avec les ST, SZ, SN et la position d'optique où la configuration place l'élément :

![Points de test](images/guide/ic_tests.png)

Pour chaque point de test :

1. Aller aux SRn, SRz, ST, SZ, SN et à la position d'optique prédits.
2. Si l'élément est sous le faisceau et au foyer **à 0,05 mm près**, cocher **Found**.
3. Sinon : garder SRn, SRz et SN, amener l'élément sous le faisceau avec ST / SZ, focaliser et entrer les **ST, SZ et
   position d'optique réels** (optique facultative). Les prédictions en rouge sortent d'une course moteur : changer
   les angles de ce point de test (il est prédit à nouveau).

**Correct the configuration with the test results → new test points** ajoute les positions réelles à l'ajustement
(les points trouvés ne font que confirmer), réajuste toutes les constantes et prédit un nouveau tour. Les tours
répondus restent dans le tableau, en lecture seule, avec leurs écarts. Répéter jusqu'à ce que tous les points d'un
tour soient trouvés, ou que les écarts soient assez petits ; une série qui reste aberrante a sans doute été mal
mesurée : la décocher et corriger à nouveau.

## Enregistrer, et comment QuickAlignment utilise le fichier

Ajouter un commentaire (date, raison, ce qui a été mesuré) et appuyer sur **Save as new configuration**. Le fichier
est écrit de façon atomique (une écriture ratée ne laisse pas de fichier partiel) et contient les constantes, la
référence optique, les séries, les points de test et leurs résidus, pour mémoire.

- QuickAlignment charge à chaque démarrage le **fichier le plus récent de l'optique choisie** par l'utilisateur. Une
  configuration zone plate ne remplace pas celle du capillaire, et inversement.
- S'il n'y a pas de fichier pour cette optique, les constantes de la platine du fichier le plus récent sont utilisées
  et la position de l'optique est indiquée comme non étalonnée.
- Les fichiers endommagés ou étrangers dans `configs/` sont ignorés. Pour retirer une mauvaise configuration,
  déplacer son fichier hors de `configs/` (ne pas le modifier).
- Les utilisateurs peuvent choisir une configuration plus ancienne pour leur session dans *Configuration…* (lecture
  seule).
- Les limites de ST, SZ, SN, SRn et SRz peuvent être modifiées dans *Configuration…* → *Motor limits* ; elles sont
  enregistrées dans `configs/motor_limits.json` (supprimer ce fichier pour revenir aux limites intégrées).

### Solides de l'anticollision

Le nez de l'analyseur, la zone plate et l'OSA et le capillaire sont modélisés par des solides simples (README,
*Anti-collision*). Les dimensions zone plate / OSA sont **provisoires** (la distance de travail du capillaire, 7,2 mm, est
la valeur de la ligne) : les mesurer (distance de chaque face avant au foyer, largeur, épaisseur ; pour l'OSA, la position OSA_S
correspondante) et les mettre dans la configuration sous `"collision"` (modifier une copie, puis l'enregistrer comme
nouveau fichier). InitialCalibration reprend les solides de la configuration précédente de la même optique.

## Entretien du programme

**Installation** (Python ≥ 3.9) : `pip install -r requirements.txt` (PyQt5 ou PySide6, numpy, matplotlib ; pytest pour
les tests). Lancer `QuickAlignment.py` / `InitialCalibration.py` (`.pyw` sous Windows, sans console).

**Tests** : `python -m pytest` dans le dossier QuickAlignment (environ 120 tests, ~15 s ; Qt hors écran). Ils couvrent
le modèle de la platine, les rotations, les ajustements d'étalonnage, la lecture des fichiers et les fenêtres
principales.

**Limites à modifier éventuellement** (un seul endroit chacune) :

| quoi | où |
|---|---|
| courses des moteurs ST, SN, SZ (champs et avertissements) | `MOTOR_SPECS` dans `quickalignment/ui/stage_panel.py` |
| SRn / SRz utilisables, limites du déflecteur, écarts acceptés, plage d'énergie, énergie de la zone plate, travail de sortie | constantes en tête de `quickalignment/bz_target.py` |
| orientation de la fente et signes des angles de fente / déflecteur | `AnalyzerGeometry` dans `quickalignment/rotation.py` |
| dessins des plaquettes (standard, gating) | `quickalignment/geometry.py` |

**Robustesse** : une erreur inattendue est affichée dans une fenêtre (avec les détails) et le programme continue, sans
perdre les positions entrées ; merci de recueillir ces détails. Sessions et configurations sont écrites de façon
atomique ; une session illisible donne un message au lieu d'un plantage ; les entrées impossibles dans les tableaux
(nan, inf, texte) sont refusées.

**Guides** : les captures d'écran sont faites par `python devtools/guide_screenshots.py`, les PDF par
`python devtools/build_guides.py` (pandoc et Playwright avec Chromium). Sources : `docs/USER_GUIDE_*.md`,
`docs/STAFF_GUIDE_*.md`.

## Dépannage

| symptôme | cause probable / action |
|---|---|
| tous les échantillons décalés de la même quantité | ST0 / SZ0 ont changé (optique réalignée) : *optique seule* |
| le décalage dépend de la rotation | les axes ont changé (moteurs réinitialisés) : *optique + moteurs* |
| résidus des séries 2–3 en *optique seule* au-delà de 0,05 mm | la mécanique a changé : *optique + moteurs* |
| une série avec un grand résidu | mauvais point, hors foyer ou faute de frappe : remesurer ou décocher |
| *Not enough data: …* | les constantes citées demandent une série avec SRn et/ou SRz tourné |
| une série demande SN sous la limite de collision | l'élément est trop bas ; prendre un élément sur un échantillon plus haut |
| QuickAlignment affiche la configuration *default* | aucun fichier lisible dans `configs/` |
