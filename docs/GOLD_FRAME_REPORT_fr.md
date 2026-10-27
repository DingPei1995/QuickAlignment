# Étalonnage par le cadre en or à partir de lignes d'intensité SPEM

ST, SZ, SN, l'axe SRn et l'axe SRz à partir de lignes SPEM d'intensité totale sur le cadre de référence en or. SZ est
le seul moteur rapide : chaque mesure est donc une ligne SZ en fly scan. Tourner le cadre de 45° avec SRn rend ses
bords diagonaux, si bien que les lignes SZ donnent aussi la position horizontale. Tous les bords de toutes les lignes
sont ajustés ensemble.

Ceci remplace la première version de la méthode, dont la troisième carte (ligne ST × SRz) demandait de longs balayages
avec le moteur ST, lent. Le rapport couvre le plan de mesure, les simulations des cas parfait et imparfaits, le rôle du
foyer de l'analyseur et de la position du faisceau, la précision, et le programme qui transforme les fichiers mesurés
en une configuration de QuickAlignment (`GoldFrameCalibration.py`).

## Sommaire

1. [En bref](#en-bref)
2. [L'échantillon, les moteurs et l'idée](#léchantillon-les-moteurs-et-lidée)
3. [Géométrie : ce que mesure une ligne SZ](#géométrie--ce-que-mesure-une-ligne-sz)
4. [Le plan de mesure](#le-plan-de-mesure)
5. [L'ajustement global](#lajustement-global)
6. [Cas parfait et cas imparfaits](#cas-parfait-et-cas-imparfaits)
7. [Foyer de l'analyseur et position du faisceau](#foyer-de-lanalyseur-et-position-du-faisceau)
8. [Précision : mesures simulées ajustées](#précision--mesures-simulées-ajustées)
9. [Protocole conseillé](#protocole-conseillé)
10. [Le programme](#le-programme)
11. [Limites](#limites)

## En bref

- **Seul SZ est balayé.** ST, SN, SRn et SRz sont réglés entre les lignes et jamais balayés. La carte ST × SRz (carte 3
  de la première version) est abandonnée.
- **Le losange.** Avec SRn = 120 ± 45°, les bords du cadre sont diagonaux. L'endroit où une ligne SZ les croise suit
  1:1 l'endroit où la ligne passe en travers du cadre : ST0, l'axe SRn et l'axe SRz se lisent donc sur l'axe rapide.
- **Plan : 33 lignes SZ en 9 réglages.**
  - A : SRn 120, 5 lignes.
  - B : SRn 165 et 75, 5 lignes chacun.
  - C : SRn 165 à SRz −25, −18, −11, −4, +3 et +10°, 3 lignes chacun.

  Le programme place les lignes avec la configuration la plus récente et vérifie les courses des moteurs et le modèle
  anti-collision. ST se déplace d'environ 20 mm en tout ; l'ancien schéma balayait ST sur environ 250 mm pour la
  seule carte 3.
- **Un ajustement global** de tous les bords de toutes les lignes (ST0, SZ0, l'axe SRn, les décalages de l'axe SRz, la
  rotation du cadre, l'inclinaison de la face d'or, les échelles ST/SZ) :
  - Aucune constante ne passe d'une étape à la suivante : l'amplification d'environ 10 fois d'une erreur sur ST0 dans
    la profondeur de l'axe SRz a disparu.
  - D'autres données peuvent être ajoutées : carte d'ensemble ST × SZ, balayage SZ × SRn, lignes isolées.
- **Points SN facultatifs :** SN au foyer de l'analyseur à d'autres SRz, saisis dans une fenêtre à part. Ils
  vérifient l'axe SRz tel que le voit l'analyseur, mais ne remplacent pas les lignes SRz : seuls, ils ne donnent sa
  profondeur qu'à environ 0,1 mm.
- **Foyer de l'analyseur et position du faisceau :** une ligne SZ reste dans la surface et suit l'axe SRz, donc le
  point éclairé ne glisse pas le long du faisceau. L'analyseur ne fait que pondérer l'intensité, et les bords restent
  là où le faisceau les croise. SN_f vient d'un balayage SN sur l'or ; un faisceau passant à côté du foyer de
  l'analyseur ne touche que SN_f.
- **Précision (simulation) :** environ 1–2 µm pour ST0, SZ0 et l'axe SRn, environ 5–20 µm pour l'axe SRz.
  L'inclinaison de la face d'or est obtenue à ±0,03°, les échelles ST/SZ à ±0,002.
- **Limite de la méthode :** le cadre est pris pour la référence de la plaque. Une erreur sur l'endroit où il est
  collé passe dans ST0, SZ0 et les axes, donc dans la position prévue de tous les autres échantillons.

## L'échantillon, les moteurs et l'idée

La référence : un cadre carré en or, 2 × 2 mm à l'extérieur avec un trou de 1 × 1 mm, collé en principe au centre de
la rehausse de la plaque standard. La colle peut le laisser décalé (u, v), tourné dans son plan, surélevé (or + colle
au-dessus du haut de la rehausse, *h*) et incliné. Seule l'intensité totale de photoémission sert
(`heason/total_int`, ou `image32` sommé) : l'or est clair, la rehausse en Ta et le fond du trou plus sombres.

**Les moteurs.** SZ est rapide et peut être balayé en fly scan, avec des pas jusqu'à 0,02 mm. ST est lent, SRn et SRz
aussi. Une mesure doit donc consister en lignes SZ, les moteurs lents ne bougeant qu'entre les lignes.

**L'idée.** À SRn 120, les bords du cadre sont horizontaux et verticaux : une ligne SZ ne croise que les bords
horizontaux et ne voit rien de la position horizontale. Tourné de 45°, le cadre est un losange. Une ligne SZ passant à
une distance p du centre du losange croise ses bords en

  SZ = SZ_c ± (√2·h − |p|) (bords extérieurs, h = 1 mm ; le trou : h = 0,5 mm, si |p| < 0,71 mm)

La longueur de la corde donne |p|, les lignes des deux côtés du centre donnent son signe, et le milieu donne SZ_c.
Tout déplacement horizontal (ST0 erroné, axe SRn hors du cadre, cadre qui bouge avec SRz) apparaît donc sur l'axe SZ
rapide, avec toute sa sensibilité.

Coordonnées comme dans QuickAlignment. Repère plaque (u, v) : vue de face, languette en haut. Labo : origine = foyer de
l'analyseur, faisceau selon +y, +ST selon t = (1, −1, 0)/√2, +SN selon n = (1, 1, 0)/√2 (en s'éloignant de
l'analyseur). Les données sont dessinées comme ANTARES les dessine : ST décroissant vers la droite et SZ décroissant
vers le haut (haut = +v).

![Vue de dessus](images/gold_frame/geometry.png)

## Géométrie : ce que mesure une ligne SZ

À SRn 120, SRz 0, avec le dessus de l'or au foyer de l'analyseur, le faisceau touche la plaque en

  u = ST0 − ST − d,  v = SZ0 − SZ,  d = SN − SN_gold

(le faisceau arrive à 45° : une surface défocalisée de d déplace le point de d selon −u).

**SRn (groupes A et B).** SRn tourne la plaque autour de sa normale, autour de l'axe A = (A_u, A_v) sur la plaque.
Avec Δ = c − A (centre du cadre moins axe) et α = SRn − 120, le centre du cadre passe en A + R(α) Δ. À α = ±45°, le
losange se déplace de Δ_u (cos α − 1) − Δ_v sin α horizontalement et de Δ_u sin α + Δ_v (cos α − 1) verticalement.
Deux losanges (+45°, −45°) donnent les deux composantes de l'axe, et la rotation du cadre vient avec.

**SRz (groupe C).** SRz tourne la platine autour d'un axe vertical. Son décalage le long de ST (o_t, repère plaque) et
sa profondeur D derrière la surface d'or (D = h + `srz_offset_n`) fixent où l'on trouve le cadre. Avec a = −SRz,
Y = o_t − u_c et SN gardé, le ST qui met le centre du cadre sur le faisceau se déplace de

  ST_c(a) − ST_c(0) = (D + Y)(cos a − 1) − (D − Y) sin a

soit environ 1,4 mm à −25° pour la configuration actuelle (D ≈ 2,6 mm). Les lignes du groupe C sont placées avec la
configuration la plus récente ; l'écart réel du losange à l'endroit prévu se lit sur les bords diagonaux, 1:1.

Une inclinaison β de la face d'or autour de la verticale change l'incidence. Le cadre paraît alors (cos β + sin β)
fois plus large en travers du faisceau, ce que mesurent les lignes SRz. L'ajustement l'obtient avec l'échelle ST.

![Où l'on trouve le cadre en fonction de SRz](images/gold_frame/srz_curves.png)

## Le plan de mesure

![Où les lignes prévues croisent le cadre](images/gold_frame/survey_plan.png)

| groupe | SRn | SRz | lignes | donne surtout |
|---|---|---|---|---|
| A | 120 | 0 | 5, ST ±0,8 mm autour du centre | SZ0, rotation, échelle SZ |
| B | 165 et 75 (±45°) | 0 | 5 chacun, ±1 mm en travers du losange | ST0, axe SRn, échelle ST |
| C | 165 | −25, −18, −11, −4, +3, +10 | 3 chacun, ±0,4 mm | axe SRz (décalage le long de ST, profondeur), inclinaison de la face d'or |

Chaque ligne : SZ ±2,2 mm autour du centre du cadre, fly scan, pas de 0,02 mm. SN est réglé une fois par réglage
SRn / SRz pour que le centre du cadre soit au foyer de l'analyseur ; entre les lignes d'un réglage, seul ST bouge
(quelques dixièmes de mm).

Le plus naturel est un fichier par réglage, ST avancé d'une ligne à l'autre et SZ rapide. Des fichiers d'une seule
ligne conviennent aussi.

*Measurement plan…* dans le programme liste chaque ligne (SRn, SRz, ST, SN, SZ de / à), la vérifie par rapport aux
courses des moteurs et au modèle anti-collision, et l'enregistre en CSV. Les lignes n'ont besoin d'être qu'à quelques
dixièmes de mm du cadre : le losange fait 2,8 mm de large.

<!-- EFFORT TABLE -->
| | lignes SZ | ST balayé | déplacements ST entre lignes | réglages SRn | réglages SRz |
|---|---|---|---|---|---|
| trois cartes (ancien, carte 3 ST × SRz) | 262 | 252 mm | 237 | 61 | 36 |
| relevé de lignes SZ (nouveau) | 33 | 0 | 33 (21 mm) | 4 | 6 |
<!-- /EFFORT TABLE -->

Le balayage ST de l'ancienne carte 3 représentait à lui seul environ 250 mm de course ST, contre environ 20 mm de
déplacements ST ici. SRn demande 4 réglages au lieu de 61 (120, 165, 75, puis retour à 165 pour le groupe C), SRz 6 au
lieu de 36.

Ajouts facultatifs, tous ajustés avec le reste :
- **Une carte d'ensemble ST × SZ** (SRn 120, SRz 0 ; des pas ST grossiers comme 0,1 mm suffisent, SZ rapide). C'est la
  première étape naturelle pour trouver le cadre, et elle donne son départ à l'ajustement.
- **Un balayage SZ × SRn** (SRn 60…180°) : plus de données SRn, lent.
- **Des points SN à d'autres SRz** (section 5).

## L'ajustement global

Toutes les lignes de tous les fichiers chargés sont ajustées ensemble : chaque bord d'or de chaque ligne est prédit
avec le modèle de platine de QuickAlignment, et les constantes sont ajustées jusqu'à ce que les bords prédits tombent
sur les bords mesurés.

- **Ajustés :** ST0, SZ0, l'axe SRn (x, y), les décalages de l'axe SRz (le long de ST, profondeur), la rotation du
  cadre dans son plan, l'inclinaison de la face d'or autour de v, et les échelles ST et SZ.
- **Par les réglages :** SN_f = SN_gold − hauteur de l'or. SN_gold est le SN qui met le dessus de l'or au foyer de
  l'analyseur, donné par le balayage SN.
- **Gardés de la configuration la plus récente** quand les données ne peuvent pas les fixer, ce qui est signalé :
  - aucune ligne avec SRn tourné : l'axe SRn ;
  - aucune ligne (ou point SN) avec SRz tourné : l'axe SRz et l'inclinaison.
- **Départ :** une carte d'ensemble, si elle est chargée, donne ST0, SZ0 et la rotation ; sinon une recherche
  grossière de ST0 / SZ0 sur les lignes à SRz 0. Puis une recherche grossière de l'axe SRz, puis les moindres carrés
  complets.
- **Robuste :** une ligne dont les bords ont été mal lus (une partie du cadre hors de la ligne, une ligne qui frôle un
  coin du trou) est écartée et signalée.
- **Points SN facultatifs** (*SN at other SRz…*, une fenêtre à part). À quelques SRz, un balayage SN (ST suivant) sur
  la barre droite du cadre donne le ST et le SN auxquels l'or sous le faisceau est au foyer de l'analyseur. Chaque
  point ajoute une équation : la distance de l'or au foyer de l'analyseur le long du faisceau, pondérée avec une
  incertitude de 10 µm contre 3 µm par bord. Les points vérifient l'axe SRz tel que le voit l'analyseur, en supposant
  que le faisceau passe par le foyer de l'analyseur (section 7). Seuls, ils sont faibles pour la profondeur (tableau,
  dernière ligne) : ils complètent les lignes SRz plutôt qu'ils ne les remplacent.

## Cas parfait et cas imparfaits

Toutes les données sont simulées par le programme et placées avec la configuration dessinée en magenta. Le faisceau est
suivi à travers le modèle de platine de QuickAlignment, avec les parois du cadre et leurs ombres (la bande sombre d'un
côté d'un bord est le faisceau qui frappe une paroi) et un bruit de Poisson. À gauche : la carte d'ensemble. À
droite : toutes les lignes SZ, groupées par SRn / SRz. Magenta : les bords du cadre parfait. Cyan : les vrais bords.

**Parfait.** Cadre au centre de la plaque, axe SRn passant par lui, axe SRz dans sa surface :
- groupe A : les bords horizontaux du cadre au même SZ sur chaque ligne ;
- groupe B : les cordes du losange symétriques autour de la ligne centrale ;
- groupe C : le même losange à chaque SRz.

![Parfait](images/gold_frame/perfect.png)

**Décalage horizontal du cadre (0,3 mm selon +u, 0,2 mm vers le bas).**
- La carte d'ensemble se déplace en bloc (ΔST = −0,3, ΔSZ = +0,2).
- Le groupe A se déplace de +0,2 en SZ.
- Dans les groupes B et C, les cordes changent : les lignes passent ailleurs sur le losange. Le losange lui-même bouge
  aussi, car pour l'axe SRn au centre de la plaque, le cadre est désormais hors axe.

L'ajustement ne peut pas distinguer ce décalage de celui de toute la plaque : il passe dans ST0/SZ0 et dans les axes.

![Décalage du cadre](images/gold_frame/frame_offset.png)

**Axe SRn décalé (0,4 mm, 0,3 mm du centre du cadre).** Le groupe A ne change pas. Les losanges à 165° et 75° se
déplacent en sens opposés (A + R(±45°) Δ).

![Décalage de l'axe SRn](images/gold_frame/srn_axis.png)

**Axe SRz décalé (0,5 mm selon +ST, 1,0 mm derrière la surface).** Les groupes A et B ne changent pas. Dans le groupe
C, le losange bouge avec SRz comme dans la formule de la section 3.

![Décalage de l'axe SRz](images/gold_frame/srz_axis.png)

**Les axes de la configuration actuelle**, avec les lignes placées par elle : chaque ligne croise le losange comme
prévu.

![Configuration actuelle](images/gold_frame/real_axes.png)

**Rotation dans le plan (3°) et inclinaison de la face (2° autour de v).**
- La rotation incline les bords de la carte d'ensemble et rend les losanges asymétriques.
- L'inclinaison change la largeur du losange avec SRz.

![Rotation et inclinaison](images/gold_frame/rotation_tilt.png)

## Foyer de l'analyseur et position du faisceau

**Aucune correction n'est nécessaire pour les positions.** Chaque bord est là où le *faisceau* croise le bord d'or.
L'analyseur ne fait que pondérer l'intensité, et un bord net reste en place.

**Les lignes SZ ne glissent pas le long du faisceau.** SZ est vertical : il est dans la surface d'or (à une
inclinaison autour de u près) et parallèle à l'axe SRz. Le long d'une ligne SZ, le point éclairé garde donc sa place
le long du faisceau, à tout SRn et tout SRz.

Entre réglages, le centre du cadre reste au foyer de l'analyseur, puisque SN est réglé à chaque réglage. Les lignes
extérieures du groupe C, à ±0,4 mm du centre, sont au plus à environ ±0,2 mm du foyer le long du faisceau. Avec une
acceptance de l'analyseur de 0,5 mm, toutes les lignes gardent leur signal (tableau : 33/33 lignes). L'ancienne carte 3,
une ligne ST à SN fixé, déplaçait le point jusqu'à 1,7 mm le long du faisceau et perdait une partie du cadre.

**SN_f par un balayage SN sur l'or.** Avec ST suivant SN (ΔST = −ΔSN), le point reste sur le faisceau et glisse le
long de celui-ci. Le pic d'intensité est SN_gold, et sa largeur est l'acceptance de l'analyseur en travers de son axe
(ici 0,29 mm).

**Faisceau à côté du foyer de l'analyseur.** Si la ligne du faisceau passe à une distance b du foyer de l'analyseur
(horizontalement, en travers du faisceau), le balayage SN culmine là où le faisceau croise l'axe de l'analyseur, √2 b
plus loin le long de cet axe. SN_f change de √2 b (0,14 mm pour b = 0,1 mm, tableau). Toutes les positions restent
celles du faisceau : ST0, SZ0 et les axes ne changent pas.

Ce qui reste : l'échantillon trouvé est à √2 b du vrai foyer de l'analyseur le long de l'axe de l'analyseur (y labo
= b : la colonne « faisceau » du tableau). Aucune constante de platine ne peut l'éliminer : c'est l'alignement du
faisceau. Un décalage vertical ne fait que baisser l'intensité et passe dans SZ0.

Les points SN facultatifs supposent b = 0. Avec b ≠ 0, ils portent le même décalage à chaque SRz, que ST0 / SN_f
absorbent pour l'essentiel.

![Balayage SN sur l'or](images/gold_frame/sn_scan.png)

## Précision : mesures simulées ajustées

Chaque cas ci-dessous a été simulé sur les axes de la configuration actuelle, avec des pas SZ de 0,02 mm, un bruit de
Poisson à 3000 coups sur l'or, et les lignes placées avec une configuration fausse de 0,2–0,3 mm. Les données ont été
ajustées par le programme comme il ajuste des fichiers mesurés. Seul le relevé a servi, sauf mention contraire.

Deux sortes de nombres :
- **Écart :** constante ajustée moins vraie, après retrait de ce que la méthode ne peut pas voir (un décalage du
  cadre passe dans ST0, SZ0 et les axes).
- **Point test :** où la configuration ajustée envoie réellement le faisceau sur la vraie platine, pour le point
  (1,5 ; 1,0) de la plaque à SRn 100, SRz −15. « Plaque » est l'écart sur la plaque ; « faisceau » la distance au
  foyer de l'analyseur le long du faisceau.

<!-- RESULTS TABLE -->
Écarts en µm (ajusté − vrai).

| cas | lignes utilisées | ST0 | SZ0 | SN_f | axe SRn x, y | décalage SRz ST, SN (± σ) | point test : plaque / faisceau |
|---|---|---|---|---|---|---|---|
| cadre parfait | 33/33 | +1 | 0 | 0 | -1, 0 | +17 ± 11, +8 ± 9 | 2 / +5 |
| cadre décalé (0,3 ; −0,2) mm, tourné de 3° | 48/54 | +2 | 0 | 0 | 0, 0 | +2 ± 7, 0 ± 6 | 360 / 0 |
| échelle ST 1,02, SZ 0,99 | 33/33 | +2 | 0 | 0 | 0, 0 | +3 ± 12, -4 ± 10 | 35 / +14 |
| face inclinée de 2° autour de v, non ajustée | 33/33 | +6 | -1 | 0 | +5, 0 | -64 ± 56, 0 ± 45 | 8 / -21 |
| face inclinée de 2° autour de v, ajustée | 32/33 | +2 | 0 | 0 | 0, 0 | -5 ± 8, -8 ± 6 | 2 / -2 |
| acceptance de l'analyseur 0,5 mm | 33/33 | +1 | 0 | 0 | -1, 0 | +13 ± 10, +7 ± 8 | 2 / +4 |
| faisceau à 0,1 mm du foyer de l'analyseur | 33/33 | +4 | 0 | +140 | -1, 0 | -21 ± 12, -10 ± 9 | 0 / +90 |
| + carte d'ensemble + balayage SRn ; cadre décalé, tourné, incliné ; analyseur 0,5 mm | 115/115 | 0 | 0 | 0 | -1, -1 | -4 ± 7, -6 ± 6 | 180 / -2 |
| sans lignes SRz : 6 points SN à la place (bruit 5 µm) | 15/15 | +1 | 0 | 0 | -1, 0 | +32 ± 23, -146 ± 134 | 42 / +4 |
<!-- /RESULTS TABLE -->

Lecture du tableau :
- **Décalage de collage du cadre :** l'ajustement est juste pour le cadre, mais tous les autres échantillons sont
  alors décalés d'autant (0,36 mm ici), comme avec toute référence unique.
- **Échelles ST / SZ :** elles sont mesurées (à ±0,001). QuickAlignment suppose 1, donc une échelle de 1,02 coûte
  quelques dizaines de µm loin du centre ; le programme le signale.
- **Inclinaison :** l'ignorer déplace le décalage SRz le long de ST de quelques dizaines de µm ; l'ajuster l'élimine.
- **Analyseur étroit :** rien n'est perdu, car les lignes SZ ne glissent pas le long du faisceau.
- **Faisceau à côté du foyer :** SN_f prend √2 b. Le point est trouvé sur le faisceau, à √2 b du foyer de l'analyseur
  le long de l'axe de l'analyseur.
- **Plus de données** (carte d'ensemble, balayage SRn) : des incertitudes plus petites, les mêmes valeurs. Le point
  test est décalé du décalage de collage du cadre (0,18 mm dans ce cas), comme plus haut.
- **Points SN à la place des lignes SRz :** le décalage SRz le long de ST est obtenu à quelques dizaines de µm, mais
  la profondeur seulement à environ 0,1 mm, car elle intervient par 1 − cos SRz (≤ 0,09). Mesurés avec les lignes SRz,
  les points SN vérifient la profondeur vue par l'analyseur.

## Protocole conseillé

1. SRn 120, SRz 0, PIX = PIY = 150. Trouver l'or (une **carte d'ensemble** : ST × SZ, ±2 mm, pas ST de 0,1 mm, SZ
   rapide). Puis faire le **balayage SN** (ST suivant) sur une barre d'or : SN_gold, et l'acceptance de l'analyseur
   par sa largeur. Faire le même balayage sur la rehausse pour la hauteur de l'or *h* (différence des pics).
   Focaliser l'optique sur l'or.
2. Ouvrir `GoldFrameCalibration.py`, régler la hauteur de l'or (et l'emplacement supposé du cadre s'il n'est pas au
   centre), appuyer sur *Measurement plan…*. Vérifier que chaque ligne est « ok », et enregistrer le CSV.
3. Mesurer les lignes des groupes A, B et C. Par réglage : régler SRn, SRz et SN, puis pour chaque ligne régler ST et
   balayer SZ (fly scan, 0,02 mm), par exemple en un balayage 2-D où ST avance.
4. Facultatif : *SN at other SRz…*, *Fill the planned positions*. À chaque ligne du tableau, faire un balayage SN (ST
   suivant) sur la barre droite et saisir le ST et le SN au pic.
5. *Add files…* (tous, la carte d'ensemble comprise), régler SN gold, *Fit*. Vérifier :
   - le rms des bords : quelques µm ;
   - les lignes écartées : peu nombreuses, et seulement là où le cadre n'est pas croisé ou pas vu ;
   - l'inclinaison : ≲ 2° ;
   - les échelles : à 0,5 % près de 1 ;
   - les bords ajustés sur les données ;
   - le changement par rapport à la configuration la plus récente.
6. *Save as new configuration*. Comme avec InitialCalibration, l'essayer sur un échantillon de position connue à une
   autre rotation (QuickAlignment, *Found here*).

## Le programme

**`GoldFrameCalibration.py`** (double-clic ; Windows : `GoldFrameCalibration.pyw`) ouvre la fenêtre d'étalonnage :

1. **Measurement plan… (plan de mesure)** Les lignes à mesurer, placées avec la configuration la plus récente de
   l'optique choisie et le cadre là où il est supposé être. Chaque ligne est vérifiée par rapport aux courses des
   moteurs et au modèle anti-collision. *Save as CSV…*.
2. **Add files… (ajouter des fichiers)** Autant de fichiers `.nxs` que voulu (ou `.npz` du simulateur) : un par
   réglage, des lignes isolées, une carte d'ensemble, un balayage SZ × SRn. La liste donne SRn, SRz, ST, SN et le
   nombre de lignes de chacun ; *Remove* / *Clear*.
3. **Réglages :**
   - SN gold (par défaut : le SN d'un fichier à SRn 120 / SRz 0) ;
   - hauteur de l'or ;
   - où le cadre est supposé être sur la plaque, sa taille extérieure et celle du trou ;
   - ajuster l'inclinaison, ajuster les échelles ;
   - diviser par la diode ;
   - l'optique et sa position au foyer de l'or (par défaut : enregistrée dans un fichier à SRn 120 / SRz 0, sinon la
     référence de la configuration la plus récente).
4. **SN at other SRz (optional)…** Une fenêtre à part pour les points SN facultatifs :
   - *Fill the planned positions* : les lignes à mesurer, avec le SN attendu ;
   - saisir le ST et le SN au pic ;
   - charger un CSV.

   Les lignes sans SN mesuré ne servent pas. Après un ajustement, chaque ligne montre la distance de son point au foyer
   de l'analyseur.
5. **Fit (ajuster) :**
   - onglet *Results* : les sept constantes avec leur incertitude, la configuration la plus récente et le changement ;
     la rotation, l'inclinaison et les échelles ; par fichier les lignes utilisées et le rms ; les avertissements.
   - onglet *Data* : la carte d'ensemble et toutes les lignes SZ avec les bords ajustés (orange).
6. **Save as new configuration (enregistrer)** (avec un commentaire) : `configs/calibration_<heure>_<optique>.json`,
   que QuickAlignment charge au démarrage suivant. L'ajustement, les fichiers et les points SN vont dans son
   enregistrement `check`.

*Load a simulated example* simule les lignes prévues sur un cadre avec des défauts connus et les charge, avec les vraies
valeurs dans la barre d'état, pour essayer la fenêtre.

![Fenêtre d'étalonnage : données avec les bords ajustés](images/gold_frame/calibration_maps.png)

![Fenêtre d'étalonnage : résultats](images/gold_frame/calibration_results.png)

![Plan de mesure](images/gold_frame/plan_dialog.png)

![SN à d'autres SRz (facultatif)](images/gold_frame/sn_dialog.png)

**`GoldFrameSimulator.py`** (double-clic ; `GoldFrameSimulator.pyw` ; aussi *Open the simulator…* dans la fenêtre)
est le simulateur interactif. Curseurs pour :
- le cadre : décalage, rotation, inclinaisons, hauteur ;
- la platine : axe SRn, décalages SRz, échelle ST ;
- le faisceau et l'analyseur : acceptance, décalage du faisceau.

Il montre la carte d'ensemble, les lignes SZ du plan et, sur demande, le balayage SZ × SRn, avec les bords du cadre
parfait (magenta).

![Simulateur](images/gold_frame/simulator.png)

En console :
- `python GoldFrameCalibration.py plan [--csv F]` : le plan.
- `python GoldFrameCalibration.py simulate [--frame-u … --srz-offset-n … --srn-sweep]` : une mesure simulée en fichiers
  ANTARES `.nxs`, avec le plan, une figure et les vraies valeurs.
- `python GoldFrameCalibration.py fit FICHIER… [--sn-gold] [--sn-points CSV] [--height] [--no-tilt] [--no-scales]
  [--optic capillary|zone_plate] [--optic-position] [--plot PNG] [--save]`.

**Lecture des fichiers** (`quickalignment/spem_nxs.py`), écrite d'après un vrai balayage SZ × SRn
(`Cp_2023-05-28_22-08-47.nxs`) :
- *Canaux :* les `scan_data/data_NN` sont reconnus par leur `long_name` (les numéros NN changent d'une configuration
  de balayage à l'autre).
- *Intensité :* `heason/total_int` (= vsum(mbsProj)) ; sinon `mbs/image32` (ou `xproj`) sommé par point.
- *Positions :* les relectures des moteurs en chaque point sont ajustées ligne par ligne, ce qui absorbe un retard de
  fly scan ou un zig-zag. Les moteurs fixes viennent de `ANTARES/i12-m-cx1-ex-sample-mt_*/position`.
- *Normalisation :* par la diode (`dtc_diode`) sur demande.

Le loader SPEM d'ARPES viewer prendrait ce format pour une carte en déflecteur : le programme lit donc les fichiers
lui-même.

## Limites

- **Le cadre est la référence de la plaque.** Son décalage de collage ne se voit pas ; il passe dans ST0/SZ0 et les
  axes. Pour le vérifier, mesurer un repère de la plaque (bord de la rehausse) ou un échantillon de position connue.
- **Référence SRn :** la rotation du cadre et le zéro de SRn ne peuvent pas être séparés. QuickAlignment garde
  SRn 120 = plaque verticale, et la rotation trouvée est rapportée.
- **Les échelles ST / SZ** sont mesurées et rapportées, pas utilisées par QuickAlignment.
- **Des lignes placées trop loin** (plus d'environ 1 mm, par ex. après une remise à zéro des moteurs) peuvent manquer le
  losange. Commencer par une carte d'ensemble à SRn 120 et, si besoin, un premier ajustement avec les groupes A et B
  seuls, puis replacer le groupe C.
- **Les intensités du simulateur et l'acceptance de l'analyseur** (gaussienne, 0,5 mm) sont provisoires.
  L'ajustement n'en dépend pas, seules les images simulées en dépendent. Mesurer l'acceptance par le balayage SN.
- **La hauteur de l'or *h*** décale SN_f et `srz_offset_n` ensemble. La mesurer.
