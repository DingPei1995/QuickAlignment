# QuickAlignment — Guide de l'utilisateur

Ligne ANTARES (SOLEIL) · retrouver les échantillons sur la plaquette, les garder sous le faisceau en tournant, et
choisir la rotation pour un point de la zone de Brillouin

## Sommaire

1. [Ce que fait QuickAlignment](#ce-que-fait-quickalignment)
2. [Démarrer le programme](#démarrer-le-programme)
3. [Coordonnées et moteurs](#coordonnées-et-moteurs)
4. [Onglet Samples : dessiner la plaquette](#onglet-samples--dessiner-la-plaquette)
5. [Onglet Stage & Optics : aller sur un échantillon](#onglet-stage--optics--aller-sur-un-échantillon)
6. [Onglet Rotate sample : tourner sans perdre l'échantillon](#onglet-rotate-sample--tourner-sans-perdre-léchantillon)
7. [Trouver les angles pour un point de la zone de Brillouin](#trouver-les-angles-pour-un-point-de-la-zone-de-brillouin)
8. [Sessions, plaquette et configuration](#sessions-plaquette-et-configuration)
9. [Un temps de faisceau type](#un-temps-de-faisceau-type)
10. [Messages et que faire](#messages-et-que-faire)

---

## Ce que fait QuickAlignment

Sur ANTARES le faisceau est micrométrique ou plus petit, alors que la plaquette fait 18 × 15,5 mm. QuickAlignment
traduit la géométrie de la plaquette et des échantillons en **positions moteurs** :

- où se trouve chaque échantillon ou dispositif à l'orientation de départ (ST, SZ, SN à SRn = 120°, SRz = 0°) ;
- les ST / SN / SZ et la position de l'optique qui mettent un échantillon sous le faisceau, au foyer de l'analyseur ;
- après une rotation (SRn, SRz), les positions qui ramènent le même point sous le faisceau ;
- pour un cristal hexagonal 2D (graphène, WSe2, …), les SRn / SRz qui amènent Γ, K ou M au centre de la fente, et
  que faire quand la platine ne peut pas les atteindre.

Le programme ne déplace jamais de moteur : il calcule des nombres, que vous entrez dans le contrôle-commande de la ligne.

## Démarrer le programme

Installation (une fois) : `pip install PyQt5 numpy matplotlib`. Puis double-cliquer sur **`QuickAlignment.py`**
(Windows : `QuickAlignment.pyw`, sans console), ou lancer `python QuickAlignment.py [session.json]`.

À chaque démarrage le programme demande quelle **plaquette** est montée et quelle **optique de focalisation** est
utilisée :

![Plaquette et optique au démarrage](images/guide/setup_dialog.png)

- **Standard Ta plate** : plaquette de 18 × 15,5 mm avec une rehausse de 11 mm de large, hauteur 5,0 mm.
- **Gating plate** : la même, avec un bloc de contact (3 plots en or, 4 vis) ; les échantillons vont seulement sur
  les 11 × 10,5 mm au-dessus du bloc.
- **Custom plate** : la plaquette de base avec votre propre bloc (longueur, largeur, centre y, hauteur depuis la face
  arrière).
- **Optique** : *zone plate + OSA* (95 eV uniquement) ou *capillary* (30–180 eV). La configuration la plus récente
  faite par le personnel de la ligne pour cette optique est chargée (affichée dans la barre d'outils).

## Coordonnées et moteurs

| nom | signification | plage |
|---|---|---|
| x, y | position sur la plaquette (mm), vue de face, languette en haut, origine = centre de la plaquette | – |
| H | hauteur de l'échantillon au-dessus de la surface de la plaquette (mm) | – |
| ST | le long du plan focal de l'analyseur ; ST < 0 déplace l'échantillon vers le haut à gauche (vue de dessus) | −6 … 6 mm |
| SN | perpendiculaire au plan focal de l'analyseur ; SN = 65 est la position de transfert | −30 … 65 mm ; sous SN_f la limite est une collision (voir *Anticollision*) |
| SZ | vertical | 35 … 45 mm |
| SRn | azimut autour de la normale ; SRn = 120° : plaquette verticale, languette en haut | utilisable 60 … 180° |
| SRz | rotation autour de la verticale ; SRz = 0 : plaquette parallèle au plan focal | utilisable −25 … +10° |
| PIX, PIY | platine piézo, 0 … 300 µm, centre 150 µm | – |

À l'orientation de départ, un point (x, y) de la plaquette est sous le faisceau à **ST = ST0 − x, SZ = SZ0 − y**, et
un échantillon de hauteur H est au foyer de l'analyseur à **SN = SN_f + H** (ST0, SZ0, SN_f viennent de la
configuration). Les champs moteurs refusent les valeurs hors course.

## Onglet Samples : dessiner la plaquette

![Onglet Samples](images/guide/samples_tab.png)

- **Dessiner un échantillon** : glisser sur une partie vide de la plaquette. Le **déplacer** en le faisant glisser,
  le **redimensionner** par un bord ou un coin (positions arrondies à 0,1 mm). Ou *Add sample* puis taper les valeurs.
- **Tableau** : nom, x, y, longueur L, largeur W et hauteur H se tapent exactement (non arrondis). *Default H* est la
  hauteur des nouveaux échantillons (0,525 mm : un wafer Si standard).
- **Dispositifs sur un substrat** : sélectionner le substrat, *Add device*, choisir les deux bords de référence
  (left/right, bottom/top) et les distances dx, dy au centre du dispositif, ou faire glisser le repère bleu. Les
  dispositifs suivent leur substrat ; un substrat avec dispositifs n'apparaît que par ses dispositifs dans les listes
  de cibles.
- **Status** : `ok`, ou le problème (hors de la zone, chevauchement, dispositif hors du substrat). Les éléments rouges
  du dessin ont un problème.
- Molette = zoom, bouton du milieu = déplacer, clic droit = plaquette entière, Suppr = effacer la sélection.

### Échantillons depuis une photo

Au lieu de les dessiner, les échantillons peuvent être trouvés sur une photo de la plaquette prise d'en haut (côté
échantillons ; une photo de téléphone suffit). Appuyer sur **From photo…** :

![Échantillons depuis une photo](images/guide/photo_dialog.png)

1. *Open photo…*. La vue de droite montre le modèle de la plaquette avec les quatre coins de la zone d'échantillons
   numérotés **1–4** ; celui à cliquer ensuite est en **rouge**. Cliquer ce point sur la photo, puis le rouge suivant
   (1 haut gauche, 2 haut droit côté languette, 3 bas droit, 4 bas gauche ; plaquette gating : 3 et 4 sont où la zone
   rencontre le bloc de contacts). Molette = zoom (zoomer autant que nécessaire pour placer le point), bouton du milieu
   = déplacer, clic droit = photo entière ; faire glisser les repères ensuite pour affiner. *Clear points* recommence.
2. La photo est projetée sur le modèle de la plaquette (vue de droite, contours bleus). Vérifier que les contours sont
   sur la plaquette. Le curseur donne les coordonnées plaquette (x, y en mm) dans la vue de droite et sur la photo.
3. Les échantillons sont trouvés par leur couleur (cadres verts, magenta = ce qui est retenu) :
   - *colour of picked samples* (par défaut) : cliquer sur un échantillon, sur la photo ou dans la vue de droite, pour
     prendre sa couleur (*Pick sample colour* pour une autre sorte d'échantillon) ; seules les régions proches de ces
     couleurs sont retenues, sans la laque d'argent ni la colle.
   - *colour different from the bare plate* : tout ce qui est sur la plaquette, laque d'argent et colle comprises. Si
     les échantillons couvrent presque toute la zone, *Pick bare plate colour* puis cliquer sur la plaquette nue.
   - *ΔE threshold* : l'écart de couleur (CIELAB) qui les sépare ; *min. size* écarte les poussières ; *border left
     out* ignore le bord de la zone.
4. Corriger à la main. Tous les cadres de la liste sont ajoutés ; *sélectionner* des cadres en cliquant dessus dans la
   vue de droite (Ctrl + clic : plusieurs) ou sur leurs lignes, puis : **Delete selected** (ou Suppr) retire ce qui
   n'est pas un échantillon, **Merge selected** réunit les morceaux d'un échantillon coupé par de la laque ou des fils.
   **Draw box** puis glisser dans la vue de droite ajoute un échantillon non trouvé. Ces corrections restent quand le
   seuil change ; *Undo hand edits* les oublie.
5. Entrer la **hauteur H** (invisible d'en haut ; par défaut *Default H*), par échantillon dans le tableau ou avec
   *Set H of all*.
6. Si besoin, placer les dispositifs sur une deuxième photo (onglet 2, ci-dessous), puis **Add to plate**. *Remove the
   samples already on the plate* remplace les échantillons présents.

Les cadres sont les rectangles englobants de ce qui a été trouvé, en coordonnées plaquette ; ils se déplacent, se
redimensionnent et reçoivent des dispositifs comme les échantillons dessinés. La précision dépend des clics sur les
coins (environ 0,1–0,3 mm) ; *Found here* dans l'onglet Stage & Optics corrige le reste. Tout est calculé sur
l'ordinateur, rien n'est envoyé.

#### Onglet 2 : dispositifs sur une deuxième photo

La photo de la plaquette montre où est un substrat, mais rarement ses dispositifs ; une photo plus proche (microscope,
appareil) montre les dispositifs mais souvent pas les bords du substrat. Les deux photos sont mises en correspondance
par des points que vous marquez sur les deux :

![Dispositifs sur une deuxième photo](images/guide/photo_devices.png)

1. Choisir le **substrat** (ou sélectionner son cadre dans l'onglet 1). La vue de gauche montre la photo de la
   plaquette autour de lui, déjà en coordonnées plaquette. **Open device photo…** (vue de droite).
2. *mark the same point on both* : cliquer à gauche un détail visible aussi sur la photo des dispositifs (point de
   laque, coin d'un motif, rayure), puis le même détail à droite ; repères numérotés, déplaçables. Avec 2 paires la
   photo est placée par rotation + échelle + translation, avec 3 par une application affine, avec 4 ou plus par une
   perspective. La ligne au-dessus des vues donne l'écart des points (µm) : avec plus de paires que nécessaire, il
   révèle un point faux. Le contour du substrat (orange) est tracé sur la photo des dispositifs pour vérifier.
3. *mark devices* : cliquer chaque dispositif sur la photo des dispositifs (ou à gauche). Le tableau donne sa position
   sur la plaquette, son substrat et dx, dy aux bords gauche / bas du substrat ; y renommer les dispositifs, effacer les
   faux. Les dispositifs n'ont pas de hauteur : ils sont à la surface de leur substrat.
4. Une autre photo de dispositifs (autre substrat, autre partie) peut être ouverte : les dispositifs déjà marqués
   gardent leur position. *Add to plate* ajoute chaque dispositif à l'échantillon sur lequel il se trouve (ceux hors de
   tout échantillon sont écartés).

La précision est celle de la photo de la plaquette (clics des coins, 0,1–0,3 mm) plus celle de la mise en
correspondance.

Une fois les échantillons dessinés, appuyer sur **Samples placed → Stage**.

## Onglet Stage & Optics : aller sur un échantillon

![Onglet Stage & Optics](images/guide/stage_tab.png)

Le cadre vert donne, pour chaque échantillon et dispositif, les **ST / SZ / SN à l'orientation de départ**
(SRn = 120°, SRz = 0°, PIX = PIY = 150 µm) qui mettent son centre sous le faisceau, au foyer de l'analyseur.

1. Entrer les positions moteurs actuelles (valeurs absolues, comme dans le contrôle-commande).
2. Choisir une **Target** et appuyer sur **Bring target onto the beam** : ST et SZ sont calculés pour les SN, SRn,
   SRz, PIX, PIY entrés (**SN gardé**, comme d'habitude). Le texte indique la distance de la cible au foyer de
   l'analyseur le long du faisceau (en rouge au-delà de 50 µm : les spectres seraient déformés) et le ΔSN qui
   l'annulerait. Seulement si elle est jugée trop grande, **Correct SN** donne SN, ST, SZ qui mettent la cible au
   foyer de l'analyseur. Si un moteur sortait de sa course, rien n'est changé et le moteur est indiqué.
3. **Optique** : entrer sa position et appuyer sur **Update schematic & optics**. Le schéma montre le faisceau, le
   foyer de l'analyseur, l'optique et la position **nécessaire** pour focaliser sur la surface éclairée.
   *Use required position* la copie dans le champ.
4. Après une focalisation à la main, **Set as optics reference** prend l'état actuel comme référence optique pour
   cette session.
5. **Found here: correct its sample** : quand un dispositif est vraiment sous le faisceau et au foyer, entrer les
   positions, choisir le dispositif et appuyer sur le bouton. Son échantillon (avec tous ses dispositifs) est déplacé
   sur le dessin de Δx, Δy, ΔH : l'erreur du dessin. Toutes les prédictions utilisent ensuite la position corrigée
   (enregistrée avec la session). Une correction de plus de 0,3 mm suggère une configuration périmée : prévenir le
   personnel de la ligne.

Le schéma n'est redessiné qu'avec *Update schematic & optics*. La souris sur la vue du plan de l'échantillon donne
les ST, SZ qui amènent ce point sous le faisceau et ce qui s'y trouve.

### Anticollision

Après *Update*, la ligne sous les moteurs donne la **plage sans collision** de ST, SN et SZ aux positions entrées (un
moteur déplacé, les autres et l'optique gardés) et ce qui fixe chaque limite, par ex. *SN −4.1 (OSA) … 65*. La vue de
dessus montre à l'échelle le nez de l'analyseur (MBS A1, à 30 mm du foyer), la zone plate et l'OSA (plaques minces ;
l'OSA ne bouge pas quand la zone plate refocalise) ou le capillaire, en rouge quand la plaquette les touche. *Bring
target onto the beam*, *Correct SN* et l'onglet Rotate refusent une position où la plaquette toucherait quelque
chose. Baisser SN rapproche la surface de l'optique et de l'analyseur : SN n'est limité que vers le bas. ST et SZ sont
libres pour une plaquette parallèle au plan focal, et limités quand SRz l'incline ou quand quelque chose dépasse (vis
de la plaquette gating). Les dimensions sont des estimations gardées dans la configuration : si on les connaît mieux, entrer les **distances de travail** (face avant de
l'OSA, de la zone plate ou du capillaire au foyer) dans les champs sous la position de l'optique (pour la session).
Garder une distance de sécurité et surveiller la caméra.

## Onglet Rotate sample : tourner sans perdre l'échantillon

![Onglet Rotate sample](images/guide/rotate_tab.png)

1. **Current position** : les positions avec le point d'intérêt sous le faisceau et au foyer, et la position de
   l'optique (*From Stage tab* les copie).
2. **Wanted angles** : les nouveaux SRn et SRz (ou *Find angles for a BZ point…*, section suivante).
3. **Compute new position** : ST et SZ avec le piézo centré et **SN gardé**, et la position de l'optique qui
   refocalise. Le texte indique la distance du point au foyer de l'analyseur (en rouge au-delà de 50 µm : les
   spectres seraient déformés). SRn seul garde le plan de la surface ; SRz non.
4. Seulement si le point est trop loin du foyer, cocher **Correct SN** (décoché à chaque nouveau calcul) pour voir SN, ST, SZ et l'optique qui mettent le point **au foyer de l'analyseur**. Si une
   course moteur ne le permet pas, la position atteignable la plus proche est donnée avec sa distance au foyer.
5. **Send to Stage & Optics tab** reprend la solution affichée (refusé si hors course).

## Trouver les angles pour un point de la zone de Brillouin

Sous *Wanted angles*, **Find angles for a BZ point…** répond, pour les cristaux hexagonaux 2D, à la question
*« de combien tourner SRn et SRz pour que K soit au centre de la fente, la fente selon Γ–K et le déflecteur proche de 0 ? »*

![Point de zone atteignable](images/guide/bz_reachable.png)

**À entrer** (lu sur le contour d'une carte dans ARPES viewer ; θ = angle du déflecteur, x du contour ; φ = angle le
long de la fente, y du contour) :

1. **The map** : SRn et SRz de la mesure (*From current position* les prend dans l'onglet Rotate), son énergie de
   photon, les angles de **Γ** et d'**un point K ou M**.
2. **Crystal** : la constante de réseau dans le plan a (préréglages : graphène 2,46 Å, WSe2 3,282 Å, WS2, MoSe2,
   MoS2, hBN).
3. **Wanted** : le point (Γ, K ou K′, K seul, K′ seul, M), la **direction de la fente** (Γ–K, K–M, Γ–M, M–K),
   l'énergie de photon de la nouvelle mesure, E − E_F du point (p. ex. −1,0 pour le haut de bande de valence de WSe2
   en K) et le travail de sortie (4,5 eV).

Appuyer sur **Compute**. Sous les entrées, *Γ–K on the map* compare la distance mesurée à la constante de réseau (un
écart de plus de 10 % signale un nombre, un point ou une énergie faux) et donne l'inclinaison de l'échantillon sur la
plaquette (prise en compte dans le résultat).

**Résultat** : *Reachable* quand, déflecteur à 0, le point est à |θ| ≤ 5° et |φ| ≤ 5° du centre de la fente, la
fente à moins de 2° de la ligne voulue, avec SRn 60 … 180° et SRz −25 … +10°. Le tableau donne tous les points
équivalents et les deux sens de rotation ; la première ligne est la recommandée (d'abord SRz ≤ 0 : faisceau plus
proche de la normale, spot plus petit ; puis la plus petite rotation). *Beam to normal* est l'angle d'incidence,
45° + SRz.

**Aperçu** : à gauche, la carte que vous mesurerez aux angles proposés (déflecteur en abscisse, angle de fente en
ordonnée ; le déflecteur a des lacunes au-delà de ±8° et s'arrête à ±12° ; le cadre vert est le ±5° accepté). À
droite, la zone 2D en impulsion, orientée comme votre carte actuelle, avec la carte actuelle (tirets) et la nouvelle
fenêtre de l'analyseur et la fente (orange).

**Use these angles** écrit SRn / SRz dans *Wanted angles* et calcule la nouvelle position. Mettre le déflecteur à 0
(et l'énergie de photon, si elle a changé).

### Quand ce n'est pas atteignable

Le manipulateur n'a **pas d'axe de tilt**. Conséquence : avec un point au centre de la fente et le déflecteur à 0, la
fente est toujours selon la ligne de Γ à ce point (Γ–K pour K). Une fente *perpendiculaire* (K–M, M–K) demande le
déflecteur à l'angle d'émission du point (15–20° à 95 eV), ce que l'analyseur fait mal :

![Coupe en bord de zone](images/guide/bz_zone_edge.png)

La fenêtre propose alors l'**alternative radiale** : K au centre, fente selon Γ–K ; la direction du déflecteur est
alors selon K–M, et une courte **carte en déflecteur** (|θ| ≤ 5°) donne la coupe K–M passant par K avec peu de
distorsion. *Show the radial alternative* y passe directement.

Quand l'angle d'émission est trop grand pour la plage de SRz, la fenêtre donne les **énergies de photon** auxquelles
le point est atteignable :

![Énergie de photon plus élevée nécessaire](images/guide/bz_photon_energy.png)

- ANTARES : 30–180 eV avec le **capillaire** ; la **zone plate ne fonctionne qu'à 95 eV**. Changer d'énergie avec la
  zone plate signifie passer au capillaire (réalignement, configuration capillaire).
- Si SRn est la limite, la fenêtre indique de combien **tourner l'échantillon sur la plaquette** au remontage.
- Si rien ne marche, il faut remonter l'échantillon ou choisir un autre point équivalent.

| exemple (E_F, travail de sortie 4,5 eV) | angle d'émission de K à 30 / 95 / 180 eV | K, fente selon Γ–K |
|---|---|---|
| WSe2, a = 3,282 Å, Γ–K = 1,28 Å⁻¹ | 29,6° / 15,2° / 10,8° | atteignable à 95 eV avec SRz ≈ −15° |
| graphène, a = 2,46 Å, Γ–K = 1,70 Å⁻¹ | 41,2° / 20,4° / 14,5° | 95 eV : SRz ≈ −20° ; 30 eV : non (il faut ≳ 61 eV) |

Les signes entre la platine et le contour d'ARPES viewer ont été vérifiés une fois (signe du déflecteur, 2026-09) ;
lors d'un nouveau type de mesure, vérifier que le point apparaît là où l'aperçu le montre.

## Sessions, plaquette et configuration

- **New / Open… / Save** (barre d'outils) : une session contient la plaquette, les échantillons et dispositifs (avec
  leurs corrections) et les positions moteurs, dans un fichier JSON. Le premier *Save* demande le nom du fichier.
  L'écriture est sûre : si elle échoue (disque plein, droits), l'ancien fichier reste intact et un message en donne
  la raison.
- **Change plate…** : une autre plaquette ; les échantillons sont gardés et ceux mal placés sont signalés.
- **Configuration…** : vue en lecture seule de la configuration utilisée (constantes de la platine et référence
  optique), faite par le personnel de la ligne. Une configuration plus ancienne peut être choisie pour la session.

![Fenêtre de configuration](images/guide/configuration_dialog.png)

## Un temps de faisceau type

1. Lancer QuickAlignment, confirmer plaquette et optique.
2. Dessiner les échantillons d'après la photo de montage (ou ouvrir la session préparée avant) ; *Samples placed →
   Stage*.
3. Aller au premier échantillon avec les ST / SZ / SN listés ; le trouver avec le faisceau (caméra, carte de
   photoémission).
4. *Found here* : corriger sa position. Les autres tombent alors juste aussi.
5. Mesurer une carte à SRn = 120°, SRz = 0° ; lire Γ et un point K / M dans ARPES viewer.
6. *Find angles for a BZ point…* → *Use these angles* → *Compute new position* (cocher *Correct SN* si le point est à
   plus de 50 µm du foyer) → *Send to Stage & Optics tab*.
7. Enregistrer la session.

## Messages et que faire

| message | signification / que faire |
|---|---|
| *Out of range: ST = … (range …)* | le point n'est pas atteignable à ces angles ; choisir d'autres angles ou la solution corrigée |
| *… µm from the analyzer focus* (rouge) | après une rotation SRz le point a quitté le plan focal : cocher *Correct SN* |
| *Found here* déplace un échantillon de plus de 0,3 mm | dessin faux, ou configuration périmée (moteurs réinitialisés) : demander au personnel |
| *The beam misses the plate* | ST / SZ ne mettent pas le faisceau sur la plaquette |
| *Check the input: Γ–K on the map is …* | constante de réseau, point ou énergie ne correspondent pas à la carte |
| *An unexpected error occurred* | le programme continue ; vérifier le dernier résultat, enregistrer la session et envoyer les détails au personnel |
